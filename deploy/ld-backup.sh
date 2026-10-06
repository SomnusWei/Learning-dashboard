#!/bin/bash
# 个人学习工作台 · 数据库每日备份脚本
# 功能：pg_dump 全量备份 + 7 天滚动保留
# 用法：手动执行 /usr/local/bin/ld-backup.sh，或由 cron/systemd timer 调度

set -euo pipefail

PROJECT_DIR="/vol1/1000/learning-dashboard"
BACKUP_DIR="${PROJECT_DIR}/data/backups"
DB_CONTAINER="ld-postgres"
DB_NAME="learning"
DB_USER="learning"
RETENTION_DAYS=7
LOG_FILE="${BACKUP_DIR}/backup.log"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/learning_${TIMESTAMP}.sql.gz"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始备份数据库..." >> "${LOG_FILE}"

# 执行 pg_dump（通过 docker exec 在 postgres 容器内执行）
if docker exec "${DB_CONTAINER}" pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${BACKUP_FILE}"; then
    SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份成功：${BACKUP_FILE} (${SIZE})" >> "${LOG_FILE}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份失败！" >> "${LOG_FILE}"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# 清理超过保留天数的旧备份
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 清理 ${RETENTION_DAYS} 天前的旧备份..." >> "${LOG_FILE}"
find "${BACKUP_DIR}" -name "learning_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete -print 2>/dev/null | while read f; do
    echo "  已删除：${f}" >> "${LOG_FILE}"
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份流程完成。当前备份文件数：$(ls -1 ${BACKUP_DIR}/learning_*.sql.gz 2>/dev/null | wc -l)" >> "${LOG_FILE}"
