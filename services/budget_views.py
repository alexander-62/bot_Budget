"""Pure presentation for category cards in reports and expense confirmations."""
from html import escape
from services.budget_settings import cached_settings
from services.money import format_money, format_money_or_dash, format_remaining_with_alert


def format_category_card(details):
    title, limit, spent, remaining, subcategories = details
    enabled = cached_settings().monthly_limits_enabled
    lines = [f"🏷️ <b>{escape(title)}</b>"]
    if enabled:
        lines.extend(["📊 Лимит / Потрачено / Осталось",
                      f"<b>{format_money_or_dash(limit)} / {format_money(spent)} / {format_remaining_with_alert(remaining)}</b>"])
    else:
        lines.append(f"Потрачено: <b>{format_money(spent)}</b>")
    lines.extend(["", "🧾 Подкатегории:"])
    for name, sub_limit, sub_spent, sub_remaining in subcategories:
        lines.append(f"👉 <b>{escape(name)}</b>")
        if enabled:
            lines.extend(["Лимит / Потрачено / Осталось",
                          f"{format_money_or_dash(sub_limit)} / {format_money(sub_spent)} / {format_remaining_with_alert(sub_remaining)}"])
        else:
            lines.append(f"Потрачено: {format_money(sub_spent)}")
        lines.append("")
    return "\n".join(lines).strip()
