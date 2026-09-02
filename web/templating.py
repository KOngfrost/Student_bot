from fastapi.templating import Jinja2Templates

# Вынесено в отдельный модуль, чтобы избежать циклического импорта:
# web.main импортирует роутеры, а роутерам нужен только templates.
templates = Jinja2Templates(directory="web/templates")


def security_context(request):
    """Контекстный процессор для передачи CSRF-токена и CSP-nonce в шаблоны.
    
    Безопасность:
    - CSRF-токен: для защиты от CSRF-атак
    - CSP nonce: для защиты от XSS (используется в тегах <script nonce="...">)
    """
    csrf_token = request.session.get("csrf_token", "")
    script_nonce = getattr(request.state, "script_nonce", "")
    style_nonce = getattr(request.state, "style_nonce", "")
    return {
        "csrf_token": csrf_token,
        "script_nonce": script_nonce,
        "style_nonce": style_nonce,
    }
