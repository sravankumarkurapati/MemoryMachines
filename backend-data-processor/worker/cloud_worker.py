"""
Cloud Run worker entry point.
Receives Pub/Sub push messages via HTTP.
"""
import asyncio
import base64
import json
import logging
from fastapi import FastAPI, Request, Response
import uvicorn

from worker.processor import LogProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Log Processor Worker")

# Initialize processor
processor = LogProcessor()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "log-processor-worker"}


@app.get("/health")
async def health():
    """Health check for Cloud Run."""
    return {"status": "healthy"}


@app.post("/")
async def process_pubsub_message(request: Request):
    """
    Receive and process Pub/Sub push messages.
    
    Pub/Sub sends messages in this format:
    {
        "message": {
            "data": "base64-encoded-data",
            "messageId": "...",
            "publishTime": "..."
        },
        "subscription": "..."
    }
    """
    try:
        envelope = await request.json()
        
        # Extract message data
        if "message" not in envelope:
            logger.error("No message field in request")
            return Response(status_code=400)
        
        pubsub_message = envelope["message"]
        
        # Decode the base64-encoded data
        if "data" in pubsub_message:
            message_data = base64.b64decode(pubsub_message["data"]).decode("utf-8")
            message_dict = json.loads(message_data)
            
            logger.info(f"Received Pub/Sub message: {pubsub_message.get('messageId')}")
            
            # Process the message
            await processor.process_message(message_dict)
            
            # Return 200 to acknowledge
            return Response(status_code=200)
        else:
            logger.error("No data in Pub/Sub message")
            return Response(status_code=400)
            
    except Exception as e:
        logger.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
        # Return 500 so Pub/Sub retries
        return Response(status_code=500)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
