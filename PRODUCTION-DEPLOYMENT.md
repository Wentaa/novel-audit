# Novel Content Intelligent Audit System - Production Deployment Guide

## Overview

This guide covers the complete production deployment process for the Novel Content Intelligent Audit System, including prerequisites, deployment steps, monitoring, and troubleshooting.

## Table of Contents

- [System Architecture](#system-architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Deployment](#detailed-deployment)
- [Security Configuration](#security-configuration)
- [Monitoring and Alerting](#monitoring-and-alerting)
- [Backup and Recovery](#backup-and-recovery)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Nginx       │    │   Novel Audit   │    │    ChromaDB     │
│ (Load Balancer) │────│      API        │────│ (Vector Store)  │
│    Port 80/443  │    │    Port 8000    │    │    Port 8001    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │      Redis      │              │
         │              │   (Caching)     │              │
         │              │   Port 6379     │              │
         │              └─────────────────┘              │
         │                                               │
┌─────────────────────────────────────────────────────────────────┐
│                    Monitoring Stack                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Prometheus    │     Grafana     │      ELK Stack              │
│   Port 9090     │   Port 3000     │  (Elasticsearch, Kibana)    │
│   (Metrics)     │  (Dashboards)   │       Ports 9200, 5601     │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## Prerequisites

### System Requirements

**Minimum Requirements:**
- CPU: 4 cores
- RAM: 8GB
- Storage: 50GB SSD
- Network: 100 Mbps

**Recommended for Production:**
- CPU: 8 cores
- RAM: 16GB
- Storage: 200GB SSD
- Network: 1 Gbps

### Software Dependencies

- **Docker**: 20.10.0+
- **Docker Compose**: 2.0.0+
- **OpenSSL**: For SSL certificate generation
- **Git**: For code management
- **curl**: For health checks

### External Services

- **OpenAI API**: GPT-4 access required
- **Domain/SSL**: Valid SSL certificates for production
- **Backup Storage**: AWS S3 or similar (optional)

## Quick Start

### 1. Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd novel-audit

# Setup security and environment
chmod +x scripts/setup-security.sh
./scripts/setup-security.sh

# Edit environment file
vi .env.prod
```

### 2. Configure Environment

Edit `.env.prod` with your settings:

```bash
# Required settings
OPENAI_API_KEY=sk-your-openai-api-key
SECRET_KEY=<generated-secure-key>
CORS_ORIGINS=https://yourdomain.com
ALLOWED_HOSTS=yourdomain.com,api.yourdomain.com
```

### 3. Deploy

```bash
# Deploy with automation script
chmod +x scripts/deploy.sh
./scripts/deploy.sh deploy
```

### 4. Verify Deployment

```bash
# Check system health
./scripts/health-check.py --url http://localhost

# Check services
docker-compose -f docker-compose.prod.yml ps
```

## Detailed Deployment

### Step 1: Environment Preparation

1. **Server Preparation**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y

   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   sudo usermod -aG docker $USER

   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. **Firewall Configuration**
   ```bash
   # Configure UFW
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow 80/tcp    # HTTP
   sudo ufw allow 443/tcp   # HTTPS
   sudo ufw enable
   ```

### Step 2: SSL Certificate Setup

**For Production (Let's Encrypt):**
```bash
# Install Certbot
sudo apt install certbot

# Generate certificates
sudo certbot certonly --standalone -d yourdomain.com -d api.yourdomain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem docker/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem docker/nginx/ssl/key.pem
sudo chown $USER:$USER docker/nginx/ssl/*.pem
```

**For Development (Self-signed):**
```bash
# Use the setup script
./scripts/setup-security.sh --ssl-only
```

### Step 3: Configuration Management

1. **Environment Configuration**
   ```bash
   # Copy template
   cp .env.prod.template .env.prod

   # Generate secure keys
   openssl rand -base64 64 | tr -d "=+/" | cut -c1-64

   # Edit configuration
   vi .env.prod
   ```

2. **Service Configuration**
   - Update `docker/nginx/nginx.conf` for your domain
   - Configure monitoring in `docker/prometheus/prometheus.yml`
   - Set up log rotation in `docker/filebeat/filebeat.yml`

### Step 4: Deployment Execution

```bash
# Pre-deployment checks
./scripts/deploy.sh status

# Create backup
./scripts/deploy.sh backup

# Deploy with monitoring
./scripts/deploy.sh deploy --verbose

# Verify deployment
./scripts/health-check.py --continuous
```

### Step 5: Post-Deployment Configuration

1. **Initialize Training Data**
   ```bash
   curl -X POST "https://api.yourdomain.com/api/v1/training/populate?case_count=200" \
        -H "X-API-Key: your-api-key"
   ```

2. **Configure Monitoring**
   - Access Grafana: `https://monitoring.yourdomain.com/grafana/`
   - Import dashboards from `docker/grafana/dashboards/`
   - Set up alerting rules

3. **Test System Functionality**
   ```bash
   # Test audit endpoint
   curl -X POST "https://api.yourdomain.com/api/v1/audit" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your-api-key" \
        -d '{"content":"测试内容"}'
   ```

## Security Configuration

### SSL/TLS Configuration

1. **Certificate Management**
   ```bash
   # Auto-renewal setup for Let's Encrypt
   echo "0 12 * * * /usr/bin/certbot renew --quiet" | sudo crontab -
   ```

2. **Security Headers**
   - HSTS enforcement
   - Content Security Policy
   - X-Frame-Options
   - X-Content-Type-Options

### API Security

1. **API Key Management**
   ```bash
   # Generate API keys
   openssl rand -base64 32

   # Add to environment
   API_KEYS=key1,key2,key3
   ```

2. **Rate Limiting**
   - 60 requests/minute per IP
   - Burst allowance: 10 requests
   - Upload endpoints: 2 requests/second

### Container Security

1. **Security Options**
   - Non-root users
   - Read-only filesystems
   - Capability dropping
   - Seccomp profiles

2. **Network Security**
   - Bridge networking
   - Internal service communication
   - Firewall rules

## Monitoring and Alerting

### Metrics Collection

**Prometheus Metrics:**
- HTTP request metrics
- Processing time metrics
- System resource metrics
- Custom application metrics

**Key Metrics to Monitor:**
- Response time (95th percentile < 500ms)
- Error rate (< 1%)
- CPU usage (< 80%)
- Memory usage (< 85%)
- Disk usage (< 90%)

### Alerting Rules

**Critical Alerts:**
- API Down (1 minute)
- High Error Rate (> 10% for 5 minutes)
- Database Connection Failed
- Disk Space Low (< 10%)

**Warning Alerts:**
- High Response Time (> 500ms for 5 minutes)
- High CPU Usage (> 80% for 5 minutes)
- High Memory Usage (> 85% for 5 minutes)
- Too Many Pending Reviews (> 1000)

### Dashboards

1. **System Overview**
   - Service status
   - Resource utilization
   - Request volume
   - Error rates

2. **Application Metrics**
   - Audit processing times
   - Confidence score distribution
   - Workflow path analysis
   - Human review queue status

3. **Infrastructure Metrics**
   - Server resources
   - Docker container stats
   - Network metrics
   - Database performance

## Backup and Recovery

### Automated Backups

```bash
# Daily backup at 2 AM
BACKUP_SCHEDULE="0 2 * * *"

# Backup includes:
# - Application data
# - Database files
# - Configuration files
# - SSL certificates
```

### Backup Verification

```bash
# Test backup integrity
./scripts/deploy.sh test-backup <backup_name>

# Restore from backup
./scripts/deploy.sh restore <backup_name>
```

### Disaster Recovery

1. **Recovery Time Objective (RTO):** 30 minutes
2. **Recovery Point Objective (RPO):** 24 hours
3. **Backup Retention:** 30 days
4. **Off-site Storage:** S3 compatible

## Troubleshooting

### Common Issues

#### 1. Service Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs <service_name>

# Check resource usage
docker stats

# Check disk space
df -h
```

#### 2. High Response Times

```bash
# Check API metrics
curl -s http://localhost:8000/api/v1/monitoring/performance

# Check system resources
htop

# Check database connections
docker exec novel-audit-redis redis-cli info
```

#### 3. Authentication Issues

```bash
# Verify API keys
grep API_KEYS .env.prod

# Check security logs
docker-compose -f docker-compose.prod.yml logs nginx | grep 401
```

#### 4. SSL Certificate Issues

```bash
# Check certificate validity
openssl x509 -in docker/nginx/ssl/cert.pem -text -noout

# Verify certificate chain
curl -I https://yourdomain.com
```

### Performance Optimization

#### 1. Database Optimization

```bash
# Monitor ChromaDB performance
curl http://localhost:8001/api/v1/heartbeat

# Check Redis memory usage
docker exec novel-audit-redis redis-cli info memory
```

#### 2. Application Tuning

```bash
# Increase worker processes
API_WORKERS=8

# Adjust timeout settings
API_TIMEOUT=180

# Tune concurrent processing
MAX_CONCURRENT_AUDITS=20
```

#### 3. Resource Scaling

```yaml
# Docker resource limits
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 8G
```

### Log Analysis

#### 1. Application Logs

```bash
# View real-time logs
docker-compose -f docker-compose.prod.yml logs -f novel-audit-api

# Search for errors
docker-compose -f docker-compose.prod.yml logs novel-audit-api | grep ERROR

# Export logs
docker-compose -f docker-compose.prod.yml logs --no-color novel-audit-api > app.log
```

#### 2. Access Logs

```bash
# Nginx access patterns
docker-compose -f docker-compose.prod.yml logs nginx | grep "POST /api/v1/audit"

# Error analysis
docker-compose -f docker-compose.prod.yml logs nginx | grep " 5[0-9][0-9] "
```

#### 3. System Logs

```bash
# System resource usage
dmesg | tail -50

# Docker daemon logs
sudo journalctl -u docker.service --since "1 hour ago"
```

## Maintenance

### Regular Maintenance Tasks

#### Daily
- [ ] Monitor system health dashboard
- [ ] Check error logs for anomalies
- [ ] Verify backup completion
- [ ] Review security alerts

#### Weekly
- [ ] Update system packages
- [ ] Review performance metrics
- [ ] Clean up old log files
- [ ] Test backup restoration

#### Monthly
- [ ] Update Docker images
- [ ] Security audit
- [ ] Performance tuning review
- [ ] Documentation updates

### Update Process

```bash
# 1. Backup current state
./scripts/deploy.sh backup

# 2. Update code
git pull origin main

# 3. Update deployment
./scripts/deploy.sh update

# 4. Verify functionality
./scripts/health-check.py --url https://api.yourdomain.com
```

### Scaling Considerations

#### Horizontal Scaling

```yaml
# Load balancer configuration
nginx:
  deploy:
    replicas: 2

novel-audit-api:
  deploy:
    replicas: 4
```

#### Vertical Scaling

```yaml
# Resource allocation
novel-audit-api:
  deploy:
    resources:
      limits:
        cpus: '8.0'
        memory: 16G
```

## Support and Contact

For technical support:
- **Documentation**: See `docs/` directory
- **Issues**: Create GitHub issue
- **Emergency**: Contact system administrator

---

**Last Updated**: 2024-01-01
**Version**: 1.0.0