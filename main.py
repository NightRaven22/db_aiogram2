import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

logging.basicConfig(level=logging.INFO)

API_TOKEN = ""
ADMIN_ID = 6413607227

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

tickets = {}
blocked_users = set()

class TicketState(StatesGroup):
    waiting_for_message = State()
    awaiting_reply = State()

@dp.message_handler(commands="start")
async def cmd_start(message: types.Message):
    user = message.from_user
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Открыть тикет", callback_data='open_ticket'),
        InlineKeyboardButton("Информация 1", callback_data='info1'),
        InlineKeyboardButton("Информация 2", callback_data='info2'),
        InlineKeyboardButton("Запрос", callback_data='request')
    )
    await message.answer(f"Привет, {user.first_name}! Выберите команду:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data in ['open_ticket', 'info1', 'info2', 'request', 'back'])
async def process_callback(callback_query: types.CallbackQuery):
    if callback_query.data == 'open_ticket':
        await open_ticket(callback_query)
    elif callback_query.data == 'info1':
        await show_info(callback_query, "Информация 1: ...")
    elif callback_query.data == 'info2':
        await show_info(callback_query, "Информация 2: ...")
    elif callback_query.data == 'request':
        await request_admin(callback_query)
    elif callback_query.data == 'back':
        await cmd_start(callback_query.message)

async def show_info(callback_query: types.CallbackQuery, info_text: str):
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("Назад", callback_data='back'))
    await callback_query.message.edit_text(info_text, reply_markup=keyboard)

async def open_ticket(callback_query: types.CallbackQuery):
    user = callback_query.from_user
    if user.id in blocked_users:
        await callback_query.message.edit_text("Вы заблокированы и не можете открыть тикет.")
        return

    ticket_id = len(tickets) + 1
    tickets[ticket_id] = {'user_id': user.id, 'username': user.username, 'messages': []}
    await TicketState.waiting_for_message.set()
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("Назад", callback_data='back'))
    await callback_query.message.edit_text(f"Тикет #{ticket_id} открыт. Опишите вашу проблему.", reply_markup=keyboard)
    state = dp.current_state(user=user.id)
    await state.update_data(ticket_id=ticket_id)

async def request_admin(callback_query: types.CallbackQuery):
    user = callback_query.from_user
    if user.id in blocked_users:
        await callback_query.message.edit_text("Вы заблокированы и не можете отправить запрос.")
        return

    await bot.send_message(chat_id=ADMIN_ID, text=f"Запрос от @{user.username} (ID: {user.id})")
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("Назад", callback_data='back'))
    await callback_query.message.edit_text("Ваш запрос отправлен администрации.", reply_markup=keyboard)

@dp.message_handler(state=TicketState.waiting_for_message, content_types=types.ContentTypes.TEXT)
async def handle_ticket_message(message: types.Message, state: FSMContext):
    user = message.from_user
    if user.id in blocked_users:
        await message.answer("Вы заблокированы и не можете отправлять сообщения.")
        return

    data = await state.get_data()
    ticket_id = data['ticket_id']
    tickets[ticket_id]['messages'].append(message.text)
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"Сообщение от @{user.username} (ID: {user.id}): {message.text}\nТикет #{ticket_id}"
    )
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("Назад", callback_data='back'))
    await message.answer(f"Ваше сообщение добавлено в тикет #{ticket_id}.", reply_markup=keyboard)
    await state.finish()

@dp.message_handler(commands="admin")
async def admin_command(message: types.Message):
    args = message.get_args().split()
    if not args:
        await message.reply("Используйте команды: /block, /unblock, /close_ticket, /stats, /reply_ticket")
        return

    command = args[0]
    if command == 'block' and len(args) == 2:
        user_id = int(args[1])
        blocked_users.add(user_id)
        await message.reply(f"Пользователь {user_id} заблокирован.")
    elif command == 'unblock' and len(args) == 2:
        user_id = int(args[1])
        blocked_users.discard(user_id)
        await message.reply(f"Пользователь {user_id} разблокирован.")
    elif command == 'close_ticket' and len(args) == 2:
        ticket_id = int(args[1])
        if ticket_id in tickets:
            del tickets[ticket_id]
            await message.reply(f"Тикет #{ticket_id} закрыт.")
        else:
            await message.reply(f"Тикет #{ticket_id} не найден.")
    elif command == 'stats':
        total_messages = sum(len(ticket['messages']) for ticket in tickets.values())
        closed_tickets = len(tickets)
        blocked_users_count = len(blocked_users)
        await message.reply(f"Отправленные сообщения: {total_messages}\n"
                            f"Закрытые тикеты: {closed_tickets}\n"
                            f"Заблокированные пользователи: {blocked_users_count}")
    elif command == 'reply_ticket' and len(args) >= 3:
        ticket_id = int(args[1])
        reply_message = ' '.join(args[2:])
        if ticket_id in tickets:
            user_id = tickets[ticket_id]['user_id']
            await bot.send_message(chat_id=user_id, text=f"Ответ от администрации: {reply_message}")
            await message.reply(f"Ответ отправлен пользователю с ID {user_id} по тикету #{ticket_id}.")
        else:
            await message.reply(f"Тикет #{ticket_id} не найден.")
    else:
        await message.reply("Неизвестная команда или неправильные аргументы.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
