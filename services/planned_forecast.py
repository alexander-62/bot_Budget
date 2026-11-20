"""Estimate pending expenses, showing unknowns instead of treating them as zero."""
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from services import planned_expenses as plans
from services.money import format_money_exact, parse_sheet_number


def forecast_message(day=None):
    day = day or plans.today()
    month_end = day.replace(day=monthrange(day.year, day.month)[1])
    week_end = day + timedelta(days=6)
    overdue, week, month, undated = [], [], [], []
    processing = 0
    for plan in plans.list_plans():
        if plan.status == 'processing':
            processing += 1
            continue
        if not plan.due_date:
            undated.append(plan.amount)
            continue
        if plan.due_date < day.isoformat():
            overdue.append(plan.amount)
            continue
        if plan.due_date <= week_end.isoformat():
            week.append(plan.amount)
        if plan.due_date <= month_end.isoformat():
            month.append(plan.amount)
    lines = ['📊 Прогноз будущих трат',
             _line(f'Ближайшие 7 дней (до {week_end:%d.%m})', week),
             _line(f'До конца месяца (до {month_end:%d.%m})', month),
             _line('Просроченные', overdue), _line('Без даты', undated),
             '', 'Периоды могут пересекаться.']
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
