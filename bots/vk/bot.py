from datetime import datetime, timedelta

from core.vk_compat import patch_vkbottle_logging

patch_vkbottle_logging()

from vkbottle import Bot
from vkbottle.bot import Message
from vkbottle.exception_factory.base_exceptions import VKAPIError
from core.config import settings
from core.bot_core import BotCore
from core.reporting import _fetch_report_data, build_daily_report, send_report_to_vk
from bots.vk.keyboards import build_main_keyboard

vk_bot = Bot(token=settings.VK_BOT_TOKEN)


def _main_reply_text() -> str:
    return (
        "Привет! Я бот-помощник студенческого совета.\n"
        "Выбери раздел в меню ниже:"
    )


@vk_bot.on.private_message(
    text=["/start", "start", "Start", "START", "старт", "меню", "Меню", "Начать"]
)
async def start_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    has_tickets = await BotCore.get_user_tickets_count(user) > 0
    keyboard = build_main_keyboard(has_tickets, await BotCore.is_admin(user))
    await message.answer(_main_reply_text(), keyboard=keyboard)


@vk_bot.on.private_message(text=["Мои заявки", "Мои заявки"])
async def tickets_stub(message: Message):
    await message.answer(
        "Активных заявок пока нет.",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(text=["Жилбыт", "Жилбыт"])
async def housing_section(message: Message):
    await message.answer(
        "Раздел «Жилбыт» открыт. Здесь можно будет сообщить о проблеме в общежитии "
        "или задать вопрос по бытовым условиям. Форма обращения готовится.",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(text=["Культмасс", "Культмасс"])
async def culture_section(message: Message):
    await message.answer(
        "Раздел «Культмасс» открыт. Здесь появятся мероприятия, анонсы и запись "
        "на события.",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(text=["Информ", "Информ"])
async def information_section(message: Message):
    await message.answer(
        "Раздел «Информ» открыт. Здесь будет справочная информация и ответы на "
        "частые вопросы.",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(text=["Корпоративный", "Корпоративный"])
async def corporate_section(message: Message):
    await message.answer(
        "Раздел «Корпоративный» открыт. Здесь можно будет обратиться по вопросам "
        "мероприятий и жизни университета.",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(text=["Анонимное обращение", "Анонимное обращение"])
async def anonymous_section(message: Message):
    await message.answer(
        "Анонимное обращение открыто. Форма отправки обращения готовится.",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(
    text=["Админ-панель", "Админ-панель"]
)
async def admin_panel(message: Message):
    if not BotCore.is_admin_vk_id(message.from_id):
        await message.answer("У вас нет доступа к админки.\n\n"
                             " По всем вопросам обращайтесь к главному администратору.")
        return

    await message.answer(
        "Админ-панель\n\n"
        "Нажми «Сформировать отчет», чтобы получить файл в VK.",
        keyboard=build_main_keyboard(False, True),
    )


@vk_bot.on.private_message(text=["Сформировать отчет", "Сформировать отчет"])
async def report_handler(message: Message):
    if not BotCore.is_admin_vk_id(message.from_id):
        await message.answer("У тебя нет доступа к отчетам.")
        return

    try:
        report_date = datetime.now() - timedelta(days=1)
        data = await _fetch_report_data(report_date)
        report_bytes = build_daily_report(data, report_date)
        filename = f"report_{report_date:%Y-%m-%d}.xlsx"
        await send_report_to_vk(
            vk_bot.api,
            settings.VK_REPORT_ADMIN_ID,
            report_bytes,
            filename,
        )
    except (ValueError, OSError, KeyError, VKAPIError) as error:
        await message.answer(f"Не удалось отправить отчет: {error}")
        return
    await message.answer("Отчет сформирован и отправлен.")



if __name__ == "__main__":
    vk_bot.run()