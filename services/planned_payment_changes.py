"""Edit or reverse the exact actual expense linked to a paid plan."""
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from uuid import uuid4

from constants import EXPENSES_SHEET_NAME
from services import planned_expenses as plans
from services.budget import clear_budget_snapshot_cache
from services.google_sheets import find_worksheet_case_insensitive, guarded_batch, transaction_guard, update_cells


def actual_row(sheet, expense_id):
    if not expense_id:
        raise ValueError('У платежа нет ID фактической траты.')
    matches = [(index, row) for index, row in enumerate(sheet.get_all_values()[1:], 2)
               if len(row) > 7 and row[7] == expense_id]
    if len(matches) > 1:
        raise ValueError('В таблице найдено несколько трат с этим ID. Проверьте таблицу.')
    return matches[0] if matches else None


def can_correct(plan, user_id, username):
    if plan.paid_by_id:
        return plan.paid_by_id == str(user_id)
    return plan.paid_by == str(user_id) or bool(username and plan.paid_by.lower() == '@' + username.lower())


def correct_payment(planned_id, revision, *, user_id, username, amount=None, payment_date=None, undo=False):
    with plans._lock:
        planned_sheet = plans._worksheet()
        planned_row, plan = plans._find(planned_sheet, planned_id)
        if plan.status != 'paid' or plan.revision != revision:
            raise plans.StalePlanError('Оплата уже изменилась. Откройте актуальную карточку.')
        if not can_correct(plan, user_id, username):
            raise ValueError('Изменить оплату может тот, кто её подтвердил.')
        spreadsheet = plans.get_spreadsheet()
        expense_sheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
        linked = actual_row(expense_sheet, plan.expense_id)
        if not linked:
            raise ValueError('Связанная трата отсутствует. Проверьте её в таблице.')
        row_number, row = linked
        actual_amount = plans.parse_amount(row[5])
        actual_date = plans.parse_date(row[0], payment=True)
        history = json.loads(plan.payment_history or '[]')
        history.append({'action': 'undo' if undo else 'edit', 'expense_id': plan.expense_id,
                        'amount': actual_amount, 'date': actual_date, 'actor_id': str(user_id),
                        'at': datetime.now(timezone.utc).isoformat()})
        if undo:
            width = 9 if len(expense_sheet.row_values(1)) > 8 and expense_sheet.row_values(1)[8].lower() == 'источник' else 8
            requests = [update_cells(expense_sheet, row_number, [None] * width)]
            updated = replace(plan, status='pending', expense_id='', actual_amount='', actual_date='',
                              paid_by='', paid_by_id='', payment_guard='', payment_source='',
                              last_reminder='')
        else:
            new_amount = plans.parse_amount(amount) if amount is not None else actual_amount
            new_date = plans.parse_date(payment_date, payment=True) if payment_date is not None else actual_date
            day = date.fromisoformat(new_date)
            requests = [
                update_cells(expense_sheet, row_number, [new_date, f'{day:%Y-%m}']),
                update_cells(expense_sheet, row_number, [float(new_amount.replace(',', '.'))], column_index=5),
            ]
            updated = replace(plan, actual_amount=new_amount, actual_date=new_date)
            history[-1].update(new_amount=new_amount, new_date=new_date)
        journal = json.dumps(history, ensure_ascii=False)
        if len(journal) > 45000:
            raise ValueError('Журнал изменений достиг предела ячейки Google Sheets.')
        updated = replace(updated, revision=uuid4().hex[:12], payment_history=journal)
        key = f'correction:{plan.planned_id}:{plan.revision}'
        requests.append(update_cells(planned_sheet, planned_row, updated.values()))
        guarded_batch(spreadsheet, requests, guard=(key, transaction_guard(key)))
        clear_budget_snapshot_cache()
        return updated
