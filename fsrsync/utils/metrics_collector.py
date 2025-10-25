"""
Comprehensive Metrics Collection System for FSRsync

Provides centralized metrics collection with:
- Multi-component monitoring
- Time-series data storage
- Metric aggregation and rollup
- Export capabilities
- Integration with monitoring systems

## Metric Categories

SYNC: File synchronization metrics
TRANSFER: File transfer metrics
PEER: Peer connection metrics
CONFLICT: Conflict detection metrics
NETWORK: Network performance metrics
SYSTEM: System resource metrics
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import json


class MetricCategory(Enum):
    """Metric category"""
    SYNC = "sync"
    TRANSFER = "transfer"
    PEER = "peer"
    CONFLICT = "conflict"
    NETWORK = "network"
    SYSTEM = "system"


class AggregationType(Enum):
    """Aggregation type for rollup"""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"


@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: float = field(default_factory=time.time)
    category: MetricCategory = MetricCategory.SYSTEM
    name: str = ""
    value: float = 0.0
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricTimeSeries:
    """Time series of metric values"""
    category: MetricCategory
    name: str
    unit: str
    points: deque = field(default_factory=lambda: deque(maxlen=10000))
    tags: Dict[str, str] = field(default_factory=dict)

    def add_point(self, value: float, timestamp: Optional[float] = None) -> None:
        """Add point to time series"""
        if timestamp is None:
            timestamp = time.time()

        point = MetricPoint(
            timestamp=timestamp,
            category=self.category,
            name=self.name,
            value=value,
            unit=self.unit,
            tags=self.tags
        )

        self.points.append(point)

    def get_stats(self) -> Dict[str, float]:
        """Get statistics for time series"""
        if not self.points:
            return {}

        values = [p.value for p in self.points]

        return {
            'count': len(values),
            'sum': sum(values),
            'avg': sum(values) / len(values),
            'min': min(values),
            'max': max(values),
            'latest': values[-1] if values else 0
        }


class MetricsCollector:
    """
    Centralized metrics collection system.

    Collects metrics from all components and provides
    aggregation, rollup, and export capabilities.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize metrics collector.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Time series storage
        self.time_series: Dict[str, MetricTimeSeries] = {}

        # Event metrics
        self.event_counters: Dict[str, int] = defaultdict(int)
        self.event_totals: Dict[str, float] = defaultdict(float)

        # Performance metrics
        self.latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.throughputs: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Component metrics
        self.component_status: Dict[str, Dict[str, Any]] = {}

        # Alerts and thresholds
        self.alerts: deque = deque(maxlen=1000)
        self.thresholds: Dict[str, Tuple[float, float]] = {}  # min, max

        self.logger.info("MetricsCollector initialized")

    def record_metric(self, category: str, name: str, value: float,
                     unit: str = "", tags: Optional[Dict[str, str]] = None) -> None:
        """
        Record a metric value.

        Args:
            category: Metric category
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            tags: Optional metric tags
        """
        try:
            cat = MetricCategory(category.lower())
            key = f"{category}_{name}"

            # Create or get time series
            if key not in self.time_series:
                self.time_series[key] = MetricTimeSeries(
                    category=cat,
                    name=name,
                    unit=unit,
                    tags=tags or {}
                )

            # Add point
            self.time_series[key].add_point(value)

            # Check threshold
            self._check_threshold(key, value)

        except Exception as e:
            self.logger.error(f"Error recording metric: {e}")

    def record_event(self, category: str, event_type: str, count: int = 1,
                    total: float = 0.0) -> None:
        """
        Record an event metric.

        Args:
            category: Metric category
            event_type: Type of event
            count: Number of events
            total: Total value for events
        """
        try:
            key = f"{category}_{event_type}"

            self.event_counters[key] += count
            self.event_totals[key] += total

        except Exception as e:
            self.logger.error(f"Error recording event: {e}")

    def record_latency(self, operation: str, latency_ms: float) -> None:
        """
        Record operation latency.

        Args:
            operation: Operation name
            latency_ms: Latency in milliseconds
        """
        try:
            self.latencies[operation].append(latency_ms)
            self.record_metric("sync", f"{operation}_latency", latency_ms, "ms")

        except Exception as e:
            self.logger.error(f"Error recording latency: {e}")

    def record_throughput(self, operation: str, throughput_mbps: float) -> None:
        """
        Record operation throughput.

        Args:
            operation: Operation name
            throughput_mbps: Throughput in MB/s
        """
        try:
            self.throughputs[operation].append(throughput_mbps)
            self.record_metric("transfer", f"{operation}_throughput", throughput_mbps, "MB/s")

        except Exception as e:
            self.logger.error(f"Error recording throughput: {e}")

    def set_component_status(self, component: str, status: Dict[str, Any]) -> None:
        """
        Set component status and metrics.

        Args:
            component: Component name
            status: Status dictionary
        """
        try:
            self.component_status[component] = {
                'status': status,
                'timestamp': time.time()
            }

        except Exception as e:
            self.logger.error(f"Error setting component status: {e}")

    def _check_threshold(self, metric_key: str, value: float) -> None:
        """Check if metric exceeds threshold and create alert"""
        try:
            if metric_key not in self.thresholds:
                return

            min_val, max_val = self.thresholds[metric_key]

            if value < min_val or value > max_val:
                alert = {
                    'timestamp': time.time(),
                    'metric': metric_key,
                    'value': value,
                    'threshold_min': min_val,
                    'threshold_max': max_val
                }

                self.alerts.append(alert)

                self.logger.warning(
                    f"Metric {metric_key} = {value} out of threshold "
                    f"({min_val}-{max_val})"
                )

        except Exception as e:
            self.logger.error(f"Error checking threshold: {e}")

    def set_threshold(self, metric_key: str, min_val: float, max_val: float) -> None:
        """Set threshold for metric"""
        self.thresholds[metric_key] = (min_val, max_val)
        self.logger.info(f"Set threshold for {metric_key}: {min_val}-{max_val}")

    def get_metric_stats(self, category: str, name: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a metric"""
        try:
            key = f"{category}_{name}"

            if key not in self.time_series:
                return None

            ts = self.time_series[key]
            stats = ts.get_stats()

            return {
                'category': category,
                'name': name,
                'unit': ts.unit,
                'tags': ts.tags,
                'stats': stats,
                'point_count': len(ts.points)
            }

        except Exception as e:
            self.logger.error(f"Error getting metric stats: {e}")
            return None

    def get_latency_stats(self, operation: str) -> Dict[str, Any]:
        """Get latency statistics"""
        try:
            if operation not in self.latencies or not self.latencies[operation]:
                return {}

            latencies = list(self.latencies[operation])

            return {
                'operation': operation,
                'count': len(latencies),
                'min_ms': min(latencies),
                'max_ms': max(latencies),
                'avg_ms': sum(latencies) / len(latencies),
                'latest_ms': latencies[-1] if latencies else 0
            }

        except Exception as e:
            self.logger.error(f"Error getting latency stats: {e}")
            return {}

    def get_throughput_stats(self, operation: str) -> Dict[str, Any]:
        """Get throughput statistics"""
        try:
            if operation not in self.throughputs or not self.throughputs[operation]:
                return {}

            throughputs = list(self.throughputs[operation])

            return {
                'operation': operation,
                'count': len(throughputs),
                'min_mbps': min(throughputs),
                'max_mbps': max(throughputs),
                'avg_mbps': sum(throughputs) / len(throughputs),
                'latest_mbps': throughputs[-1] if throughputs else 0
            }

        except Exception as e:
            self.logger.error(f"Error getting throughput stats: {e}")
            return {}

    def aggregate_metrics(self, category: str = None,
                         aggregation_type: str = "avg") -> Dict[str, Any]:
        """
        Aggregate metrics across time series.

        Args:
            category: Filter by category (None for all)
            aggregation_type: Type of aggregation

        Returns:
            Aggregated metrics
        """
        try:
            agg_type = AggregationType(aggregation_type.lower())
            result = {}

            for key, ts in self.time_series.items():
                # Filter by category if specified
                if category and ts.category.value != category:
                    continue

                stats = ts.get_stats()

                if agg_type == AggregationType.SUM:
                    result[key] = stats.get('sum', 0)
                elif agg_type == AggregationType.AVG:
                    result[key] = stats.get('avg', 0)
                elif agg_type == AggregationType.MIN:
                    result[key] = stats.get('min', 0)
                elif agg_type == AggregationType.MAX:
                    result[key] = stats.get('max', 0)
                elif agg_type == AggregationType.COUNT:
                    result[key] = stats.get('count', 0)

            return result

        except Exception as e:
            self.logger.error(f"Error aggregating metrics: {e}")
            return {}

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        try:
            summary = {
                'timestamp': time.time(),
                'time_series_count': len(self.time_series),
                'event_types': len(self.event_counters),
                'total_events': sum(self.event_counters.values()),
                'active_alerts': len(self.alerts),
                'components': len(self.component_status),
                'time_series': {},
                'events': {},
                'components': {}
            }

            # Add time series summaries
            for key, ts in self.time_series.items():
                stats = ts.get_stats()
                summary['time_series'][key] = {
                    'unit': ts.unit,
                    'stats': stats
                }

            # Add event summaries
            for key in sorted(set(k.rsplit('_', 1)[0] for k in self.event_counters.keys())):
                count_key = f"{key}_count"
                total_key = f"{key}_total"

                if count_key in self.event_counters or total_key in self.event_counters:
                    summary['events'][key] = {
                        'count': self.event_counters.get(count_key, 0),
                        'total': self.event_totals.get(total_key, 0)
                    }

            # Add component status
            for component, data in self.component_status.items():
                summary['components'][component] = data['status']

            return summary

        except Exception as e:
            self.logger.error(f"Error getting metrics summary: {e}")
            return {}

    def export_metrics(self, filename: str) -> bool:
        """Export metrics to JSON file"""
        try:
            summary = self.get_metrics_summary()

            with open(filename, 'w') as f:
                json.dump(summary, f, indent=2, default=str)

            self.logger.info(f"Exported metrics to {filename}")
            return True

        except Exception as e:
            self.logger.error(f"Error exporting metrics: {e}")
            return False

    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent alerts"""
        return list(reversed(list(self.alerts)))[:limit]
