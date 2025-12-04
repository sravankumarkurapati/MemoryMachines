# Backend Data Processor - Memory Machines Co-op

**Live API:** https://log-processor-api-267365813208.us-east1.run.app

Scalable, multi-tenant log processing system on GCP Cloud Run.

## Quick Test

1. JSON Format:
curl -X POST https://log-processor-api-267365813208.us-east1.run.app/ingest \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"demo","log_id":"test_001","text":"Test with email test@example.com"}'

Expected Response:
{"status":"accepted","message":"Log queued for processing","log_id":"test_001","tenant_id":"demo","request_id":"..."}

2. Text Format:
curl -X POST https://log-processor-api-267365813208.us-east1.run.app/ingest \
  -H "Content-Type: text/plain" \
  -H "X-Tenant-ID: demo" \
  -d "Plain text log with phone 555-1234"

Expected Response:
{"status":"accepted","message":"Log queued for processing","log_id":"demo_20241203..._a1b2c3d4","tenant_id":"demo","request_id":"..."}

## Architecture Diagram

                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
         JSON Format              Text Format
              │                         │
    Content-Type:            Content-Type: text/plain
    application/json         X-Tenant-ID: acme
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
                  ┌────────────────┐
                  │  Cloud Run API │
                  │  - Validate    │
                  │  - Normalize   │
                  │  - Return 202  │
                  └────────┬───────┘
                           │ Publish
                           ▼
                  ┌────────────────┐
                  │ Cloud Pub/Sub  │
                  │ Topic          │
                  └────────┬───────┘
                           │ Push (HTTP)
                           ▼
                  ┌────────────────┐
                  │ Cloud Run      │
                  │ Worker         │
                  │ - Process      │
                  │ - Redact PII   │
                  │ - Sleep 0.05s/c│
                  └────────┬───────┘
                           │ Save
                           ▼
                  ┌────────────────┐
                  │ Cloud Firestore│
                  │ tenants/       │
                  │  {tenant_id}/  │
                  │   processed_   │
                  │     logs/      │
                  │      {log_id}  │
                  └────────────────┘

KEY: Both JSON and Text paths normalize to same internal format before publishing to Pub/Sub.

## Multi-Tenant Isolation

Firestore Schema: tenants/{tenant_id}/processed_logs/{log_id}

Example:
tenants/
├── acme_corp/
│   └── processed_logs/
│       └── log_123
└── beta_inc/
    └── processed_logs/
        └── log_456

Physical separation ensures acme_corp cannot access beta_inc data.

## Crash Recovery

HOW CRASHES ARE HANDLED:

1. Pub/Sub Guarantees At-Least-Once Delivery
   - If worker crashes, message is NOT acknowledged
   - Pub/Sub automatically retries after timeout (600s)
   - New worker instance picks up the message

2. Idempotent Processing
   - Firestore document key = log_id
   - Duplicate processing → overwrites with same data
   - No duplicates created

3. Example Crash Scenario:
   - Worker receives message for log_id="123"
   - Starts processing (sleep 0.05s per char)
   - Worker crashes mid-processing
   - Message not acknowledged to Pub/Sub
   - Pub/Sub retries after timeout
   - New worker reprocesses log_id="123"
   - Saves to Firestore (using log_id="123" as key)
   - If already exists → overwrites (idempotent)
   - Result: No data loss, no duplicates

KEY DESIGN DECISIONS:
- Message queue persistence (Pub/Sub)
- Idempotency key (log_id as document key)
- Auto-restart (Cloud Run)
- Structured logging (trace failures)

## Performance

Load Test Results:
- 1,000 requests: 100% success
- Throughput: 41 RPS (2,463 RPM)
- Response time: 24ms average
- Cost: $0 (GCP free tier)

## Technology Stack

- API: FastAPI (Python 3.11)
- Queue: Google Cloud Pub/Sub
- Compute: Google Cloud Run
- Database: Google Cloud Firestore (Native mode)
- Region: us-east1

## Project Structure

backend-data-processor/
├── api/                    # FastAPI application
├── worker/                 # Worker service
├── shared/                 # Database & queue abstractions
├── tests/                  # Unit & integration tests
├── Dockerfile.api.cloud    # API production container
├── Dockerfile.worker.cloud # Worker production container
└── docker-compose.yml      # Local development

## Local Development

docker-compose up -d
curl http://localhost:8000/health

## Author

Sravan Kumar Kurapati
MS Information Systems, Northeastern University
13+ years software engineering experience
Email: kurapati.sr@northeastern.edu
