import json


def build_main_keyboard(has_active_tickets: bool, is_admin: bool = False) -> str:
    buttons = [
        ("Жилбыт", "primary"),
        ("Культмасс", "primary"),
        ("Информ", "primary"),
        ("Корпоративный", "primary"),
        ("Анонимное обращение", "secondary"),
    ]
    if has_active_tickets:
        buttons.append(("Мои заявки", "primary"))
    if is_admin:
        buttons.append(("Сформировать отчет", "positive"))

    keyboard = {
        "one_time": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": label}, "color": color}
                for label, color in row
            ]
            for row in [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
        ],
    }
    return json.dumps(keyboard)
