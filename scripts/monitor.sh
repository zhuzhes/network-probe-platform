#!/bin/bash

# 网络拨测平台监控脚本

set -e

# 配置
ALERT_EMAIL="${ALERT_EMAIL}"
SLACK_WEBHOOK="${SLACK_WEBHOOK_URL}"
CHECK_INTERVAL=60
LOG_FILE="/var/log/network-probe-monitor.log"

# 阈值配置
CPU_THRESHOLD=80
MEMORY_THRESHOLD=80
DISK_THRESHOLD=85
RESPONSE_TIME_THRESHOLD=5000

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 发送警报
send_alert() {
    local severity=$1
    local message=$2
    local emoji=""
    
    case $severity in
        "CRITICAL") emoji="🚨" ;;
        "WARNING") emoji="⚠️" ;;
        "INFO") emoji="ℹ️" ;;
        "RESOLVED") emoji="✅" ;;
    esac
    
    log "$severity: $message"
    
    # 发送Slack通知
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"$emoji [$severity] 网络拨测平台: $message\"}" \
            "$SLACK_WEBHOOK" 2>/dev/null || true
    fi
    
    # 发送邮件通知
    if [ -n "$ALERT_EMAIL" ]; then
        echo "$message" | mail -s "[$severity] 网络拨测平台监控警报" "$ALERT_EMAIL" 2>/dev/null || true
    fi
}

# 检查Docker容器状态
check_containers() {
    local failed_containers=()
    
    # 检查关键容器
    local containers=(
        "network-probe-management-prod"
        "network-probe-postgres-prod"
        "network-probe-redis-prod"
        "network-probe-rabbitmq-prod"
    )
    
    for container in "${containers[@]}"; do
        if ! docker ps --format "table {{.Names}}" | grep -q "^$container$"; then
            failed_containers+=("$container")
        fi
    done
    
    if [ ${#failed_containers[@]} -gt 0 ]; then
        send_alert "CRITICAL" "容器停止运行: ${failed_containers[*]}"
        return 1
    fi
    
    return 0
}

# 检查服务健康状态
check_health() {
    local health_url="http://localhost:8000/health/detailed"
    local response
    
    response=$(curl -s -w "%{http_code}" "$health_url" 2>/dev/null || echo "000")
    local http_code="${response: -3}"
    local body="${response%???}"
    
    if [ "$http_code" != "200" ]; then
        send_alert "CRITICAL" "健康检查失败 (HTTP $http_code)"
        return 1
    fi
    
    # 检查响应时间
    local response_time
    response_time=$(curl -o /dev/null -s -w "%{time_total}" "$health_url" 2>/dev/null || echo "999")
    response_time_ms=$(echo "$response_time * 1000" | bc -l | cut -d. -f1)
    
    if [ "$response_time_ms" -gt "$RESPONSE_TIME_THRESHOLD" ]; then
        send_alert "WARNING" "响应时间过慢: ${response_time_ms}ms (阈值: ${RESPONSE_TIME_THRESHOLD}ms)"
    fi
    
    # 解析健康检查结果
    if command -v jq >/dev/null 2>&1; then
        local status
        status=$(echo "$body" | jq -r '.status' 2>/dev/null || echo "unknown")
        
        if [ "$status" != "healthy" ]; then
            local failed_checks
            failed_checks=$(echo "$body" | jq -r '.checks | to_entries[] | select(.value.status != "healthy") | .key' 2>/dev/null || echo "")
            
            if [ -n "$failed_checks" ]; then
                send_alert "CRITICAL" "服务组件异常: $failed_checks"
                return 1
            fi
        fi
    fi
    
    return 0
}

# 检查系统资源
check_system_resources() {
    # 检查CPU使用率
    local cpu_usage
    cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    cpu_usage=${cpu_usage%.*}
    
    if [ "$cpu_usage" -gt "$CPU_THRESHOLD" ]; then
        send_alert "WARNING" "CPU使用率过高: ${cpu_usage}% (阈值: ${CPU_THRESHOLD}%)"
    fi
    
    # 检查内存使用率
    local memory_usage
    memory_usage=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
    
    if [ "$memory_usage" -gt "$MEMORY_THRESHOLD" ]; then
        send_alert "WARNING" "内存使用率过高: ${memory_usage}% (阈值: ${MEMORY_THRESHOLD}%)"
    fi
    
    # 检查磁盘使用率
    local disk_usage
    disk_usage=$(df / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
    
    if [ "$disk_usage" -gt "$DISK_THRESHOLD" ]; then
        send_alert "WARNING" "磁盘使用率过高: ${disk_usage}% (阈值: ${DISK_THRESHOLD}%)"
    fi
}

# 检查数据库连接
check_database() {
    if ! docker exec network-probe-postgres-prod pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
        send_alert "CRITICAL" "数据库连接失败"
        return 1
    fi
    
    # 检查数据库连接数
    local connections
    connections=$(docker exec network-probe-postgres-prod psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | xargs)
    
    if [ "$connections" -gt 150 ]; then
        send_alert "WARNING" "数据库连接数过多: $connections"
    fi
    
    return 0
}

# 检查Redis状态
check_redis() {
    if ! docker exec network-probe-redis-prod redis-cli ping >/dev/null 2>&1; then
        send_alert "CRITICAL" "Redis连接失败"
        return 1
    fi
    
    # 检查Redis内存使用
    local redis_memory
    redis_memory=$(docker exec network-probe-redis-prod redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    
    log "Redis内存使用: $redis_memory"
    
    return 0
}

# 检查RabbitMQ状态
check_rabbitmq() {
    if ! docker exec network-probe-rabbitmq-prod rabbitmq-diagnostics ping >/dev/null 2>&1; then
        send_alert "CRITICAL" "RabbitMQ连接失败"
        return 1
    fi
    
    # 检查队列长度
    local queue_length
    queue_length=$(docker exec network-probe-rabbitmq-prod rabbitmqctl list_queues -p "${RABBITMQ_VHOST}" 2>/dev/null | awk '{sum += $2} END {print sum+0}')
    
    if [ "$queue_length" -gt 1000 ]; then
        send_alert "WARNING" "消息队列积压: $queue_length 条消息"
    fi
    
    return 0
}

# 检查SSL证书过期
check_ssl_certificates() {
    local cert_file="/opt/network-probe-platform/certs/fullchain.pem"
    
    if [ -f "$cert_file" ]; then
        local expiry_date
        expiry_date=$(openssl x509 -enddate -noout -in "$cert_file" | cut -d= -f2)
        local expiry_timestamp
        expiry_timestamp=$(date -d "$expiry_date" +%s)
        local current_timestamp
        current_timestamp=$(date +%s)
        local days_until_expiry
        days_until_expiry=$(( (expiry_timestamp - current_timestamp) / 86400 ))
        
        if [ "$days_until_expiry" -lt 30 ]; then
            send_alert "WARNING" "SSL证书即将过期: $days_until_expiry 天后过期"
        elif [ "$days_until_expiry" -lt 7 ]; then
            send_alert "CRITICAL" "SSL证书即将过期: $days_until_expiry 天后过期"
        fi
    fi
}

# 检查日志错误
check_logs() {
    local error_count
    error_count=$(docker logs network-probe-management-prod --since="5m" 2>&1 | grep -i error | wc -l)
    
    if [ "$error_count" -gt 10 ]; then
        send_alert "WARNING" "应用日志中发现大量错误: $error_count 条错误"
    fi
}

# 生成监控报告
generate_report() {
    local report_file="/tmp/network-probe-monitor-report.txt"
    
    {
        echo "网络拨测平台监控报告"
        echo "生成时间: $(date)"
        echo "=========================="
        echo ""
        
        echo "容器状态:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep network-probe
        echo ""
        
        echo "系统资源:"
        echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')"
        echo "内存: $(free -h | grep Mem | awk '{print $3"/"$2}')"
        echo "磁盘: $(df -h / | tail -1 | awk '{print $3"/"$2" ("$5")"}')"
        echo ""
        
        echo "服务健康状态:"
        curl -s http://localhost:8000/health/detailed | jq '.' 2>/dev/null || echo "无法获取健康状态"
        
    } > "$report_file"
    
    echo "$report_file"
}

# 主监控循环
monitor_loop() {
    log "开始监控网络拨测平台..."
    
    while true; do
        local all_checks_passed=true
        
        # 执行各项检查
        check_containers || all_checks_passed=false
        check_health || all_checks_passed=false
        check_system_resources
        check_database || all_checks_passed=false
        check_redis || all_checks_passed=false
        check_rabbitmq || all_checks_passed=false
        check_ssl_certificates
        check_logs
        
        if [ "$all_checks_passed" = true ]; then
            log "所有检查通过"
        fi
        
        sleep "$CHECK_INTERVAL"
    done
}

# 一次性检查
run_once() {
    log "执行一次性监控检查..."
    
    check_containers
    check_health
    check_system_resources
    check_database
    check_redis
    check_rabbitmq
    check_ssl_certificates
    check_logs
    
    local report_file
    report_file=$(generate_report)
    log "监控报告已生成: $report_file"
}

# 主函数
main() {
    case "${1:-loop}" in
        "loop")
            monitor_loop
            ;;
        "once")
            run_once
            ;;
        "report")
            generate_report
            ;;
        *)
            echo "用法: $0 [loop|once|report]"
            echo "  loop   - 持续监控 (默认)"
            echo "  once   - 执行一次检查"
            echo "  report - 生成监控报告"
            exit 1
            ;;
    esac
}

# 创建日志目录
mkdir -p "$(dirname "$LOG_FILE")"

# 执行主函数
main "$@"