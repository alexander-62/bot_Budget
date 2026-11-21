from aiogram.utils.keyboard import InlineKeyboardBuilder


def settings_keyboard(session, settings, *, planned_enabled):
    builder = InlineKeyboardBuilder()
    for text, action in [
        (f"Валюта: {settings.currency}", "currency"),
        (f"Месячные лимиты: {'включены' if settings.monthly_limits_enabled else 'выключены'}", "limits"),
        (f"Будущие траты: {'включены' if planned_enabled else 'выключены'}", "planned"),
        ("➕ Создать категорию", "new"),
        ("➕ Добавить подкатегорию", "sub"),
        ("Закрыть", "cancel"),
    ]:
        builder.button(text=text, callback_data=f"cfg:{session.token}:{action}")
    builder.adjust(1)
    return builder.as_markup()


def choice_keyboard(session, choices, *, back=True):
    builder = InlineKeyboardBuilder()
    for text, action in choices:
        builder.button(text=text, callback_data=f"cfg:{session.token}:{action}")
    if back:
        builder.button(text="Назад", callback_data=f"cfg:{session.token}:back")
    builder.button(text="Отмена", callback_data=f"cfg:{session.token}:cancel")
    builder.adjust(1)
    return builder.as_markup()
