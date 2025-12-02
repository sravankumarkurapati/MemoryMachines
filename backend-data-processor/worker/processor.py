"""
Worker service for processing queued log messages.
Simulates heavy processing and saves to database.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any

from worker.config import settings
from api.models import NormalizedMessage, ProcessedLog
from api.utils import PIIRedactor
from shared.message_queue import get_message_queue
from shared.database import get_database

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize services
database = get_database(
    use_emulator=settings.database_type == "emulator",
    emulator_host=settings.firestore_emulator_host,
    use_sqlite=settings.database_type == "sqlite",
    db_path=settings.sqlite_db_path
)

message_queue = get_message_queue(
    queue_type=settings.queue_type,
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    queue_name=settings.redis_queue_name,
    project_id=settings.gcp_project_id,
    topic_name=settings.pubsub_topic
)


class LogProcessor:
    """Processes log messages from the queue."""
    
    def __init__(self):
        """Initialize the log processor."""
        self.pii_redactor = PIIRedactor()
        self.processing_stats = {
            'total_processed': 0,
            'total_failed': 0,
            'total_processing_time': 0.0
        }
    
    async def process_message(self, message_data: Dict[str, Any]) -> None:
        """
        Process a single message from the queue.
        
        Args:
            message_data: Message dictionary containing log data
        """
        start_time = time.time()
        
        try:
            # Deserialize message
            message = NormalizedMessage.from_dict(message_data)
            
            logger.info(
                f"Processing log: tenant={message.tenant_id}, "
                f"log_id={message.log_id}, request_id={message.request_id}"
            )
            
            # Simulate heavy CPU-bound processing
            # 0.05 seconds per character
            await self._simulate_processing(message.text)
            
            # Apply PII redaction
            modified_text, redaction_count = self.pii_redactor.redact(
                message.text,
                enable=settings.enable_pii_redaction
            )
            
            if redaction_count > 0:
                logger.info(f"Redacted {redaction_count} PII instances in log {message.log_id}")
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Create processed log document
            processed_log = ProcessedLog(
                log_id=message.log_id,
                tenant_id=message.tenant_id,
                source=f"{message.source}_upload",
                original_text=message.text,
                modified_data=modified_text,
                ingested_at=message.ingested_at,
                processed_at=datetime.utcnow(),
                processing_time_seconds=round(processing_time, 3),
                character_count=len(message.text),
                request_id=message.request_id
            )
            
            # Save to database with multi-tenant isolation
            success = await database.save_processed_log(
                tenant_id=message.tenant_id,
                log_id=message.log_id,
                data=processed_log.to_firestore_dict()
            )
            
            if success:
                self.processing_stats['total_processed'] += 1
                self.processing_stats['total_processing_time'] += processing_time
                
                logger.info(
                    f"Successfully processed log: tenant={message.tenant_id}, "
                    f"log_id={message.log_id}, time={processing_time:.3f}s"
                )
            else:
                self.processing_stats['total_failed'] += 1
                logger.error(f"Failed to save processed log: {message.log_id}")
                # In production, would push to dead-letter queue
        
        except Exception as e:
            self.processing_stats['total_failed'] += 1
            logger.error(
                f"Error processing message: {e}",
                exc_info=True
            )
            # In production, would implement retry logic and dead-letter queue
    
    async def _simulate_processing(self, text: str) -> None:
        """
        Simulate CPU-bound heavy processing.
        Sleeps for 0.05 seconds per character.
        
        Args:
            text: Text to process
        """
        char_count = len(text)
        sleep_time = char_count * settings.processing_time_per_char
        
        logger.debug(f"Simulating {sleep_time:.2f}s processing for {char_count} characters")
        
        # Use asyncio.sleep to not block the event loop
        await asyncio.sleep(sleep_time)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.
        
        Returns:
            Dictionary with processing stats
        """
        total = self.processing_stats['total_processed'] + self.processing_stats['total_failed']
        avg_time = (
            self.processing_stats['total_processing_time'] / 
            self.processing_stats['total_processed']
            if self.processing_stats['total_processed'] > 0
            else 0
        )
        
        return {
            'total_messages': total,
            'successful': self.processing_stats['total_processed'],
            'failed': self.processing_stats['total_failed'],
            'success_rate': (
                self.processing_stats['total_processed'] / total * 100
                if total > 0
                else 0
            ),
            'average_processing_time_seconds': round(avg_time, 3)
        }


async def main():
    """Main worker loop."""
    logger.info("Starting log processor worker...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Queue type: {settings.queue_type}")
    logger.info(f"Database type: {settings.database_type}")
    
    processor = LogProcessor()
    
    try:
        # Subscribe to message queue
        await message_queue.subscribe(processor.process_message)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error in worker: {e}", exc_info=True)
    finally:
        # Print final statistics
        stats = processor.get_stats()
        logger.info(f"Worker statistics: {stats}")
        
        # Cleanup
        await message_queue.close()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
