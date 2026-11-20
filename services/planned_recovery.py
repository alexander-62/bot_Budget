"""Inspect and recover payment intentions from an explicitly selected workbook."""
from dataclasses import dataclass, replace
from uuid import uuid4

from constants import EXPENSES_SHEET_NAME, PLANNED_EXPENSES_SHEET_NAME
from services import planned_expenses as plans
from services.expenses import write_planned_payment
from services.google_sheets import guarded_batch, normalize_text, transaction_guard
from services.planned_payment_changes import actual_row


@dataclass(frozen=True)
class RecoveryItem:
    planned_id: str
    revision: str
    expense_id: str
    title: str
    amount: str
    date: str
    state: str

    @property
    def recoverable(self):
        return self.state in {'found', 'retry'}


def _sheets(spreadsheet):
    sheets = {normalize_text(ws.title): ws for ws in spreadsheet.worksheets()}
    try:
        planned = sheets[normalize_text(PLANNED_EXPENSES_SHEET_NAME)]
        actual = sheets[normalize_text(EXPENSES_SHEET_NAME)]
    except KeyError:
        raise ValueError('Не найдены листы будущих и фактических трат выбранного бюджета.') from None
    plans.validate_planned_header(planned.row_values(1), allow_legacy=True)
    return planned, actual


def _state(plan, actual_rows):
    if not plan.expense_id or not plan.actual_amount or not plan.actual_date:
        return 'conflict'
    try:
        linked = actual_row(actual_rows, plan.expense_id)
        if not linked:
            return 'retry' if plan.payment_guard else 'legacy'
        _, row = linked
        same = (plans.parse_date(row[0]) == plan.actual_date
                and tuple(row[2:5]) == (plan.paid_by, plan.category, plan.subcategory)
                and plans.parse_amount(row[5]) == plans.parse_amount(plan.actual_amount)
                and (not plan.payment_source or len(row) > 8 and row[8] == plan.payment_source))
        return 'found' if same else 'conflict'
    except ValueError:
        return 'conflict'


def inspect_recovery(spreadsheet):
    planned, expenses = _sheets(spreadsheet)
    pending = [p for _, p in plans._read(planned) if p.status == 'processing']
    if not pending:
        return []
    actual_rows = expenses.get_all_values()
    return [RecoveryItem(p.planned_id, p.revision, p.expense_id, p.title, p.actual_amount, p.actual_date,
                         _state(p, actual_rows)) for p in pending]


def recover_payment(spreadsheet, item):
    """Run with the selected worker stopped and its OS runtime lock held."""
    planned, expenses = _sheets(spreadsheet)
    row, plan = plans._find(planned, item.planned_id)
    if plan.status == 'paid' and item.expense_id and plan.expense_id == item.expense_id:
        return plan
    if plan.status != 'processing' or plan.revision != item.revision:
        raise plans.StalePlanError('Платёж уже изменился. Обновите список.')
    state = _state(plan, expenses.get_all_values())
    paid = replace(plan, status='paid', revision=uuid4().hex[:12])
    if state == 'found':
        # An existing matching actual row is enough to close the plan without appending.
        key = (f'payment:{plan.expense_id}:{plan.payment_guard}' if plan.payment_guard
               else f'reconcile:{plan.expense_id}:{plan.revision}')
        if len(planned.row_values(1)) < len(plans.HEADERS):
            plans.ensure_planned_sheet(spreadsheet)
        guarded_batch(spreadsheet, plans.payment_updates(planned, row, paid), guard=(key, transaction_guard(key)))
    elif state == 'retry':
        try:
            write_planned_payment(planned, row, paid, spreadsheet=spreadsheet, expense_sheet=expenses)
        except Exception:
            # The original batch may have won the race while this retry was in flight.
            persisted = plans._find(planned, item.planned_id)[1]
            if persisted.status == 'paid' and persisted.expense_id == plan.expense_id:
                return persisted
            raise
    else:
        raise ValueError('Безопасное восстановление недоступно. Бот не изменил записи.')
    return paid
