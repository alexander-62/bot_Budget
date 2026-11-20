from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def actions(session, choices, *, close=True):
    rows = [[InlineKeyboardButton(text=label, callback_data=f'fut:{session.token}:{action}')]
            for label, action in choices]
    if close:
        rows.append([InlineKeyboardButton(text='Закрыть', callback_data=f'fut:{session.token}:close')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def open_plan_keyboard(planned_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Открыть платёж', callback_data=f'fut:open:{planned_id}')]])
