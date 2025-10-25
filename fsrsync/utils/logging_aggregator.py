"""
Logging Aggregation System for FSRsync

Provides centralized logging with:
- Multi-level logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Circular buffer for in-memory log storage
- Log filtering and searching
- Performance metrics logging
- Transfer event logging
- Error tracking and aggregation

## Log Levels

DEBUG: Detailed diagnostic information
INFO: General informational messages
WARNING: Warning messages for potential issues
ERROR: Error messages for failures
CRITICAL: Critical system failures

## Usage

```python
aggregator = LogAggregator(max_entries=10000)

# Log a message
aggregator.log("INFO", "Transfer started", {
    "transfer_id": "abc123",
    "file": "/path/to/file"
})

# Search logs
errors = aggregator.search(level="ERROR", limit=100)

# Get summary
summary = aggregator.get_summary()
```
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """Log level enumeration"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """Single log entry"""
    timestamp: float
    level: str
    message: str
    component: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'level': self.level,
            'message': self.message,
            'component': self.component,
            'context': self.context
        }


@dataclass
class LogSummary:
    """Summary of logged events"""
    total_entries: int
    by_level: Dict[str, int] = field(default_factory=dict)
    by_component: Dict[str, int] = field(default_factory=dict)
    recent_errors: List[LogEntry] = field(default_factory=list)
    recent_warnings: List[LogEntry] = field(default_factory=list)


class LogAggregator:
    """
    Centralized logging aggregator for FSRsync.
    
    Maintains circular buffer of logs with search and filtering
    capabilities for diagnostic and monitoring purposes.
    """

    def __init__(self, max_entries: int = 10000, logger_instance=None):
        """
        Initialize log aggregator.
        
        Args:
            max_entries: Maximum number of log entries to keep
            logger_instance: Optional Python logger instance
        """
        self.max_entries = max_entries
        self.logger = logger_instance or logging.getLogger(__name__)
        self.logs: deque = deque(maxlen=max_entries)
        self.error_count = 0
        self.warning_count = 0
        self.started_at = time.time()

    def log(self, level: str, message: str, component: str = "app",
            context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a message.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            component: Component that generated the log
            context: Additional context data
        """
        entry = LogEntry(
            timestamp=time.time(),
            level=level.upper(),
            message=message,
            component=component,
            context=context or {}
        )

        self.logs.append(entry)

        # Track counts
        if level.upper() == "ERROR":
            self.error_count += 1
        elif level.upper() == "WARNING":
            self.warning_count += 1

        # Also log to Python logger
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(f"[{component}] {message}")

    def search(self, level: Optional[str] = None, component: Optional[str] = None,
               message_filter: Optional[str] = None, limit: int = 100) -> List[LogEntry]:
        """
        Search logs with filters.
        
        Args:
            level: Filter by log level
            component: Filter by component
            message_filter: Filter by message text (substring match)
            limit: Maximum results to return
            
        Returns:
            Filtered list of log entries
        """
        results = []
        level_upper = level.upper() if level else None

        for entry in reversed(self.logs):  # Search most recent first
            if level_upper and entry.level != level_upper:
                continue
            if component and entry.component != component:
                continue
            if message_filter and message_filter.lower() not in entry.message.lower():
                continue

            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def get_recent(self, limit: int = 100) -> List[LogEntry]:
        """Get most recent log entries"""
        return list(reversed(list(self.logs)[-limit:]))

    def get_errors(self, limit: int = 50) -> List[LogEntry]:
        """Get recent error entries"""
        return self.search(level="ERROR", limit=limit)

    def get_warnings(self, limit: int = 50) -> List[LogEntry]:
        """Get recent warning entries"""
        return self.search(level="WARNING", limit=limit)

    def get_by_component(self, component: str, limit: int = 100) -> List[LogEntry]:
        """Get logs from specific component"""
        return self.search(component=component, limit=limit)

    def get_summary(self) -> LogSummary:
        """Get summary of logged events"""
        by_level: Dict[str, int] = {}
        by_component: Dict[str, int] = {}

        for entry in self.logs:
            by_level[entry.level] = by_level.get(entry.level, 0) + 1
            by_component[entry.component] = by_component.get(entry.component, 0) + 1

        return LogSummary(
            total_entries=len(self.logs),
            by_level=by_level,
            by_component=by_component,
            recent_errors=self.get_errors(10),
            recent_warnings=self.get_warnings(10)
        )

    def clear(self) -> None:
        """Clear all logs"""
        self.logs.clear()
        self.error_count = 0
        self.warning_count = 0

    def export_to_list(self) -> List[Dict[str, Any]]:
        """Export all logs as list of dictionaries"""
        return [entry.to_dict() for entry in self.logs]

    def get_health_stats(self) -> Dict[str, Any]:
        """Get health statistics from logs"""
        summary = self.get_summary()
        uptime = time.time() - self.started_at

        return {
            'uptime_seconds': uptime,
            'total_entries': summary.total_entries,
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'errors_per_hour': (self.error_count / uptime * 3600) if uptime > 0 else 0,
            'by_level': summary.by_level,
            'by_component': summary.by_component,
            'buffer_usage_percent': (len(self.logs) / self.max_entries * 100)
        }
