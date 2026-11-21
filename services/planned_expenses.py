"""Durable one-off plans in the profile's Sheet. Call I/O via run_blocking.

Mutations are serialized within the one-process-per-budget runtime. Revisions
protect stale Telegram cards; identity never depends on a remembered row number.
"""
from dataclasses import dataclass, replace, fields
from datetime import date, datetime
from decimal import InvalidOperation
import re
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

from gspread.utils import rowcol_to_a1

import config
from config import BOT_TIMEZONE
from constants import PLANNED_EXPENSES_SHEET_NAME
from services.expenses import parse_amount as _parse_amount
from services.expenses import parse_amount_with_optional_comment
from services.money import parse_sheet_number
from services.google_sheets import (
    append_cells, get_spreadsheet, guarded_batch, normalize_text, transaction_guard, update_cells,
)

LEGACY_HEADERS = (
    'planned_id', 'Название', 'Категория', 'Подкатегория', 'Плановая сумма',
    'Дата оплаты', 'Комментарий', 'creator_id', 'Создатель', 'Статус',
    'revision', 'created_at', 'expense_id', 'Фактическая сумма',
    'Фактическая дата', 'paid_by', 'last_reminder',
)
HEADERS = LEGACY_HEADERS + (
    'remind_on', 'repeat_rule', 'repeat_anchor', 'paid_by_id',
    'payment_history', 'payment_guard', 'payment_source',
)
LAST_COLUMN = rowcol_to_a1(1, len(HEADERS))[:-1]
_lock = RLock()


@dataclass(frozen=True)
class PlannedExpense:
    planned_id: str
    title: str
    category: str
    subcategory: str
    amount: str
    due_date: str
    comment: str
    creator_id: str
    creator: str
    status: str = 'pending'
    revision: str = ''
    created_at: str = ''
    expense_id: str = ''
    actual_amount: str = ''
    actual_date: str = ''
    paid_by: str = ''
    last_reminder: str = ''
    remind_on: str = ''
    repeat_rule: str = ''
    repeat_anchor: str = ''
    paid_by_id: str = ''
    payment_history: str = ''
    payment_guard: str = ''
    payment_source: str = ''

    @property
    def display_title(self) -> str:
        return self.title or self.subcategory

    def values(self):
        return [str(getattr(self, f.name)) for f in fields(self)]


class StalePlanError(ValueError):
    pass


def require_enabled():
    if not config.PLANNED_EXPENSES_ENABLED:
        raise ValueError('Будущие траты выключены для этого бота.')


def set_feature_enabled(enabled: bool, *, expected: bool) -> None:
    from services.bot_profiles import get_profile, set_profile_planned_expenses
    from services.process_control import ProcessLock

    start_lock = ProcessLock(config.PROFILE_RUNTIME_DIR / ".bot-start.lock")
    if not start_lock.acquire():
        raise ValueError("Настройки бота уже меняются. Попробуйте ещё раз.")
    try:
        with _lock:
            profile = get_profile(config.PROFILE_ID, config.BASE_DIR)
            if profile.planned_expenses_enabled != expected:
                raise ValueError("Настройка уже изменилась. Откройте настройки заново.")
            if enabled:
                from services.startup_validation import validate_planned_expenses_schema
                validate_planned_expenses_schema(get_spreadsheet(), profile)
            set_profile_planned_expenses(profile.id, enabled, base_dir=config.BASE_DIR)
            config.PLANNED_EXPENSES_ENABLED = enabled
    finally:
        start_lock.release()


def today():
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).date()


def parse_date(value: str, *, optional=False, payment=False) -> str:
    value = value.strip()
    if not value and optional:
        return ''
    if value.lower() in {'сегодня', 'today'}:
        result = today()
    else:
        result = None
        for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
            try:
                result = datetime.strptime(value, fmt).date()
                break
            except ValueError:
                pass
        if result is None:
            raise ValueError('Введите дату ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.')
    if payment and result > today():
        raise ValueError('Дата фактической оплаты не может быть в будущем.')
    return result.isoformat()


def parse_amount(value):
    # Reject NaN/Infinity, negative and amounts that round to zero.
    numeric = parse_sheet_number(value)
    if numeric <= 0:
        raise ValueError('Сумма должна быть больше нуля.')
    try:
        parsed = _parse_amount(str(numeric))
    except InvalidOperation as error:
        raise ValueError('Сумма слишком велика.') from error
    if parse_sheet_number(parsed) <= 0:
        raise ValueError('Сумма должна быть не меньше 0,01.')
    return parsed


def parse_entry(raw: str) -> tuple[str, str]:
    def parse_grouped_amount(value: str) -> str:
        # Keep a count at the start of a description from silently inflating
        # the amount, for example "74000 2 головы".
        value = value.replace("\xa0", ' ').replace("\u202f", ' ')
        if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?: \d{3})+)(?:[,.]\d+)?(?: *(?:₽|€|RUB|EUR|руб\.?))?', value):
            raise ValueError('Введите сумму, например: 74 000 Головы латекс.')
        return parse_amount(value)

    amount, description = parse_amount_with_optional_comment(raw, amount_parser=parse_grouped_amount)
    return amount, validate_text(description, 'Описание') if description else ''


def validate_text(value, name, maximum=120):
    value = value.strip()
    if not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f'{name}: от 1 до {maximum} символов без переносов строк.')
    return value


def _validated_values(category, subcategory, title='', amount='', due_date='', comment=''):
    if len(comment) > 500:
        raise ValueError('Комментарий: не больше 500 символов.')
    return dict(title=validate_text(title, 'Описание') if title.strip() else '',
                category=validate_text(category, 'Категория', 64),
                subcategory=validate_text(subcategory, 'Подкатегория', 64),
                amount=parse_amount(amount) if amount else '',
                due_date=parse_date(due_date, optional=True), comment=comment.strip())


def validate_category(category, subcategory):
    from services.budget import get_subcategories_for_category
    if subcategory not in get_subcategories_for_category(category):
        raise ValueError('Категория или подкатегория больше не активна. Выберите другую.')


def validate_planned_header(values, *, allow_legacy=False):
    actual = tuple(normalize_text(value) for value in values)
    expected = tuple(normalize_text(value) for value in HEADERS)
    if actual[:len(expected)] == expected:
        return
    legacy = expected[:len(LEGACY_HEADERS)]
    if allow_legacy and actual == legacy:
        return
    raise ValueError('Лист «Будущие_траты»: проверьте заголовки по шаблону.')


def ensure_planned_sheet(spreadsheet):
    """Add only missing headers to an empty sheet or a known legacy layout."""
    with _lock:
        matches = [ws for ws in spreadsheet.worksheets()
                   if normalize_text(ws.title) == normalize_text(PLANNED_EXPENSES_SHEET_NAME)]
        ws = matches[0] if matches else spreadsheet.add_worksheet(
            title=PLANNED_EXPENSES_SHEET_NAME, rows=1000, cols=len(HEADERS))
        header = ws.row_values(1)
        if not header and not any(any(str(v).strip() for v in r) for r in ws.get_all_values()):
            start = 1
        else:
            validate_planned_header(header, allow_legacy=True)
            if len(header) >= len(HEADERS):
                return ws
            start = len(LEGACY_HEADERS) + 1
            if any(any(str(value).strip() for value in row[start - 1:len(HEADERS)])
                   for row in ws.get_all_values()[1:]):
                raise ValueError('Лист «Будущие_траты»: новые служебные столбцы уже заняты.')
        if getattr(ws, 'col_count', len(HEADERS)) < len(HEADERS):
            ws.resize(cols=len(HEADERS))
        ws.update(range_name=f'{rowcol_to_a1(1, start)}:{LAST_COLUMN}1',
                  values=[list(HEADERS[start - 1:])], value_input_option='RAW')
        return ws


def _worksheet():
    require_enabled()
    from services.google_sheets import find_worksheet_case_insensitive
    ws = find_worksheet_case_insensitive(get_spreadsheet(), PLANNED_EXPENSES_SHEET_NAME)
    validate_planned_header(ws.row_values(1))
    return ws


def _read(ws):
    result = []
    seen = set()
    for row_number, row in enumerate(ws.get_all_values()[1:], 2):
        if not row or not any(str(v).strip() for v in row):
            continue
        row = [str(v) for v in row] + [''] * max(0, len(HEADERS) - len(row))
        plan = PlannedExpense(*row[:len(HEADERS)])
        if not plan.planned_id or plan.planned_id in seen or plan.status not in {'pending', 'processing', 'paid', 'cancelled'}:
            raise ValueError('Лист «Будущие_траты»: некорректный или повторный ID/статус.')
        # Canonicalize dates from older rows or the sheet's display locale.
        plan = replace(plan, due_date=parse_date(plan.due_date, optional=True),
                       remind_on=parse_date(plan.remind_on, optional=True))
        seen.add(plan.planned_id)
        result.append((row_number, plan))
    return result


def _find(ws, planned_id):
    for number, plan in _read(ws):
        if plan.planned_id == planned_id:
            return number, plan
    raise ValueError('Будущая трата не найдена. Откройте список заново.')


def transition_guard(plan):
    # A delayed mutation of this revision must compete with all newer actions
    # based on the same snapshot, even if its HTTP request is still running.
    key = f'plan-change:{plan.planned_id}:{plan.revision}'
    return key, transaction_guard(key)


def change_plan(ws, row, previous, updated):
    guarded_batch(get_spreadsheet(), [update_cells(ws, row, updated.values())],
                  guard=transition_guard(previous))


def get_plan(planned_id):
    return _find(_worksheet(), planned_id)[1]


def list_plans(*, history=False, include_paid_series=False):
    plans = [p for _, p in _read(_worksheet())
             if (p.status not in {'pending', 'processing'}) == history
             or (include_paid_series and p.status == 'paid' and p.repeat_rule)]
    if history:
        return sorted(plans, key=lambda p: p.created_at, reverse=True)
    current = today().isoformat()
    return sorted(plans, key=lambda p: (0 if p.due_date and p.due_date < current else 1 if p.due_date else 2,
                                       p.due_date or '9999-12-31', p.created_at, p.planned_id))


def create_plan(*, planned_id=None, creator_id, creator, **values):
    require_enabled()
    cleaned = _validated_values(**values)
    validate_category(cleaned['category'], cleaned['subcategory'])
    with _lock:
        ws = _worksheet()
        stable_id = planned_id or uuid4().hex
        for _, existing in _read(ws):
            if existing.planned_id == stable_id:
                if existing.creator_id != str(creator_id):
                    raise StalePlanError('Такой ID уже занят.')
                return existing
        plan = PlannedExpense(stable_id, **cleaned, creator_id=str(creator_id), creator=creator,
                              revision=uuid4().hex[:12],
                              created_at=datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat())
        # The same draft can be retried even if the first request is still running.
        key = f'plan-create:{stable_id}'
        guarded_batch(get_spreadsheet(), [append_cells(ws, plan.values())],
                      guard=(key, transaction_guard(key)))
        return plan


def update_plan(planned_id, expected_revision, **values):
    require_enabled()
    cleaned = _validated_values(**values)
    validate_category(cleaned['category'], cleaned['subcategory'])
    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        _assert_pending(plan, expected_revision)
        if plan.repeat_rule and not cleaned['due_date']:
            raise ValueError('Сначала отключите повторение: для серии нужна дата оплаты.')
        anchor = plan.repeat_anchor
        if plan.repeat_rule == 'monthly' and cleaned['due_date'] != plan.due_date:
            anchor = str(date.fromisoformat(cleaned['due_date']).day)
        updated = replace(plan, **cleaned, repeat_anchor=anchor, revision=uuid4().hex[:12])
        change_plan(ws, row, plan, updated)
        return updated


def cancel_plan(planned_id, expected_revision):
    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        _assert_pending(plan, expected_revision)
        updated = replace(plan, status='cancelled', revision=uuid4().hex[:12], repeat_rule='', repeat_anchor='')
        change_plan(ws, row, plan, updated)
        return updated


def _assert_pending(plan, expected_revision):
    if plan.status != 'pending' or plan.revision != expected_revision:
        raise StalePlanError('Платёж уже изменён или закрыт. Откройте карточку заново.')


def payment_updates(ws, row, plan):
    """Write payment columns without overwriting a generated recurrence."""
    values = plan.values()
    return [update_cells(ws, row, values[start:end], column_index=start)
            for start, end in ((9, 11), (12, 16), (20, 24))]


def pay_plan(planned_id, expected_revision, *, amount, payment_date, actor, actor_id='', money_source=''):
    """Record the confirmed intention, then submit an idempotent financial batch."""
    from gspread.exceptions import APIError
    from config import TRACK_MONEY_SOURCE
    from services.expenses import write_planned_payment
    from services.budget import clear_budget_snapshot_cache

    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        if plan.status == 'paid':
            clear_budget_snapshot_cache()
            return plan
        if plan.status == 'processing':
            raise ValueError('Результат оплаты ещё проверяется. Оператор может открыть восстановление в панели.')
        _assert_pending(plan, expected_revision)
        actual_amount = parse_amount(amount)
        actual_date = parse_date(payment_date, payment=True)
        validate_category(plan.category, plan.subcategory)
        if TRACK_MONEY_SOURCE:
            from services.money_sources import validate_money_source
            validate_money_source(money_source)
        expense_id = 'planned-' + plan.planned_id
        if plan.payment_history:
            expense_id += '-' + plan.revision
        processing = replace(plan, status='processing', expense_id=expense_id,
                             actual_amount=actual_amount, actual_date=actual_date, paid_by=actor,
                             paid_by_id=str(actor_id), payment_guard=plan.revision,
                             payment_source=money_source if TRACK_MONEY_SOURCE else '')
        spreadsheet = get_spreadsheet()
        guarded_batch(spreadsheet, payment_updates(ws, row, processing), guard=transition_guard(plan))
        paid = replace(processing, status='paid', revision=uuid4().hex[:12])
        try:
            write_planned_payment(ws, row, paid)
        except APIError as error:
            if 400 <= error.code < 500 and error.code != 408:
                # A definitive rejection of this first financial request
                # permits a fresh confirmation with a new revision.
                current_row, current = _find(ws, planned_id)
                if current.status == 'processing' and current.payment_guard == processing.payment_guard:
                    guarded_batch(spreadsheet, payment_updates(ws, current_row, replace(plan, revision=uuid4().hex[:12])))
            raise
        return paid


def snooze_plan(planned_id, expected_revision, user_id, date_value):
    remind_on = parse_date(date_value)
    if remind_on <= today().isoformat():
        raise ValueError('Выберите дату напоминания позже сегодняшней.')
    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        _assert_pending(plan, expected_revision)
        if plan.creator_id != str(user_id):
            raise ValueError('Отложить напоминание может создатель платежа.')
        updated = replace(plan, remind_on=remind_on, revision=uuid4().hex[:12])
        change_plan(ws, row, plan, updated)
        return updated
