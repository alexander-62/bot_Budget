"""Estimate pending expenses, showing unknowns instead of treating them as zero."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from services import planned_expenses as plans
from services.money import format_money_exact, parse_sheet_number
from services.planned_recurrence import next_due


def forecast_message(day=None):
    day = day or plans.today()
    month_end = day.replace(day=monthrange(day.year, day.month)[1])
    week_end = day + timedelta(days=6)
    overdue, week, month, undated = [], [], [], []
    processing = 0
    for plan in plans.list_plans(include_paid_series=True):
        if plan.status == 'processing':
            processing += 1
            continue
        if not plan.due_date:
            undated.append(plan.amount)
            continue
        due = date.fromisoformat(plan.due_date)
        if plan.status == 'pending':
            if due < day:
                overdue.append(plan.amount)
            else:
                if due <= week_end:
                    week.append(plan.amount)
                if due <= month_end:
                    month.append(plan.amount)
        if plan.repeat_rule:
            # Include projected installments even before the scheduler materializes them.
            if plan.repeat_rule == 'weekly' and due < day - timedelta(days=7):
                due += timedelta(days=7 * ((day - due).days // 7 - 1))
            elif plan.repeat_rule == 'monthly' and (due.year, due.month) < (day.year, day.month):
                previous_month = day.replace(day=1) - timedelta(days=1)
                due = previous_month
            while due < max(week_end, month_end):
                due = next_due(due, plan.repeat_rule, plan.repeat_anchor)
                if day <= due <= week_end:
                    week.append(plan.amount)
                if day <= due <= month_end:
                    month.append(plan.amount)
    lines = ['📊 Прогноз будущих трат',
             _line(f'Ближайшие 7 дней (до {week_end:%d.%m})', week),
             _line(f'До конца месяца (до {month_end:%d.%m})', month),
             _line('Просроченные', overdue), _line('Без даты', undated),
             '', 'Периоды могут пересекаться. Повторяющиеся платежи учтены по расписанию.']
    if processing:
        lines.append(f'Ожидают проверки оплаты: {processing}. Они показаны отдельно.')
    return '\n'.join(lines)


def _line(label, amounts):
    if not amounts:
        return f'{label}: нет платежей'
    known = [parse_sheet_number(value) for value in amounts if value]
    unknown = len(amounts) - len(known)
    parts = [format_money_exact(sum(known, Decimal(0)))] if known else []
    if unknown:
        parts.append(f'без суммы — {unknown}')
    return f'{label}: {", ".join(parts)}'
