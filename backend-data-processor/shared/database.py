"""
Database abstraction layer for Firestore.
Supports both local emulator and cloud Firestore.
"""
import os
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Database(ABC):
    """Abstract base class for database implementations."""
    
    @abstractmethod
    async def save_processed_log(self, tenant_id: str, log_id: str, data: dict) -> bool:
        """Save a processed log to the database."""
        pass
    
    @abstractmethod
    async def get_processed_log(self, tenant_id: str, log_id: str) -> Optional[dict]:
        """Retrieve a processed log from the database."""
        pass
    
    @abstractmethod
    async def list_tenant_logs(self, tenant_id: str, limit: int = 100) -> list:
        """List all logs for a tenant."""
        pass


class FirestoreDatabase(Database):
    """
    Firestore database implementation with multi-tenant isolation.
    Schema: tenants/{tenant_id}/processed_logs/{log_id}
    """
    
    def __init__(self, use_emulator: bool = False, emulator_host: str = "localhost:8080"):
        """
        Initialize Firestore database.
        
        Args:
            use_emulator: Whether to use Firestore emulator
            emulator_host: Emulator host and port
        """
        self.use_emulator = use_emulator
        self.emulator_host = emulator_host
        self._db = None
        self._initialized = False
    
    def _initialize(self) -> None:
        """Initialize Firestore client."""
        if self._initialized:
            return
        
        from google.cloud import firestore
        
        if self.use_emulator:
            os.environ['FIRESTORE_EMULATOR_HOST'] = self.emulator_host
            logger.info(f"Using Firestore emulator at {self.emulator_host}")
        
        try:
            self._db = firestore.Client()
            self._initialized = True
            logger.info("Firestore client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise
    
    async def save_processed_log(self, tenant_id: str, log_id: str, data: dict) -> bool:
        """
        Save a processed log with strict multi-tenant isolation.
        
        Args:
            tenant_id: Tenant identifier
            log_id: Log identifier
            data: Log data to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._initialize()
            
            # Multi-tenant path: tenants/{tenant_id}/processed_logs/{log_id}
            doc_ref = (
                self._db
                .collection('tenants')
                .document(tenant_id)
                .collection('processed_logs')
                .document(log_id)
            )
            
            # Use set with merge=False to ensure idempotency
            # If document exists, it will be overwritten (idempotent)
            doc_ref.set(data)
            
            logger.info(f"Saved log to Firestore: tenant={tenant_id}, log_id={log_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save to Firestore: {e}")
            return False
    
    async def get_processed_log(self, tenant_id: str, log_id: str) -> Optional[dict]:
        """
        Retrieve a processed log for a specific tenant.
        
        Args:
            tenant_id: Tenant identifier
            log_id: Log identifier
            
        Returns:
            Log data if found, None otherwise
        """
        try:
            self._initialize()
            
            doc_ref = (
                self._db
                .collection('tenants')
                .document(tenant_id)
                .collection('processed_logs')
                .document(log_id)
            )
            
            doc = doc_ref.get()
            
            if doc.exists:
                logger.info(f"Retrieved log: tenant={tenant_id}, log_id={log_id}")
                return doc.to_dict()
            else:
                logger.warning(f"Log not found: tenant={tenant_id}, log_id={log_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve from Firestore: {e}")
            return None
    
    async def list_tenant_logs(self, tenant_id: str, limit: int = 100) -> list:
        """
        List all processed logs for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of logs to return
            
        Returns:
            List of log documents
        """
        try:
            self._initialize()
            
            collection_ref = (
                self._db
                .collection('tenants')
                .document(tenant_id)
                .collection('processed_logs')
                .limit(limit)
            )
            
            docs = collection_ref.stream()
            logs = [doc.to_dict() for doc in docs]
            
            logger.info(f"Retrieved {len(logs)} logs for tenant={tenant_id}")
            return logs
            
        except Exception as e:
            logger.error(f"Failed to list logs: {e}")
            return []
    
    async def verify_tenant_isolation(self, tenant_id: str) -> Dict[str, Any]:
        """
        Verify that tenant data is properly isolated.
        Returns statistics about the tenant's data.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary with isolation verification data
        """
        try:
            self._initialize()
            
            logs = await self.list_tenant_logs(tenant_id, limit=1000)
            
            # Verify all logs belong to this tenant
            other_tenant_logs = [
                log for log in logs 
                if log.get('tenant_id') != tenant_id
            ]
            
            return {
                'tenant_id': tenant_id,
                'total_logs': len(logs),
                'isolation_violated': len(other_tenant_logs) > 0,
                'cross_tenant_leaks': other_tenant_logs
            }
            
        except Exception as e:
            logger.error(f"Failed to verify isolation: {e}")
            return {
                'tenant_id': tenant_id,
                'error': str(e)
            }


def get_database(use_emulator: bool = False, emulator_host: str = "localhost:8080", 
                use_sqlite: bool = False, db_path: str = "/app/data/logs.db"):
    """
    Factory function to get the appropriate database implementation.
    
    Args:
        use_emulator: Whether to use Firestore emulator
        emulator_host: Emulator host and port
        use_sqlite: Use SQLite database (for local development)
        db_path: SQLite database path
        
    Returns:
        Database implementation
    """
    if use_sqlite:
        from shared.sqlite_database import SQLiteDatabase
        return SQLiteDatabase(db_path=db_path)
    
    return FirestoreDatabase(use_emulator=use_emulator, emulator_host=emulator_host)
