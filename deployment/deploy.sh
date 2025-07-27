#!/bin/bash

# Deployment script for network probe platform
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[DEPLOY]${NC} $1"
}

# Default values
ENVIRONMENT="production"
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
BUILD=false
PULL=false
PROFILES=""

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --environment ENV     Environment (production|development) [default: production]"
    echo "  -f, --file FILE          Docker compose file [default: docker-compose.yml]"
    echo "  --env-file FILE          Environment file [default: .env]"
    echo "  -b, --build              Build images before deploying"
    echo "  -p, --pull               Pull latest images before deploying"
    echo "  --profile PROFILE        Enable specific profiles (nginx,dev-tools)"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                       Deploy production environment"
    echo "  $0 -e development        Deploy development environment"
    echo "  $0 -b --profile nginx    Build and deploy with nginx"
    echo "  $0 -e development --profile dev-tools  Deploy dev with admin tools"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -f|--file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        -b|--build)
            BUILD=true
            shift
            ;;
        -p|--pull)
            PULL=true
            shift
            ;;
        --profile)
            PROFILES="$PROFILES --profile $2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Set compose files based on environment
if [[ "$ENVIRONMENT" == "development" ]]; then
    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.dev.yml"
    ENV_FILE="${ENV_FILE:-".env.dev"}"
else
    COMPOSE_FILES="-f docker-compose.yml"
    ENV_FILE="${ENV_FILE:-".env"}"
fi

print_header "Network Probe Platform Deployment"
print_status "Environment: $ENVIRONMENT"
print_status "Compose files: $COMPOSE_FILES"
print_status "Environment file: $ENV_FILE"
print_status "Profiles: ${PROFILES:-"(none)"}"

# Check if environment file exists
if [[ ! -f "$ENV_FILE" ]]; then
    print_warning "Environment file $ENV_FILE not found"
    if [[ -f ".env.example" ]]; then
        print_status "Copying .env.example to $ENV_FILE"
        cp .env.example "$ENV_FILE"
        print_warning "Please edit $ENV_FILE with your configuration before continuing"
        exit 1
    else
        print_error "No environment file found. Please create $ENV_FILE"
        exit 1
    fi
fi

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# Pre-deployment checks
print_status "Running pre-deployment checks..."

# Check Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed"
    exit 1
fi

# Use docker compose or docker-compose based on availability
DOCKER_COMPOSE_CMD="docker-compose"
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
fi

print_status "Using: $DOCKER_COMPOSE_CMD"

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p ../certs ../logs

# Pull images if requested
if [[ "$PULL" == true ]]; then
    print_status "Pulling latest images..."
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES pull
fi

# Build images if requested
if [[ "$BUILD" == true ]]; then
    print_status "Building images..."
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES build
fi

# Stop existing services
print_status "Stopping existing services..."
$DOCKER_COMPOSE_CMD $COMPOSE_FILES down

# Start services
print_status "Starting services..."
$DOCKER_COMPOSE_CMD $COMPOSE_FILES up -d $PROFILES

# Wait for services to be healthy
print_status "Waiting for services to be healthy..."
sleep 10

# Check service status
print_status "Checking service status..."
$DOCKER_COMPOSE_CMD $COMPOSE_FILES ps

# Run database migrations for production
if [[ "$ENVIRONMENT" == "production" ]]; then
    print_status "Running database migrations..."
    $DOCKER_COMPOSE_CMD $COMPOSE_FILES exec -T management alembic upgrade head
    
    # Run health checks
    print_status "Running health checks..."
    sleep 30
    
    # Check management platform health
    if curl -f http://localhost:${MANAGEMENT_PORT:-8000}/health > /dev/null 2>&1; then
        print_status "Management platform is healthy"
    else
        print_error "Management platform health check failed"
        print_status "Checking logs..."
        $DOCKER_COMPOSE_CMD $COMPOSE_FILES logs management
        exit 1
    fi
    
    # Check database connectivity
    if $DOCKER_COMPOSE_CMD $COMPOSE_FILES exec -T postgres pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB} > /dev/null 2>&1; then
        print_status "Database is healthy"
    else
        print_error "Database health check failed"
        exit 1
    fi
    
    # Check Redis connectivity
    if $DOCKER_COMPOSE_CMD $COMPOSE_FILES exec -T redis redis-cli ping > /dev/null 2>&1; then
        print_status "Redis is healthy"
    else
        print_error "Redis health check failed"
        exit 1
    fi
    
    # Setup backup cron job
    print_status "Setting up backup cron job..."
    if [[ "${BACKUP_ENABLED:-false}" == "true" ]]; then
        # Add backup cron job
        (crontab -l 2>/dev/null; echo "${BACKUP_SCHEDULE:-0 2 * * *} /opt/network-probe-platform/scripts/backup.sh") | crontab -
        print_status "Backup cron job configured"
    fi
    
    # Setup log rotation
    print_status "Setting up log rotation..."
    cat > /etc/logrotate.d/network-probe-platform << EOF
/opt/network-probe-platform/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        docker kill --signal="USR1" network-probe-management-prod 2>/dev/null || true
    endscript
}
EOF
fi

print_header "Deployment completed successfully!"
print_status "Services are running. Check logs with:"
print_status "  $DOCKER_COMPOSE_CMD $COMPOSE_FILES logs -f"
print_status ""
print_status "Access the application at:"
if [[ "$PROFILES" == *"nginx"* ]]; then
    print_status "  http://localhost:${HTTP_PORT:-80}"
    if [[ -n "${HTTPS_PORT}" ]]; then
        print_status "  https://localhost:${HTTPS_PORT}"
    fi
else
    print_status "  http://localhost:${MANAGEMENT_PORT:-8000}"
fi

if [[ "$ENVIRONMENT" == "development" && "$PROFILES" == *"dev-tools"* ]]; then
    print_status ""
    print_status "Development tools:"
    print_status "  PgAdmin: http://localhost:5050 (admin@example.com / admin)"
    print_status "  Redis Commander: http://localhost:8081"
    print_status "  RabbitMQ Management: http://localhost:15672 (${RABBITMQ_USER:-admin} / ${RABBITMQ_PASSWORD:-admin})"
fi