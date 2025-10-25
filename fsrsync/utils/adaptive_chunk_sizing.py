"""
Adaptive Chunk Sizing System for FSRsync

Provides intelligent, real-time chunk size optimization with:
- Network condition adaptation
- File characteristic analysis
- Performance-based feedback loop
- CPU and memory awareness
- Historical performance tracking
- Predictive sizing based on patterns

## Sizing Strategies

CONSERVATIVE: Small chunks for low-bandwidth or high-latency networks
BALANCED: Medium chunks for typical conditions
AGGRESSIVE: Large chunks for high-bandwidth, low-latency networks
ADAPTIVE: Automatically adjusts based on real-time conditions
PREDICTIVE: Uses ML-like pattern matching on historical data
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics


class SizingStrategy(Enum):
    """Chunk sizing strategy"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    ADAPTIVE = "adaptive"
    PREDICTIVE = "predictive"


@dataclass
class NetworkConditions:
    """Current network conditions"""
    bandwidth_mbps: float
    latency_ms: float
    packet_loss_percent: float = 0.0
    jitter_ms: float = 0.0
    connection_age_seconds: float = 0.0


@dataclass
class SystemResources:
    """Current system resource availability"""
    available_memory_mb: float
    available_cpu_percent: float
    disk_io_utilization: float = 0.0
    thread_count: int = 0


@dataclass
class ChunkSizeRecommendation:
    """Chunk size recommendation"""
    recommended_size: int
    min_size: int
    max_size: int
    strategy: SizingStrategy
    confidence: float  # 0-1
    estimated_throughput_mbps: float
    estimated_latency_impact_ms: float
    reasoning: str


@dataclass
class SizingMetrics:
    """Metrics for chunk sizing decision"""
    file_size: int
    file_type: str
    network_bandwidth: float
    network_latency: float
    memory_available: float
    cpu_available: float
    historic_throughput: float = 0.0
    throughput_trend: float = 0.0  # positive = improving
    successful_transfers: int = 0
    failed_transfers: int = 0


class AdaptiveChunkSizer:
    """
    Intelligent chunk sizing optimizer.

    Dynamically adjusts chunk sizes based on network conditions,
    file characteristics, and historical performance.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize adaptive chunk sizer.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Sizing parameters
        self.min_chunk_size = 64 * 1024  # 64KB
        self.max_chunk_size = 256 * 1024 * 1024  # 256MB
        self.default_chunk_size = 4 * 1024 * 1024  # 4MB

        # Current strategy
        self.current_strategy = SizingStrategy.ADAPTIVE

        # Metrics history (file_type -> deque of metrics)
        self.performance_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Size recommendations history
        self.sizing_history: deque = deque(maxlen=500)

        # Network profile cache (bandwidth_range -> avg_optimal_chunk_size)
        self.network_profiles: Dict[Tuple[float, float], float] = {}

        # File type optimal sizes
        self.file_type_preferences: Dict[str, Dict[str, int]] = {
            "text": {"small_net": 512 * 1024, "medium_net": 2 * 1024 * 1024, "large_net": 8 * 1024 * 1024},
            "code": {"small_net": 512 * 1024, "medium_net": 2 * 1024 * 1024, "large_net": 8 * 1024 * 1024},
            "binary": {"small_net": 1 * 1024 * 1024, "medium_net": 4 * 1024 * 1024, "large_net": 16 * 1024 * 1024},
            "video": {"small_net": 8 * 1024 * 1024, "medium_net": 32 * 1024 * 1024, "large_net": 128 * 1024 * 1024},
            "image": {"small_net": 2 * 1024 * 1024, "medium_net": 8 * 1024 * 1024, "large_net": 32 * 1024 * 1024},
            "archive": {"small_net": 4 * 1024 * 1024, "medium_net": 16 * 1024 * 1024, "large_net": 64 * 1024 * 1024},
        }

        # Lock for thread safety
        self.lock = threading.Lock()

        self.logger.info("AdaptiveChunkSizer initialized")

    def recommend_chunk_size(self, metrics: SizingMetrics,
                            network: NetworkConditions,
                            resources: SystemResources) -> ChunkSizeRecommendation:
        """
        Recommend optimal chunk size based on all factors.

        Args:
            metrics: Sizing metrics
            network: Network conditions
            resources: System resources

        Returns:
            ChunkSizeRecommendation
        """
        try:
            # Calculate base size recommendations from different strategies
            conservative_size = self._calculate_conservative_size(metrics, network, resources)
            balanced_size = self._calculate_balanced_size(metrics, network, resources)
            aggressive_size = self._calculate_aggressive_size(metrics, network, resources)
            adaptive_size = self._calculate_adaptive_size(metrics, network, resources)
            predictive_size = self._calculate_predictive_size(metrics, network, resources)

            # Select based on current strategy
            if self.current_strategy == SizingStrategy.CONSERVATIVE:
                recommended = conservative_size
            elif self.current_strategy == SizingStrategy.BALANCED:
                recommended = balanced_size
            elif self.current_strategy == SizingStrategy.AGGRESSIVE:
                recommended = aggressive_size
            elif self.current_strategy == SizingStrategy.PREDICTIVE:
                recommended = predictive_size
            else:  # ADAPTIVE
                recommended = adaptive_size

            # Constrain to valid range
            recommended = max(self.min_chunk_size, min(recommended, self.max_chunk_size))

            # Calculate confidence and throughput estimates
            confidence = self._calculate_confidence(metrics, network, resources)
            estimated_throughput = self._estimate_throughput(recommended, network, resources)
            latency_impact = self._estimate_latency_impact(recommended, network)

            recommendation = ChunkSizeRecommendation(
                recommended_size=recommended,
                min_size=self.min_chunk_size,
                max_size=self.max_chunk_size,
                strategy=self.current_strategy,
                confidence=confidence,
                estimated_throughput_mbps=estimated_throughput,
                estimated_latency_impact_ms=latency_impact,
                reasoning=self._generate_reasoning(
                    metrics, network, resources, recommended, confidence
                )
            )

            # Record in history
            with self.lock:
                self.sizing_history.append({
                    'timestamp': time.time(),
                    'file_type': metrics.file_type,
                    'recommendation': recommendation
                })

            self.logger.debug(
                f"Chunk size recommendation: {recommended} bytes "
                f"(strategy={self.current_strategy.value}, confidence={confidence:.2f})"
            )

            return recommendation

        except Exception as e:
            self.logger.error(f"Error recommending chunk size: {e}")
            return ChunkSizeRecommendation(
                recommended_size=self.default_chunk_size,
                min_size=self.min_chunk_size,
                max_size=self.max_chunk_size,
                strategy=SizingStrategy.BALANCED,
                confidence=0.0,
                estimated_throughput_mbps=0.0,
                estimated_latency_impact_ms=0.0,
                reasoning="Error calculating recommendation, using default"
            )

    def _calculate_conservative_size(self, metrics: SizingMetrics,
                                     network: NetworkConditions,
                                     resources: SystemResources) -> int:
        """Calculate conservative chunk size (small, reliable)"""
        try:
            # Base on network bandwidth
            if network.bandwidth_mbps < 1:
                return 256 * 1024  # 256KB for very slow networks
            elif network.bandwidth_mbps < 10:
                return 512 * 1024  # 512KB for slow networks
            else:
                return 1 * 1024 * 1024  # 1MB for moderate networks

        except Exception as e:
            self.logger.error(f"Error calculating conservative size: {e}")
            return 1 * 1024 * 1024

    def _calculate_balanced_size(self, metrics: SizingMetrics,
                                network: NetworkConditions,
                                resources: SystemResources) -> int:
        """Calculate balanced chunk size (medium, good for most scenarios)"""
        try:
            # Get file type preference
            file_prefs = self.file_type_preferences.get(metrics.file_type, {})

            if network.bandwidth_mbps < 1:
                return file_prefs.get("small_net", 512 * 1024)
            elif network.bandwidth_mbps < 50:
                return file_prefs.get("medium_net", 4 * 1024 * 1024)
            else:
                return file_prefs.get("large_net", 16 * 1024 * 1024)

        except Exception as e:
            self.logger.error(f"Error calculating balanced size: {e}")
            return 4 * 1024 * 1024

    def _calculate_aggressive_size(self, metrics: SizingMetrics,
                                  network: NetworkConditions,
                                  resources: SystemResources) -> int:
        """Calculate aggressive chunk size (large, for high-bandwidth networks)"""
        try:
            # Start with network bandwidth * latency to optimize round-trip
            # bandwidth_mbps * latency_ms = bytes in flight for optimal throughput
            bandwidth_bytes_per_ms = (network.bandwidth_mbps * 1024 * 1024) / 1000
            optimal_in_flight = bandwidth_bytes_per_ms * (network.latency_ms + 10)  # +10ms buffer

            # Adjust for memory availability
            memory_limit = resources.available_memory_mb * 1024 * 1024 * 0.1  # Use 10% of available

            size = min(optimal_in_flight, memory_limit)

            # File type adjustment
            if metrics.file_type in ["video", "archive"]:
                size = min(size * 1.5, self.max_chunk_size)
            elif metrics.file_type in ["text", "code"]:
                size = max(size // 2, 4 * 1024 * 1024)

            return int(size)

        except Exception as e:
            self.logger.error(f"Error calculating aggressive size: {e}")
            return 16 * 1024 * 1024

    def _calculate_adaptive_size(self, metrics: SizingMetrics,
                                network: NetworkConditions,
                                resources: SystemResources) -> int:
        """Calculate adaptive size based on recent performance trends"""
        try:
            # Get historical performance for this file type
            history = self.performance_history.get(metrics.file_type, deque())

            if len(history) < 5:
                # Not enough history, use balanced approach
                return self._calculate_balanced_size(metrics, network, resources)

            # Analyze recent performance
            recent = list(history)[-10:]
            throughputs = [h.get('throughput', 0) for h in recent]
            chunk_sizes = [h.get('chunk_size', 0) for h in recent]

            if not throughputs or not chunk_sizes:
                return self._calculate_balanced_size(metrics, network, resources)

            # Find correlation between chunk size and throughput
            avg_throughput = statistics.mean(throughputs)

            # If throughput is increasing, we can use larger chunks
            if metrics.throughput_trend > 0:
                return int(metrics.historic_throughput * network.latency_ms * 1024 * 1024 / 1000)
            # If declining, reduce chunk size
            elif metrics.throughput_trend < -0.1:
                current_best = max(zip(throughputs, chunk_sizes), key=lambda x: x[0])[1]
                return int(current_best * 0.8)
            else:
                return int(statistics.mean(chunk_sizes))

        except Exception as e:
            self.logger.error(f"Error calculating adaptive size: {e}")
            return self._calculate_balanced_size(metrics, network, resources)

    def _calculate_predictive_size(self, metrics: SizingMetrics,
                                  network: NetworkConditions,
                                  resources: SystemResources) -> int:
        """Calculate predictive size using pattern matching on historical data"""
        try:
            # Find similar network conditions in history
            similar_profiles = []

            for (bw_min, bw_max), optimal_size in self.network_profiles.items():
                if bw_min <= network.bandwidth_mbps <= bw_max:
                    similar_profiles.append(optimal_size)

            if similar_profiles:
                # Use average of similar network profiles
                return int(statistics.mean(similar_profiles))

            # Fall back to adaptive if no similar profile exists
            return self._calculate_adaptive_size(metrics, network, resources)

        except Exception as e:
            self.logger.error(f"Error calculating predictive size: {e}")
            return self._calculate_balanced_size(metrics, network, resources)

    def _calculate_confidence(self, metrics: SizingMetrics,
                             network: NetworkConditions,
                             resources: SystemResources) -> float:
        """Calculate confidence in the recommendation"""
        try:
            confidence = 0.5

            # More confidence with stable network
            if network.jitter_ms < 10:
                confidence += 0.2
            if network.packet_loss_percent < 1:
                confidence += 0.15

            # More confidence with historical data
            history = self.performance_history.get(metrics.file_type, deque())
            if len(history) > 20:
                confidence += 0.1
            elif len(history) > 5:
                confidence += 0.05

            # More confidence with available resources
            if resources.available_memory_mb > 500:
                confidence += 0.1
            if resources.available_cpu_percent > 20:
                confidence += 0.05

            return min(confidence, 1.0)

        except Exception as e:
            self.logger.error(f"Error calculating confidence: {e}")
            return 0.5

    def _estimate_throughput(self, chunk_size: int,
                            network: NetworkConditions,
                            resources: SystemResources) -> float:
        """Estimate achievable throughput with given chunk size"""
        try:
            # Base throughput from network
            base_throughput = network.bandwidth_mbps

            # Overhead from latency (round-trip time)
            rtt_seconds = (network.latency_ms * 2) / 1000
            chunk_mb = chunk_size / (1024 * 1024)
            transfer_time = chunk_mb / base_throughput if base_throughput > 0 else 0
            overhead_ratio = rtt_seconds / (transfer_time + rtt_seconds) if transfer_time > 0 else 0

            # Apply overhead reduction
            effective_throughput = base_throughput * (1 - overhead_ratio)

            # Apply resource constraints
            if resources.available_cpu_percent < 10:
                effective_throughput *= 0.8
            if resources.disk_io_utilization > 80:
                effective_throughput *= 0.9

            return max(effective_throughput, 0.1)

        except Exception as e:
            self.logger.error(f"Error estimating throughput: {e}")
            return network.bandwidth_mbps

    def _estimate_latency_impact(self, chunk_size: int,
                                network: NetworkConditions) -> float:
        """Estimate latency impact of chunk size"""
        try:
            # Number of round trips for 1GB file
            gb_size = 1024 * 1024 * 1024
            chunks = gb_size / chunk_size if chunk_size > 0 else 1
            total_latency = chunks * network.latency_ms * 2  # RTT

            return total_latency

        except Exception as e:
            self.logger.error(f"Error estimating latency impact: {e}")
            return network.latency_ms

    def _generate_reasoning(self, metrics: SizingMetrics,
                           network: NetworkConditions,
                           resources: SystemResources,
                           recommended: int,
                           confidence: float) -> str:
        """Generate human-readable reasoning for recommendation"""
        try:
            reasons = []

            # Network conditions
            if network.bandwidth_mbps < 1:
                reasons.append("Slow network detected - using conservative sizing")
            elif network.bandwidth_mbps > 100:
                reasons.append("High-bandwidth network - using larger chunks")

            if network.latency_ms > 100:
                reasons.append("High latency - optimizing for latency tolerance")
            if network.jitter_ms > 50:
                reasons.append("Network instability detected - using smaller chunks")

            # File characteristics
            if metrics.file_type in ["text", "code"]:
                reasons.append(f"{metrics.file_type.capitalize()} file - good compression potential")
            elif metrics.file_type in ["video", "archive"]:
                reasons.append(f"{metrics.file_type.capitalize()} file - already compressed")

            # Resource constraints
            if resources.available_memory_mb < 100:
                reasons.append("Low memory available - constraining chunk size")
            if resources.available_cpu_percent < 20:
                reasons.append("CPU-bound system - reducing overhead")

            # Confidence
            if confidence < 0.6:
                reasons.append("Low confidence - recommend monitoring actual performance")

            return " | ".join(reasons) if reasons else "Standard sizing applied"

        except Exception as e:
            self.logger.error(f"Error generating reasoning: {e}")
            return "Error generating reasoning"

    def record_sizing_result(self, file_type: str, chunk_size: int,
                            throughput_mbps: float, duration_seconds: float,
                            success: bool) -> None:
        """
        Record result of using a specific chunk size.

        Args:
            file_type: Type of file transferred
            chunk_size: Chunk size used
            throughput_mbps: Achieved throughput
            duration_seconds: Transfer duration
            success: Whether transfer was successful
        """
        try:
            with self.lock:
                history = self.performance_history[file_type]
                history.append({
                    'timestamp': time.time(),
                    'chunk_size': chunk_size,
                    'throughput': throughput_mbps,
                    'duration': duration_seconds,
                    'success': success
                })

                self.logger.debug(
                    f"Recorded: {file_type} chunk_size={chunk_size} "
                    f"throughput={throughput_mbps:.1f} MB/s success={success}"
                )

        except Exception as e:
            self.logger.error(f"Error recording sizing result: {e}")

    def update_network_profile(self, bandwidth_mbps: float, optimal_chunk_size: int) -> None:
        """
        Update network profile with optimal chunk size for bandwidth.

        Args:
            bandwidth_mbps: Network bandwidth in MB/s
            optimal_chunk_size: Optimal chunk size for this bandwidth
        """
        try:
            with self.lock:
                # Create bandwidth range
                range_size = 10  # 10 MB/s ranges
                bw_min = (bandwidth_mbps // range_size) * range_size
                bw_max = bw_min + range_size
                key = (float(bw_min), float(bw_max))

                # Record or average with existing
                if key in self.network_profiles:
                    # Running average
                    existing = self.network_profiles[key]
                    self.network_profiles[key] = (existing + optimal_chunk_size) / 2
                else:
                    self.network_profiles[key] = float(optimal_chunk_size)

                self.logger.debug(
                    f"Updated network profile: {bw_min}-{bw_max} MB/s → {optimal_chunk_size} bytes"
                )

        except Exception as e:
            self.logger.error(f"Error updating network profile: {e}")

    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get optimization summary"""
        try:
            total_records = sum(len(h) for h in self.performance_history.values())

            file_type_stats = {}
            for file_type, history in self.performance_history.items():
                if history:
                    throughputs = [h['throughput'] for h in history]
                    file_type_stats[file_type] = {
                        'samples': len(history),
                        'avg_throughput': statistics.mean(throughputs),
                        'max_throughput': max(throughputs),
                        'min_throughput': min(throughputs)
                    }

            return {
                'timestamp': time.time(),
                'total_recommendations': len(self.sizing_history),
                'file_types_tracked': len(self.performance_history),
                'network_profiles': len(self.network_profiles),
                'file_type_stats': file_type_stats,
                'current_strategy': self.current_strategy.value,
                'min_chunk_size': self.min_chunk_size,
                'max_chunk_size': self.max_chunk_size,
                'default_chunk_size': self.default_chunk_size
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
