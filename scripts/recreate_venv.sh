#!/usr/bin/env bash
# Пересоздание локального виртуального окружения проекта.
#
# Проблема, которую решает: локальный .venv был повреждён (Python 3.14.6,
# не импортировались pytest-asyncio/httpx). Проект таргетирует Python 3.11.
#
# Использование:
#   ./scripts/recreate_venv.sh
#
# Требования: на машине установлен Python 3.11 (py -3.11 на Windows,
# python3.11 на Linux/macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Определяем команду python 3.11
PYTHON=""
for candidate in python3.11 python3.12 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ Не найден Python 3.10+. Установите Python 3.11 (см. https://python.org)." >&2
    exit 1
fi

echo "▶ Удаляем старый .venv (при наличии)..."
rm -rf .venv

echo "▶ Создаём .venv через $PYTHON..."
"$PYTHON" -m venv .venv

echo "▶ Устанавливаем зависимости..."
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt -r requirements-dev.txt

echo ""
echo "✅ Готово. Активируйте окружение:"
echo "   source .venv/bin/activate"
echo "   python -m pytest -q"