"""
Performance Regression Testing System for FSRsync

Provides performance regression detection with:
- Baseline establishment and tracking
- Performance comparison across commits
- Statistical regression analysis
- Automated regression alerts
- Performance trend reporting
- Baseline restoration and rollback

## Regression Detection Methods

THRESHOLD: Simple percentage threshold comparison
STATISTICAL: T-test based statistical significance
TREND: Trend analysis with confidence intervals
ANOMALY: Anomaly detection against historical data
"""

import time
import logging
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics
import math


class RegressionMethod(Enum):
    """Method for detecting regression"""
    THRESHOLD = "threshold"
    STATISTICAL = "statistical"
    TREND = "trend"
    ANOMALY = "anomaly"


class RegressionSeverity(Enum):
    """Severity of regression"""
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


@dataclass
class PerformanceBaseline:
    """Baseline performance metrics"""
    baseline_id: str
    commit_hash: str
    timestamp: float
    metric_name: str
    baseline_value: float
    std_dev: float = 0.0
    sample_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class RegressionResult:
    """Regression detection result"""
    metric_name: str
    commit_hash: str
    baseline_value: float
    current_value: float
    baseline_commit: str
    percent_change: float
    severity: RegressionSeverity
    detection_method: RegressionMethod
    is_regression: bool
    confidence: float  # 0-1
    recommended_action: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class PerformanceTrend:
    """Performance trend data"""
    metric_name: str
    commits: List[str] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    trend_direction: str = "stable"  # up, down, stable
    trend_slope: float = 0.0
    trend_confidence: float = 0.0


class RegressionTester:
    """
    Performance regression testing and detection system.

    Tracks performance metrics across commits and detects
    regressions using statistical methods.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize regression tester.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Baseline storage (metric_name -> list of baselines)
        self.baselines: Dict[str, List[PerformanceBaseline]] = defaultdict(list)

        # Current measurements (metric_name -> deque of values)
        self.measurements: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Regression results (metric_name -> list of results)
        self.regression_results: Dict[str, List[RegressionResult]] = defaultdict(list)

        # Performance trends (metric_name -> PerformanceTrend)
        self.trends: Dict[str, PerformanceTrend] = {}

        # Regression detection settings
        self.threshold_percent = 10.0  # Default 10% threshold
        self.min_samples_for_detection = 5
        self.statistical_confidence = 0.95  # 95% confidence

        # Alert settings
        self.regression_alerts: deque = deque(maxlen=100)
        self.alert_thresholds: Dict[str, float] = {}  # metric_name -> threshold

        self.logger.info("RegressionTester initialized")

    def establish_baseline(self, metric_name: str, commit_hash: str,
                          values: List[float],
                          metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Establish performance baseline for a metric.

        Args:
            metric_name: Name of metric
            commit_hash: Git commit hash
            values: List of measured values
            metadata: Optional metadata

        Returns:
            Baseline ID if successful
        """
        try:
            if len(values) < 2:
                self.logger.warning(f"Not enough samples for baseline: {len(values)}")
                return None

            import uuid
            baseline_id = str(uuid.uuid4())

            mean_value = statistics.mean(values)
            std_dev = statistics.stdev(values) if len(values) > 1 else 0.0

            baseline = PerformanceBaseline(
                baseline_id=baseline_id,
                commit_hash=commit_hash,
                timestamp=time.time(),
                metric_name=metric_name,
                baseline_value=mean_value,
                std_dev=std_dev,
                sample_count=len(values),
                metadata=metadata or {}
            )

            self.baselines[metric_name].append(baseline)

            self.logger.info(
                f"Established baseline for {metric_name}: "
                f"mean={mean_value:.2f}, std_dev={std_dev:.2f}"
            )
            return baseline_id

        except Exception as e:
            self.logger.error(f"Error establishing baseline: {e}")
            return None

    def record_measurement(self, metric_name: str, value: float,
                          commit_hash: Optional[str] = None) -> None:
        """
        Record a performance measurement.

        Args:
            metric_name: Name of metric
            value: Measured value
            commit_hash: Optional commit hash
        """
        try:
            self.measurements[metric_name].append({
                'value': value,
                'timestamp': time.time(),
                'commit_hash': commit_hash
            })

        except Exception as e:
            self.logger.error(f"Error recording measurement: {e}")

    def detect_regression(self, metric_name: str,
                         method: RegressionMethod = RegressionMethod.THRESHOLD) -> Optional[RegressionResult]:
        """
        Detect performance regression for a metric.

        Args:
            metric_name: Name of metric
            method: Regression detection method

        Returns:
            RegressionResult if regression detected
        """
        try:
            if metric_name not in self.baselines or not self.baselines[metric_name]:
                return None

            if metric_name not in self.measurements or len(self.measurements[metric_name]) < self.min_samples_for_detection:
                return None

            # Get latest baseline
            latest_baseline = self.baselines[metric_name][-1]
            recent_measurements = list(self.measurements[metric_name])[-self.min_samples_for_detection:]
            current_values = [m['value'] for m in recent_measurements]
            current_mean = statistics.mean(current_values)

            # Calculate percent change
            percent_change = ((current_mean - latest_baseline.baseline_value) / latest_baseline.baseline_value) * 100

            # Detect regression based on method
            is_regression = False
            severity = RegressionSeverity.NONE
            confidence = 0.0

            if method == RegressionMethod.THRESHOLD:
                threshold = self.alert_thresholds.get(metric_name, self.threshold_percent)
                is_regression = abs(percent_change) > threshold
                confidence = min(abs(percent_change) / threshold, 1.0) if threshold > 0 else 0.0

            elif method == RegressionMethod.STATISTICAL:
                is_regression, confidence = self._statistical_regression_test(
                    latest_baseline, current_values
                )

            elif method == RegressionMethod.TREND:
                is_regression, confidence = self._trend_regression_test(
                    metric_name, current_values
                )

            elif method == RegressionMethod.ANOMALY:
                is_regression, confidence = self._anomaly_regression_test(
                    latest_baseline, current_values
                )

            # Determine severity
            if is_regression:
                severity = self._get_regression_severity(percent_change, confidence)

            result = RegressionResult(
                metric_name=metric_name,
                commit_hash=recent_measurements[-1].get('commit_hash', 'unknown'),
                baseline_value=latest_baseline.baseline_value,
                current_value=current_mean,
                baseline_commit=latest_baseline.commit_hash,
                percent_change=percent_change,
                severity=severity,
                detection_method=method,
                is_regression=is_regression,
                confidence=confidence,
                recommended_action=self._get_recommended_action(severity, percent_change)
            )

            if is_regression:
                self.regression_results[metric_name].append(result)
                self._create_alert(result)

            return result

        except Exception as e:
            self.logger.error(f"Error detecting regression: {e}")
            return None

    def _statistical_regression_test(self, baseline: PerformanceBaseline,
                                    current_values: List[float]) -> Tuple[bool, float]:
        """Perform t-test statistical regression test"""
        try:
            if baseline.std_dev == 0 or len(current_values) < 2:
                return False, 0.0

            current_mean = statistics.mean(current_values)
            current_std = statistics.stdev(current_values)

            # Simplified t-test
            t_statistic = abs(current_mean - baseline.baseline_value) / (
                math.sqrt(baseline.std_dev ** 2 + current_std ** 2)
            ) if (baseline.std_dev ** 2 + current_std ** 2) > 0 else 0

            # Critical value for 95% confidence
            critical_value = 2.0

            is_significant = t_statistic > critical_value
            confidence = min(t_statistic / critical_value, 1.0)

            return is_significant, confidence

        except Exception as e:
            self.logger.error(f"Error in statistical test: {e}")
            return False, 0.0

    def _trend_regression_test(self, metric_name: str,
                              current_values: List[float]) -> Tuple[bool, float]:
        """Detect regression based on trend analysis"""
        try:
            trend = self.trends.get(metric_name)
            if not trend or len(trend.values) < 3:
                return False, 0.0

            # Check if recent measurements exceed confidence interval
            recent_mean = statistics.mean(current_values)
            all_values = trend.values + current_values

            mean_all = statistics.mean(all_values)
            std_all = statistics.stdev(all_values) if len(all_values) > 1 else 0

            # Regression if recent mean is >2 std devs above historical mean
            z_score = abs(recent_mean - mean_all) / (std_all + 0.0001)
            is_regression = z_score > 2.0

            confidence = min(z_score / 2.0, 1.0)

            return is_regression, confidence

        except Exception as e:
            self.logger.error(f"Error in trend test: {e}")
            return False, 0.0

    def _anomaly_regression_test(self, baseline: PerformanceBaseline,
                                current_values: List[float]) -> Tuple[bool, float]:
        """Detect regression based on anomaly detection"""
        try:
            anomaly_count = 0
            current_mean = statistics.mean(current_values)

            # Count values that are >1.5 std devs away from baseline
            threshold = baseline.baseline_value + (1.5 * baseline.std_dev)

            for value in current_values:
                if value > threshold:
                    anomaly_count += 1

            anomaly_rate = anomaly_count / len(current_values)
            is_regression = anomaly_rate > 0.5  # >50% of samples are anomalies

            confidence = anomaly_rate

            return is_regression, confidence

        except Exception as e:
            self.logger.error(f"Error in anomaly test: {e}")
            return False, 0.0

    def _get_regression_severity(self, percent_change: float, confidence: float) -> RegressionSeverity:
        """Determine regression severity"""
        abs_change = abs(percent_change)

        if confidence < 0.5:
            return RegressionSeverity.NONE

        if abs_change < 5:
            return RegressionSeverity.MINOR
        elif abs_change < 15:
            return RegressionSeverity.MODERATE
        elif abs_change < 30:
            return RegressionSeverity.SEVERE
        else:
            return RegressionSeverity.CRITICAL

    def _get_recommended_action(self, severity: RegressionSeverity, percent_change: float) -> str:
        """Get recommended action for regression"""
        if severity == RegressionSeverity.NONE:
            return "No action required"
        elif severity == RegressionSeverity.MINOR:
            return f"Monitor performance; {percent_change:+.1f}% change detected"
        elif severity == RegressionSeverity.MODERATE:
            return f"Review recent changes; {percent_change:+.1f}% degradation"
        elif severity == RegressionSeverity.SEVERE:
            return f"Investigate urgently; {percent_change:+.1f}% performance loss"
        else:
            return f"Critical: {percent_change:+.1f}% performance loss; consider rollback"

    def _create_alert(self, result: RegressionResult) -> None:
        """Create regression alert"""
        try:
            alert = {
                'timestamp': time.time(),
                'metric': result.metric_name,
                'severity': result.severity.value,
                'percent_change': result.percent_change,
                'confidence': result.confidence,
                'action': result.recommended_action
            }

            self.regression_alerts.append(alert)

            self.logger.warning(
                f"REGRESSION ALERT: {result.metric_name} - "
                f"{result.severity.value} ({result.percent_change:+.1f}%)"
            )

        except Exception as e:
            self.logger.error(f"Error creating alert: {e}")

    def analyze_performance_trend(self, metric_name: str) -> Optional[PerformanceTrend]:
        """
        Analyze performance trend for metric.

        Args:
            metric_name: Name of metric

        Returns:
            PerformanceTrend if available
        """
        try:
            if metric_name not in self.measurements:
                return None

            measurements = list(self.measurements[metric_name])

            if len(measurements) < 3:
                return None

            values = [m['value'] for m in measurements]
            commits = [m.get('commit_hash', 'unknown') for m in measurements]
            timestamps = [m.get('timestamp', 0) for m in measurements]

            # Calculate linear trend
            x = list(range(len(values)))
            slope, _, _ = self._linear_regression(x, values)

            # Determine direction
            if abs(slope) < 0.001:
                direction = "stable"
            elif slope > 0:
                direction = "down" if metric_name.endswith('_latency') else "up"
            else:
                direction = "up" if metric_name.endswith('_latency') else "down"

            trend = PerformanceTrend(
                metric_name=metric_name,
                commits=commits,
                values=values,
                timestamps=timestamps,
                trend_direction=direction,
                trend_slope=slope,
                trend_confidence=min(abs(slope), 1.0)
            )

            self.trends[metric_name] = trend
            return trend

        except Exception as e:
            self.logger.error(f"Error analyzing trend: {e}")
            return None

    def _linear_regression(self, x: List[float], y: List[float]) -> Tuple[float, float, float]:
        """Perform linear regression"""
        try:
            n = len(x)
            if n < 2:
                return 0.0, 0.0, 0.0

            mean_x = statistics.mean(x)
            mean_y = statistics.mean(y)

            numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

            if denominator == 0:
                return 0.0, mean_y, 0.0

            slope = numerator / denominator
            intercept = mean_y - slope * mean_x

            # Calculate R-squared
            y_pred = [slope * x[i] + intercept for i in range(n)]
            ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
            ss_tot = sum((y[i] - mean_y) ** 2 for i in range(n))

            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            return slope, intercept, r_squared

        except Exception as e:
            self.logger.error(f"Error in linear regression: {e}")
            return 0.0, 0.0, 0.0

    def get_regression_report(self, metric_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get regression analysis report.

        Args:
            metric_name: Optional metric to filter by

        Returns:
            Regression report
        """
        try:
            if metric_name:
                results = self.regression_results.get(metric_name, [])
            else:
                results = []
                for metric_results in self.regression_results.values():
                    results.extend(metric_results)

            recent_regressions = sorted(
                [r for r in results if r.is_regression],
                key=lambda x: x.timestamp,
                reverse=True
            )[:10]

            return {
                'timestamp': time.time(),
                'total_regressions': sum(len(v) for v in self.regression_results.values()),
                'baseline_count': sum(len(v) for v in self.baselines.values()),
                'recent_alerts': list(self.regression_alerts)[-5:],
                'recent_regressions': [
                    {
                        'metric': r.metric_name,
                        'severity': r.severity.value,
                        'percent_change': r.percent_change,
                        'confidence': r.confidence,
                        'action': r.recommended_action,
                        'timestamp': r.timestamp
                    }
                    for r in recent_regressions
                ]
            }

        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            return {}

    def set_alert_threshold(self, metric_name: str, threshold_percent: float) -> None:
        """
        Set custom alert threshold for metric.

        Args:
            metric_name: Name of metric
            threshold_percent: Threshold percentage
        """
        try:
            self.alert_thresholds[metric_name] = threshold_percent
            self.logger.info(f"Set alert threshold for {metric_name}: {threshold_percent}%")

        except Exception as e:
            self.logger.error(f"Error setting threshold: {e}")

    def get_regression_summary(self) -> Dict[str, Any]:
        """Get regression system summary"""
        try:
            critical_count = sum(
                1 for alerts in self.regression_alerts
                if alerts.get('severity') == 'critical'
            )

            return {
                'timestamp': time.time(),
                'total_metrics_tracked': len(self.measurements),
                'total_baselines': sum(len(v) for v in self.baselines.values()),
                'total_regressions_detected': sum(len(v) for v in self.regression_results.values()),
                'critical_regressions': critical_count,
                'active_trends': len(self.trends),
                'pending_alerts': list(self.regression_alerts)[-10:]
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
