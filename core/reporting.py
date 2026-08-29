import asyncio
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from vkbottle.tools.uploader import DocMessagesUploader

from core.config import settings
from core.database import async_session_maker
from core.models import Department, Ticket, TicketStatus

logger = logging.getLogger(__name__)

COMPLETED_STATUSES = {TicketStatus.COMPLETED, TicketStatus.COMPLETED_AUTO}


def _status_text(status) -> str:
    """Возвращает человекочитаемый статус заявки."""
    if status is None:
        return ""
    if isinstance(status, TicketStatus):
        return status.value
    return str(status)


def _user_full_name(user) -> str:
    return user.full_name if user and user.full_name else "—"


def _user_dormitory(user) -> str:
    return user.dormitory if user and user.dormitory else "—"


def _department_name(department) -> str:
    return department.name if department else "—"


async def _fetch_report_data(report_date: datetime) -> dict:
    """Собирает данные для отчёта за указанную дату."""
    day_start = datetime.combine(report_date.date(), datetime.min.time())
    day_end = day_start + timedelta(days=1)

    async with async_session_maker() as session:
        tickets = await session.scalars(
            select(Ticket)
            .options(selectinload(Ticket.user), selectinload(Ticket.department))
            .where(Ticket.created_at >= day_start, Ticket.created_at < day_end)
            .order_by(Ticket.created_at)
        )
        departments = await session.scalars(
            select(Department).order_by(Department.name)
        )

    return {
        "tickets": list(tickets),
        "departments": list(departments),
    }


def _build_summary_sheet(workbook: Workbook, data: dict) -> None:
    """Лист 1: Сводка по отделам и процент выполнения."""
    sheet = workbook.active
    sheet.title = "Сводка"

    headers = [
        "Отдел",
        "Новые",
        "В обработке",
        "Передано в адм.",
        "Передано в хоз.",
        "Выполнено",
        "Выполнено (авто)",
        "Анонимные",
        "Всего",
        "% выполнения",
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    tickets = data["tickets"]
    departments = data["departments"]

    def _count(predicate) -> int:
        return sum(1 for t in tickets if predicate(t))

    rows = []
    for department in departments:
        dept_tickets = [t for t in tickets if t.department_id == department.id]
        if not dept_tickets:
            continue
        total = len(dept_tickets)
        completed = sum(1 for t in dept_tickets if t.status in COMPLETED_STATUSES)
        percent = round(completed / total * 100, 1) if total else 0.0
        rows.append(
            [
                department.name,
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.NEW),
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.IN_PROGRESS),
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.TRANSFERRED_ADMIN),
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.TRANSFERRED_HOUSEKEEPING),
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.COMPLETED),
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.COMPLETED_AUTO),
                _count(lambda t, d=department: t.department_id == d.id and t.status == TicketStatus.ANONYMOUS),
                total,
                percent,
            ]
        )

    # Итоговая строка
    total = len(tickets)
    completed = sum(1 for t in tickets if t.status in COMPLETED_STATUSES)
    percent = round(completed / total * 100, 1) if total else 0.0
    rows.append(
        [
            "ИТОГО",
            _count(lambda t: t.status == TicketStatus.NEW),
            _count(lambda t: t.status == TicketStatus.IN_PROGRESS),
            _count(lambda t: t.status == TicketStatus.TRANSFERRED_ADMIN),
            _count(lambda t: t.status == TicketStatus.TRANSFERRED_HOUSEKEEPING),
            _count(lambda t: t.status == TicketStatus.COMPLETED),
            _count(lambda t: t.status == TicketStatus.COMPLETED_AUTO),
            _count(lambda t: t.status == TicketStatus.ANONYMOUS),
            total,
            percent,
        ]
    )

    for row in rows:
        sheet.append(row)

    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = max_length + 2


def _build_details_sheet(workbook: Workbook, data: dict) -> None:
    """Лист 2: Детализация заявок."""
    sheet = workbook.create_sheet("Детализация")

    headers = [
        "ID",
        "ФИО",
        "Общежитие",
        "Отдел",
        "Тема",
        "Описание",
        "Статус",
        "Ответ",
        "Маркер",
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for ticket in data["tickets"]:
        marker = "авто" if ticket.auto_closed else "ручной"
        sheet.append(
            [
                ticket.id,
                _user_full_name(ticket.user),
                _user_dormitory(ticket.user),
                _department_name(ticket.department),
                ticket.topic or "",
                ticket.description or "",
                _status_text(ticket.status),
                ticket.response_text or "",
                marker,
            ]
        )

    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 60)


def _build_anonymous_sheet(workbook: Workbook, data: dict) -> None:
    """Лист 3: Анонимные обращения."""
    sheet = workbook.create_sheet("Анонимные обращения")

    headers = ["ID", "Тема", "Описание", "Статус", "Дата создания"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    anonymous = [t for t in data["tickets"] if t.is_anonymous or t.status == TicketStatus.ANONYMOUS]
    for ticket in anonymous:
        sheet.append(
            [
                ticket.id,
                ticket.topic or "",
                ticket.description or "",
                _status_text(ticket.status),
                ticket.created_at.strftime("%Y-%m-%d %H:%M") if ticket.created_at else "",
            ]
        )

    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 60)


def build_daily_report(data: dict, report_date: datetime) -> bytes:
    """Строит Excel-отчёт по ТЗ: Сводка, Детализация, Анонимные обращения."""
    workbook = Workbook()

    _build_summary_sheet(workbook, data)
    _build_details_sheet(workbook, data)
    _build_anonymous_sheet(workbook, data)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def send_report_email(report_bytes: bytes, filename: str) -> None:
    """Отправляет отчёт по email через SMTP."""
    if not settings.SMTP_HOST or not settings.REPORT_EMAILS:
        logger.info("SMTP не настроен, email-рассылка пропущена")
        return

    msg = MIMEMultipart()
    msg["Subject"] = f"Отчёт студенческого бота за {datetime.now():%d.%m.%Y}"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(settings.REPORT_EMAILS)

    msg.attach(MIMEText("Ежедневный отчёт во вложении.", "plain", "utf-8"))

    attachment = MIMEApplication(
        report_bytes,
        _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM, settings.REPORT_EMAILS, msg.as_string())

    logger.info("Отчёт отправлен по email: %s", ", ".join(settings.REPORT_EMAILS))


async def send_report_to_vk(api, admin_vk_id: int, report_bytes: bytes, filename: str) -> None:
    """Отправляет отчёт в VK как документ через встроенный uploader vkbottle."""
    if not admin_vk_id:
        raise ValueError("VK_REPORT_ADMIN_ID не настроен")

    uploader = DocMessagesUploader(api)
    attachment = await uploader.upload(
        file_source=BytesIO(report_bytes),
        peer_id=admin_vk_id,
        title=filename,
    )

    await api.messages.send(
        peer_id=admin_vk_id,
        random_id=0,
        message="Ежедневный отчёт во вложении.",
        attachment=attachment,
    )


def _seconds_until_report() -> float:
    try:
        report_time = datetime.strptime(settings.REPORT_TIME, "%H:%M").time()
    except ValueError as error:
        raise ValueError("REPORT_TIME должен быть в формате HH:MM") from error

    now = datetime.now()
    next_report = datetime.combine(now.date(), report_time)
    if next_report <= now:
        next_report += timedelta(days=1)
    return (next_report - now).total_seconds()


async def _report_loop(api, admin_vk_id: int) -> None:
    while True:
        try:
            await asyncio.sleep(_seconds_until_report())

            report_date = datetime.now() - timedelta(days=1)
            data = await _fetch_report_data(report_date)
            report_bytes = build_daily_report(data, report_date)
            filename = f"report_{report_date:%Y-%m-%d}.xlsx"

            if admin_vk_id:
                await send_report_to_vk(api, admin_vk_id, report_bytes, filename)
            if settings.REPORT_EMAILS:
                await asyncio.to_thread(send_report_email, report_bytes, filename)

            logger.info("Ежедневный отчёт отправлен")
        except Exception:
            logger.exception("Не удалось отправить ежедневный отчёт")
            await asyncio.sleep(60)


def start_report_scheduler(api, admin_vk_id: int) -> asyncio.Task:
    """Запускает asyncio-планировщик ежедневных отчётов."""
    task = asyncio.create_task(_report_loop(api, admin_vk_id))
    return task