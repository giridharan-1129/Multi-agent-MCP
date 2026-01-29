# Deployment Guide

Production deployment guide for the FastAPI Multi-Agent System.

## 🏢 Pre-Deployment Checklist

- [ ] All tests passing (`make test`)
- [ ] Code linted (`make lint`)
- [ ] Environment variables configured
- [ ] OpenAI API key active and tested
- [ ] Neo4j database configured
- [ ] Docker images built
- [ ] Security review completed
- [ ] Backup strategy in place
- [ ] Monitoring setup planned
- [ ] Rollback plan defined

## 🐳 Docker Deployment

### Build Production Images
```bash
# Build gateway image
docker build -f docker/Dockerfile.gateway -t multiagent-gateway:1.0.0 .

# Tag for registry
docker tag multiagent-gateway:1.0.0 your-registry/multiagent-gateway:1.0.0

# Push to registry
docker push your-registry/multiagent-gateway:1.0.0
```

### Deploy with Docker Compose
```bash
# Pull latest images
docker-compose pull

# Start services
docker-compose up -d

# Verify services
docker-compose ps

# Check logs
docker-compose logs -f gateway
```

## ☸️ Kubernetes Deployment

### Prerequisites

- kubectl configured
- Container registry access
- Persistent volumes available

### Sample Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: multiagent-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: multiagent-gateway
  template:
    metadata:
      labels:
        app: multiagent-gateway
    spec:
      containers:
      - name: gateway
        image: your-registry/multiagent-gateway:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: NEO4J_URI
          value: "bolt://neo4j-service:7687"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-credentials
              key: api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
```

## 🔒 Security Configuration

### Environment Variables
```bash
# .env.production
ENVIRONMENT=production
LOG_LEVEL=WARNING
LOG_FORMAT=json

# Neo4j
NEO4J_URI=bolt://neo4j.internal:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=$(openssl rand -base64 32)

# OpenAI
OPENAI_API_KEY=<your-key>

# Gateway
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
GATEWAY_RELOAD=false

# Security
SESSION_TIMEOUT_MINUTES=60
CONVERSATION_MEMORY_SIZE=100
```

### Secrets Management

Use your platform's secrets manager:
```bash
# Docker Secrets (Swarm)
echo "your-secret-value" | docker secret create openai_api_key -

# Kubernetes Secrets
kubectl create secret generic openai-credentials \
  --from-literal=api-key=your-api-key

# AWS Secrets Manager, Azure KeyVault, etc.
```

## 📊 Monitoring & Logging

### Health Checks
```bash
# Regular health checks
*/5 * * * * curl -f http://localhost:8000/health || alert

# Service status
curl http://localhost:8000/agents | jq '.agents[].status'
```

### Log Aggregation
```bash
# Collect logs (using ELK, Datadog, etc.)
docker logs gateway | jq '.correlation_id' | sort | uniq -c

# Monitor error rates
docker logs gateway | jq 'select(.level == "ERROR")' | wc -l
```

### Metrics to Track

- Request latency (p50, p95, p99)
- Agent response times
- Neo4j query performance
- Error rates by type
- Active sessions
- Memory usage
- CPU usage

## 🔄 Scaling Strategy

### Horizontal Scaling
```yaml
# Load balance multiple gateway instances
services:
  load_balancer:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf

  gateway_1:
    image: multiagent-gateway:1.0.0
    environment:
      - INSTANCE_ID=1

  gateway_2:
    image: multiagent-gateway:1.0.0
    environment:
      - INSTANCE_ID=2

  gateway_3:
    image: multiagent-gateway:1.0.0
    environment:
      - INSTANCE_ID=3
```

### Vertical Scaling
```bash
# Increase resources
docker update --memory 2g gateway
docker restart gateway

# Monitor memory usage
docker stats gateway
```

## ��️ Database Backups

### Neo4j Backup
```bash
# Full backup
docker exec neo4j neo4j-admin database dump neo4j /backups/neo4j-$(date +%Y%m%d).dump

# Restore backup
docker exec neo4j neo4j-admin database load neo4j /backups/neo4j-backup.dump --from-stdin < backup.dump

# Schedule backups (cron)
0 2 * * * docker exec neo4j neo4j-admin database dump neo4j /backups/neo4j-$(date +\%Y\%m\%d).dump
```

## 🔄 Rolling Updates
```bash
# Zero-downtime update
docker pull your-registry/multiagent-gateway:1.1.0

# Update load balancer config
# ... remove instances one at a time

for i in 1 2 3; do
  docker stop gateway_$i
  docker rm gateway_$i
  docker run -d --name gateway_$i \
    your-registry/multiagent-gateway:1.1.0
  sleep 10  # Wait for health check
done
```

## 🚨 Troubleshooting Production Issues

### High Memory Usage
```bash
# Check memory
docker stats gateway

# Reduce conversation memory size
# Restart with CONVERSATION_MEMORY_SIZE=20

# Check for memory leaks
docker exec gateway python -m memory_profiler
```

### Slow Query Performance
```bash
# Profile Neo4j queries
docker exec neo4j cypher-shell
:profile MATCH (n) RETURN count(n)

# Add indexes
docker exec neo4j cypher-shell
CREATE INDEX entity_name FOR (e) ON (e.name)
```

### Agents Timing Out
```bash
# Increase timeout
# Edit MCP_TIMEOUT=60 (in seconds)

# Check agent logs
docker logs indexer_agent

# Restart agent
docker restart indexer_agent
```

## 📈 Capacity Planning

### Storage

- Neo4j database: ~1GB per 100k entities
- Repository cache: Varies by repo size
- Logs: ~100MB per day (with rotation)

### Memory

- Gateway: ~512MB base + request memory
- Neo4j: ~1GB minimum, 4GB recommended
- Agents: ~256MB each

### CPU

- Single gateway: 1-2 cores sufficient
- Multiple gateways: 1 core per instance
- Neo4j: 2-4 cores recommended

## ✅ Post-Deployment Verification
```bash
# Check all services running
curl http://localhost:8000/health | jq

# List agents
curl http://localhost:8000/agents | jq

# Test indexing
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/tiangolo/fastapi"}'

# Monitor ongoing
watch -n 5 'docker stats gateway'
```

## 🔄 Rollback Procedure
```bash
# If deployment fails
docker-compose down
docker-compose up -d  # Starts previous version

# Or switch image version
docker pull multiagent-gateway:1.0.0
docker tag multiagent-gateway:1.0.0 multiagent-gateway:latest
docker-compose restart gateway
```

---

For more help, see [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
