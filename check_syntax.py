"""Временная проверка синтаксиса и импортов (удалить после использования)."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

files = [
    "core/config.py",
    "core/models.py",
    "core/vk_client.py",
    "core/outbox.py",
    "core/ticket_service.py",
    "core/reporting.py",
    "core/bot_core.py",
    "web/main.py",
    "web/security/csrf.py",
    "web/security/middleware.py",
    "web/routes/auth.py",
    "web/routes/tickets.py",
    "web/routes/admin_panel.py",
    "web/routes/knowledge_base.py",
    "web/routes/faq.py",
    "web/routes/events.py",
    "bots/vk/bot.py",
    "bots/vk/keyboards.py",
    "alembic/versions/d5e6f7a8b9c0_add_login_attempts_vk_outbox.py",
    "tests/test_auth.py",
    "tests/conftest.py",
]

ok = True
for rel in files:
    path = ROOT / rel
    if not path.exists():
        print(f"MISSING: {rel}")
        ok = False
        continue
    try:
        ast.parse(path.read_text(encoding="utf-8-sig"))
        print(f"OK      {rel}")
    except SyntaxError as exc:
        ok = False
        print(f"SYNTAX  {rel}: {exc}")

# Проверка на остатки send_vk_message в ticket_service
text = (ROOT / "core/ticket_service.py").read_text(encoding="utf-8-sig")
if "async def send_vk_message" in text:
    print("ERROR   ticket_service все ещё содержит send_vk_message")
    ok = False

print("RESULT:", "ALL OK" if ok else "HAS ERRORS")
sys.exit(0 if ok else 1)