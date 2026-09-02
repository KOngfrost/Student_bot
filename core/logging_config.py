"""Настройка логирования для проекта Student Bot.

Выводит логи в stdout и в файлы с ротацией:
- student_bot.log — все логи уровня INFO и выше
- student_bot_error.log — только ошибки (ERROR и выше)

Ротация: ежедневно или при достижении 10 MB.
Хранится 30 архивных файлов.
"""

import logging
import logging.handlers
import os
import sys


def setup_logging(
    log_dir: str = "logs",
    level: int = logging.INFO,
) -> None:
    """Настроить логирование в stdout и файлы.

    Вызывается один раз при запуске бота или панели.

    Args:
        log_dir: Директория для логов (создаётся автоматически).
        level: Уровень логирования по умолчанию.
    """
    # Создаём директорию для логов
    os.makedirs(log_dir, exist_ok=True)

    # Форматер для логов
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Очистим предыдущие handlers (если setup_logging вызывается повторно)
    root_logger.handlers.clear()

    # Handler для stdout (всегда активен)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    # Handler для общего лога (INFO и выше)
    general_log = os.path.join(log_dir, "student_bot.log")
    general_handler = logging.handlers.RotatingFileHandler(
        general_log,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=30,
        encoding="utf-8",
    )
    general_handler.setLevel(level)
    general_handler.setFormatter(formatter)
    root_logger.addHandler(general_handler)

    # Handler для ошибок (ERROR и выше) — отдельный файл
    error_log = os.path.join(log_dir, "student_bot_error.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_log,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    logging.info("Логирование настроено: stdout + файлы в %s", log_dir)
