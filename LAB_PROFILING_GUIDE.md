# FSRsync Lab Profiling Guide

## Overview

Phase 16 integrates comprehensive performance profiling into the Docker lab environment, enabling real-world performance testing and analysis of FSRsync sync operations.

## Infrastructure

### Components

1. **sync_instrumentation.py** - Decorator-based performance instrumentation
   - Context managers for profiling sync operations
   - Automatic metrics collection
   - I/O tracking
   - Real-time performance streaming

2. **lab_profiler.py** - Lab profiling orchestrator
   - Runs test scenarios with full instrumentation
   - Collects comprehensive metrics
   - Generates performance reports
   - Creates performance baselines

3. **Docker Lab Environment**
   - 5 FSRsync instances (1 primary + 4 remotes)
   - Multi-host synchronization testing
   - Network simulation with latency/bandwidth control
   - Shared volumes for scenario testing

4. **Test Scenarios**
   - Basic synchronization
   - Conflict resolution
   - Large file transfers
   - Network failure recovery
   - Multi-peer synchronization
   - Bandwidth throttling
   - Concurrent operations
   - Data integrity verification

## Usage

### Quick Start

```bash
# Run single scenario with profiling
python lab_profiler.py --scenario basic_sync --profile

# Run all scenarios
python lab_profiler.py --scenario all --output results.json

# Create performance baseline
python lab_profiler.py --scenario all --baseline

# Run with debug logging
python lab_profiler.py --scenario large_file_transfer --log-level DEBUG
```

### Advanced Usage

```bash
# Run with custom duration
python lab_profiler.py --scenario bandwidth_throttling --duration 120

# Save detailed results
python lab_profiler.py --scenario all --output /tmp/profile_results.json

# Profile specific scenario repeatedly
for i in {1..5}; do
    python lab_profiler.py --scenario concurrent_operations --output run_$i.json
done
```

## Profiling Data

### Collected Metrics

Each profiling run collects:

1. **Performance Metrics**
   - Operation latency (min, max, avg, std dev)
   - Throughput (MB/s)
   - Memory usage
   - CPU utilization

2. **I/O Metrics**
   - Read/write operations
   - Seek operations
   - File sync calls
   - I/O throughput
   - Error rates

3. **Network Metrics**
   - Data transferred
   - Network latency
   - Bandwidth utilization
   - Packet loss (simulated)

4. **Bottlenecks**
   - Slowest functions
   - Memory hotspots
   - I/O bottlenecks
   - Network bottlenecks

### Output Format

Results are saved as JSON with the following structure:

```json
{
  "timestamp": 1234567890,
  "config": {
    "scenario": "basic_sync",
    "duration": 60,
    "profile_enabled": true
  },
  "results": {
    "scenario": "basic_sync",
    "duration": 45.23,
    "test_results": [...],
    "metrics_summary": {...},
    "benchmark_report": {...},
    "io_summary": {...},
    "bottlenecks": [...]
  },
  "duration": 45.23
}
```

## Performance Instrumentation

### Using Decorators

```python
from fsrsync.utils.sync_instrumentation import SyncInstrumentation

# Instrument transfer operations
@SyncInstrumentation.instrument_transfer("file_transfer")
def transfer_file(source, dest):
    # Your transfer code here
    return {'bytes_transferred': 1024}

# Instrument I/O operations
@SyncInstrumentation.instrument_io("read_file", "read")
def read_file(path):
    # Your read code here
    return data

# Instrument sync operations
@SyncInstrumentation.instrument_sync("sync_directory")
def sync_directory(source, dest):
    # Your sync code here
    pass
```

### Using Context Managers

```python
from fsrsync.utils.sync_instrumentation import SyncInstrumentation

# Profile sync operation
with SyncInstrumentation.profile_sync_operation(
    operation_name="directory_scan",
    operation_type="sync"
):
    # Your code here
    pass

# Track file transfer
with SyncInstrumentation.track_transfer(file_path, file_size):
    # Your transfer code here
    pass
```

## Docker Lab Setup

### Start Lab Environment

```bash
# Build and start all containers
docker-compose -f docker-compose.lab.yml up -d

# Check status
docker-compose -f docker-compose.lab.yml ps

# View logs
docker-compose -f docker-compose.lab.yml logs -f

# Stop environment
docker-compose -f docker-compose.lab.yml down -v
```

### Container Details

- **Primary** (fsrsync-primary)
  - Address: 10.0.1.10
  - Web UI: http://localhost:8080
  - Sync Port: 9876

- **Remote 1-4** (fsrsync-remote-1 to 4)
  - Addresses: 10.0.1.11 - 10.0.1.14
  - Web UIs: http://localhost:8081-8084
  - Sync Ports: 9877-9880

## Performance Analysis

### API Endpoints

Check instrumentation status:
```bash
curl "http://localhost:8080/api/instrumentation/summary?secret=YOUR_SECRET"
```

Get performance metrics:
```bash
curl "http://localhost:8080/api/performance/metrics?secret=YOUR_SECRET"
```

Get I/O analysis:
```bash
curl "http://localhost:8080/api/io/summary?secret=YOUR_SECRET"
```

Get regression report:
```bash
curl "http://localhost:8080/api/regression/report?secret=YOUR_SECRET"
```

### Integration

The profiling system automatically integrates with:

- **MetricsCollector** - Records operation metrics
- **PerformanceBenchmarker** - Tracks latency/throughput
- **IOAnalyzer** - Profiles filesystem operations
- **PerformanceStreamer** - Streams real-time metrics
- **RegressionTester** - Detects performance regressions

## Benchmarking Scenarios

### Basic Synchronization
- Small file set synchronization
- Baseline performance measurement
- Duration: ~30 seconds

### Large File Transfer
- Single large file (100MB+)
- Throughput measurement
- Memory usage tracking
- Duration: ~60 seconds

### Concurrent Operations
- Multiple parallel transfers
- Concurrency overhead measurement
- Resource contention analysis
- Duration: ~45 seconds

### Network Failure Recovery
- Simulated network interruptions
- Recovery time measurement
- Data integrity verification
- Duration: ~90 seconds

### Multi-Peer Sync
- 5-node synchronization
- Consensus overhead measurement
- Bandwidth efficiency
- Duration: ~60 seconds

## Interpreting Results

### Performance Metrics

- **Latency** < 100ms: Excellent
- **Latency** 100-500ms: Good
- **Latency** 500-2000ms: Acceptable
- **Latency** > 2000ms: Investigate

### Throughput

- **Throughput** > 50 MB/s: Excellent
- **Throughput** 10-50 MB/s: Good
- **Throughput** < 10 MB/s: Investigate

### Memory Usage

- Baseline: < 50MB per instance
- Under load: < 200MB per instance
- Spike handling: < 500MB peak

## Troubleshooting

### Profiler Not Running

```bash
# Check if instrumentation is enabled
curl "http://localhost:8080/api/instrumentation/summary?secret=YOUR_SECRET"

# Look for error logs
docker logs fsrsync-primary | grep instrumentation
```

### No Metrics Collected

1. Ensure decorators are applied to functions
2. Check that SyncInstrumentation is initialized
3. Verify metrics_collector is available
4. Check logs for collection errors

### Lab Containers Not Starting

```bash
# Check docker-compose configuration
docker-compose -f docker-compose.lab.yml config

# Check container logs
docker-compose -f docker-compose.lab.yml logs

# Rebuild containers
docker-compose -f docker-compose.lab.yml build --no-cache
```

## Best Practices

1. **Run Multiple Iterations**
   - Run each scenario 3+ times
   - Average results to reduce noise
   - Watch for outliers

2. **Control Variables**
   - Keep scenario parameters consistent
   - Test one variable at a time
   - Document test conditions

3. **Create Baselines**
   - Establish baseline before optimization
   - Compare against baseline after changes
   - Track baseline over time

4. **Monitor Resources**
   - Watch memory trends
   - Track I/O operations
   - Identify bottlenecks early

5. **Archive Results**
   - Save all profiling results
   - Version control important runs
   - Compare results across versions

## Performance Optimization Workflow

1. **Baseline** - Establish baseline performance
2. **Profile** - Run lab profiling
3. **Analyze** - Identify bottlenecks
4. **Optimize** - Implement improvements
5. **Verify** - Measure improvement with profiling
6. **Track** - Create new baseline for future comparisons

## Files Modified

- `sync_instrumentation.py` - New instrumentation module
- `lab_profiler.py` - New profiling orchestrator
- `web_app.py` - Added instrumentation integration
- `docker-compose.lab.yml` - Existing lab configuration
- `test_scenarios.py` - Used for profiling tests

## Next Steps

1. Run initial profiling baseline
2. Identify top 3 bottlenecks
3. Implement targeted optimizations
4. Verify improvements with profiling
5. Create performance regression tests

## References

- Performance Modules (Phases 12-15): 15 modules covering benchmarking, analytics, regression testing, optimization
- Test Scenarios: 8 comprehensive test scenarios
- Docker Lab: 5-node synchronization environment
- API Endpoints: 75+ endpoints for performance monitoring
