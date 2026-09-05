from fastapi.templating import Jinja2Templates
from fastapi import Request

# Вынесено в отдельный модуль, чтобы избежать циклического импорта:
# web.main импортирует роутеры, а роутерам нужен только templates.
templates = Jinja2Templates(directory="web/templates")

# Фильтры статусов заявки:
# {{ ticket.status|status_label }} — русская метка,
# {{ ticket.status|status_badge }} — CSS-класс бейджа.
from core.ticket_service import status_label  # noqa: E402
from web.constants import status_badge_class  # noqa: E402

templates.env.filters["status_label"] = status_label
templates.env.filters["status_badge"] = status_badge_class

