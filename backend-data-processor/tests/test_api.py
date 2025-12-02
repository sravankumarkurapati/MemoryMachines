"""
Unit tests for the API service.
"""
import pytest
from httpx import AsyncClient
from api.main import app


@pytest.fixture
def sample_json_payload():
    """Sample JSON payload for testing."""
    return {
        "tenant_id": "acme_corp",
        "log_id": "test_123",
        "text": "User 555-0199 accessed resource at 10:00 AM"
    }


@pytest.fixture
def sample_text_payload():
    """Sample text payload for testing."""
    return "This is a test log entry with phone 555-0199"


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint returns service info."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_check():
    """Test readiness check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_ingest_json_success(sample_json_payload):
    """Test successful JSON ingestion."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            json=sample_json_payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["tenant_id"] == "acme_corp"
        assert data["log_id"] == "test_123"
        assert "request_id" in data


@pytest.mark.asyncio
async def test_ingest_json_invalid_tenant():
    """Test JSON ingestion with invalid tenant ID."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            json={
                "tenant_id": "invalid@tenant!",
                "log_id": "test_123",
                "text": "Test log"
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_ingest_json_missing_fields():
    """Test JSON ingestion with missing required fields."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            json={
                "tenant_id": "acme_corp",
                "log_id": "test_123"
                # Missing 'text' field
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_ingest_text_success(sample_text_payload):
    """Test successful text ingestion."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            content=sample_text_payload,
            headers={
                "Content-Type": "text/plain",
                "X-Tenant-ID": "beta_inc"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["tenant_id"] == "beta_inc"
        assert "log_id" in data
        assert "request_id" in data


@pytest.mark.asyncio
async def test_ingest_text_missing_tenant_header(sample_text_payload):
    """Test text ingestion without X-Tenant-ID header."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            content=sample_text_payload,
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "X-Tenant-ID" in data["message"]


@pytest.mark.asyncio
async def test_ingest_text_empty_payload():
    """Test text ingestion with empty payload."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            content="",
            headers={
                "Content-Type": "text/plain",
                "X-Tenant-ID": "test_tenant"
            }
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_ingest_unsupported_content_type():
    """Test ingestion with unsupported content type."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            content="test",
            headers={"Content-Type": "application/xml"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "Unsupported Content-Type" in data["message"]


@pytest.mark.asyncio
async def test_tenant_id_normalization():
    """Test that tenant IDs are properly normalized."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/ingest",
            json={
                "tenant_id": "Acme-Corp_123",
                "log_id": "test",
                "text": "Test"
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 202
        data = response.json()
        # Should be normalized to lowercase with safe characters
        assert data["tenant_id"] == "acme-corp_123"


@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test handling multiple concurrent requests."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        tasks = []
        for i in range(10):
            task = client.post(
                "/ingest",
                json={
                    "tenant_id": f"tenant_{i}",
                    "log_id": f"log_{i}",
                    "text": f"Test log {i}"
                },
                headers={"Content-Type": "application/json"}
            )
            tasks.append(task)
        
        import asyncio
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for response in responses:
            assert response.status_code == 202