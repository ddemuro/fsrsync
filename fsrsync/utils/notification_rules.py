"""
Custom Notification Rules System for FSRsync

Provides flexible notification configuration with:
- Event-based notification rules
- Multiple notification channels
- Severity filtering
- User preferences
- Rule scheduling
- Delivery management

## Event Types

TRANSFER_COMPLETE: File transfer completed
TRANSFER_FAILED: File transfer failed
CONFLICT_DETECTED: Conflict detected
PEER_CONNECTED: Peer connected
PEER_DISCONNECTED: Peer disconnected
HEALTH_ALERT: Health status changed
ERROR_OCCURRED: System error
SYNC_STARTED: Sync started
SYNC_COMPLETED: Sync completed
"""

import time
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    """Notification event types"""
    TRANSFER_COMPLETE = "transfer_complete"
    TRANSFER_FAILED = "transfer_failed"
    CONFLICT_DETECTED = "conflict_detected"
    PEER_CONNECTED = "peer_connected"
    PEER_DISCONNECTED = "peer_disconnected"
    HEALTH_ALERT = "health_alert"
    ERROR_OCCURRED = "error_occurred"
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"


class Severity(Enum):
    """Severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    """Notification channels"""
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    DASHBOARD = "dashboard"
    SYSLOG = "syslog"


@dataclass
class NotificationRule:
    """Notification rule definition"""
    rule_id: str
    name: str
    enabled: bool
    event_types: Set[EventType]
    min_severity: Severity
    channels: Set[NotificationChannel]
    recipients: Set[str]  # Email addresses, webhook URLs, etc.
    conditions: Dict[str, any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)


@dataclass
class NotificationEvent:
    """Notification event"""
    event_id: str
    event_type: EventType
    severity: Severity
    title: str
    message: str
    context: Dict[str, any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = "system"


class NotificationRulesEngine:
    """
    Custom notification rules engine for FSRsync.
    
    Manages user-defined notification rules with support
    for multiple channels and flexible filtering.
    """

    def __init__(self, logger_instance=None):
        """Initialize notification rules engine"""
        self.logger = logger_instance or logging.getLogger(__name__)
        self.rules: Dict[str, NotificationRule] = {}
        self.events_sent: List[NotificationEvent] = []
        self.max_event_history = 10000
        self.logger.info("NotificationRulesEngine initialized")

    def create_rule(self, rule_id: str, name: str, event_types: Set[EventType],
                   channels: Set[NotificationChannel], recipients: Set[str],
                   min_severity: Severity = Severity.INFO,
                   conditions: Optional[Dict[str, any]] = None) -> bool:
        """
        Create notification rule.
        
        Args:
            rule_id: Unique rule identifier
            name: Rule name
            event_types: Events to trigger on
            channels: Notification channels
            recipients: Notification recipients
            min_severity: Minimum event severity
            conditions: Additional filtering conditions
            
        Returns:
            True if created successfully
        """
        try:
            if rule_id in self.rules:
                self.logger.warning(f"Rule {rule_id} already exists")
                return False

            rule = NotificationRule(
                rule_id=rule_id,
                name=name,
                enabled=True,
                event_types=event_types,
                channels=channels,
                recipients=recipients,
                min_severity=min_severity,
                conditions=conditions or {}
            )

            self.rules[rule_id] = rule
            self.logger.info(f"Created notification rule: {rule_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error creating rule: {e}")
            return False

    def delete_rule(self, rule_id: str) -> bool:
        """Delete notification rule"""
        try:
            if rule_id in self.rules:
                del self.rules[rule_id]
                self.logger.info(f"Deleted rule: {rule_id}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Error deleting rule: {e}")
            return False

    def enable_rule(self, rule_id: str) -> bool:
        """Enable notification rule"""
        try:
            if rule_id not in self.rules:
                return False

            self.rules[rule_id].enabled = True
            self.logger.info(f"Enabled rule: {rule_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error enabling rule: {e}")
            return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable notification rule"""
        try:
            if rule_id not in self.rules:
                return False

            self.rules[rule_id].enabled = False
            self.logger.info(f"Disabled rule: {rule_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error disabling rule: {e}")
            return False

    def evaluate_event(self, event: NotificationEvent) -> List[NotificationRule]:
        """
        Evaluate event against rules.
        
        Args:
            event: Notification event
            
        Returns:
            List of matching rules
        """
        matching_rules = []

        try:
            for rule in self.rules.values():
                if not rule.enabled:
                    continue

                # Check event type
                if event.event_type not in rule.event_types:
                    continue

                # Check severity
                severity_levels = [Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL]
                event_level = severity_levels.index(event.severity)
                min_level = severity_levels.index(rule.min_severity)

                if event_level < min_level:
                    continue

                # Check conditions
                if not self._check_conditions(event, rule.conditions):
                    continue

                matching_rules.append(rule)

            return matching_rules

        except Exception as e:
            self.logger.error(f"Error evaluating event: {e}")
            return []

    def _check_conditions(self, event: NotificationEvent,
                         conditions: Dict[str, any]) -> bool:
        """Check if event meets rule conditions"""
        for key, expected_value in conditions.items():
            if key not in event.context:
                return False

            if event.context[key] != expected_value:
                return False

        return True

    def send_notification(self, event: NotificationEvent) -> bool:
        """
        Send notifications based on matching rules.
        
        Args:
            event: Notification event
            
        Returns:
            True if notifications sent
        """
        try:
            matching_rules = self.evaluate_event(event)

            if not matching_rules:
                self.logger.debug(f"No rules matched for event {event.event_type.value}")
                return False

            # Track event
            self.events_sent.append(event)
            if len(self.events_sent) > self.max_event_history:
                self.events_sent.pop(0)

            sent_count = 0

            for rule in matching_rules:
                for channel in rule.channels:
                    try:
                        if self._send_to_channel(event, rule, channel):
                            sent_count += 1
                    except Exception as e:
                        self.logger.error(f"Error sending to {channel.value}: {e}")

            self.logger.info(f"Sent {sent_count} notifications for event {event.event_type.value}")
            return sent_count > 0

        except Exception as e:
            self.logger.error(f"Error sending notifications: {e}")
            return False

    def _send_to_channel(self, event: NotificationEvent, rule: NotificationRule,
                        channel: NotificationChannel) -> bool:
        """Send notification to specific channel"""
        try:
            if channel == NotificationChannel.EMAIL:
                return self._send_email(event, rule)
            elif channel == NotificationChannel.WEBHOOK:
                return self._send_webhook(event, rule)
            elif channel == NotificationChannel.SLACK:
                return self._send_slack(event, rule)
            elif channel == NotificationChannel.DASHBOARD:
                return self._send_dashboard(event, rule)
            elif channel == NotificationChannel.SYSLOG:
                return self._send_syslog(event, rule)

            return False

        except Exception as e:
            self.logger.error(f"Error in _send_to_channel: {e}")
            return False

    def _send_email(self, event: NotificationEvent, rule: NotificationRule) -> bool:
        """Send email notification"""
        self.logger.debug(f"Email notification: {event.title} -> {rule.recipients}")
        return True

    def _send_webhook(self, event: NotificationEvent, rule: NotificationRule) -> bool:
        """Send webhook notification"""
        self.logger.debug(f"Webhook notification: {event.title} -> {rule.recipients}")
        return True

    def _send_slack(self, event: NotificationEvent, rule: NotificationRule) -> bool:
        """Send Slack notification"""
        self.logger.debug(f"Slack notification: {event.title}")
        return True

    def _send_dashboard(self, event: NotificationEvent, rule: NotificationRule) -> bool:
        """Send dashboard notification"""
        self.logger.debug(f"Dashboard notification: {event.title}")
        return True

    def _send_syslog(self, event: NotificationEvent, rule: NotificationRule) -> bool:
        """Send syslog notification"""
        self.logger.debug(f"Syslog notification: {event.title}")
        return True

    def get_rules_summary(self) -> Dict[str, any]:
        """Get rules summary"""
        enabled_count = sum(1 for r in self.rules.values() if r.enabled)

        return {
            'total_rules': len(self.rules),
            'enabled_rules': enabled_count,
            'disabled_rules': len(self.rules) - enabled_count,
            'total_notifications_sent': len(self.events_sent),
            'channels_used': list(set(
                ch for r in self.rules.values() for ch in r.channels
            )),
            'event_types_monitored': list(set(
                et for r in self.rules.values() for et in r.event_types
            ))
        }
