# Backend Data Processor - Robust Log Ingestion System

A scalable, event-driven backend system for ingesting, processing, and storing multi-tenant log data with strict isolation guarantees.

## 🏗️ Architecture Overview

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /ingest (JSON/TXT)
       ▼
┌──────────────────┐
│   API Service    │  ← FastAPI (Cloud Run / Local)
│  - Validates     │
│  - Normalizes    │
│  - Queues        │
└────────┬─────────┘
         │ Async Publish
         ▼
┌──────────────────┐
│  Message Queue   │  ← Redis (Local) / Pub/Sub (Cloud)
└────────┬─────────┘
         │ Subscribe
         ▼
┌──────────────────┐
│  Worker Service  │  ← Python Worker (Cloud Run / Local)
│  - Process       │
│  - Redact PII    │
│  - Store         │
└────────┬─────────┘
         │ Write with isolation
         ▼
┌──────────────────────────┐
│  Firestore Database      │
│  tenants/                │
│    ├─ acme/              │
│    │  └─ processed_logs/ │
│    └─ beta/              │
│       └─ processed_logs/ │
└──────────────────────────┘
```

## ✨ Key Features

- **Multi-Format Ingestion**: Supports JSON and plain text
- **Async Processing**: Non-blocking API with queue-based workers
- **Multi-Tenant Isolation**: Physical data separation at collection level
- **PII Redaction**: Automatic masking of sensitive data
- **Crash Recovery**: At-least-once delivery with idempotency
- **Scalable**: Serverless-ready architecture
- **Local Development**: Full stack runs with Docker Compose

## 🚀 Quick Start (Local Development)

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local testing)
- Git

### 1. Clone and Setup

```bash
git clone <your-repo>
cd backend-data-processor

# Copy environment file
cp .env.example .env
```

### 2. Start All Services

```bash
# Start Redis, Firestore Emulator, API, and Worker
docker-compose up -d

# View logs
docker-compose logs -f
```

Services will be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Redis**: localhost:6379
- **Firestore Emulator**: localhost:8080

### 3. Test the API

**JSON Format:**
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme_corp",
    "log_id": "log_001",
    "text": "User 555-0199 accessed dashboard at 10:00 AM"
  }'
```

**Plain Text Format:**
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: text/plain" \
  -H "X-Tenant-ID: beta_inc" \
  -d "Server error on 192.168.1.1 - contact admin@example.com"
```

Expected Response (202 Accepted):
```json
{
  "status": "accepted",
  "message": "Log queued for processing",
  "log_id": "log_001",
  "tenant_id": "acme_corp",
  "request_id": "uuid-here"
}
```

### 4. Verify Data in Firestore

The worker processes messages asynchronously. After a few seconds, check the Firestore emulator:

```bash
# Connect to Firestore container
docker exec -it log_processor_firestore bash

# Or use the Firestore UI at http://localhost:4000
```

## 🧪 Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=api --cov=worker --cov=shared

# Run specific test file
pytest tests/test_api.py -v
```

## 📊 Project Structure

```
backend-data-processor/
├── api/                    # API service
│   ├── main.py            # FastAPI application
│   ├── models.py          # Pydantic models
│   ├── config.py          # Configuration
│   └── utils.py           # Utilities (PII redaction, etc.)
├── worker/                # Worker service
│   ├── processor.py       # Message processor
│   └── config.py          # Worker config
├── shared/                # Shared components
│   ├── message_queue.py   # Queue abstraction
│   └── database.py        # Database abstraction
├── tests/                 # Test suite
│   ├── test_api.py
│   ├── test_worker.py
│   └── test_integration.py
├── docker-compose.yml     # Local development stack
├── Dockerfile.api         # API container
├── Dockerfile.worker      # Worker container
└── requirements.txt       # Python dependencies
```

## 🔑 Key Design Decisions

### 1. Multi-Tenancy Strategy
- **Physical Isolation**: Each tenant gets their own sub-collection
- **Path**: `tenants/{tenant_id}/processed_logs/{log_id}`
- **Benefit**: Eliminates possibility of cross-tenant data leaks

### 2. Crash Recovery
- **At-least-once delivery**: Pub/Sub guarantees message delivery
- **Idempotency**: Using `log_id` as document key prevents duplicates
- **Retry Logic**: Failed messages automatically retry with backoff

### 3. Performance Optimization
- **Async API**: Returns 202 immediately, processing happens async
- **Queue Buffering**: Decouples API from worker for independent scaling
- **Connection Pooling**: Reuses database connections

### 4. PII Protection
- Automatic detection and redaction of:
  - Phone numbers
  - Email addresses
  - SSN
  - Credit card numbers
  - IP addresses

## 🌍 Environment Variables

| Variable | Description | Local Default | Cloud Default |
|----------|-------------|---------------|---------------|
| `ENVIRONMENT` | Deployment environment | `local` | `production` |
| `QUEUE_TYPE` | Message queue type | `redis` | `pubsub` |
| `DATABASE_TYPE` | Database type | `emulator` | `firestore` |
| `LOG_LEVEL` | Logging level | `INFO` | `INFO` |
| `PROCESSING_TIME_PER_CHAR` | Simulated processing time | `0.05` | `0.05` |

## 📈 Performance Characteristics

### Local Development
- **API Response Time**: < 10ms (202 Accepted)
- **Worker Processing**: 0.05s per character + PII redaction
- **Throughput**: ~100 RPM (limited by single worker)

### Cloud Production (Expected)
- **API Response Time**: < 50ms
- **Throughput**: 1000+ RPM with auto-scaling
- **Worker Auto-scaling**: 0-1000 instances based on queue depth

## 🔍 Monitoring & Debugging

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f worker
```

### Check Queue Depth
```bash
# Connect to Redis
docker exec -it log_processor_redis redis-cli

# Check queue length
LLEN log-ingestion
```

### Inspect Database
```bash
# The Firestore emulator doesn't have a built-in UI
# Use the Cloud Console locally or check logs
docker-compose logs firestore
```

## 🛠️ Development Workflow

### Making Changes

1. **Edit code** in `api/`, `worker/`, or `shared/`
2. **Services auto-reload** (via volume mounts)
3. **Run tests**: `pytest tests/ -v`
4. **Commit changes**: Follow conventional commits

### Adding Dependencies

```bash
# Add to requirements.txt
echo "new-package==1.0.0" >> requirements.txt

# Rebuild containers
docker-compose down
docker-compose build
docker-compose up -d
```

## 🐛 Troubleshooting

### API not responding
```bash
# Check if container is running
docker-compose ps

# Check logs
docker-compose logs api

# Restart service
docker-compose restart api
```

### Worker not processing
```bash
# Check worker logs
docker-compose logs worker

# Verify Redis connection
docker exec -it log_processor_redis redis-cli ping
```

### Can't connect to Firestore
```bash
# Ensure emulator is running
docker-compose ps firestore

# Check emulator logs
docker-compose logs firestore
```

## 📝 API Documentation

### Endpoints

#### `POST /ingest`
Ingest a log for processing.

**JSON Format:**
```bash
POST /ingest
Content-Type: application/json

{
  "tenant_id": "string",
  "log_id": "string",
  "text": "string"
}
```

**Plain Text Format:**
```bash
POST /ingest
Content-Type: text/plain
X-Tenant-ID: string

<raw text content>
```

**Response (202 Accepted):**
```json
{
  "status": "accepted",
  "message": "Log queued for processing",
  "log_id": "string",
  "tenant_id": "string",
  "request_id": "string"
}
```

#### `GET /health`
Health check endpoint.

#### `GET /readiness`
Readiness check for load balancers.

## 🎯 Next Steps (Phase 2)

Ready to deploy to GCP? See the deployment guide for:
- Setting up GCP project
- Configuring Pub/Sub and Firestore
- Deploying to Cloud Run
- Setting up monitoring

## 📄 License

MIT License - See LICENSE file for details

## 👤 Author

**Sravan Kumar Kurapati**
- GitHub: [@your-github]
- LinkedIn: [your-linkedin]

---

**Memory Machines Co-Op Application Project**
Built with ❤️ showcasing 13+ years of enterprise backend engineering experience.