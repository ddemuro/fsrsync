"""
Sync Operation Instrumentation for FSRsync

Provides automatic performance instrumentation with:
- Decorator-based profiling for sync operations
- Metrics collection integration
- I/O operation tracking
- Performance streaming
- Automatic bottleneck detection
- Real-time performance monitoring

## Instrumentation Types

SYNC: Synchronization operation profiling
TRANSFER: File transfer profiling
IO: Filesystem I/O operation tracking
NETWORK: Network operation tracking
CONFLICT: Conflict resolution profiling
METADATA: Metadata operation tracking
"""

import time
import logging
import functools
from typing import Any, Callable, Optional, Dict
from contextlib import contextmanager


class SyncInstrumentation:
    """
    Sync operation instrumentation manager.

    Provides decorators and context managers for automatic
    performance profiling of sync operations.
    """

    # Global performance collectors (set by application)
    metrics_collector = None
    performance_benchmarker = None
    io_analyzer = None
    performance_streamer = None
    profiler = None
    logger = None

    @classmethod
    def initialize(cls, metrics_collector=None, benchmarker=None,
                  io_analyzer=None, streamer=None, profiler=None,
                  logger_instance=None):
        """
        Initialize instrumentation with performance modules.

        Args:
            metrics_collector: MetricsCollector instance
            benchmarker: PerformanceBenchmarker instance
            io_analyzer: IOAnalyzer instance
            streamer: PerformanceStreamer instance
            profiler: FunctionProfiler instance
            logger_instance: Logger instance
        """
        cls.metrics_collector = metrics_collector
        cls.performance_benchmarker = benchmarker
        cls.io_analyzer = io_analyzer
        cls.performance_streamer = streamer
        cls.profiler = profiler
        cls.logger = logger_instance or logging.getLogger(__name__)

    @classmethod
    @contextmanager
    def profile_sync_operation(cls, operation_name: str, operation_type: str = "sync",
                             metadata: Optional[Dict[str, Any]] = None):
        """
        Context manager for profiling sync operations.

        Args:
            operation_name: Name of operation
            operation_type: Type of operation (sync, transfer, io, network, etc.)
            metadata: Optional metadata

        Yields:
            Operation context with timing info
        """
        start_time = time.time()
        start_memory = None

        try:
            # Get initial memory if available
            if cls.performance_benchmarker:
                import tracemalloc
                try:
                    start_memory = tracemalloc.get_traced_memory()[0]
                except:
                    pass

            # Publish start event if streaming available
            if cls.performance_streamer:
                try:
                    cls.performance_streamer.publish_event(
                        event_type=f"{operation_type}_started",
                        metric_name=operation_name,
                        value=0,
                        metadata=metadata or {}
                    )
                except Exception as e:
                    if cls.logger:
                        cls.logger.debug(f"Error publishing start event: {e}")

            yield {
                'start_time': start_time,
                'operation_name': operation_name,
                'operation_type': operation_type
            }

        finally:
            end_time = time.time()
            duration = end_time - start_time

            # Calculate memory delta if available
            memory_used = None
            if start_memory is not None and cls.performance_benchmarker:
                try:
                    import tracemalloc
                    end_memory = tracemalloc.get_traced_memory()[0]
                    memory_used = end_memory - start_memory
                except:
                    pass

            # Record metrics
            if cls.metrics_collector:
                try:
                    cls.metrics_collector.record_metric(
                        component=operation_type,
                        metric_name=f"{operation_name}_duration",
                        value=duration * 1000,  # Convert to ms
                        metric_type="latency"
                    )
                except Exception as e:
                    if cls.logger:
                        cls.logger.debug(f"Error recording metric: {e}")

            # Record in benchmark
            if cls.performance_benchmarker:
                try:
                    cls.performance_benchmarker.record_metric(
                        metric_name=f"{operation_name}_latency",
                        value=duration * 1000
                    )
                except Exception as e:
                    if cls.logger:
                        cls.logger.debug(f"Error recording benchmark: {e}")

            # Publish completion event
            if cls.performance_streamer:
                try:
                    cls.performance_streamer.publish_metric(
                        metric_name=f"{operation_name}_duration_ms",
                        value=duration * 1000,
                        metadata={'operation_type': operation_type, 'memory_bytes': memory_used}
                    )
                except Exception as e:
                    if cls.logger:
                        cls.logger.debug(f"Error publishing metric: {e}")

            if cls.logger:
                cls.logger.debug(
                    f"[{operation_type.upper()}] {operation_name}: "
                    f"{duration*1000:.2f}ms"
                    f"{f', {memory_used/1024/1024:.1f}MB' if memory_used else ''}"
                )

    @classmethod
    def instrument_transfer(cls, operation_name: str):
        """
        Decorator for profiling file transfer operations.

        Args:
            operation_name: Name of transfer operation

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with cls.profile_sync_operation(
                    operation_name=operation_name,
                    operation_type="transfer",
                    metadata={
                        'function': func.__name__,
                        'args_count': len(args),
                        'kwargs_keys': list(kwargs.keys())
                    }
                ):
                    result = func(*args, **kwargs)

                    # Extract transfer metrics if available
                    if isinstance(result, dict) and 'bytes_transferred' in result:
                        if cls.metrics_collector:
                            try:
                                cls.metrics_collector.record_metric(
                                    component="transfer",
                                    metric_name=f"{operation_name}_bytes",
                                    value=result['bytes_transferred'],
                                    metric_type="throughput"
                                )
                            except Exception as e:
                                if cls.logger:
                                    cls.logger.debug(f"Error recording transfer metric: {e}")

                    return result

            return wrapper
        return decorator

    @classmethod
    def instrument_io(cls, operation_name: str, operation_type_str: str):
        """
        Decorator for profiling I/O operations.

        Args:
            operation_name: Name of I/O operation
            operation_type_str: Type of I/O (read, write, seek, etc.)

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()

                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    success = True
                    error_msg = ""

                    # Extract size if available
                    size = 0
                    if isinstance(result, dict) and 'bytes' in result:
                        size = result['bytes']
                    elif isinstance(result, bytes):
                        size = len(result)

                    # Record in I/O analyzer
                    if cls.io_analyzer:
                        try:
                            cls.io_analyzer.record_operation(
                                operation_type=operation_type_str,
                                path=kwargs.get('path', 'unknown'),
                                duration=duration,
                                size=size,
                                success=success
                            )
                        except Exception as e:
                            if cls.logger:
                                cls.logger.debug(f"Error recording I/O: {e}")

                    return result

                except Exception as e:
                    duration = time.time() - start_time

                    # Record failure in I/O analyzer
                    if cls.io_analyzer:
                        try:
                            cls.io_analyzer.record_operation(
                                operation_type=operation_type_str,
                                path=kwargs.get('path', 'unknown'),
                                duration=duration,
                                size=0,
                                success=False,
                                error_msg=str(e)
                            )
                        except Exception as e2:
                            if cls.logger:
                                cls.logger.debug(f"Error recording I/O failure: {e2}")

                    raise

            return wrapper
        return decorator

    @classmethod
    def instrument_sync(cls, operation_name: str):
        """
        Decorator for profiling sync operations.

        Args:
            operation_name: Name of sync operation

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with cls.profile_sync_operation(
                    operation_name=operation_name,
                    operation_type="sync"
                ):
                    return await func(*args, **kwargs)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with cls.profile_sync_operation(
                    operation_name=operation_name,
                    operation_type="sync"
                ):
                    return func(*args, **kwargs)

            # Return appropriate wrapper based on whether function is async
            if functools.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    @classmethod
    @contextmanager
    def track_transfer(cls, file_path: str, total_size: int):
        """
        Context manager for tracking file transfer progress.

        Args:
            file_path: Path to file being transferred
            total_size: Total size in bytes

        Yields:
            Transfer context with progress tracking
        """
        start_time = time.time()
        bytes_transferred = 0

        try:
            yield {
                'start_time': start_time,
                'file_path': file_path,
                'total_size': total_size,
                'get_progress': lambda: bytes_transferred / total_size if total_size > 0 else 0
            }

        finally:
            end_time = time.time()
            duration = end_time - start_time
            throughput = total_size / duration if duration > 0 else 0

            # Record transfer metrics
            if cls.metrics_collector:
                try:
                    cls.metrics_collector.record_metric(
                        component="transfer",
                        metric_name="file_transfer",
                        value=throughput / 1024 / 1024,  # Convert to MB/s
                        metric_type="throughput"
                    )
                except Exception as e:
                    if cls.logger:
                        cls.logger.debug(f"Error recording transfer metric: {e}")

            if cls.logger:
                cls.logger.debug(
                    f"[TRANSFER] {file_path}: "
                    f"{total_size / 1024 / 1024:.1f}MB in {duration:.2f}s "
                    f"({throughput / 1024 / 1024:.1f}MB/s)"
                )

    @classmethod
    def get_instrumentation_summary(cls) -> Dict[str, Any]:
        """Get instrumentation system summary"""
        return {
            'timestamp': time.time(),
            'metrics_collector': cls.metrics_collector is not None,
            'benchmarker': cls.performance_benchmarker is not None,
            'io_analyzer': cls.io_analyzer is not None,
            'streamer': cls.performance_streamer is not None,
            'profiler': cls.profiler is not None
        }
