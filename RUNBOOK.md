# Novel Content Audit System - Operations Runbook

## Table of Contents

1. [Emergency Procedures](#emergency-procedures)
2. [Service Management](#service-management)
3. [Monitoring and Alerts](#monitoring-and-alerts)
4. [Common Issues](#common-issues)
5. [Maintenance Procedures](#maintenance-procedures)
6. [Security Incidents](#security-incidents)
7. [Performance Troubleshooting](#performance-troubleshooting)
8. [Data Management](#data-management)

## Emergency Procedures

### 🚨 System Down - Complete Outage

**Immediate Actions (0-5 minutes):**

1. **Check System Status**
   ```bash
   # Quick health check
   curl -f http://localhost:8000/health

   # Check all services
   docker-compose -f docker-compose.prod.yml ps
   ```

2. **Identify Failed Services**
   ```bash
   # Check for unhealthy containers
   docker ps --filter "health=unhealthy"

   # Check recent logs
   docker-compose -f docker-compose.prod.yml logs --tail=50 --timestamps
   ```

3. **Attempt Quick Recovery**
   ```bash
   # Restart failed services
   docker-compose -f docker-compose.prod.yml restart <service_name>

   # Or restart entire stack if multiple failures
   docker-compose -f docker-compose.prod.yml restart
   ```

**If Quick Recovery Fails (5-15 minutes):**

4. **Full System Restart**
   ```bash
   # Stop all services
   docker-compose -f docker-compose.prod.yml down

   # Start services in order
   docker-compose -f docker-compose.prod.yml up -d redis chromadb
   sleep 30
   docker-compose -f docker-compose.prod.yml up -d novel-audit-api
   sleep 30
   docker-compose -f docker-compose.prod.yml up -d nginx
   ```

5. **Verify Recovery**
   ```bash
   # Run health checks
   ./scripts/health-check.py --url http://localhost

   # Test core functionality
   curl -X POST http://localhost:8000/api/v1/audit \
        -H "Content-Type: application/json" \
        -d '{"content":"测试内容"}'
   ```

**If System Still Down (15+ minutes):**

6. **Rollback to Last Known Good State**
   ```bash
   ./scripts/deploy.sh rollback
   ```

7. **Contact Development Team**
   - Document the issue
   - Collect all relevant logs
   - Escalate to development team

### 🔥 High Error Rate Alert

**Response Procedure:**

1. **Check Error Pattern**
   ```bash
   # Check recent error logs
   docker-compose -f docker-compose.prod.yml logs novel-audit-api | grep ERROR | tail -20

   # Check Nginx error logs
   docker-compose -f docker-compose.prod.yml logs nginx | grep " 5[0-9][0-9] "
   ```

2. **Identify Root Cause**
   - Database connectivity issues
   - External API failures (OpenAI)
   - Resource exhaustion
   - Invalid requests

3. **Immediate Mitigation**
   ```bash
   # If OpenAI API issues
   # Check status at https://status.openai.com

   # If database issues
   docker-compose -f docker-compose.prod.yml restart redis chromadb

   # If resource issues
   docker stats  # Check resource usage
   ```

### 💥 Database Corruption

**Response Procedure:**

1. **Stop Application Services**
   ```bash
   docker-compose -f docker-compose.prod.yml stop novel-audit-api
   ```

2. **Assess Damage**
   ```bash
   # Check database files
   ls -la data/

   # Try to access databases
   docker exec novel-audit-redis redis-cli ping
   curl http://localhost:8001/api/v1/heartbeat
   ```

3. **Restore from Backup**
   ```bash
   # List available backups
   ls -la backups/

   # Restore latest backup
   ./scripts/deploy.sh restore <latest_backup>
   ```

## Service Management

### Starting Services

```bash
# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Start specific service
docker-compose -f docker-compose.prod.yml up -d novel-audit-api

# Start with dependencies
docker-compose -f docker-compose.prod.yml up -d --no-deps novel-audit-api
```

### Stopping Services

```bash
# Stop all services gracefully
docker-compose -f docker-compose.prod.yml down

# Stop specific service
docker-compose -f docker-compose.prod.yml stop novel-audit-api

# Force stop (emergency)
docker-compose -f docker-compose.prod.yml kill novel-audit-api
```

### Service Health Checks

```bash
# Check all services
docker-compose -f docker-compose.prod.yml ps

# Detailed health status
./scripts/health-check.py --url http://localhost

# Individual service health
curl -f http://localhost:8000/health                    # API
curl -f http://localhost:8001/api/v1/heartbeat         # ChromaDB
docker exec novel-audit-redis redis-cli ping           # Redis
curl -f http://localhost:9090/-/healthy                # Prometheus
```

### Scaling Services

```bash
# Scale API service
docker-compose -f docker-compose.prod.yml up -d --scale novel-audit-api=3

# Check scaled instances
docker ps | grep novel-audit-api
```

## Monitoring and Alerts

### Key Metrics Dashboard URLs

- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Kibana**: http://localhost:5601

### Critical Alerts and Response

#### API Down Alert

**Symptoms:**
- Health check endpoint returning 5xx or timeout
- No response from API service

**Response:**
1. Check if container is running: `docker ps | grep novel-audit-api`
2. Check logs: `docker-compose -f docker-compose.prod.yml logs novel-audit-api`
3. Restart service: `docker-compose -f docker-compose.prod.yml restart novel-audit-api`

#### High Response Time Alert

**Symptoms:**
- 95th percentile response time > 500ms for 5+ minutes

**Response:**
1. Check system resources: `docker stats`
2. Check for long-running requests:
   ```bash
   curl http://localhost:8000/api/v1/monitoring/performance
   ```
3. Scale API service if CPU/memory bound:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d --scale novel-audit-api=2
   ```

#### Database Connection Failed

**Symptoms:**
- Connection errors in application logs
- Database health checks failing

**Response:**
1. Check database containers:
   ```bash
   docker exec novel-audit-redis redis-cli ping
   curl http://localhost:8001/api/v1/heartbeat
   ```
2. Restart databases:
   ```bash
   docker-compose -f docker-compose.prod.yml restart redis chromadb
   ```
3. Check disk space: `df -h`

### Setting Up Alerts

#### Prometheus Alerting

```yaml
# Edit docker/prometheus/rules/novel-audit-alerts.yml
groups:
  - name: custom-alerts
    rules:
      - alert: CustomMetricHigh
        expr: custom_metric > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Custom metric is high"
```

#### External Alerting (Email/Slack)

```bash
# Configure Alertmanager
# Edit docker/prometheus/alertmanager.yml
```

## Common Issues

### Issue: "OpenAI API Rate Limited"

**Symptoms:**
- 429 errors in logs
- Audit requests failing with rate limit messages

**Diagnosis:**
```bash
grep "rate_limit" docker-compose -f docker-compose.prod.yml logs novel-audit-api
```

**Solution:**
1. Check OpenAI usage limits
2. Implement request queuing
3. Add retry logic with exponential backoff

### Issue: "ChromaDB Connection Timeout"

**Symptoms:**
- RAG analysis failing
- Vector similarity search errors

**Diagnosis:**
```bash
curl -w "%{time_total}s" http://localhost:8001/api/v1/heartbeat
docker-compose -f docker-compose.prod.yml logs chromadb
```

**Solution:**
```bash
# Restart ChromaDB
docker-compose -f docker-compose.prod.yml restart chromadb

# Check disk space for ChromaDB data
du -sh data/chroma/

# Clear old embeddings if disk full
# (Requires manual intervention)
```

### Issue: "High Memory Usage"

**Symptoms:**
- System becoming unresponsive
- OOMKilled containers

**Diagnosis:**
```bash
docker stats
free -h
cat /proc/meminfo
```

**Solution:**
```bash
# Immediate: Restart memory-hungry services
docker-compose -f docker-compose.prod.yml restart novel-audit-api

# Long-term: Adjust memory limits
# Edit docker-compose.prod.yml deploy.resources.limits
```

### Issue: "SSL Certificate Expired"

**Symptoms:**
- HTTPS requests failing
- Browser certificate warnings

**Diagnosis:**
```bash
openssl x509 -in docker/nginx/ssl/cert.pem -text -noout | grep "Not After"
```

**Solution:**
```bash
# Renew Let's Encrypt certificates
sudo certbot renew

# Copy new certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem docker/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem docker/nginx/ssl/key.pem

# Restart Nginx
docker-compose -f docker-compose.prod.yml restart nginx
```

## Maintenance Procedures

### Daily Maintenance Checklist

- [ ] **System Health Check**
  ```bash
  ./scripts/health-check.py --url http://localhost
  ```

- [ ] **Log Review**
  ```bash
  # Check for errors in last 24 hours
  docker-compose -f docker-compose.prod.yml logs --since="24h" | grep ERROR
  ```

- [ ] **Backup Verification**
  ```bash
  # Check if backup completed successfully
  ls -la backups/ | head -5
  ```

- [ ] **Resource Usage Check**
  ```bash
  df -h        # Disk usage
  free -h      # Memory usage
  docker stats # Container resources
  ```

### Weekly Maintenance

#### System Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker-compose -f docker-compose.prod.yml pull

# Restart services with new images
docker-compose -f docker-compose.prod.yml up -d
```

#### Log Rotation and Cleanup

```bash
# Clean up old Docker logs
sudo find /var/lib/docker/containers/ -name "*.log" -exec truncate -s 0 {} \;

# Rotate application logs
docker-compose -f docker-compose.prod.yml exec novel-audit-api logrotate /etc/logrotate.conf

# Clean up old backups (keep last 30 days)
find backups/ -name "backup_*.tar.gz" -mtime +30 -delete
```

#### Database Maintenance

```bash
# Optimize ChromaDB
# (This would require specific ChromaDB maintenance commands)

# Redis maintenance
docker exec novel-audit-redis redis-cli BGREWRITEAOF
```

### Monthly Maintenance

#### Security Updates

```bash
# Update base images
docker system prune -a

# Security scan
# (Use tools like docker scan or similar)

# SSL certificate check
openssl x509 -in docker/nginx/ssl/cert.pem -text -noout | grep "Not After"
```

#### Performance Review

```bash
# Generate performance report
curl http://localhost:8000/api/v1/monitoring/performance > monthly_perf_report.json

# Review slow queries and optimize
```

## Security Incidents

### Suspected Intrusion

**Immediate Actions:**

1. **Isolate System**
   ```bash
   # Block suspicious IPs at firewall level
   sudo ufw insert 1 deny from <suspicious_ip>

   # Check active connections
   netstat -an | grep ESTABLISHED
   ```

2. **Review Access Logs**
   ```bash
   # Check Nginx access logs for suspicious activity
   docker-compose -f docker-compose.prod.yml logs nginx | grep -E "(4[0-9]{2}|5[0-9]{2})"

   # Check authentication logs
   grep "authentication" /var/log/auth.log
   ```

3. **Preserve Evidence**
   ```bash
   # Create forensic backup
   ./scripts/deploy.sh backup --forensic

   # Collect system state
   ps aux > incident_processes.txt
   netstat -an > incident_network.txt
   ```

### API Key Compromise

**Response:**

1. **Revoke Compromised Keys**
   ```bash
   # Remove from environment file
   vi .env.prod

   # Restart API service
   docker-compose -f docker-compose.prod.yml restart novel-audit-api
   ```

2. **Generate New Keys**
   ```bash
   ./scripts/setup-security.sh --generate-keys
   ```

3. **Audit Usage**
   ```bash
   # Check for unauthorized usage
   grep "api_key" docker-compose -f docker-compose.prod.yml logs novel-audit-api
   ```

### DDoS Attack

**Response:**

1. **Implement Rate Limiting**
   ```bash
   # Edit Nginx configuration for stricter limits
   vi docker/nginx/nginx.conf

   # Restart Nginx
   docker-compose -f docker-compose.prod.yml restart nginx
   ```

2. **Block Attack Sources**
   ```bash
   # Use fail2ban or similar tools
   # Or manually block IPs
   sudo ufw deny from <attack_ip>
   ```

## Performance Troubleshooting

### Slow Response Times

**Investigation Steps:**

1. **Identify Bottleneck**
   ```bash
   # Check API performance metrics
   curl http://localhost:8000/api/v1/monitoring/performance

   # Check database performance
   docker stats | grep -E "(chromadb|redis)"

   # Check system resources
   htop
   ```

2. **Analyze Request Patterns**
   ```bash
   # Check most frequent endpoints
   docker-compose -f docker-compose.prod.yml logs nginx | grep "POST /api" | cut -d'"' -f2 | sort | uniq -c | sort -nr

   # Check response time distribution
   docker-compose -f docker-compose.prod.yml logs nginx | grep -o "rt=[0-9.]*" | cut -d'=' -f2 | sort -n
   ```

3. **Optimization Actions**
   ```bash
   # Scale API service
   docker-compose -f docker-compose.prod.yml up -d --scale novel-audit-api=3

   # Increase worker processes
   # Edit .env.prod: API_WORKERS=8

   # Optimize caching
   # Check Redis hit rate
   docker exec novel-audit-redis redis-cli info stats | grep hit
   ```

### High Resource Usage

**CPU Optimization:**

```bash
# Check CPU-intensive processes
docker stats --no-stream | sort -k3 -nr

# Limit CPU usage
# Edit docker-compose.prod.yml:
# deploy.resources.limits.cpus: '2.0'
```

**Memory Optimization:**

```bash
# Check memory usage by service
docker stats --no-stream | sort -k4 -nr

# Implement memory limits
# Edit docker-compose.prod.yml:
# deploy.resources.limits.memory: 4G
```

## Data Management

### Backup Procedures

**Manual Backup:**

```bash
# Create immediate backup
./scripts/deploy.sh backup

# Verify backup integrity
tar -tf backups/backup_<timestamp>.tar.gz
```

**Automated Backup Setup:**

```bash
# Setup cron job
echo "0 2 * * * cd /path/to/novel-audit && ./scripts/deploy.sh backup" | crontab -
```

### Data Recovery

**Partial Recovery:**

```bash
# Restore specific data directory
tar -xf backups/backup_<timestamp>.tar.gz data/chroma
docker-compose -f docker-compose.prod.yml restart chromadb
```

**Full System Recovery:**

```bash
# Stop all services
docker-compose -f docker-compose.prod.yml down

# Restore complete backup
./scripts/deploy.sh restore backup_<timestamp>

# Start services
docker-compose -f docker-compose.prod.yml up -d
```

### Data Migration

**Migrating to New Environment:**

```bash
# Export data
./scripts/deploy.sh backup --export

# Copy to new environment
scp backups/backup_<timestamp>.tar.gz user@newserver:/path/

# Import on new environment
./scripts/deploy.sh restore backup_<timestamp>
```

---

## Emergency Contacts

**System Administrator**: [Your contact info]
**Development Team**: [Team contact info]
**Security Team**: [Security contact info]

## Revision History

| Version | Date       | Changes                    |
|---------|------------|----------------------------|
| 1.0     | 2024-01-01 | Initial runbook creation   |

---

**Document Status**: Current
**Next Review Date**: 2024-04-01