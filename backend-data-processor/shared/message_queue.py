"""
Message Queue abstraction layer.
Supports Redis (local) and Google Cloud Pub/Sub (cloud).
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any
import asyncio

logger = logging.getLogger(__name__)


class MessageQueue(ABC):
    """Abstract base class for message queue implementations."""
    
    @abstractmethod
    async def publish(self, message: dict) -> bool:
        """Publish a message to the queue."""
        pass
    
    @abstractmethod
    async def subscribe(self, callback: Callable[[dict], Any]) -> None:
        """Subscribe to messages and process them with callback."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass


class RedisMessageQueue(MessageQueue):
    """Redis-based message queue for local development."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, 
                 db: int = 0, queue_name: str = "log-ingestion"):
        """
        Initialize Redis message queue.
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            queue_name: Name of the queue (Redis list)
        """
        self.host = host
        self.port = port
        self.db = db
        self.queue_name = queue_name
        self._client: Optional[Any] = None
        self._is_connected = False
    
    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self._is_connected:
            return
        
        try:
            import redis.asyncio as aioredis
            self._client = await aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self._client.ping()
            self._is_connected = True
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def publish(self, message: dict) -> bool:
        """
        Publish a message to Redis queue.
        
        Args:
            message: Dictionary to publish
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.connect()
            message_json = json.dumps(message)
            await self._client.rpush(self.queue_name, message_json)
            logger.info(f"Published message to {self.queue_name}: log_id={message.get('log_id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            return False
    
    async def subscribe(self, callback: Callable[[dict], Any], 
                       poll_interval: float = 0.1) -> None:
        """
        Subscribe to messages and process them.
        
        Args:
            callback: Async function to call with each message
            poll_interval: Time to wait between polls (seconds)
        """
        await self.connect()
        logger.info(f"Started subscribing to {self.queue_name}")
        
        while True:
            try:
                # BLPOP: Blocking left pop with timeout
                result = await self._client.blpop(self.queue_name, timeout=1)
                
                if result:
                    _, message_json = result
                    message = json.loads(message_json)
                    logger.info(f"Received message: log_id={message.get('log_id')}")
                    
                    # Process message with callback
                    try:
                        await callback(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        # In production, would push to dead-letter queue
                
                await asyncio.sleep(poll_interval)
                
            except asyncio.CancelledError:
                logger.info("Subscription cancelled")
                break
            except Exception as e:
                logger.error(f"Error in subscription loop: {e}")
                await asyncio.sleep(1)  # Back off on error
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._is_connected = False
            logger.info("Closed Redis connection")


class PubSubMessageQueue(MessageQueue):
    """Google Cloud Pub/Sub message queue for production."""
    
    def __init__(self, project_id: str, topic_name: str):
        """
        Initialize Pub/Sub message queue.
        
        Args:
            project_id: GCP project ID
            topic_name: Pub/Sub topic name
        """
        self.project_id = project_id
        self.topic_name = topic_name
        self._publisher = None
        self._subscriber = None
    
    async def publish(self, message: dict) -> bool:
        """
        Publish a message to Pub/Sub.
        
        Args:
            message: Dictionary to publish
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from google.cloud import pubsub_v1
            
            if not self._publisher:
                self._publisher = pubsub_v1.PublisherClient()
            
            topic_path = self._publisher.topic_path(self.project_id, self.topic_name)
            message_json = json.dumps(message)
            future = self._publisher.publish(topic_path, message_json.encode('utf-8'))
            future.result()  # Wait for publish to complete
            
            logger.info(f"Published message to Pub/Sub: log_id={message.get('log_id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish to Pub/Sub: {e}")
            return False
    
    async def subscribe(self, callback: Callable[[dict], Any]) -> None:
        """Subscribe to Pub/Sub messages."""
        # For Cloud Run, this is handled by push subscriptions
        # This method is not used in production
        pass
    
    async def close(self) -> None:
        """Close Pub/Sub connections."""
        if self._publisher:
            self._publisher = None
        if self._subscriber:
            self._subscriber = None


def get_message_queue(queue_type: str, **kwargs) -> MessageQueue:
    """
    Factory function to get the appropriate message queue implementation.
    
    Args:
        queue_type: Type of queue ('redis' or 'pubsub')
        **kwargs: Configuration parameters
        
    Returns:
        MessageQueue implementation
    """
    if queue_type == "redis":
        return RedisMessageQueue(
            host=kwargs.get('host', 'localhost'),
            port=kwargs.get('port', 6379),
            db=kwargs.get('db', 0),
            queue_name=kwargs.get('queue_name', 'log-ingestion')
        )
    elif queue_type == "pubsub":
        return PubSubMessageQueue(
            project_id=kwargs.get('project_id', ''),
            topic_name=kwargs.get('topic_name', 'log-ingestion')
        )
    else:
        raise ValueError(f"Unknown queue type: {queue_type}")