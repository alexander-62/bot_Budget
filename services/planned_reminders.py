"""Independent future-payment subscription and durable notification buckets."""
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo
from uuid import uuid4

from config import BOT_TIMEZONE
from constants import USERS_SHEET_NAME
from services import planned_expenses as plans
from services.google_sheets import get_spreadsheet, find_worksheet_case_insensitive, normalize_text
from services.money import format_money_exact

SUBSCRIPTION_HEADER = 'planned_reminders_enabled'
OFF = {'false', '0', 'no', 'нет', 'выкл', 'выключено'}


@dataclass(frozen=True)
class ReminderJob:
    chat_id: int
    text: str
    # plan ID + revision prevents a delayed acknowledgement overwriting edits.
    items: tuple[tuple[str, str, str], ...]
    titles: tuple[str, ...]


def _user_rows():
    plans.require_enabled()
    ws = find_worksheet_case_insensitive(get_spreadsheet(), USERS_SHEET_NAME)
    rows = ws.get_all_values()
    if not rows:
        raise ValueError('Лист «Users» пуст.')
    header = {normalize_text(v): i for i, v in enumerate(rows[0]) if v.strip()}
    id_index = next((header[key] for key in ('user_id','userid','chat_id','chatid','id') if key in header), None)
    if id_index is None:
        raise ValueError('Лист «Users»: нужен user_id или chat_id.')
    return ws, rows, header, id_index


def _cell(row, index):
    return str(row[index]).strip() if index is not None and len(row) > index else ''


def reminder_recipients():
    _, rows, header, id_index = _user_rows()
    result = {}
    for row in rows[1:]:
        raw_id = _cell(row, id_index)
        if not raw_id.isdigit() or int(raw_id) <= 0:
            continue
        enabled = normalize_text(_cell(row, header.get(SUBSCRIPTION_HEADER))) not in OFF
        result[int(raw_id)] = enabled
    return result


def subscription_enabled(user_id):
    return reminder_recipients().get(user_id, False)


def set_subscription(user_id, enabled):
    with plans._lock:
        ws, rows, header, id_index = _user_rows()
        matches = [(i, row) for i, row in enumerate(rows[1:], 2) if _cell(row, id_index) == str(user_id)]
        if len(matches) != 1:
            raise ValueError('Лист «Users»: не найдена единственная строка пользователя.')
        column = header.get(SUBSCRIPTION_HEADER)
        if column is None:
            column = len(rows[0])
            ws.update_cell(1, column + 1, SUBSCRIPTION_HEADER)
        ws.update_cell(matches[0][0], column + 1, 'TRUE' if enabled else 'FALSE')
        return enabled


def build_reminder_jobs(now=None):
    plans.require_enabled()
    timezone = ZoneInfo(BOT_TIMEZONE)
    current = now or datetime.now(timezone)
    current = current.replace(tzinfo=timezone) if current.tzinfo is None else current.astimezone(timezone)
    if current.time() < time(21,30):
        return []
    recipients = reminder_recipients()
    day = current.date()
    weekly = {}
    jobs = []
    for plan in plans.list_plans():
        if plan.status != 'pending' or not plan.creator_id.isdigit():
            continue
        user_id = int(plan.creator_id)
        if not recipients.get(user_id, False):
            continue
        if plan.remind_on:
            if plan.remind_on > day.isoformat():
                continue
            bucket = 'snooze:' + day.isoformat()
            amount = format_money_exact(plan.amount) if plan.amount else 'сумма пока неизвестна'
            text = f'📅 Отложенное напоминание\n\n{escape(plan.title)}\n{amount}\nДата оплаты: {plan.due_date or "без даты"}'
            jobs.append(ReminderJob(user_id, text, ((plan.planned_id, plan.revision, bucket),), (plan.title,)))
        elif plan.due_date:
            due = datetime.strptime(plan.due_date, '%Y-%m-%d').date()
            if due > day + timedelta(days=1):
                continue
            bucket = 'day:' + day.isoformat()
            if plan.last_reminder == bucket:
                continue
            label = 'Просроченный платёж' if due < day else 'Оплатить сегодня' if due == day else 'Оплатить завтра'
            amount = format_money_exact(plan.amount) if plan.amount else 'сумма пока неизвестна'
            text = f'📅 {label}\n\n{escape(plan.title)}\n{amount}\nДата оплаты: {plan.due_date}'
            jobs.append(ReminderJob(user_id, text, ((plan.planned_id, plan.revision, bucket),), (plan.title,)))
        elif day.weekday() == 0:
            bucket = 'week:' + day.strftime('%G-W%V')
            if plan.last_reminder not in {bucket, 'day:' + day.isoformat()}:
                weekly.setdefault(user_id, []).append((plan, bucket))
    for user_id, entries in weekly.items():
        for offset in range(0, len(entries), 8):
            batch = entries[offset:offset+8]
            lines = ['📅 Будущие траты без даты', '']
            for plan, _ in batch:
                lines.append(escape(plan.title) + (f' — {format_money_exact(plan.amount)}' if plan.amount else ' — сумма пока неизвестна'))
            lines += ['', 'Что-то уже оплатили? Откройте платёж и подтвердите оплату.']
            jobs.append(ReminderJob(user_id, '\n'.join(lines), tuple((p.planned_id, p.revision, b) for p,b in batch),
                                    tuple(p.title for p,b in batch)))
    return jobs


def mark_delivered(job):
    with plans._lock:
        ws = plans._worksheet()
        for planned_id, revision, bucket in job.items:
            try:
                row, current = plans._find(ws, planned_id)
            except ValueError:
                continue
            if current.revision == revision and current.status == 'pending':
                if bucket.startswith('snooze:'):
                    updated = replace(current, remind_on='', revision=uuid4().hex[:12],
                                      last_reminder=bucket.replace('snooze:', 'day:', 1))
                    plans.change_plan(ws, row, current, updated)
                else:
                    ws.update_cell(row, plans.HEADERS.index('last_reminder') + 1, bucket)
