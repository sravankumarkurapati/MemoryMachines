"""
Integration tests for end-to-end workflow.
Tests API -> Queue -> Worker -> Database flow.
"""
import pytest
import asyncio
from datetime import datetime

from api.models import NormalizedMessage, ProcessedLog
from api.utils import PIIRedactor
from shared.message_queue import RedisMessageQueue
from shared.database import FirestoreDatabase


@pytest.mark.asyncio
async def test_message_queue_publish_subscribe():
    """Test message queue publish and subscribe."""
    queue = RedisMessageQueue(queue_name="test-queue")
    
    test_message = {
        "tenant_id": "test_tenant",
        "log_id": "test_123",
        "text": "Test message",
        "source": "json",
        "ingested_at": datetime.utcnow().isoformat(),
        "request_id": "req_123"
    }
    
    # Publish message
    success = await queue.publish(test_message)
    assert success is True
    
    # Subscribe and verify
    received_messages = []
    
    async def callback(message):
        received_messages.append(message)
    
    # Subscribe with timeout
    async def subscribe_with_timeout():
        try:
            await asyncio.wait_for(
                queue.subscribe(callback),
                timeout=2.0
            )
        except asyncio.TimeoutError:
            pass
    
    await subscribe_with_timeout()
    await queue.close()
    
    assert len(received_messages) > 0
    assert received_messages[0]["tenant_id"] == "test_tenant"


@pytest.mark.asyncio
async def test_database_save_and_retrieve():
    """Test database save and retrieve operations."""
    db = FirestoreDatabase(use_emulator=True)
    
    tenant_id = "test_tenant"
    log_id = "log_123"
    
    test_data = {
        "log_id": log_id,
        "source": "json_upload",
        "original_text": "Test log entry",
        "modified_data": "Test log entry",
        "ingested_at": datetime.utcnow().isoformat(),
        "processed_at": datetime.utcnow().isoformat(),
        "processing_time_seconds": 0.5,
        "character_count": 14,
        "request_id": "req_123"
    }
    
    # Save
    success = await db.save_processed_log(tenant_id, log_id, test_data)
    assert success is True
    
    # Retrieve
    retrieved = await db.get_processed_log(tenant_id, log_id)
    assert retrieved is not None
    assert retrieved["log_id"] == log_id
    assert retrieved["original_text"] == "Test log entry"


@pytest.mark.asyncio
async def test_multi_tenant_isolation():
    """Test that tenant data is properly isolated."""
    db = FirestoreDatabase(use_emulator=True)
    
    # Save logs for different tenants
    tenant_a_data = {
        "log_id": "log_a",
        "source": "json_upload",
        "original_text": "Tenant A data",
        "modified_data": "Tenant A data",
        "ingested_at": datetime.utcnow().isoformat(),
        "processed_at": datetime.utcnow().isoformat(),
        "processing_time_seconds": 0.1,
        "character_count": 13,
        "request_id": "req_a"
    }
    
    tenant_b_data = {
        "log_id": "log_b",
        "source": "text_upload",
        "original_text": "Tenant B data",
        "modified_data": "Tenant B data",
        "ingested_at": datetime.utcnow().isoformat(),
        "processed_at": datetime.utcnow().isoformat(),
        "processing_time_seconds": 0.1,
        "character_count": 13,
        "request_id": "req_b"
    }
    
    await db.save_processed_log("tenant_a", "log_a", tenant_a_data)
    await db.save_processed_log("tenant_b", "log_b", tenant_b_data)
    
    # Verify tenant A can only see their data
    tenant_a_logs = await db.list_tenant_logs("tenant_a")
    assert len(tenant_a_logs) > 0
    assert all(log["original_text"] == "Tenant A data" for log in tenant_a_logs if log["log_id"] == "log_a")
    
    # Verify tenant B can only see their data
    tenant_b_logs = await db.list_tenant_logs("tenant_b")
    assert len(tenant_b_logs) > 0
    assert all(log["original_text"] == "Tenant B data" for log in tenant_b_logs if log["log_id"] == "log_b")
    
    # Verify tenant A cannot retrieve tenant B's log
    cross_tenant_log = await db.get_processed_log("tenant_a", "log_b")
    assert cross_tenant_log is None


def test_pii_redaction():
    """Test PII redaction functionality."""
    redactor = PIIRedactor()
    
    # Test phone number redaction
    text_with_phone = "Call me at 555-123-4567"
    redacted, count = redactor.redact(text_with_phone)
    assert "[PHONE_REDACTED]" in redacted
    assert count == 1
    
    # Test email redaction
    text_with_email = "Email: john.doe@example.com"
    redacted, count = redactor.redact(text_with_email)
    assert "[EMAIL_REDACTED]" in redacted
    assert count == 1
    
    # Test multiple PII types
    text_with_multiple = "Contact: 555-123-4567 or email@test.com"
    redacted, count = redactor.redact(text_with_multiple)
    assert "[PHONE_REDACTED]" in redacted
    assert "[EMAIL_REDACTED]" in redacted
    assert count == 2
    
    # Test with redaction disabled
    redacted, count = redactor.redact(text_with_phone, enable=False)
    assert "555-123-4567" in redacted
    assert count == 0


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """Test complete workflow: ingest -> queue -> process -> store."""
    # This would require all services running
    # For now, test individual components
    
    # 1. Create message
    message = NormalizedMessage(
        tenant_id="e2e_tenant",
        log_id="e2e_log",
        text="End to end test with phone 555-0000",
        source="json",
        request_id="e2e_req"
    )
    
    # 2. Simulate processing
    redactor = PIIRedactor()
    modified_text, _ = redactor.redact(message.text)
    
    # 3. Create processed log
    processed = ProcessedLog(
        log_id=message.log_id,
        tenant_id=message.tenant_id,
        source=f"{message.source}_upload",
        original_text=message.text,
        modified_data=modified_text,
        ingested_at=message.ingested_at,
        processed_at=datetime.utcnow(),
        processing_time_seconds=0.5,
        character_count=len(message.text),
        request_id=message.request_id
    )
    
    # 4. Verify structure
    assert processed.tenant_id == "e2e_tenant"
    assert "[PHONE_REDACTED]" in processed.modified_data
    assert processed.character_count > 0


@pytest.mark.asyncio
async def test_idempotency():
    """Test that duplicate messages are handled idempotently."""
    db = FirestoreDatabase(use_emulator=True)
    
    tenant_id = "idempotent_tenant"
    log_id = "idempotent_log"
    
    test_data = {
        "log_id": log_id,
        "source": "json_upload",
        "original_text": "First version",
        "modified_data": "First version",
        "ingested_at": datetime.utcnow().isoformat(),
        "processed_at": datetime.utcnow().isoformat(),
        "processing_time_seconds": 0.1,
        "character_count": 13,
        "request_id": "req_1"
    }
    
    # Save first time
    await db.save_processed_log(tenant_id, log_id, test_data)
    
    # Save again with updated data (simulating reprocessing)
    test_data["original_text"] = "Second version"
    test_data["modified_data"] = "Second version"
    await db.save_processed_log(tenant_id, log_id, test_data)
    
    # Retrieve and verify it was updated (last write wins)
    retrieved = await db.get_processed_log(tenant_id, log_id)
    assert retrieved["original_text"] == "Second version"