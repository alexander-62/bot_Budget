"""Durable one-off plans in the profile's Sheet. Call I/O via run_blocking.

Mutations are serialized within the one-process-per-budget runtime. Revisions
protect stale Telegram cards; identity never depends on a remembered row number.
"""
from dataclasses import dataclass, replace, fields
from datetime import date, datetime
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

from gspread.utils import rowcol_to_a1

from config import BOT_TIMEZONE, PLANNED_EXPENSES_ENABLED
from constants import PLANNED_EXPENSES_SHEET_NAME
from services.expenses import parse_amount as _parse_amount
from services.money import parse_sheet_number
from services.google_sheets import get_spreadsheet, normalize_text

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

    def values(self):
        return [str(getattr(self, f.name)) for f in fields(self)]


class StalePlanError(ValueError):
    pass


def require_enabled():
    if not PLANNED_EXPENSES_ENABLED:
        raise ValueError('Будущие траты выключены для этого бота.')


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
    parsed = _parse_amount(str(numeric))
    if parse_sheet_number(parsed) <= 0:
        raise ValueError('Сумма должна быть не меньше 0,01.')
    return parsed


def validate_text(value, name, maximum=120):
    value = value.strip()
    if not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f'{name}: от 1 до {maximum} символов без переносов строк.')
    return value


def _validated_values(title, category, subcategory, amount='', due_date='', comment=''):
    if len(comment) > 500:
        raise ValueError('Комментарий: не больше 500 символов.')
    return dict(title=validate_text(title, 'Название'),
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


def _write(ws, row_number, plan):
    ws.update(range_name=f'A{row_number}:{LAST_COLUMN}{row_number}', values=[plan.values()], value_input_option='RAW')


def get_plan(planned_id):
    return _find(_worksheet(), planned_id)[1]


def list_plans(*, history=False):
    plans = [p for _, p in _read(_worksheet()) if (p.status not in {'pending', 'processing'}) == history]
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
        ws.append_row(plan.values(), value_input_option='RAW', table_range=f'A:{LAST_COLUMN}')
        return plan


def update_plan(planned_id, expected_revision, **values):
    require_enabled()
    cleaned = _validated_values(**values)
    validate_category(cleaned['category'], cleaned['subcategory'])
    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        _assert_pending(plan, expected_revision)
        updated = replace(plan, **cleaned, revision=uuid4().hex[:12])
        _write(ws, row, updated)
        return updated


def cancel_plan(planned_id, expected_revision):
    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        _assert_pending(plan, expected_revision)
        updated = replace(plan, status='cancelled', revision=uuid4().hex[:12])
        _write(ws, row, updated)
        return updated


def _assert_pending(plan, expected_revision):
    if plan.status != 'pending' or plan.revision != expected_revision:
        raise StalePlanError('Платёж уже изменён или закрыт. Откройте карточку заново.')


def pay_plan(planned_id, expected_revision, *, amount, payment_date, actor, money_source=''):
    """At most one payment per plan under the one-writer runtime contract."""
    from services.expenses import write_planned_payment
    with _lock:
        ws = _worksheet()
        row, plan = _find(ws, planned_id)
        if plan.status == 'paid':
            # Includes a successful batch whose HTTP response was lost.
            from services.budget import clear_budget_snapshot_cache
            clear_budget_snapshot_cache()
            return plan
        if plan.status == 'processing':
            raise ValueError('Результат предыдущей оплаты пока не подтверждён. Нажмите «Проверить результат». '
                             'Повторная запись заблокирована; если статус не меняется, оператору нужно проверить таблицу.')
        _assert_pending(plan, expected_revision)
        actual_amount = parse_amount(amount)
        actual_date = parse_date(payment_date, payment=True)
        validate_category(plan.category, plan.subcategory)
        expense_id = 'planned-' + plan.planned_id
        updated = replace(plan, status='paid', revision=uuid4().hex[:12],
                          expense_id=expense_id, actual_amount=actual_amount,
                          actual_date=actual_date, paid_by=actor)
        # Persistent intent is written BEFORE dispatch. A timeout can leave the
        # original request still in flight; a read of pending alone must never
        # authorize a second append, including after a process restart.
        from config import TRACK_MONEY_SOURCE
        if TRACK_MONEY_SOURCE:
            from services.money_sources import validate_money_source
            validate_money_source(money_source)
        processing = replace(updated, status='processing', revision=plan.revision)
        _write(ws, row, processing)
        try:
            write_planned_payment(ws, row, updated.values(), expense_id=expense_id,
                                  expense_date=date.fromisoformat(actual_date), username=actor,
                                  category=plan.category, subcategory=plan.subcategory,
                                  amount=actual_amount, comment=plan.title + (' — ' + plan.comment if plan.comment else ''),
                                  money_source=money_source)
        except Exception as error:
            from gspread.exceptions import APIError
            if isinstance(error, APIError) and 400 <= error.code < 500 and error.code != 408:
                # A definite rejection means the atomic batch made no change.
                _write(ws, row, replace(plan, revision=uuid4().hex[:12]))
            raise
        return updated


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
        _write(ws, row, updated)
        return updated
