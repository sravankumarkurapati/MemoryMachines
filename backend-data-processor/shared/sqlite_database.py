"""
SQLite-based database for local development.
Mimics Firestore multi-tenant structure without Docker networking issues.
"""
import json
import logging
import sqlite3
import aiosqlite
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLiteDatabase:
    """
    SQLite database implementation with multi-tenant isolation.
    Mimics Firestore structure: tenants/{tenant_id}/processed_logs/{log_id}
    """
    
    def __init__(self, db_path: str = "/app/data/logs.db"):
        """
        Initialize SQLite database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialized = False
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def _initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Create table with multi-tenant structure
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS processed_logs (
                        tenant_id TEXT NOT NULL,
                        log_id TEXT NOT NULL,
                        data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (tenant_id, log_id)
                    )
                """)
                
                # Create index for faster tenant queries
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tenant_id 
                    ON processed_logs(tenant_id)
                """)
                
                await db.commit()
            
            self._initialized = True
            logger.info(f"SQLite database initialized at {self.db_path}")
        
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
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
            await self._initialize()
            
            # Serialize data to JSON
            data_json = json.dumps(data)
            
            async with aiosqlite.connect(self.db_path) as db:
                # Use INSERT OR REPLACE for idempotency
                await db.execute("""
                    INSERT OR REPLACE INTO processed_logs 
                    (tenant_id, log_id, data, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (tenant_id, log_id, data_json))
                
                await db.commit()
            
            logger.info(f"Saved log to SQLite: tenant={tenant_id}, log_id={log_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save to SQLite: {e}")
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
            await self._initialize()
            
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT data FROM processed_logs
                    WHERE tenant_id = ? AND log_id = ?
                """, (tenant_id, log_id)) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        logger.info(f"Retrieved log: tenant={tenant_id}, log_id={log_id}")
                        return json.loads(row[0])
                    else:
                        logger.warning(f"Log not found: tenant={tenant_id}, log_id={log_id}")
                        return None
        
        except Exception as e:
            logger.error(f"Failed to retrieve from SQLite: {e}")
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
            await self._initialize()
            
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT data FROM processed_logs
                    WHERE tenant_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (tenant_id, limit)) as cursor:
                    rows = await cursor.fetchall()
                    logs = [json.loads(row[0]) for row in rows]
            
            logger.info(f"Retrieved {len(logs)} logs for tenant={tenant_id}")
            return logs
        
        except Exception as e:
            logger.error(f"Failed to list logs: {e}")
            return []
    
    async def get_all_tenants(self) -> list:
        """
        Get list of all tenant IDs.
        
        Returns:
            List of tenant IDs
        """
        try:
            await self._initialize()
            
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT DISTINCT tenant_id FROM processed_logs
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        
        except Exception as e:
            logger.error(f"Failed to get tenants: {e}")
            return []
    
    async def verify_tenant_isolation(self, tenant_id: str) -> Dict[str, Any]:
        """
        Verify that tenant data is properly isolated.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary with isolation verification data
        """
        try:
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
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Returns:
            Dictionary with database stats
        """
        try:
            await self._initialize()
            
            async with aiosqlite.connect(self.db_path) as db:
                # Total logs
                async with db.execute("SELECT COUNT(*) FROM processed_logs") as cursor:
                    total_logs = (await cursor.fetchone())[0]
                
                # Total tenants
                async with db.execute("SELECT COUNT(DISTINCT tenant_id) FROM processed_logs") as cursor:
                    total_tenants = (await cursor.fetchone())[0]
            
            return {
                'total_logs': total_logs,
                'total_tenants': total_tenants,
                'database_path': self.db_path
            }
        
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
