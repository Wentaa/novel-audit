#!/bin/bash

# Novel Content Audit System - Production Deployment Script
# This script automates the deployment process for production environments

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
BACKUP_DIR="backups"
LOG_FILE="logs/deployment.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

# Help function
show_help() {
    cat << EOF
Novel Content Audit System - Deployment Script

Usage: $0 [OPTIONS] COMMAND

Commands:
    deploy      Deploy the system to production
    update      Update an existing deployment
    rollback    Rollback to previous version
    status      Show deployment status
    logs        Show application logs
    backup      Create system backup
    restore     Restore from backup
    test        Run deployment tests

Options:
    -e, --env FILE         Environment file (default: .env.prod)
    -f, --force           Force deployment without confirmation
    -v, --verbose         Enable verbose output
    -h, --help            Show this help message

Examples:
    $0 deploy                    # Deploy with default settings
    $0 update --force           # Force update without confirmation
    $0 rollback                 # Rollback to previous version
    $0 status                   # Check deployment status

EOF
}

# Pre-deployment checks
pre_deployment_checks() {
    log "Running pre-deployment checks..."

    # Check if Docker is running
    if ! docker info &>/dev/null; then
        error "Docker is not running. Please start Docker and try again."
    fi

    # Check if docker-compose is available
    if ! command -v docker-compose &>/dev/null; then
        error "docker-compose is not installed. Please install docker-compose."
    fi

    # Check if required files exist
    if [[ ! -f "$PROJECT_ROOT/$COMPOSE_FILE" ]]; then
        error "Docker compose file not found: $COMPOSE_FILE"
    fi

    if [[ ! -f "$PROJECT_ROOT/$ENV_FILE" ]]; then
        warning "Environment file not found: $ENV_FILE. Using defaults."
    fi

    # Check available disk space
    AVAILABLE_SPACE=$(df "$PROJECT_ROOT" | awk 'NR==2 {print $4}')
    if [[ $AVAILABLE_SPACE -lt 2097152 ]]; then  # 2GB in KB
        warning "Less than 2GB disk space available. Deployment may fail."
    fi

    # Check required environment variables
    if [[ -f "$PROJECT_ROOT/$ENV_FILE" ]]; then
        source "$PROJECT_ROOT/$ENV_FILE"

        if [[ -z "${OPENAI_API_KEY:-}" ]]; then
            error "OPENAI_API_KEY is not set in environment file."
        fi

        if [[ -z "${SECRET_KEY:-}" ]]; then
            error "SECRET_KEY is not set in environment file."
        fi
    fi

    success "Pre-deployment checks passed."
}

# Create backup
create_backup() {
    log "Creating backup before deployment..."

    local backup_timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_path="$PROJECT_ROOT/$BACKUP_DIR/backup_$backup_timestamp"

    mkdir -p "$backup_path"

    # Backup data directories
    if [[ -d "$PROJECT_ROOT/data" ]]; then
        log "Backing up data directory..."
        cp -r "$PROJECT_ROOT/data" "$backup_path/"
    fi

    # Backup configuration files
    log "Backing up configuration files..."
    cp "$PROJECT_ROOT/$ENV_FILE" "$backup_path/" 2>/dev/null || true
    cp "$PROJECT_ROOT/$COMPOSE_FILE" "$backup_path/"

    # Create backup manifest
    cat > "$backup_path/manifest.json" << EOF
{
    "backup_timestamp": "$backup_timestamp",
    "project_version": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "backup_type": "pre_deployment",
    "backup_path": "$backup_path"
}
EOF

    # Compress backup
    log "Compressing backup..."
    tar -czf "$backup_path.tar.gz" -C "$PROJECT_ROOT/$BACKUP_DIR" "backup_$backup_timestamp"
    rm -rf "$backup_path"

    success "Backup created: backup_$backup_timestamp.tar.gz"
    echo "$backup_timestamp" > "$PROJECT_ROOT/.last_backup"
}

# Deploy function
deploy() {
    log "Starting deployment process..."

    pre_deployment_checks
    create_backup

    # Pull latest images
    log "Pulling latest Docker images..."
    cd "$PROJECT_ROOT"
    docker-compose -f "$COMPOSE_FILE" pull

    # Build custom images
    log "Building custom images..."
    docker-compose -f "$COMPOSE_FILE" build

    # Create necessary directories
    log "Creating necessary directories..."
    mkdir -p data/{chroma,redis,elasticsearch,grafana,prometheus} logs backups

    # Set proper permissions
    log "Setting directory permissions..."
    chmod -R 755 data logs backups
    chown -R 1000:1000 data/elasticsearch 2>/dev/null || true
    chown -R 472:472 data/grafana 2>/dev/null || true

    # Start services
    log "Starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d

    # Wait for services to be healthy
    log "Waiting for services to become healthy..."
    local max_attempts=60
    local attempt=1

    while [[ $attempt -le $max_attempts ]]; do
        if docker-compose -f "$COMPOSE_FILE" ps | grep -q "unhealthy"; then
            log "Some services are still starting... (attempt $attempt/$max_attempts)"
            sleep 5
            ((attempt++))
        else
            break
        fi
    done

    if [[ $attempt -gt $max_attempts ]]; then
        error "Services failed to become healthy within timeout period."
    fi

    # Populate training data if needed
    log "Checking if training data population is needed..."
    if ! curl -s -f "http://localhost:8000/api/v1/monitoring/performance" &>/dev/null; then
        log "Populating initial training data..."
        sleep 10  # Wait a bit more for API to be ready
        curl -X POST "http://localhost:8000/api/v1/training/populate?case_count=50" \
             -H "Content-Type: application/json" || warning "Failed to populate training data"
    fi

    # Run deployment tests
    run_deployment_tests

    success "Deployment completed successfully!"
    show_deployment_status
}

# Update function
update() {
    log "Starting update process..."

    if [[ -z "${FORCE:-}" ]]; then
        echo -n "Are you sure you want to update the deployment? (y/N): "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log "Update cancelled by user."
            exit 0
        fi
    fi

    create_backup

    log "Pulling latest images..."
    cd "$PROJECT_ROOT"
    docker-compose -f "$COMPOSE_FILE" pull

    log "Rebuilding services..."
    docker-compose -f "$COMPOSE_FILE" build

    log "Restarting services with zero downtime..."
    docker-compose -f "$COMPOSE_FILE" up -d --no-deps --build

    # Wait for health checks
    sleep 30

    run_deployment_tests

    success "Update completed successfully!"
}

# Rollback function
rollback() {
    log "Starting rollback process..."

    if [[ ! -f "$PROJECT_ROOT/.last_backup" ]]; then
        error "No backup found for rollback. Cannot proceed."
    fi

    local last_backup=$(cat "$PROJECT_ROOT/.last_backup")
    local backup_file="$PROJECT_ROOT/$BACKUP_DIR/backup_${last_backup}.tar.gz"

    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
    fi

    echo -n "Are you sure you want to rollback to backup from $last_backup? (y/N): "
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Rollback cancelled by user."
        exit 0
    fi

    log "Stopping current services..."
    docker-compose -f "$COMPOSE_FILE" down

    log "Restoring from backup..."
    cd "$PROJECT_ROOT"
    tar -xzf "$backup_file" -C "$BACKUP_DIR"

    # Restore data directory
    if [[ -d "$BACKUP_DIR/backup_${last_backup}/data" ]]; then
        rm -rf data
        mv "$BACKUP_DIR/backup_${last_backup}/data" .
    fi

    # Restore configuration
    if [[ -f "$BACKUP_DIR/backup_${last_backup}/$ENV_FILE" ]]; then
        cp "$BACKUP_DIR/backup_${last_backup}/$ENV_FILE" .
    fi

    log "Starting services after rollback..."
    docker-compose -f "$COMPOSE_FILE" up -d

    success "Rollback completed successfully!"
    cleanup_temp_files
}

# Status function
show_deployment_status() {
    log "Checking deployment status..."

    cd "$PROJECT_ROOT"

    echo -e "\n${BLUE}=== Service Status ===${NC}"
    docker-compose -f "$COMPOSE_FILE" ps

    echo -e "\n${BLUE}=== Health Checks ===${NC}"

    # API Health
    if curl -s -f "http://localhost:8000/health" &>/dev/null; then
        success "✓ API is healthy"
    else
        error "✗ API is not responding"
    fi

    # ChromaDB Health
    if curl -s -f "http://localhost:8001/api/v1/heartbeat" &>/dev/null; then
        success "✓ ChromaDB is healthy"
    else
        warning "✗ ChromaDB is not responding"
    fi

    # Redis Health
    if docker exec novel-audit-redis redis-cli ping &>/dev/null; then
        success "✓ Redis is healthy"
    else
        warning "✗ Redis is not responding"
    fi

    echo -e "\n${BLUE}=== Resource Usage ===${NC}"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        novel-audit-api novel-audit-chromadb novel-audit-redis novel-audit-nginx 2>/dev/null || true

    echo -e "\n${BLUE}=== Recent Logs (last 10 lines) ===${NC}"
    docker-compose -f "$COMPOSE_FILE" logs --tail=10 novel-audit-api
}

# Show logs
show_logs() {
    local service="${1:-novel-audit-api}"
    local lines="${2:-100}"

    cd "$PROJECT_ROOT"
    docker-compose -f "$COMPOSE_FILE" logs --tail="$lines" -f "$service"
}

# Run deployment tests
run_deployment_tests() {
    log "Running deployment tests..."

    # API connectivity test
    log "Testing API connectivity..."
    local api_response
    api_response=$(curl -s -w "%{http_code}" -o /dev/null "http://localhost:8000/health" || echo "000")

    if [[ "$api_response" == "200" ]]; then
        success "✓ API connectivity test passed"
    else
        error "✗ API connectivity test failed (HTTP $api_response)"
    fi

    # Basic audit test
    log "Testing basic audit functionality..."
    local audit_response
    audit_response=$(curl -s -X POST "http://localhost:8000/api/v1/audit" \
        -H "Content-Type: application/json" \
        -d '{"content":"这是一个测试内容"}' \
        -w "%{http_code}" -o /dev/null || echo "000")

    if [[ "$audit_response" == "200" ]]; then
        success "✓ Basic audit test passed"
    else
        warning "✗ Basic audit test failed (HTTP $audit_response)"
    fi

    success "Deployment tests completed"
}

# Cleanup temporary files
cleanup_temp_files() {
    log "Cleaning up temporary files..."
    find "$PROJECT_ROOT/$BACKUP_DIR" -name "backup_*" -type d -exec rm -rf {} + 2>/dev/null || true
}

# Main execution
main() {
    local command=""
    local env_file=".env.prod"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--env)
                env_file="$2"
                shift 2
                ;;
            -f|--force)
                FORCE=1
                shift
                ;;
            -v|--verbose)
                set -x
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            deploy|update|rollback|status|logs|backup|restore|test)
                command="$1"
                shift
                break
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done

    if [[ -z "$command" ]]; then
        show_help
        exit 1
    fi

    # Set global variables
    ENV_FILE="$env_file"

    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"

    # Execute command
    case "$command" in
        deploy)
            deploy
            ;;
        update)
            update
            ;;
        rollback)
            rollback
            ;;
        status)
            show_deployment_status
            ;;
        logs)
            show_logs "$@"
            ;;
        backup)
            create_backup
            ;;
        test)
            run_deployment_tests
            ;;
        *)
            error "Unknown command: $command"
            ;;
    esac
}

# Run main function with all arguments
main "$@"