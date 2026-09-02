from datetime import datetime, timedelta

import logging
import re

from core.vk_compat import patch_vkbottle_logging

patch_vkbottle_logging()

from vkbottle import Bot, StateGroup
from vkbottle.bot import Message
from vkbottle.dispatch.rules.base import RegexRule
from vkbottle.exception_factory.base_exceptions import VKAPIError
from core.config import settings
from core.bot_core import BotCore
from core.heartbeat import touch_heartbeat
from core.reporting import _fetch_report_data, build_daily_report, get_report_for_date, get_report_for_period, parse_report_date, send_report_to_vk
from core.ticket_service import (
    create_anonymous_ticket,
    format_ticket_details,
    format_ticket_list,
    get_ticket_messages,
    get_user_tickets,
)
from bots.vk.keyboards import build_main_keyboard, build_tickets_keyboard

vk_bot = Bot(token=settings.VK_BOT_TOKEN)

logger = logging.getLogger(__name__)


# FSM StateGroup для отчётов
class ReportStates(StateGroup):
    WAITING_DATE = "waiting_date"
    WAITING_DATE_FROM = "waiting_date_from"
    WAITING_DATE_TO = "waiting_date_to"


# FSM StateGroup для анонимных обращений
class AnonymousStates(StateGroup):
    WAITING_DESCRIPTION = "waiting_anonymous_description"


def _main_reply_text() -> str:
    return (
        "Привет! Я бот-помощник студенческого совета.\n"
        "Выбери раздел в меню ниже:"
    )


@vk_bot.on.private_message(
    text=["/start", "start", "Start", "START", "старт", "меню", "Меню", "Начать"]
)
async def start_handler(message: Message):
    touch_heartbeat()
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    has_tickets = await BotCore.get_user_tickets_count(user) > 0
    await BotCore.log_action(user, "start", "Пользователь нажал /start")
    keyboard = build_main_keyboard(has_tickets, await BotCore.is_admin(user))
    await message.answer(_main_reply_text(), keyboard=keyboard)


@vk_bot.on.private_message(text=["Мои заявки", "мои заявки"])
async def my_tickets_handler(message: Message):
    """Список заявок пользователя из базы: номер, отдел, тема, дата, статус, ответ."""
    touch_heartbeat()
    await BotCore.get_or_create_user(vk_id=message.from_id)
    tickets = await get_user_tickets(message.from_id, include_completed=True, limit=10)

    if not tickets:
        await message.answer(
            "У вас пока нет заявок.\n\n"
            "Чтобы создать заявку, выберите раздел в меню.",
            keyboard=build_main_keyboard(False),
        )
        return

    await message.answer(
        format_ticket_list(tickets),
        keyboard=build_tickets_keyboard([t.id for t in tickets]),
    )


@vk_bot.on.private_message(text=["Подробнее"])
async def ticket_details_handler(message: Message):
    """История заявки: «Подробнее #N» — номер, отдел, тема, статус, вся переписка."""
    touch_heartbeat()
    match = re.search(r"#(\d+)", message.text or "")
    if not match:
        await message.answer(
            "Укажите номер заявки, например: «Подробнее #12».",
            keyboard=build_main_keyboard(False),
        )
        return

    ticket_id = int(match.group(1))
    tickets = await get_user_tickets(message.from_id, include_completed=True, limit=50)
    ticket = next((t for t in tickets if t.id == ticket_id), None)

    if ticket is None:
        await message.answer(
            f"Заявка #{ticket_id} не найдена среди ваших заявок.",
            keyboard=build_main_keyboard(False),
        )
        return

    history = await get_ticket_messages(ticket.id)
    await message.answer(
        format_ticket_details(ticket, history),
        keyboard=build_tickets_keyboard([ticket.id]),
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
async def anonymous_section_start(message: Message, state: vkbottle.StateType):
    """Начало создания анонимной заявки — бот запрашивает текст."""
    touch_heartbeat()
    # Устанавливаем FSM-состояние
    await state.set(AnonymousStates.WAITING_DESCRIPTION)
    await message.answer(
        "🔒 Анонимное обращение\n\n"
        "Вы можете anonymously сообщить о проблеме.\n"
        "Ваше имя и VK ID НЕ будут привязаны к заявке.\n\n"
        "Опишите вашу проблему или предложение в одном сообщении.\n"
        "Чем подробнее — тем быстрее мы сможем помочь.\n\n"
        "Введите текст обращения:",
        keyboard=build_main_keyboard(False),
    )


@vk_bot.on.private_message(state=AnonymousStates.WAITING_DESCRIPTION)
async def anonymous_section_submit(message: Message):
    """Отправка анонимной заявки — сохранение в БД."""
    touch_heartbeat()
    description = message.text.strip()

    if not description or len(description) < 10:
        await message.answer(
            "⚠️ Описание слишком короткое.\n\n"
            "Пожалуйста, опишите проблему подробнее (минимум 10 символов).\n\n"
            "Введите текст обращения:"
        )
        return

    try:
        ticket = await create_anonymous_ticket(
            topic="Анонимное обращение",
            description=description,
        )

        await message.answer(
            f"✅ Ваше обращение принято!\n\n"
            f"Номер заявки: #{ticket.id}\n"
            f"Статус: Анонимное\n\n"
            f"Обращение доступно для обработки суперадминистратору.\n"
            f"Мы ответим вам через бота, когда будет готов ответ."
        )

        # Уведомляем суперадмина о новой анонимной заявке
        from core.vk_client import send_vk_message
        await send_vk_message(
            settings.VK_REPORT_ADMIN_ID,
            f"🔒 Новая анонимная заявка #{ticket.id}\n"
            f"{description[:200]}",
        )

    except Exception:
        logger.exception("Ошибка при создании анонимной заявки")
        await message.answer(
            "❌ Произошла ошибка при отправке обращения.\n"
            "Пожалуйста, попробуйте позже."
        )


@vk_bot.on.private_message(
    text=["Админ", "Админ"]
)
async def admin_panel(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к админ-панели.\n\n"
                              "По всем вопросам обращайтесь к главному администратору.")
        return

    await BotCore.log_action(user, "admin_panel", "Открыта админ-панель")
    await message.answer(
        "Админ-панель\n\n"
        "Нажми «Сформировать отчет», чтобы получить файл в VK.",
        keyboard=build_main_keyboard(False, True),
    )


@vk_bot.on.private_message(text=["Сформировать отчет", "Сформировать отчет"])
async def report_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к отчетам.")
        return

    try:
        from core.reporting import get_app_tz

        report_date = datetime.now(get_app_tz()) - timedelta(days=1)
        data = await _fetch_report_data(report_date)
        report_bytes = build_daily_report(data, report_date)
        filename = f"report_{report_date:%Y-%m-%d}.xlsx"
        await send_report_to_vk(
            vk_bot.api,
            settings.VK_REPORT_ADMIN_ID,
            report_bytes,
            filename,
        )
        await BotCore.log_action(user, "report_generated", f"Сформирован отчёт {filename}")
    except (ValueError, OSError, KeyError, VKAPIError) as error:
        logger.exception("Ошибка при формировании отчёта")
        await BotCore.log_action(user, "report_failed", "Ошибка при формировании отчёта")
        await message.answer(
            "Не удалось сформировать отчёт. Попробуйте ещё раз позже или обратитесь "
            "к администратору."
        )
        return
    await message.answer("Отчет сформирован и отправлен.")


@vk_bot.on.private_message(text="Отчет по дате", state=ReportStates.WAITING_DATE)
async def report_by_date_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к отчетам.")
        return
    await message.answer("Введите дату в формате ДД.ММ.ГГГГ (например: 31.08.2026)")


@vk_bot.on.private_message(RegexRule(r"^\d{2}\.\d{2}\.\d{4}$"), state=ReportStates.WAITING_DATE)
async def report_by_date_input(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        return

    parsed = parse_report_date(message.text)
    if parsed is None:
        await message.answer("Неверный формат. Введите дату в формате ДД.ММ.ГГГГ (например: 31.08.2026)")
        return

    try:
        data = await get_report_for_date(parsed)
        report_bytes = build_daily_report(data, datetime(*parsed.timetuple()[:6]))
        filename = f"report_{parsed:%Y-%m-%d}.xlsx"
        await send_report_to_vk(
            vk_bot.api,
            settings.VK_REPORT_ADMIN_ID,
            report_bytes,
            filename,
        )
        await BotCore.log_action(user, "report_generated", f"Сформирован отчёт за {parsed} (по дате)")
        await message.answer(f"Отчет за {parsed:%d.%m.%Y} сформирован и отправлен.")
    except Exception as error:
        logger.exception("Ошибка при формировании отчёта за %s", parsed)
        await BotCore.log_action(user, "report_failed", f"Ошибка при формировании отчёта за {parsed}")
        await message.answer(
            "Не удалось отправить отчёт. Попробуйте позже; детали записаны в журнал."
        )


@vk_bot.on.private_message(text="Отчет за период", state=ReportStates.WAITING_DATE_FROM)
async def report_by_period_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к отчетам.")
        return
    await message.answer(
        "Введите диапазон дат в формате:\n"
        "31.08.2026 - 15.09.2026\n"
        "или\n"
        "с 31.08.2026 по 15.09.2026"
    )


@vk_bot.on.private_message(RegexRule(r"^\d{2}\.\d{2}\.\d{4}\s*[-–—]\s*\d{2}\.\d{2}\.\d{4}$"), state=ReportStates.WAITING_DATE_FROM)
async def report_by_period_input(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        return

    parts = re.split(r"\s*[-–—]\s*", message.text.strip())
    if len(parts) != 2:
        await message.answer("Неверный формат. Введите две даты через тире (например: 31.08.2026 - 15.09.2026)")
        return

    date_from = parse_report_date(parts[0])
    date_to = parse_report_date(parts[1])

    if date_from is None or date_to is None:
        await message.answer("Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 31.08.2026)")
        return

    if date_from > date_to:
        await message.answer("Дата начала не может быть позже даты окончания.")
        return

    try:
        data = await get_report_for_period(date_from, date_to)
        report_bytes = build_daily_report(data, datetime(*date_from.timetuple()[:6]))
        filename = f"report_{date_from:%Y-%m-%d}_to_{date_to:%Y-%m-%d}.xlsx"
        await send_report_to_vk(
            vk_bot.api,
            settings.VK_REPORT_ADMIN_ID,
            report_bytes,
            filename,
        )
        await BotCore.log_action(user, "report_generated", f"Сформирован отчёт за период {date_from} - {date_to}")
        await message.answer(f"Отчет за период с {date_from:%d.%m.%Y} по {date_to:%d.%m.%Y} сформирован и отправлен.")
    except Exception as error:
        logger.exception(
            "Ошибка при формировании отчёта за период %s - %s",
            date_from,
            date_to,
        )
        await BotCore.log_action(
            user,
            "report_failed",
            f"Ошибка при формировании отчёта за период {date_from} - {date_to}",
        )
        await message.answer(
            "Не удалось отправить отчёт. Попробуйте позже; детали записаны в журнал."
        )


if __name__ == "__main__":
    # Глобальный перехватчик ошибок: ни одна ошибка не должна
    # попасть в виде traceback в сообщение пользователю.
    @vk_bot.exception_handler()
    async def handle_all_errors(error: Exception):
        logger.exception("Необработанная ошибка в боте", exc_info=error)
        # Пользователю — безопасное сообщение без деталей
        return {"error": "Произошла внутренняя ошибка. Пожалуйста, попробуйте позже."}

    vk_bot.run()