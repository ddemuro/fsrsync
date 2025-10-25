"""
Advanced Analytics Engine for FSRsync

Provides comprehensive analytics with:
- Real-time data aggregation
- Time-series analysis
- Trend detection
- Anomaly detection
- Forecasting
- Correlation analysis
- Custom metrics computation

## Analytics Dimensions

TIME_SERIES: Historical trend analysis
COMPARISON: Multi-metric comparisons
DISTRIBUTION: Statistical distributions
CORRELATION: Metric correlations
ANOMALY: Anomaly detection and alerting
FORECAST: Predictive analysis
"""

import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics
import math


class AnalyticsType(Enum):
    """Type of analytics"""
    TIME_SERIES = "time_series"
    COMPARISON = "comparison"
    DISTRIBUTION = "distribution"
    CORRELATION = "correlation"
    ANOMALY = "anomaly"
    FORECAST = "forecast"


class TrendDirection(Enum):
    """Trend direction"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class DataPoint:
    """Single data point for analytics"""
    timestamp: float
    value: float
    metric_name: str
    category: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TrendAnalysis:
    """Trend analysis result"""
    metric_name: str
    direction: TrendDirection
    slope: float  # Change per time unit
    r_squared: float  # Goodness of fit
    start_value: float
    end_value: float
    percent_change: float
    confidence: float  # 0-1


@dataclass
class AnomalyDetection:
    """Anomaly detection result"""
    metric_name: str
    timestamp: float
    value: float
    expected_value: float
    deviation_std: float  # Standard deviations from mean
    is_anomaly: bool
    severity: str  # low, medium, high, critical


@dataclass
class Forecast:
    """Forecasting result"""
    metric_name: str
    forecast_type: str  # linear, exponential, seasonal
    current_value: float
    predicted_value: float
    confidence_interval: Tuple[float, float]
    time_period: int  # seconds
    accuracy: float  # 0-1


class AnalyticsEngine:
    """
    Advanced analytics engine for FSRsync.

    Provides comprehensive analytics including trend detection,
    anomaly detection, forecasting, and correlation analysis.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize analytics engine.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Data storage (metric_name -> deque of DataPoints)
        self.metrics_data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))

        # Cached analyses
        self.trends: Dict[str, TrendAnalysis] = {}
        self.anomalies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.forecasts: Dict[str, Forecast] = {}

        # Correlation matrix
        self.correlations: Dict[str, float] = {}

        # Anomaly detection settings
        self.anomaly_threshold = 2.5  # Standard deviations
        self.min_samples_for_analysis = 10

        # Forecasting settings
        self.forecast_period = 3600  # 1 hour
        self.forecast_lookback = 86400  # 1 day of historical data

        self.logger.info("AnalyticsEngine initialized")

    def add_data_point(self, metric_name: str, value: float, category: str = "",
                      tags: Optional[Dict[str, str]] = None) -> None:
        """
        Add a data point for analytics.

        Args:
            metric_name: Name of metric
            value: Metric value
            category: Metric category
            tags: Optional tags
        """
        try:
            point = DataPoint(
                timestamp=time.time(),
                value=value,
                metric_name=metric_name,
                category=category,
                tags=tags or {}
            )

            self.metrics_data[metric_name].append(point)

        except Exception as e:
            self.logger.error(f"Error adding data point: {e}")

    def get_trend(self, metric_name: str, lookback_seconds: int = 3600) -> Optional[TrendAnalysis]:
        """
        Analyze trend for metric.

        Args:
            metric_name: Name of metric
            lookback_seconds: Time period to analyze

        Returns:
            TrendAnalysis if available
        """
        try:
            if metric_name not in self.metrics_data:
                return None

            points = list(self.metrics_data[metric_name])

            if len(points) < self.min_samples_for_analysis:
                return None

            # Filter by time window
            now = time.time()
            recent_points = [p for p in points if (now - p.timestamp) <= lookback_seconds]

            if len(recent_points) < self.min_samples_for_analysis:
                return None

            # Calculate linear regression
            x = [(p.timestamp - recent_points[0].timestamp) / 60 for p in recent_points]  # Convert to minutes
            y = [p.value for p in recent_points]

            slope, intercept, r_squared = self._linear_regression(x, y)

            start_value = recent_points[0].value
            end_value = recent_points[-1].value
            percent_change = ((end_value - start_value) / start_value * 100) if start_value != 0 else 0

            # Determine direction
            if abs(slope) < 0.01:
                direction = TrendDirection.STABLE
            elif slope > 0:
                direction = TrendDirection.UP
            else:
                direction = TrendDirection.DOWN

            trend = TrendAnalysis(
                metric_name=metric_name,
                direction=direction,
                slope=slope,
                r_squared=r_squared,
                start_value=start_value,
                end_value=end_value,
                percent_change=percent_change,
                confidence=min(r_squared, 1.0)
            )

            self.trends[metric_name] = trend
            return trend

        except Exception as e:
            self.logger.error(f"Error analyzing trend: {e}")
            return None

    def detect_anomalies(self, metric_name: str, lookback_seconds: int = 3600) -> List[AnomalyDetection]:
        """
        Detect anomalies in metric data.

        Args:
            metric_name: Name of metric
            lookback_seconds: Time period to analyze

        Returns:
            List of detected anomalies
        """
        try:
            if metric_name not in self.metrics_data:
                return []

            points = list(self.metrics_data[metric_name])

            if len(points) < self.min_samples_for_analysis:
                return []

            # Filter by time window
            now = time.time()
            recent_points = [p for p in points if (now - p.timestamp) <= lookback_seconds]

            if len(recent_points) < self.min_samples_for_analysis:
                return []

            # Calculate mean and std dev
            values = [p.value for p in recent_points]
            mean_value = statistics.mean(values)
            std_dev = statistics.stdev(values) if len(values) > 1 else 0

            anomalies = []

            # Detect anomalies (values outside threshold)
            for point in recent_points[-10:]:  # Check last 10 points
                if std_dev > 0:
                    deviation = abs(point.value - mean_value) / std_dev
                else:
                    deviation = 0

                is_anomaly = deviation > self.anomaly_threshold

                anomaly = AnomalyDetection(
                    metric_name=metric_name,
                    timestamp=point.timestamp,
                    value=point.value,
                    expected_value=mean_value,
                    deviation_std=deviation,
                    is_anomaly=is_anomaly,
                    severity=self._get_anomaly_severity(deviation)
                )

                if is_anomaly:
                    anomalies.append(anomaly)
                    self.anomalies[metric_name].append(anomaly)

            return anomalies

        except Exception as e:
            self.logger.error(f"Error detecting anomalies: {e}")
            return []

    def forecast(self, metric_name: str, method: str = "linear") -> Optional[Forecast]:
        """
        Forecast future metric values.

        Args:
            metric_name: Name of metric
            method: Forecasting method (linear, exponential)

        Returns:
            Forecast if available
        """
        try:
            if metric_name not in self.metrics_data:
                return None

            points = list(self.metrics_data[metric_name])

            if len(points) < self.min_samples_for_analysis:
                return None

            # Filter by lookback window
            now = time.time()
            historical_points = [p for p in points if (now - p.timestamp) <= self.forecast_lookback]

            if len(historical_points) < self.min_samples_for_analysis:
                return None

            current_value = historical_points[-1].value
            x = [(p.timestamp - historical_points[0].timestamp) / 60 for p in historical_points]
            y = [p.value for p in historical_points]

            if method == "linear":
                slope, intercept, r_squared = self._linear_regression(x, y)
                # Predict next period
                future_x = x[-1] + (self.forecast_period / 60)
                predicted_value = slope * future_x + intercept
                confidence_low = predicted_value * 0.9
                confidence_high = predicted_value * 1.1
                accuracy = r_squared

            elif method == "exponential":
                # Simple exponential smoothing
                alpha = 0.3
                smoothed = y[0]
                for val in y[1:]:
                    smoothed = alpha * val + (1 - alpha) * smoothed

                predicted_value = smoothed
                trend = (smoothed - y[-1]) if len(y) > 1 else 0
                predicted_value += trend
                confidence_low = predicted_value * 0.85
                confidence_high = predicted_value * 1.15
                accuracy = 0.7

            else:
                return None

            forecast = Forecast(
                metric_name=metric_name,
                forecast_type=method,
                current_value=current_value,
                predicted_value=predicted_value,
                confidence_interval=(confidence_low, confidence_high),
                time_period=self.forecast_period,
                accuracy=accuracy
            )

            self.forecasts[metric_name] = forecast
            return forecast

        except Exception as e:
            self.logger.error(f"Error forecasting: {e}")
            return None

    def calculate_correlation(self, metric1: str, metric2: str) -> float:
        """
        Calculate correlation between two metrics.

        Args:
            metric1: First metric name
            metric2: Second metric name

        Returns:
            Correlation coefficient (-1 to 1)
        """
        try:
            if metric1 not in self.metrics_data or metric2 not in self.metrics_data:
                return 0.0

            points1 = list(self.metrics_data[metric1])
            points2 = list(self.metrics_data[metric2])

            if len(points1) < self.min_samples_for_analysis or len(points2) < self.min_samples_for_analysis:
                return 0.0

            # Align timestamps and get values
            min_len = min(len(points1), len(points2))
            values1 = [p.value for p in points1[-min_len:]]
            values2 = [p.value for p in points2[-min_len:]]

            correlation = self._pearson_correlation(values1, values2)

            key = f"{metric1}:{metric2}"
            self.correlations[key] = correlation

            return correlation

        except Exception as e:
            self.logger.error(f"Error calculating correlation: {e}")
            return 0.0

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

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        try:
            n = len(x)
            if n < 2:
                return 0.0

            mean_x = statistics.mean(x)
            mean_y = statistics.mean(y)

            numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
            sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))

            denominator = math.sqrt(sum_sq_x * sum_sq_y)

            if denominator == 0:
                return 0.0

            return numerator / denominator

        except Exception as e:
            self.logger.error(f"Error calculating correlation: {e}")
            return 0.0

    def _get_anomaly_severity(self, deviation: float) -> str:
        """Determine anomaly severity"""
        if deviation < 2.5:
            return "low"
        elif deviation < 3.5:
            return "medium"
        elif deviation < 4.5:
            return "high"
        else:
            return "critical"

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get summary of all analytics"""
        try:
            return {
                'timestamp': time.time(),
                'metrics_tracked': len(self.metrics_data),
                'trends_analyzed': len(self.trends),
                'anomalies_detected': sum(len(v) for v in self.anomalies.values()),
                'forecasts_generated': len(self.forecasts),
                'correlations_calculated': len(self.correlations),
                'trends': {
                    name: {
                        'direction': trend.direction.value,
                        'slope': trend.slope,
                        'percent_change': trend.percent_change,
                        'confidence': trend.confidence
                    }
                    for name, trend in list(self.trends.items())[:10]
                },
                'recent_anomalies': {
                    name: [
                        {
                            'value': a.value,
                            'expected': a.expected_value,
                            'deviation_std': a.deviation_std,
                            'severity': a.severity
                        }
                        for a in list(self.anomalies[name])[-5:]
                    ]
                    for name in list(self.anomalies.keys())[:5]
                }
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
