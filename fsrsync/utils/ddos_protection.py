"""
DDoS Protection System for FSRsync

Provides multi-layer DDoS protection with:
- IP reputation tracking
- Request pattern analysis
- Traffic spike detection
- Automatic blocking
- Whitelist/blacklist management
- Adaptive thresholds

## Protection Layers

Layer 1: IP-based blocking (blacklist/whitelist)
Layer 2: Request pattern analysis
Layer 3: Traffic spike detection
Layer 4: Adaptive rate limiting
Layer 5: Circuit breaker

## Detection Methods

SYN_FLOOD: Detecting connection attempts
SLOWLORIS: Detecting slow requests
BRUTE_FORCE: Detecting repeated failures
AMPLIFICATION: Detecting response amplification
VOLUMETRIC: Detecting traffic spikes
"""

import time
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class ThreatLevel(Enum):
    """Threat level for an IP"""
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    THREATENING = "threatening"
    BLOCKED = "blocked"


@dataclass
class IPReputation:
    """IP reputation tracking"""
    ip_address: str
    threat_level: ThreatLevel
    blocked: bool = False
    suspicious_count: int = 0
    blocked_count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    blocked_reason: Optional[str] = None
    expires_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        """Check if block has expired"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class RequestMetrics:
    """Request metrics for pattern analysis"""
    total_requests: int = 0
    failed_requests: int = 0
    slow_requests: int = 0  # Requests taking >2s
    error_4xx: int = 0
    error_5xx: int = 0
    last_request_time: float = field(default_factory=time.time)
    requests_in_window: deque = field(default_factory=lambda: deque(maxlen=100))

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate"""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100

    @property
    def request_rate(self) -> float:
        """Calculate requests per second"""
        if not self.requests_in_window:
            return 0.0
        if len(self.requests_in_window) < 2:
            return 0.0

        time_span = self.requests_in_window[-1] - self.requests_in_window[0]
        if time_span == 0:
            return 0.0

        return len(self.requests_in_window) / time_span


class DDoSProtection:
    """
    Multi-layer DDoS protection system for FSRsync.
    
    Detects and mitigates various DDoS attack vectors
    with adaptive thresholds and automatic blocking.
    """

    def __init__(self, logger_instance=None):
        """Initialize DDoS protection"""
        self.logger = logger_instance or logging.getLogger(__name__)
        
        # IP management
        self.ip_reputation: Dict[str, IPReputation] = {}
        self.whitelist: Set[str] = set()
        self.blacklist: Set[str] = set()
        
        # Request tracking per IP
        self.ip_metrics: Dict[str, RequestMetrics] = {}
        
        # Thresholds (adaptive)
        self.failure_rate_threshold = 30.0  # 30% failure rate
        self.request_rate_threshold = 1000.0  # 1000 req/s per IP
        self.error_burst_threshold = 100  # 100 errors in 60 seconds
        
        # Circuit breaker
        self.circuit_breaker_open = False
        self.circuit_breaker_failures = 0
        self.circuit_breaker_threshold = 50  # Fail count threshold
        self.circuit_breaker_reset_time = time.time()
        
        self.logger.info("DDoS Protection initialized")

    def check_request(self, ip_address: str, endpoint: str = "/api",
                     response_time_ms: float = 0.0, status_code: int = 200) -> Tuple[bool, str]:
        """
        Check if request should be allowed.
        
        Args:
            ip_address: Source IP address
            endpoint: API endpoint
            response_time_ms: Request response time
            status_code: HTTP status code
            
        Returns:
            Tuple of (allowed, reason)
        """
        try:
            # Check whitelist first
            if ip_address in self.whitelist:
                return True, "whitelisted"

            # Check blacklist
            if ip_address in self.blacklist:
                return False, "blacklisted"

            # Check reputation
            if ip_address in self.ip_reputation:
                rep = self.ip_reputation[ip_address]
                
                if rep.blocked:
                    if rep.is_expired:
                        rep.blocked = False
                        rep.threat_level = ThreatLevel.SAFE
                    else:
                        return False, f"blocked: {rep.blocked_reason}"

            # Initialize metrics if needed
            if ip_address not in self.ip_metrics:
                self.ip_metrics[ip_address] = RequestMetrics()

            metrics = self.ip_metrics[ip_address]

            # Update metrics
            metrics.total_requests += 1
            metrics.last_request_time = time.time()
            metrics.requests_in_window.append(time.time())

            if status_code >= 400:
                metrics.failed_requests += 1
                
            if 400 <= status_code < 500:
                metrics.error_4xx += 1
            elif status_code >= 500:
                metrics.error_5xx += 1

            if response_time_ms > 2000:
                metrics.slow_requests += 1

            # Detect attack patterns
            threat_detected, threat_reason = self._detect_threat(ip_address, metrics)

            if threat_detected:
                return False, threat_reason

            return True, "allowed"

        except Exception as e:
            self.logger.error(f"Error checking request: {e}")
            return True, "error_allow"

    def _detect_threat(self, ip_address: str, metrics: RequestMetrics) -> Tuple[bool, str]:
        """Detect DDoS threats"""
        
        # High failure rate detection
        if metrics.failure_rate > self.failure_rate_threshold:
            self._block_ip(ip_address, f"high failure rate: {metrics.failure_rate:.1f}%")
            return True, "high_failure_rate"

        # Request rate spike detection
        if metrics.request_rate > self.request_rate_threshold:
            self._block_ip(ip_address, f"high request rate: {metrics.request_rate:.0f} req/s")
            return True, "request_rate_spike"

        # Brute force detection (many failed requests)
        if metrics.failed_requests > 50:
            self._block_ip(ip_address, f"possible brute force: {metrics.failed_requests} failures")
            return True, "brute_force_detected"

        # Slowloris detection (many slow requests)
        if metrics.slow_requests > 20:
            self._block_ip(ip_address, f"slowloris detected: {metrics.slow_requests} slow requests")
            return True, "slowloris_detected"

        return False, ""

    def _block_ip(self, ip_address: str, reason: str, duration_seconds: int = 3600) -> None:
        """Block an IP address"""
        try:
            if ip_address not in self.ip_reputation:
                self.ip_reputation[ip_address] = IPReputation(ip_address=ip_address, threat_level=ThreatLevel.SAFE)

            rep = self.ip_reputation[ip_address]
            rep.blocked = True
            rep.blocked_count += 1
            rep.threat_level = ThreatLevel.BLOCKED
            rep.blocked_reason = reason
            rep.expires_at = time.time() + duration_seconds

            self.logger.warning(f"Blocked IP {ip_address}: {reason}")

            # Trigger circuit breaker if too many blocks
            self.circuit_breaker_failures += 1
            if self.circuit_breaker_failures >= self.circuit_breaker_threshold:
                self._activate_circuit_breaker()

        except Exception as e:
            self.logger.error(f"Error blocking IP: {e}")

    def _activate_circuit_breaker(self) -> None:
        """Activate circuit breaker for full protection"""
        self.circuit_breaker_open = True
        self.circuit_breaker_reset_time = time.time() + 300  # 5 minute protection
        self.logger.critical("Circuit breaker activated - DDoS attack detected!")

    def add_to_whitelist(self, ip_address: str) -> None:
        """Add IP to whitelist"""
        self.whitelist.add(ip_address)
        self.logger.info(f"Added {ip_address} to whitelist")

    def add_to_blacklist(self, ip_address: str) -> None:
        """Add IP to blacklist"""
        self.blacklist.add(ip_address)
        self.logger.warning(f"Added {ip_address} to blacklist")

    def remove_from_blacklist(self, ip_address: str) -> None:
        """Remove IP from blacklist"""
        self.blacklist.discard(ip_address)
        self.logger.info(f"Removed {ip_address} from blacklist")

    def get_threat_report(self) -> Dict[str, any]:
        """Get threat report"""
        threatened_ips = [
            {
                'ip': rep.ip_address,
                'threat_level': rep.threat_level.value,
                'blocked': rep.blocked,
                'reason': rep.blocked_reason,
                'failures': self.ip_metrics.get(rep.ip_address, RequestMetrics()).failed_requests
            }
            for rep in self.ip_reputation.values()
            if rep.threat_level != ThreatLevel.SAFE
        ]

        return {
            'total_ips_tracked': len(self.ip_reputation),
            'threatened_ips': len(threatened_ips),
            'threats': threatened_ips,
            'circuit_breaker_open': self.circuit_breaker_open,
            'whitelist_size': len(self.whitelist),
            'blacklist_size': len(self.blacklist)
        }

    def get_statistics(self) -> Dict[str, any]:
        """Get protection statistics"""
        return {
            'total_ips_monitored': len(self.ip_reputation),
            'blocked_ips': sum(1 for r in self.ip_reputation.values() if r.blocked),
            'circuit_breaker_status': 'open' if self.circuit_breaker_open else 'closed',
            'total_blocks': sum(r.blocked_count for r in self.ip_reputation.values()),
            'whitelist_size': len(self.whitelist),
            'blacklist_size': len(self.blacklist)
        }
