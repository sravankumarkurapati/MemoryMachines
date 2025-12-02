"""
FastAPI application for log ingestion.
Handles both JSON and plain text formats with async processing.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.models import (
    JSONLogPayload, 
    IngestResponse, 
    ErrorResponse, 
    NormalizedMessage
)
from api.utils import PIIRedactor, normalize_tenant_id, validate_text_size, generate_log_id
from shared.message_queue import get_message_queue

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize message queue
message_queue = get_message_queue(
    queue_type=settings.queue_type,
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    queue_name=settings.redis_queue_name,
    project_id=settings.gcp_project_id,
    topic_name=settings.pubsub_topic
)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Queue type: {settings.queue_type}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down gracefully...")
    await message_queue.close()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/readiness")
async def readiness_check():
    """Readiness check endpoint."""
    # In production, check if message queue is accessible
    return {"status": "ready", "timestamp": datetime.utcnow().isoformat()}


@app.post("/ingest", 
          response_model=IngestResponse,
          status_code=status.HTTP_202_ACCEPTED,
          responses={
              202: {"description": "Log accepted for processing"},
              400: {"model": ErrorResponse, "description": "Bad request"},
              413: {"model": ErrorResponse, "description": "Payload too large"},
              500: {"model": ErrorResponse, "description": "Internal server error"}
          })
async def ingest_log(
    request: Request,
    content_type: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
):
    """
    Unified ingestion endpoint for logs.
    
    Supports two formats:
    1. JSON: Content-Type: application/json
       Body: {"tenant_id": "acme", "log_id": "123", "text": "..."}
    
    2. Plain Text: Content-Type: text/plain
       Header: X-Tenant-ID: acme
       Body: Raw text string
    
    Returns:
        202 Accepted with tracking information
    """
    request_id = str(uuid.uuid4())
    
    try:
        # Determine content type
        content_type_lower = (content_type or "").lower()
        
        # Handle JSON payload
        if "application/json" in content_type_lower:
            return await handle_json_ingestion(request, request_id)
        
        # Handle plain text payload
        elif "text/plain" in content_type_lower:
            return await handle_text_ingestion(request, x_tenant_id, request_id)
        
        else:
            logger.warning(f"Unsupported content type: {content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported Content-Type: {content_type}. Use application/json or text/plain"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during ingestion"
        )


async def handle_json_ingestion(request: Request, request_id: str) -> IngestResponse:
    """
    Handle JSON format ingestion.
    
    Args:
        request: FastAPI request object
        request_id: Unique request identifier
        
    Returns:
        IngestResponse
    """
    try:
        # Parse JSON body
        body = await request.json()
        payload = JSONLogPayload(**body)
        
        # Validate text size
        if not validate_text_size(payload.text, settings.max_request_size // (1024 * 1024)):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Text payload exceeds maximum size"
            )
        
        # Normalize tenant ID
        tenant_id = normalize_tenant_id(payload.tenant_id)
        
        # Create normalized message
        normalized_msg = NormalizedMessage(
            tenant_id=tenant_id,
            log_id=payload.log_id,
            text=payload.text,
            source="json",
            request_id=request_id
        )
        
        # Publish to message queue (non-blocking)
        success = await message_queue.publish(normalized_msg.to_dict())
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to queue message for processing"
            )
        
        logger.info(f"JSON log queued: tenant={tenant_id}, log_id={payload.log_id}, request_id={request_id}")
        
        return IngestResponse(
            log_id=payload.log_id,
            tenant_id=tenant_id,
            request_id=request_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling JSON ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {str(e)}"
        )


async def handle_text_ingestion(
    request: Request, 
    tenant_id: Optional[str], 
    request_id: str
) -> IngestResponse:
    """
    Handle plain text format ingestion.
    
    Args:
        request: FastAPI request object
        tenant_id: Tenant ID from X-Tenant-ID header
        request_id: Unique request identifier
        
    Returns:
        IngestResponse
    """
    try:
        # Validate tenant ID header
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID header is required for text/plain content"
            )
        
        # Read text body
        text = await request.body()
        text_str = text.decode('utf-8')
        
        if not text_str.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text payload cannot be empty"
            )
        
        # Validate text size
        if not validate_text_size(text_str, settings.max_request_size // (1024 * 1024)):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Text payload exceeds maximum size"
            )
        
        # Normalize tenant ID
        normalized_tenant = normalize_tenant_id(tenant_id)
        
        # Generate log ID
        log_id = generate_log_id(normalized_tenant)
        
        # Create normalized message
        normalized_msg = NormalizedMessage(
            tenant_id=normalized_tenant,
            log_id=log_id,
            text=text_str,
            source="text",
            request_id=request_id
        )
        
        # Publish to message queue (non-blocking)
        success = await message_queue.publish(normalized_msg.to_dict())
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to queue message for processing"
            )
        
        logger.info(f"Text log queued: tenant={normalized_tenant}, log_id={log_id}, request_id={request_id}")
        
        return IngestResponse(
            log_id=log_id,
            tenant_id=normalized_tenant,
            request_id=request_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling text ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid text payload: {str(e)}"
        )


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
            "request_id": str(uuid.uuid4())
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "Internal server error",
            "request_id": str(uuid.uuid4())
        }
    )