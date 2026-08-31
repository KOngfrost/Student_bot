#!/usr/bin/env bash
# Восстановление базы student_bot из резервной копии.
#
# Использование:
#   ./scripts/restore.sh /var/backups/student_bot/student_bot_2026-08-31.sql.gz
#
# ВНИМАНИЕ: полностью перезаписывает текущую базу!
# Перед восстановлением остановите бота и веб-панель:
#   docker compose stop bot web-admin
# После восстановления запустите снова:
#   docker compose start bot web-admin
#
# Раз в месяц ОБЯЗАТЕЛЬНО проверяйте восстановление на тестовой базе.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Использование: $0 <backup.sql.gz>"
    exit 1
fi

BACKUP_FILE="$1"
[[ -f "$BACKUP_FILE" ]] || { echo "Файл не найден: $BACKUP_FILE"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
    # shellcheck disable=SC1091
    set -a
    source "${SCRIPT_DIR}/../.env"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER is required}"
POSTGRES_DB="${POSTGRES_DB:?POSTGRES_DB is required}"

echo "Восстановление ${BACKUP_FILE} в базу ${POSTGRES_DB}."
read -r -p "Текущие данные будут удалены. Продолжить? (yes/no): " CONFIRM
[[ "$CONFIRM" == "yes" ]] || { echo "Отменено"; exit 1; }

echo "[$(date '+%F %T)] Restore started"

gunzip -c "$BACKUP_FILE" | docker compose -f "${SCRIPT_DIR}/../docker-compose.yml" exec -T db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q

echo "[$(date '+%F %T)] Restore finished. Проверьте данные:"
echo "  docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c 'SELECT count(*) FROM tickets;'"
