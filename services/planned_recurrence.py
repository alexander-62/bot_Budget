"""Roll the active recurrence rule forward when an installment becomes due."""
from calendar import monthrange
from dataclasses import replace
from datetime import date, timedelta
import logging
from uuid import NAMESPACE_URL, uuid4, uuid5

from services import planned_expenses as plans
from services.google_sheets import atomic_append_and_update

RULES = {'weekly': 'Каждую неделю', 'monthly': 'Каждый месяц'}


def set_recurrence(planned_id, revision, rule):
    if rule and rule not in RULES:
        raise ValueError('Выберите период повторения.')
    with plans._lock:
        ws = plans._worksheet()
        row, plan = plans._find(ws, planned_id)
        if plan.revision != revision or plan.status not in {'pending', 'paid'}:
            raise plans.StalePlanError('Откройте актуальную карточку платежа.')
        if rule and (plan.status != 'pending' or not plan.due_date):
            raise ValueError('Повторение можно задать только открытому платежу с датой.')
        anchor = str(date.fromisoformat(plan.due_date).day) if rule == 'monthly' else ''
        updated = replace(plan, repeat_rule=rule, repeat_anchor=anchor, revision=uuid4().hex[:12])
        plans.change_plan(ws, row, plan, updated)
        return updated


def next_due(due, rule, anchor):
    if rule == 'weekly':
        return due + timedelta(days=7)
    if rule == 'monthly':
        year, month = (due.year + 1, 1) if due.month == 12 else (due.year, due.month + 1)
        return date(year, month, min(int(anchor or due.day), monthrange(year, month)[1]))
    raise ValueError('Неизвестный период повторения.')


def advance_due_series(now=None):
    """At most one new occurrence per active series per pass."""
    day = now or plans.today()
    with plans._lock:
        ws = plans._worksheet()
        for row, plan in plans._read(ws):
            if not plan.repeat_rule or plan.status not in {'pending', 'paid'} or not plan.due_date:
                continue
            due = date.fromisoformat(plan.due_date)
            if due > day:
                continue
            try:
                _roll_forward(ws, row, plan, due)
            except Exception:
                logging.exception('Не удалось создать следующий повторяющийся платёж')


def _roll_forward(ws, row, plan, due):
    # Identity is tied to this occurrence even if a user changes its rule
    # before a retry. The guard makes ambiguous responses safe to repeat.
    key = f'recurrence:{plan.planned_id}'
    planned_id = uuid5(NAMESPACE_URL, key).hex
    next_date = next_due(due, plan.repeat_rule, plan.repeat_anchor).isoformat()
    following = plans.PlannedExpense(
        planned_id, plan.title, plan.category, plan.subcategory, plan.amount, next_date,
        plan.comment, plan.creator_id, plan.creator, revision=uuid4().hex[:12],
        created_at=plan.created_at, repeat_rule=plan.repeat_rule, repeat_anchor=plan.repeat_anchor,
    )
    previous = replace(plan, repeat_rule='', repeat_anchor='', revision=uuid4().hex[:12])
    atomic_append_and_update(plans.get_spreadsheet(), ws, following.values(), ws, row, previous.values(),
                             guard=plans.transition_guard(plan))
