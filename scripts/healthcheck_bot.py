#!/usr/bin/env python3
"""Healthcheck VK-бота для docker compose.

Проверяет свежесть heartbeat-файла, который бот обновляет при обработке
событий и раз в минуту. Код возврата 0 — бот жив, 1 — нездоров.

Запуск: python scripts/healthcheck_bot.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.heartbeat import MAX_AGE_SECONDS, heartbeat_age_seconds


def main() -> int:
    age = heartbeat_age_seconds()
    if age is None:
        print(f"unhealthy: heartbeat file not found ({age=})")
        return 1
    if age > MAX_AGE_SECONDS:
        print(f"unhealthy: heartbeat age {age:.0f}s > {MAX_AGE_SECONDS}s")
        return 1
    print(f"healthy: heartbeat age {age:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
