"""
Utility functions for data processing and PII redaction.
"""
import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class PIIRedactor:
    """Handles PII (Personally Identifiable Information) redaction."""
    
    # Regex patterns for common PII
    PATTERNS = {
        'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        'ip_address': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    }
    
    @classmethod
    def redact(cls, text: str, enable: bool = True) -> Tuple[str, int]:
        """
        Redact PII from text.
        
        Args:
            text: Input text to redact
            enable: Whether to enable redaction (can be disabled for testing)
            
        Returns:
            Tuple of (redacted_text, redaction_count)
        """
        if not enable:
            return text, 0
        
        redacted_text = text
        total_redactions = 0
        
        for pii_type, pattern in cls.PATTERNS.items():
            matches = re.findall(pattern, redacted_text)
            if matches:
                count = len(matches)
                total_redactions += count
                redacted_text = re.sub(pattern, f'[{pii_type.upper()}_REDACTED]', redacted_text)
                logger.debug(f"Redacted {count} {pii_type} instances")
        
        return redacted_text, total_redactions


def normalize_tenant_id(tenant_id: str) -> str:
    """
    Normalize tenant ID to ensure it's safe for use in paths.
    
    Args:
        tenant_id: Raw tenant ID
        
    Returns:
        Normalized tenant ID
    """
    # Remove any potentially dangerous characters
    normalized = re.sub(r'[^a-zA-Z0-9_-]', '_', tenant_id)
    
    # Ensure it doesn't start with a special character
    if normalized and normalized[0] in ('_', '-'):
        normalized = 'tenant' + normalized
    
    return normalized.lower()


def generate_log_id(tenant_id: str, original_log_id: str = None) -> str:
    """
    Generate a unique log ID.
    
    Args:
        tenant_id: Tenant identifier
        original_log_id: Original log ID if provided
        
    Returns:
        Unique log ID
    """
    import uuid
    from datetime import datetime
    
    if original_log_id:
        return original_log_id
    
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"{tenant_id}_{timestamp}_{unique_id}"


def validate_text_size(text: str, max_size_mb: int = 10) -> bool:
    """
    Validate that text size is within acceptable limits.
    
    Args:
        text: Text to validate
        max_size_mb: Maximum size in MB
        
    Returns:
        True if valid, False otherwise
    """
    size_bytes = len(text.encode('utf-8'))
    max_bytes = max_size_mb * 1024 * 1024
    return size_bytes <= max_bytes