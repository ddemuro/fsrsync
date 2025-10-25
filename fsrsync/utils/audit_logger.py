"""
Audit Logging System for FSRsync Security

Provides comprehensive audit trail for:
- User authentication and authorization
- Configuration changes
- Data access and transfers
- Security events
- API calls with sensitive operations
- Error and warning events

## Audit Events

AUTH: Authentication attempts (success/failure)
AUTHZ: Authorization checks (allow/deny)
CONFIG: Configuration changes
ACCESS: Data access and queries
TRANSFER: File transfer operations
SECURITY: Security-related events
API: API calls to sensitive endpoints
ERROR: System errors and exceptions

## Usage

```python
auditor = AuditLogger()

# Log authentication
auditor.log_auth("user123", success=True, method="token")

# Log configuration change
auditor.log_config("user123", "bandwidth_limit", "50", "100", "changed global limit")

# Log API access
auditor.log_api("user123", "POST", "/api/coordinator/pause", 200, "paused sync")
```
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from enum import Enum


class AuditEventType(Enum):
    """Type of audit event"""
    AUTH = "AUTH"
    AUTHZ = "AUTHZ"
    CONFIG = "CONFIG"
    ACCESS = "ACCESS"
    TRANSFER = "TRANSFER"
    SECURITY = "SECURITY"
    API = "API"
    ERROR = "ERROR"


@dataclass
class AuditEvent:
    """Single audit event entry"""
    timestamp: float
    event_type: str
    user_id: str
    action: str
    resource: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    status: str = "success"  # success, failure, denied
    details: Optional[str] = None
    ip_address: Optional[str] = None
    source: str = "api"  # api, cli, config_file, auto
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'event_type': self.event_type,
            'user_id': self.user_id,
            'action': self.action,
            'resource': self.resource,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'status': self.status,
            'details': self.details,
            'ip_address': self.ip_address,
            'source': self.source
        }


class AuditLogger:
    """
    Comprehensive audit logging system for FSRsync.
    
    Maintains immutable audit trail of all security-relevant
    events for compliance and forensic analysis.
    """

    def __init__(self, max_entries: int = 50000, logger_instance=None):
        """
        Initialize audit logger.
        
        Args:
            max_entries: Maximum audit entries to keep in memory
            logger_instance: Python logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.max_entries = max_entries
        self.events: deque = deque(maxlen=max_entries)
        self.event_counts: Dict[str, int] = {}
        self.started_at = time.time()

    def log_event(self, event_type: str, user_id: str, action: str,
                  resource: Optional[str] = None, old_value: Optional[str] = None,
                  new_value: Optional[str] = None, status: str = "success",
                  details: Optional[str] = None, ip_address: Optional[str] = None,
                  source: str = "api") -> None:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event (AUTH, CONFIG, API, etc.)
            user_id: User identifier
            action: Action performed
            resource: Resource affected
            old_value: Previous value (for changes)
            new_value: New value (for changes)
            status: Event status (success, failure, denied)
            details: Additional details
            ip_address: Source IP address
            source: Source of event (api, cli, config_file, auto)
        """
        event = AuditEvent(
            timestamp=time.time(),
            event_type=event_type.upper(),
            user_id=user_id,
            action=action,
            resource=resource,
            old_value=old_value,
            new_value=new_value,
            status=status,
            details=details,
            ip_address=ip_address,
            source=source
        )

        self.events.append(event)

        # Update counts
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1

        # Also log to Python logger
        log_level = logging.WARNING if status != "success" else logging.INFO
        self.logger.log(
            log_level,
            f"[AUDIT] {event_type} - {action} on {resource} by {user_id}: {status}"
        )

    def log_auth(self, user_id: str, success: bool, method: str = "password",
                 ip_address: Optional[str] = None, details: Optional[str] = None) -> None:
        """Log authentication attempt"""
        self.log_event(
            event_type="AUTH",
            user_id=user_id,
            action=f"login via {method}",
            resource="authentication",
            status="success" if success else "failure",
            details=details or f"Authentication {method}",
            ip_address=ip_address
        )

    def log_authz(self, user_id: str, action: str, resource: str,
                  allowed: bool, ip_address: Optional[str] = None) -> None:
        """Log authorization check"""
        self.log_event(
            event_type="AUTHZ",
            user_id=user_id,
            action=action,
            resource=resource,
            status="success" if allowed else "denied",
            ip_address=ip_address
        )

    def log_config(self, user_id: str, setting: str, old_value: str,
                   new_value: str, details: Optional[str] = None) -> None:
        """Log configuration change"""
        self.log_event(
            event_type="CONFIG",
            user_id=user_id,
            action="modified setting",
            resource=setting,
            old_value=old_value,
            new_value=new_value,
            details=details
        )

    def log_access(self, user_id: str, resource: str, action: str) -> None:
        """Log resource access"""
        self.log_event(
            event_type="ACCESS",
            user_id=user_id,
            action=f"{action} access",
            resource=resource
        )

    def log_transfer(self, user_id: str, file_path: str, destination: str,
                     status: str = "started", size_bytes: Optional[int] = None) -> None:
        """Log transfer operation"""
        details = None
        if size_bytes:
            details = f"Size: {size_bytes} bytes"

        self.log_event(
            event_type="TRANSFER",
            user_id=user_id,
            action=status,
            resource=f"{file_path} -> {destination}",
            details=details
        )

    def log_security(self, user_id: str, event: str, severity: str = "info",
                     details: Optional[str] = None) -> None:
        """Log security event"""
        status = "success" if severity == "info" else "failure"

        self.log_event(
            event_type="SECURITY",
            user_id=user_id,
            action=event,
            status=status,
            details=details
        )

    def log_api(self, user_id: str, method: str, endpoint: str,
                status_code: int, details: Optional[str] = None,
                ip_address: Optional[str] = None) -> None:
        """Log API call"""
        status = "success" if 200 <= status_code < 300 else "failure"

        self.log_event(
            event_type="API",
            user_id=user_id,
            action=f"{method} {endpoint}",
            resource=endpoint,
            status=status,
            details=f"HTTP {status_code}: {details}",
            ip_address=ip_address
        )

    def log_error(self, user_id: str, component: str, error_msg: str) -> None:
        """Log error event"""
        self.log_event(
            event_type="ERROR",
            user_id=user_id,
            action="error in component",
            resource=component,
            status="failure",
            details=error_msg
        )

    def search(self, event_type: Optional[str] = None, user_id: Optional[str] = None,
               status: Optional[str] = None, limit: int = 100) -> List[AuditEvent]:
        """
        Search audit events.
        
        Args:
            event_type: Filter by event type
            user_id: Filter by user
            status: Filter by status
            limit: Maximum results
            
        Returns:
            Matching audit events
        """
        results = []

        for event in reversed(self.events):
            if event_type and event.event_type != event_type.upper():
                continue
            if user_id and event.user_id != user_id:
                continue
            if status and event.status != status:
                continue

            results.append(event)
            if len(results) >= limit:
                break

        return results

    def get_summary(self) -> Dict[str, Any]:
        """Get audit summary"""
        return {
            'total_events': len(self.events),
            'uptime_seconds': time.time() - self.started_at,
            'by_type': self.event_counts.copy(),
            'buffer_usage_percent': (len(self.events) / self.max_entries * 100)
        }

    def export_to_list(self) -> List[Dict[str, Any]]:
        """Export all audit events as list"""
        return [event.to_dict() for event in self.events]
