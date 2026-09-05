from datetime import datetime, timedelta

import json
import logging
import re

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.vk_compat import patch_vkbottle_logging

patch_vkbottle_logging()

from vkbottle import BaseStateGroup, Bot
from vkbottle.bot import Message
from vkbottle.dispatch.rules.base import RegexRule
from vkbottle.exception_factory.base_exceptions import VKAPIError
from core.commands import (
    ADMIN_REPLY_PATTERN,
    ADMIN_STATUS_PATTERN,
    COMMANDS_ADMIN,
    COMMANDS_ADMIN_TICKETS,
    COMMANDS_ANONYMOUS,
    COMMANDS_ANONYMOUS_STAY,
    COMMANDS_CORPORATE,
    COMMANDS_CULTURE,
    COMMANDS_HOUSING,
    COMMANDS_INFORMATION,
    COMMANDS_MY_TICKETS,
    COMMANDS_QUESTION,
    COMMANDS_REGULAR_MENU,
    COMMANDS_REPORT,
    COMMAND_REPORT_BY_DATE,
    COMMAND_REPORT_BY_PERIOD,
    COMMAND_TICKET_DETAILS,
    COMMANDS_START,
)
from core.config import settings
from core.bot_core import BotCore
from core.database import async_session_maker
from core.heartbeat import touch_heartbeat
from core.models import Admin, Ticket, TicketStatus, User, UserRole
from core.reporting import build_daily_report, get_app_tz, get_report_for_date, get_report_for_period, parse_report_date, send_report_to_vk
from core.ticket_service import (
    STATUS_LABELS,
    StatusTransitionError,
    change_ticket_status,
    create_ticket,
    format_ticket_details,
    format_ticket_list,
    get_ticket_messages,
    get_user_tickets,
    reply_to_ticket,
    status_label,
)
from web.dependencies import get_admin_scope_for_vk_id
from bots.vk.keyboards import build_admin_keyboard, build_main_keyboard, build_tickets_keyboard

vk_bot = Bot(token=settings.VK_BOT_TOKEN)

logger = logging.getLogger(__name__)


# FSM StateGroup для отчётов
class ReportStates(BaseStateGroup):
    WAITING_DATE = "waiting_date"
    WAITING_DATE_FROM = "waiting_date_from"
    WAITING_DATE_TO = "waiting_date_to"


# FSM StateGroup для создания обращений (разделы меню, «Задать вопрос», анонимные)
class TicketStates(BaseStateGroup):
    WAITING_DESCRIPTION = "waiting_description"
    WAITING_IDENTITY_CHOICE = "waiting_identity_choice"


def build_anonymous_choice_keyboard() -> str:
    return json.dumps({
        "one_time": True,
        "buttons": [[
            {"action": {"type": "text", "label": "Остаться анонимным"}, "color": "secondary"},
            {"action": {"type": "text", "label": "Остаться не анонимным"}, "color": "primary"},
        ]],
    })


def _main_reply_text() -> str:
    return (
        "Привет! Я бот-помощник студенческого совета.\n"
        "Выбери раздел в меню ниже:"
    )


async def _main_keyboard_for(vk_id: int) -> str:
    user = await BotCore.get_or_create_user(vk_id=vk_id)
    return build_main_keyboard(await BotCore.is_admin(user))


@vk_bot.on.private_message(text=COMMANDS_START)
async def start_handler(message: Message):
    touch_heartbeat()
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    await BotCore.log_action(user, "start", "Пользователь нажал /start")
    keyboard = build_main_keyboard(await BotCore.is_admin(user))
    await message.answer(_main_reply_text(), keyboard=keyboard)


@vk_bot.on.private_message(text=COMMANDS_MY_TICKETS)
async def my_tickets_handler(message: Message):
    """Список заявок пользователя из базы: номер, отдел, тема, дата, статус, ответ."""
    touch_heartbeat()
    await BotCore.get_or_create_user(vk_id=message.from_id)
    tickets = await get_user_tickets(message.from_id, include_completed=True, limit=10)

    if not tickets:
        await message.answer(
            "У вас пока нет заявок.\n\n"
            "Чтобы создать заявку, выберите раздел в меню.",
            keyboard=build_main_keyboard(),
        )
        return

    await message.answer(
        format_ticket_list(tickets),
        keyboard=build_tickets_keyboard([t.id for t in tickets]),
    )


@vk_bot.on.private_message(text=COMMAND_TICKET_DETAILS)
async def ticket_details_handler(message: Message):
    """История заявки: «Подробнее #N» — номер, отдел, тема, статус, вся переписка."""
    touch_heartbeat()
    match = re.search(r"#(\d+)", message.text or "")
    if not match:
        await message.answer(
            "Укажите номер заявки, например: «Подробнее #12».",
            keyboard=build_main_keyboard(),
        )
        return

    ticket_id = int(match.group(1))
    tickets = await get_user_tickets(message.from_id, include_completed=True, limit=50)
    ticket = next((t for t in tickets if t.id == ticket_id), None)

    if ticket is None:
        await message.answer(
            f"Заявка #{ticket_id} не найдена среди ваших заявок.",
            keyboard=build_main_keyboard(),
        )
        return

    history = await get_ticket_messages(ticket.id)
    await message.answer(
        format_ticket_details(ticket, history),
        keyboard=build_tickets_keyboard([ticket.id]),
    )


async def _start_ticket_flow(
    message: Message,
    topic: str,
    department: str | None = None,
) -> None:
    """Единый старт создания обращения: разделы меню, вопрос или анонимный запрос."""
    touch_heartbeat()
    await vk_bot.state_dispenser.set(
        message.from_id,
        TicketStates.WAITING_DESCRIPTION,
        topic=topic,
        department=department,
    )
    header = f"Раздел «{topic}»" if department else "Задать вопрос"
    await message.answer(
        f"{header}\n\n"
        "Опишите вашу проблему одним сообщением: что случилось, когда и где.\n"
        "Чем подробнее описание, тем быстрее ответственный отдел сможет помочь.\n\n"
        "После текста вы сможете выбрать, оставить ли свой VK ID для ответа.",
        keyboard=build_main_keyboard(),
    )


@vk_bot.on.private_message(text=COMMANDS_HOUSING)
async def housing_section(message: Message):
    """Раздел «Жилбыт»: бытовые условия и проблемы в общежитии."""
    await _start_ticket_flow(message, "Жилбыт", "Жилбыт")


@vk_bot.on.private_message(text=COMMANDS_CULTURE)
async def culture_section(message: Message):
    """Раздел «Культмасс»: мероприятия, анонсы, запись на события."""
    await _start_ticket_flow(message, "Культмасс", "Культмасс")


@vk_bot.on.private_message(text=COMMANDS_INFORMATION)
async def information_section(message: Message):
    """Раздел «Информ»: справочная информация и частые вопросы."""
    await _start_ticket_flow(message, "Информ", "Информ")


@vk_bot.on.private_message(text=COMMANDS_CORPORATE)
async def corporate_section(message: Message):
    """Раздел «Корпоративный»: вопросы мероприятий и жизни университета."""
    await _start_ticket_flow(message, "Корпоративный", "Корпоративный")


@vk_bot.on.private_message(text=COMMANDS_QUESTION)
async def question_section_start(message: Message):
    """Общий вопрос без привязки к конкретному отделу."""
    await _start_ticket_flow(message, "Вопрос")


@vk_bot.on.private_message(text=COMMANDS_ANONYMOUS)
async def anonymous_section_start(message: Message):
    """Начало анонимного обращения — бот запрашивает текст."""
    touch_heartbeat()
    await vk_bot.state_dispenser.set(
        message.from_id,
        TicketStates.WAITING_DESCRIPTION,
        topic="Анонимное обращение",
        department=None,
    )
    await message.answer(
        "Анонимное обращение\n\n"
        "Вы можете сообщить о проблеме без указания своего имени.\n"
        "Ваше имя и VK ID не будут привязаны к обращению.\n\n"
        "Опишите проблему в одном сообщении:",
        keyboard=build_main_keyboard(),
    )


@vk_bot.on.private_message(state=TicketStates.WAITING_DESCRIPTION)
async def ticket_description_handler(message: Message):
    """Получить текст обращения и запросить режим обратной связи."""
    touch_heartbeat()
    description = message.text.strip()

    if len(description) < 10:
        await message.answer(
            "Описание слишком короткое.\n\n"
            "Пожалуйста, опишите проблему подробнее (минимум 10 символов).\n\n"
            "Введите текст обращения:"
        )
        return

    state_peer = await vk_bot.state_dispenser.get(message.from_id)
    topic = state_peer.payload.get("topic", "Вопрос") if state_peer else "Вопрос"
    department = state_peer.payload.get("department") if state_peer else None
    await vk_bot.state_dispenser.set(
        message.from_id,
        TicketStates.WAITING_IDENTITY_CHOICE,
        description=description,
        topic=topic,
        department=department,
    )
    await message.answer(
        "Выберите режим обращения:\n\n"
        "«Остаться анонимным» — VK ID не будет сохранён, ответ через VK невозможен.\n"
        "«Остаться не анонимным» — администратор сможет ответить вам в VK.",
        keyboard=build_anonymous_choice_keyboard(),
    )


@vk_bot.on.private_message(
    state=TicketStates.WAITING_IDENTITY_CHOICE,
    text=COMMANDS_ANONYMOUS_STAY,
)
async def ticket_identity_choice_handler(message: Message):
    """Создать обращение после выбора канала обратной связи."""
    keep_identity = message.text == "Остаться не анонимным"
    state_peer = await vk_bot.state_dispenser.get(message.from_id)
    payload = state_peer.payload if state_peer else {}
    description = payload.get("description", "")
    topic = payload.get("topic", "Вопрос")
    department = payload.get("department")

    try:
        ticket = await create_ticket(
            topic=topic,
            description=description,
            vk_id=message.from_id,
            keep_identity=keep_identity,
            department_name=department,
        )

        department_name = ticket.department.name if ticket.department else "Общая"
        answer_tail = (
            "Администратор сможет ответить вам в этом диалоге."
            if keep_identity
            else "VK ID не сохранён. Ответ через VK на это обращение не отправляется."
        )
        await message.answer(
            f"Ваше обращение принято.\n\n"
            f"Номер обращения: #{ticket.id}\n"
            f"Раздел: {department_name}\n"
            f"Статус: {status_label(ticket.status)}\n\n"
            f"{answer_tail}",
            keyboard=await _main_keyboard_for(message.from_id),
        )

        await vk_bot.state_dispenser.delete(message.from_id)

    except Exception:
        logger.exception("Ошибка при создании обращения")
        await message.answer(
            "Не удалось отправить обращение. Попробуйте ещё раз позже.",
            keyboard=await _main_keyboard_for(message.from_id),
        )
        await vk_bot.state_dispenser.delete(message.from_id)


@vk_bot.on.private_message(
    text=COMMANDS_ADMIN
)
async def admin_panel(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer(
            "У вас нет доступа к админ-панели.\n\n"
            "По всем вопросам обращайтесь к главному администратору.",
            keyboard=await _main_keyboard_for(message.from_id),
        )
        return

    await BotCore.log_action(user, "admin_panel", "Открыта админ-панель")
    await message.answer(
        "Админ-панель\n\n"
        "Доступные функции: просмотр заявок, формирование отчётов.\n"
        "Нажмите «Заявки администратора» для просмотра активных заявок.\n"
        "Нажмите «Сформировать отчет», чтобы получить файл отчёта в VK.",
        keyboard=build_admin_keyboard(),
    )


@vk_bot.on.private_message(text=COMMANDS_REGULAR_MENU)
async def regular_menu_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    await message.answer(
        _main_reply_text(),
        keyboard=build_main_keyboard(await BotCore.is_admin(user)),
    )


@vk_bot.on.private_message(text=COMMANDS_ADMIN_TICKETS)
async def admin_tickets_handler(message: Message):
    """Показать оператору заявки, доступные его отделу."""
    async with async_session_maker() as session:
        is_super, dept_id = await get_admin_scope_for_vk_id(session, message.from_id)
    
    if not is_super and dept_id is None:
        await message.answer(
            "У вас нет доступа к заявкам администратора.",
            keyboard=await _main_keyboard_for(message.from_id),
        )
        return
    
    async with async_session_maker() as session:
        stmt = (
            select(Ticket).options(selectinload(Ticket.department))
            .order_by(Ticket.created_at.desc()).limit(20)
        )
        if not is_super and dept_id is not None:
            stmt = stmt.where(Ticket.department_id == dept_id)
        count_stmt = select(func.count(Ticket.id)).where(
            Ticket.status.not_in((TicketStatus.COMPLETED, TicketStatus.COMPLETED_AUTO))
        )
        total_count_stmt = select(func.count(Ticket.id))
        if not is_super and dept_id is not None:
            count_stmt = count_stmt.where(Ticket.department_id == dept_id)
            total_count_stmt = total_count_stmt.where(Ticket.department_id == dept_id)
        pending_count = await session.scalar(count_stmt)
        total_count = await session.scalar(total_count_stmt)
        tickets = list((await session.scalars(stmt)).all())
    if not tickets:
        await message.answer(
            f"Всего доступных заявок: {total_count or 0}\n"
            f"Незавершенных заявок: {pending_count or 0}\n"
            "Доступных заявок нет.",
            keyboard=build_admin_keyboard(),
        )
        return
    lines = [
        f"Всего доступных заявок: {total_count or 0}",
        f"Незавершенных заявок: {pending_count or 0}",
        "Заявки (последние 20):",
    ]
    for ticket in tickets:
        description = (ticket.description or "Без описания").strip()
        if len(description) > 500:
            description = description[:500].rstrip() + "..."
        lines.append(
            f"\n#{ticket.id} [{status_label(ticket.status)}] {ticket.topic or 'Без темы'}\n"
            f"Описание: {description}"
        )
    lines.append("")
    lines.append("Как ответить на заявку:")
    lines.append("  Ответ #N: текст ответа. Например: «Ответ #12: Уже исправили»")
    lines.append("  Статус #N: статус. Например: «Статус #12: Выполнено»")
    await message.answer("\n".join(lines), keyboard=build_admin_keyboard())


async def _operator_can_access(vk_id: int, ticket_id: int) -> bool:
    async with async_session_maker() as session:
        is_super, dept_id = await get_admin_scope_for_vk_id(session, vk_id)
        if is_super:
            return True
        ticket = await session.get(Ticket, ticket_id)
        return ticket is not None and ticket.department_id == dept_id


@vk_bot.on.private_message(RegexRule(ADMIN_REPLY_PATTERN))
async def admin_reply_handler(message: Message):
    match = re.match(ADMIN_REPLY_PATTERN, message.text or "", re.DOTALL)
    if not match or not await _operator_can_access(message.from_id, int(match.group(1))):
        await message.answer(
            "Заявка не найдена или недоступна.",
            keyboard=build_admin_keyboard(),
        )
        return
    ticket_id, text = int(match.group(1)), match.group(2).strip()
    ticket, delivered = await reply_to_ticket(
        ticket_id=ticket_id, admin_username=str(message.from_id), message=text
    )
    if ticket is None:
        await message.answer("Заявка не найдена.", keyboard=build_admin_keyboard())
        return
    await message.answer(
        "Ответ сохранён." + (" Уведомление поставлено в очередь VK." if delivered else ""),
        keyboard=build_admin_keyboard(),
    )


def _parse_status(value: str) -> TicketStatus:
    """Распознать статус по имени enum или по русской метке."""
    value = value.strip()
    try:
        return TicketStatus(value)
    except ValueError:
        pass
    for status, label in STATUS_LABELS.items():
        if label.lower() == value.lower():
            return status
    raise ValueError(f"Неизвестный статус: {value!r}")


@vk_bot.on.private_message(RegexRule(ADMIN_STATUS_PATTERN))
async def admin_status_handler(message: Message):
    match = re.match(ADMIN_STATUS_PATTERN, message.text or "", re.DOTALL)
    if not match or not await _operator_can_access(message.from_id, int(match.group(1))):
        await message.answer(
            "Заявка не найдена или недоступна.",
            keyboard=build_admin_keyboard(),
        )
        return
    try:
        new_status = _parse_status(match.group(2))
        ticket = await change_ticket_status(
            int(match.group(1)), new_status, str(message.from_id)
        )
    except (ValueError, StatusTransitionError):
        await message.answer(
            "Неизвестный статус или недопустимый переход.\n"
            "Допустимые статусы: Новое, В обработке, Выполнено, Передано в администрацию, "
            "Передано в хозчасть.",
            keyboard=build_admin_keyboard(),
        )
        return
    await message.answer(
        f"Статус заявки #{match.group(1)} изменён: {status_label(ticket.status)}."
        if ticket
        else "Заявка не найдена.",
        keyboard=build_admin_keyboard(),
    )


@vk_bot.on.private_message(text=COMMANDS_REPORT)
async def report_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к отчетам.", keyboard=build_main_keyboard())
        return

    try:
        from core.reporting import get_app_tz

        report_date = datetime.now(get_app_tz()) - timedelta(days=1)
        data = await get_report_for_date(report_date.date())
        report_bytes = build_daily_report(data, report_date)
        filename = f"report_{report_date:%Y-%m-%d}.xlsx"
        await send_report_to_vk(
            vk_bot.api,
            message.from_id,
            report_bytes,
            filename,
        )
        await BotCore.log_action(user, "report_generated", f"Сформирован отчёт {filename}")
    except (ValueError, OSError, KeyError, VKAPIError):
        logger.exception("Ошибка при формировании отчёта")
        await BotCore.log_action(user, "report_failed", "Ошибка при формировании отчёта")
        await message.answer(
            "Не удалось сформировать отчёт. Попробуйте ещё раз позже или обратитесь "
            "к администратору.",
            keyboard=build_admin_keyboard(),
        )
        return
    await message.answer(
        f"Отчёт за {report_date:%d.%m.%Y} сформирован и отправлен вам в VK.",
        keyboard=build_admin_keyboard(),
    )


@vk_bot.on.private_message(text=COMMAND_REPORT_BY_DATE)
async def report_by_date_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к отчетам.", keyboard=build_main_keyboard())
        return
    await vk_bot.state_dispenser.set(message.from_id, ReportStates.WAITING_DATE)
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
            message.from_id,
            report_bytes,
            filename,
        )
        await BotCore.log_action(user, "report_generated", f"Сформирован отчёт за {parsed} (по дате)")
        await vk_bot.state_dispenser.delete(message.from_id)
        await message.answer(
            f"Отчет за {parsed:%d.%m.%Y} сформирован и отправлен.",
            keyboard=build_admin_keyboard(),
        )
    except Exception:
        logger.exception("Ошибка при формировании отчёта за %s", parsed)
        await BotCore.log_action(user, "report_failed", f"Ошибка при формировании отчёта за {parsed}")
        await message.answer(
            "Не удалось отправить отчёт. Попробуйте позже; детали записаны в журнал.",
            keyboard=build_admin_keyboard(),
        )
        await vk_bot.state_dispenser.delete(message.from_id)


@vk_bot.on.private_message(text=COMMAND_REPORT_BY_PERIOD)
async def report_by_period_handler(message: Message):
    user = await BotCore.get_or_create_user(vk_id=message.from_id)
    if not await BotCore.is_admin(user):
        await message.answer("У вас нет доступа к отчетам.", keyboard=build_main_keyboard())
        return
    await vk_bot.state_dispenser.set(message.from_id, ReportStates.WAITING_DATE_FROM)
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
            message.from_id,
            report_bytes,
            filename,
        )
        await BotCore.log_action(user, "report_generated", f"Сформирован отчёт за период {date_from} - {date_to}")
        await vk_bot.state_dispenser.delete(message.from_id)
        await message.answer(
            f"Отчёт за период с {date_from:%d.%m.%Y} по {date_to:%d.%m.%Y} "
            "сформирован и отправлен вам в VK.",
            keyboard=build_admin_keyboard(),
        )
    except Exception:
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
            "Не удалось отправить отчёт. Попробуйте позже; детали записаны в журнал.",
            keyboard=build_admin_keyboard(),
        )
        await vk_bot.state_dispenser.delete(message.from_id)


@vk_bot.on.private_message()
async def fallback_handler(message: Message):
    """Возвращает пользователя в основное меню для неизвестных сообщений."""
    touch_heartbeat()
    await message.answer(
        "Я не распознал команду. Выберите действие в меню:",
        keyboard=await _main_keyboard_for(message.from_id),
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