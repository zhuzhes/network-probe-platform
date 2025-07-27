#!/bin/bash

# 网络拨测平台备份脚本

set -e

# 配置
BACKUP_DIR="/opt/backups/network-probe-platform"
RETENTION_DAYS=30
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="network-probe-backup-${TIMESTAMP}"

# 数据库配置
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-network_probe}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD}"

# S3配置（可选）
S3_BUCKET="${BACKUP_S3_BUCKET}"
S3_REGION="${BACKUP_S3_REGION:-us-east-1}"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 创建备份目录
create_backup_dir() {
    log "创建备份目录: ${BACKUP_DIR}/${BACKUP_NAME}"
    mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"
}

# 备份数据库
backup_database() {
    log "开始备份数据库..."
    
    export PGPASSWORD="${DB_PASSWORD}"
    
    pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --verbose --clean --no-owner --no-privileges \
        --format=custom \
        --file="${BACKUP_DIR}/${BACKUP_NAME}/database.dump"
    
    if [ $? -eq 0 ]; then
        log "数据库备份完成"
    else
        log "数据库备份失败"
        exit 1
    fi
}

# 备份上传文件
backup_uploads() {
    log "开始备份上传文件..."
    
    if [ -d "/app/uploads" ]; then
        tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" -C /app uploads/
        log "上传文件备份完成"
    else
        log "上传目录不存在，跳过"
    fi
}

# 备份配置文件
backup_configs() {
    log "开始备份配置文件..."
    
    CONFIG_DIR="${BACKUP_DIR}/${BACKUP_NAME}/configs"
    mkdir -p "${CONFIG_DIR}"
    
    # 备份环境配置
    if [ -f "/opt/network-probe-platform/.env" ]; then
        cp "/opt/network-probe-platform/.env" "${CONFIG_DIR}/"
    fi
    
    # 备份Docker Compose文件
    if [ -f "/opt/network-probe-platform/docker-compose.yml" ]; then
        cp "/opt/network-probe-platform/docker-compose.yml" "${CONFIG_DIR}/"
    fi
    
    # 备份Nginx配置
    if [ -d "/opt/network-probe-platform/nginx" ]; then
        cp -r "/opt/network-probe-platform/nginx" "${CONFIG_DIR}/"
    fi
    
    # 备份SSL证书
    if [ -d "/opt/network-probe-platform/certs" ]; then
        cp -r "/opt/network-probe-platform/certs" "${CONFIG_DIR}/"
    fi
    
    log "配置文件备份完成"
}

# 备份Redis数据
backup_redis() {
    log "开始备份Redis数据..."
    
    # 触发Redis保存
    docker exec network-probe-redis-prod redis-cli -a "${REDIS_PASSWORD}" BGSAVE
    
    # 等待保存完成
    sleep 5
    
    # 复制RDB文件
    docker cp network-probe-redis-prod:/data/dump.rdb "${BACKUP_DIR}/${BACKUP_NAME}/redis.rdb"
    
    log "Redis数据备份完成"
}

# 创建备份元数据
create_metadata() {
    log "创建备份元数据..."
    
    cat > "${BACKUP_DIR}/${BACKUP_NAME}/metadata.json" << EOF
{
    "backup_name": "${BACKUP_NAME}",
    "timestamp": "${TIMESTAMP}",
    "date": "$(date -Iseconds)",
    "version": "1.0.0",
    "components": {
        "database": true,
        "uploads": $([ -f "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" ] && echo "true" || echo "false"),
        "configs": true,
        "redis": true
    },
    "sizes": {
        "database": "$(du -h "${BACKUP_DIR}/${BACKUP_NAME}/database.dump" | cut -f1)",
        "uploads": "$([ -f "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" ] && du -h "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" | cut -f1 || echo "0")",
        "total": "$(du -sh "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)"
    }
}
EOF
    
    log "备份元数据创建完成"
}

# 压缩备份
compress_backup() {
    log "压缩备份文件..."
    
    cd "${BACKUP_DIR}"
    tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}/"
    rm -rf "${BACKUP_NAME}/"
    
    log "备份压缩完成: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
}

# 上传到S3（可选）
upload_to_s3() {
    if [ -n "${S3_BUCKET}" ]; then
        log "上传备份到S3..."
        
        aws s3 cp "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" \
            "s3://${S3_BUCKET}/backups/network-probe-platform/${BACKUP_NAME}.tar.gz" \
            --region "${S3_REGION}"
        
        if [ $? -eq 0 ]; then
            log "S3上传完成"
        else
            log "S3上传失败"
        fi
    fi
}

# 清理旧备份
cleanup_old_backups() {
    log "清理${RETENTION_DAYS}天前的备份..."
    
    find "${BACKUP_DIR}" -name "network-probe-backup-*.tar.gz" -mtime +${RETENTION_DAYS} -delete
    
    # 清理S3中的旧备份
    if [ -n "${S3_BUCKET}" ]; then
        aws s3 ls "s3://${S3_BUCKET}/backups/network-probe-platform/" | \
        while read -r line; do
            createDate=$(echo $line | awk '{print $1" "$2}')
            createDate=$(date -d "$createDate" +%s)
            olderThan=$(date -d "${RETENTION_DAYS} days ago" +%s)
            if [[ $createDate -lt $olderThan ]]; then
                fileName=$(echo $line | awk '{print $4}')
                if [[ $fileName != "" ]]; then
                    aws s3 rm "s3://${S3_BUCKET}/backups/network-probe-platform/$fileName"
                fi
            fi
        done
    fi
    
    log "旧备份清理完成"
}

# 发送通知
send_notification() {
    local status=$1
    local message=$2
    
    if [ -n "${SLACK_WEBHOOK_URL}" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"${status} 网络拨测平台备份: ${message}\"}" \
            "${SLACK_WEBHOOK_URL}"
    fi
    
    if [ -n "${EMAIL_NOTIFICATION}" ]; then
        echo "${message}" | mail -s "${status} 网络拨测平台备份" "${EMAIL_NOTIFICATION}"
    fi
}

# 主函数
main() {
    log "开始备份网络拨测平台..."
    
    # 检查必要的环境变量
    if [ -z "${DB_PASSWORD}" ]; then
        log "错误: 未设置数据库密码"
        exit 1
    fi
    
    # 创建备份目录
    create_backup_dir
    
    # 执行备份
    backup_database
    backup_uploads
    backup_configs
    backup_redis
    create_metadata
    compress_backup
    upload_to_s3
    cleanup_old_backups
    
    log "备份完成: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    
    # 发送成功通知
    send_notification "✅" "备份成功完成 - ${BACKUP_NAME}"
}

# 错误处理
trap 'log "备份过程中发生错误"; send_notification "❌" "备份失败 - ${BACKUP_NAME}"; exit 1' ERR

# 执行主函数
main "$@"