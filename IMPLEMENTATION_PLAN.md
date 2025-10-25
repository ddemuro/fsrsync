# Enhanced FSRsync Implementation Plan

**Last Updated:** 2025-10-25
**Status:** Plan approved, ready for implementation
**Estimated Timeline:** 7 weeks (Phase 0-5)

## Executive Summary

This plan transforms FSRsync from an rsync-wrapper into a sophisticated, high-performance multi-host synchronization system. Key improvements:

- **Custom Transport Protocol:** 3-5x faster than rsync with automatic delta sync, block-level transfers, and compression
- **Optimized Change Detection:** Coalesced inotify events + multi-level detection = 10-100x fewer redundant syncs
- **Advanced Multithreading:** Lock-free queues + dynamic thread pool = 2-5x throughput improvement
- **Multi-Host Sync:** Vector clocks + distributed consensus = support for 3-10+ machines
- **Real-Time Dashboard:** WebSocket updates with live file changes and sync progress
- **Performance Targets:** <100ms sync latency for small files, 50-70% bandwidth reduction, sub-second conflict resolution

---

## Phase 0: Foundation (Weeks 1-2)

### 0.1 Advanced Inotify Event Aggregation & Deduplication
**File:** `fsrsync/utils/inotify_engine.py` (NEW)

**Problem:** inotify can generate 100s of events per second during bulk operations, overwhelming the sync engine

**Solution:**
- **Event Coalescing:** Aggregate repeated MODIFY events on same file within 100ms window
- **Deduplication:** Detect consecutive identical events, collapse to single event
- **Smart Ordering:** Process DELETE → CREATE (overwrite detection), CLOSE_WRITE → MODIFY
- **Watch Recursion:** Prevent duplicate watches, cleanup orphaned watches
- **Buffer Protection:** Monitor inotify kernel buffer, alert when approaching capacity
- **Event Ring Buffer:** Store last 1000 events for pattern analysis and debugging

**Expected Impact:** 10-100x reduction in redundant events during bulk operations

```python
class InotifyEngine:
    def coalesce_events(self, events: List[Event]) -> List[Event]:
        """Deduplicate and coalesce events within time window"""

    def get_optimal_event_order(self) -> List[Event]:
        """Order events for optimal processing (DELETE before CREATE, etc.)"""

    def check_buffer_pressure(self) -> float:
        """Return inotify kernel buffer usage percentage"""

    def get_event_patterns(self) -> Dict[str, int]:
        """Analyze event frequency patterns"""
```

---

### 0.2 Multi-Level Change Detection Strategy
**File:** `fsrsync/utils/change_detector.py` (NEW)

**Problem:** Relying solely on inotify misses some changes, and rechecking everything is expensive

**Solution:** Layered approach, each faster than the previous:

**Level 1: inotify (fastest)**
- Subsecond detection for actively monitored files

**Level 2: Stat-based hashing (fast)**
- Use `os.stat()` to check mtime + size
- Detects 99% of changes without reading file

**Level 3: Content hash (medium)**
- xxHash64 of file content (incremental)
- Cached with mtime validation
- Detects actual content changes
- Identifies moved files by hash match

**Level 4: Fuzzy hashing (detailed)**
- Optional: ssdeep/nilsimsa for pattern matching
- Find near-duplicates for deduplication

```python
class FileChangeDetector:
    def quick_check(self, file_path: str) -> bool:
        """Check if file changed using stat info only (mtime/size)"""

    def get_file_hash(self, file_path: str) -> str:
        """Get xxHash64 with caching"""

    def detect_rename_moves(self, old_state, new_state) -> List[Tuple[str, str]]:
        """Find files with same hash but different path"""

    def is_stable(self, file_path: str, min_stable_time: float = 2.0) -> bool:
        """Check if file unchanged for N seconds"""
```

**Expected Impact:** Eliminate 80%+ of redundant hash calculations

---

### 0.3 File State Machine & Stability Detection
**File:** `fsrsync/utils/file_state.py` (NEW)

**Problem:** Syncing partially-written files causes corruption or extra transfers

**Solution:** State machine with stability detection:

```
PENDING → WRITING → CLOSED → STABLE → SYNCED
```

- **PENDING:** File event detected, not yet open
- **WRITING:** File open or actively changing (inotify MODIFY events)
- **CLOSED:** File closed (CLOSE_WRITE event)
- **STABLE:** Closed for >N seconds without modification (ready to sync)
- **SYNCED:** Successfully transferred to destination

**Features:**
- **Configurable stability threshold** (default 2 seconds)
- **Change rate analysis:** Track MODIFY events/second
  - Bursty files (rapid changes) → longer timeout
  - Steady files → shorter timeout
- **Adaptive timeout:** Based on file modification pattern

```python
class FileState(Enum):
    PENDING = 1
    WRITING = 2
    CLOSED = 3
    STABLE = 4
    SYNCED = 5

class FileStateTracker:
    def update_state(self, file_path: str, event_type: str) -> FileState:
        """Update file state based on inotify event"""

    def is_stable(self, file_path: str) -> bool:
        """Check if file has been stable for threshold"""

    def get_change_rate(self, file_path: str) -> float:
        """Return MODIFY events per second (for adaptive timeout)"""
```

**Expected Impact:** Prevent syncing partially-written files, reduce extra transfers

---

### 0.4 Efficient Lock Detection Without psutil
**File:** `fsrsync/utils/lock_detector.py` (NEW)

**Problem:** `psutil.process_iter()` iterates ALL processes, expensive O(n) operation

**Solution:** Use Linux-native lock detection:

**Approach 1: /proc/locks (Fast, Linux-specific)**
```python
# Check /proc/locks for file locks by inode
# O(n) where n = number of locks (typically < 100)
# Much faster than O(m) where m = number of processes (typically 100-1000s)
```

**Approach 2: fcntl checks (Portable)**
```python
# Attempt non-blocking fcntl.flock()
# If successful, file is not locked
# Works on most filesystems
```

**Approach 3: lsof (if available)**
```python
# Cache results, refresh periodically (every 5 sec)
# Faster than full process scan
```

**Hybrid Strategy:**
```python
class LockDetector:
    def is_file_locked(self, file_path: str) -> bool:
        """Check if file is locked using optimal method"""
        # Try /proc/locks first (Linux)
        # Fall back to fcntl check
        # Use psutil only if necessary + caching
```

**Expected Impact:** 10-100x faster lock detection, reduce CPU usage during syncs

---

### 0.5 Lock-Free Data Structures
**File:** `fsrsync/utils/lockfree_queues.py` (NEW)

**Problem:** Multiple threads contending on single `threading.Lock` causes contention

**Solution:** Replace lock-protected sets with atomic queues:

**Before (Poor Concurrency):**
```python
self.immediate_sync_lock = Lock()
self.immediate_sync = set()  # 3 threads wait for 1 lock
```

**After (Better Concurrency):**
```python
self.immediate_sync_queue = queue.PriorityQueue()  # Lock-free semantics
self.immediate_sync_set = set()  # Track unique files (lock-free reads)
```

**Implementation Details:**
- Use `queue.Queue` for producer-consumer (built on locks but optimized)
- Use `collections.deque` with atomic `append`/`pop` for simple cases
- Implement custom lock-free circular buffer for event ring
- Per-destination queues reduce lock contention

```python
class LockFreeQueues:
    def __init__(self):
        self.immediate_sync = queue.PriorityQueue()  # (priority, file_path)
        self.regular_sync = queue.PriorityQueue()
        self.open_files = set()  # Read-heavy, lock-free for reads
```

**Expected Impact:** 2-5x throughput improvement under high concurrency

---

### 0.6 Advanced Thread Pool
**File:** `fsrsync/utils/thread_pool.py` (ENHANCED)

**Problem:** Current design spawns one thread per destination, doesn't scale

**Solution:** Dynamic, smart thread pool:

**Features:**
- **Dynamic scaling:** Start with `cpu_count()`, scale up to `max_workers` based on queue depth
- **Per-destination pools:** Each destination gets independent pool (prevents one from blocking others)
- **Work stealing:** Idle workers steal from other destination queues when their queue is empty
- **Priority queues:** Smaller files execute before large files
- **Metrics:** Track queue depth, worker utilization, task duration

```python
class AdvancedThreadPool:
    def __init__(self, destinations: List[str], base_workers: int = None):
        # Create pool per destination
        self.pools = {dest: ThreadPoolExecutor(max_workers=base_workers)
                     for dest in destinations}

    def scale_workers(self, destination: str):
        """Add workers if queue depth high, remove if idle"""

    def work_steal(self):
        """Idle workers check other destination queues"""

    def get_metrics(self) -> Dict:
        """Return pool utilization metrics"""
```

**Expected Impact:** 2-5x throughput improvement, better hardware utilization

---

### 0.7 Async/Await Integration
**File:** `fsrsync/sync_app.py` (PARTIAL REFACTOR)

**Current:** Fully blocking threaded architecture
**Enhanced:** Hybrid threading + asyncio

**Strategy:**
- **inotify loop:** Remains threaded (blocking read is acceptable)
- **Network I/O:** Converted to asyncio (non-blocking)
- **File operations:** Remain threaded (CPU-bound)

**Benefits:**
- Handle 100s of simultaneous web API connections
- Non-blocking socket operations
- Better resource utilization under load

```python
# Before: Blocking rsync calls block thread
self.rsync_manager.run(files)  # Blocks for minutes

# After: Async wrapper, non-blocking I/O
await self.transfer_engine.transfer_files(files)  # Responsive
```

**Expected Impact:** Handle 10-100x more concurrent connections on web API

---

### 0.8-0.10: FSRsync Binary Transport Protocol
**Files:** `fsrsync/utils/transport_protocol.py` (NEW), `fsrsync/utils/transport_server.py` (NEW)

**Problem:** rsync is general-purpose, not optimized for our sync patterns

**Solution:** Purpose-built protocol with automatic optimizations

**Protocol Header (16 bytes):**
```
[Protocol Version: 1 byte]
[Command Type: 1 byte]         # SYNC, ACK, HEARTBEAT, FILE_META, etc.
[Flags: 2 bytes]               # Compression, encryption, delta, etc.
[Payload Length: 4 bytes]      # 0-4GB
[Sequence Number: 4 bytes]     # For ordering/dedup
[Checksum: 2 bytes]            # CRC16
```

**Command Types:**
- `0x00` SYNC_START
- `0x01` FILE_META (name, perms, size, mtime, hash)
- `0x02` FILE_DATA (raw chunks)
- `0x03` FILE_DELTA (only changed blocks)
- `0x04` FILE_END (with checksum)
- `0x05` ACK
- `0x0C` MOVE (rename/move detection)
- `0x0D` DELETE

**Compression:**
```python
COMP_NONE = 0x00
COMP_ZSTD = 0x01    # Zstandard (best compression/speed)
COMP_LZ4 = 0x02     # LZ4 (fastest)

# Auto-select based on file type/size
if file_size < 1KB: COMP_NONE
if is_already_compressed(file): COMP_NONE  # .zip, .mp4, etc.
if file_size > 100MB: COMP_LZ4  # Speed > compression
else: COMP_ZSTD  # Best compression
```

**Delta Sync (Block-Level):**
```
Traditional: Send full 1GB file
Protocol: Query remote hash, receive diff, send only changed 100MB blocks
Result: 90% bandwidth savings
```

**Move/Rename Optimization:**
```
Detect: source.hash == dest.hash && source.path != dest.path
Send: MOVE command instead of DELETE + CREATE + transfer
Result: Instant move, zero bandwidth
```

```python
class FSRsyncProtocol:
    def send_file(self, local_path: str, remote_path: str,
                  compression: int = COMP_AUTO) -> bool:
        """Send with automatic compression and delta sync"""

    def send_batch(self, files_list: List[str]) -> Dict[str, bool]:
        """Send multiple files in single connection"""

    def request_delta(self, local_path: str, remote_hash: str) -> bytes:
        """Request only changed blocks from remote"""

    def handle_moves(self, old_state: FileState, new_state: FileState):
        """Detect and optimize moved files"""
```

**Expected Impact:** 3-5x faster transfers, 50-70% bandwidth reduction, sub-second move operations

---

### 0.12: Filesystem Metadata Preservation
**File:** `fsrsync/utils/fs_metadata.py` (NEW)

**Problem:** Permissions/ACLs are lost during transfer, or forced to default

**Solution:** Smart metadata preservation with optional mapping

**Supported Metadata:**
- File mode (rwx rwx rwx + suid/sgid/sticky)
- Ownership (UID/GID)
- Timestamps (atime, mtime)
- Extended attributes (xattr)
- POSIX ACLs
- SELinux context (if available)

**Mapping/Forcing Options:**
```python
class PermissionMapper:
    def __init__(self, force_user: str = None, force_group: str = None,
                 force_mode: int = None):
        self.force_user = force_user      # e.g., "nobody"
        self.force_group = force_group    # e.g., "nogroup"
        self.force_mode = force_mode      # e.g., 0o755

    def map_permissions(self, source_stat) -> (int, int, int):
        """Return (uid, gid, mode) for target"""
        if self.force_user: uid = resolve_user(self.force_user)
        # ... similar for group, mode
```

**Graceful Fallback:**
```python
def apply_metadata(file_path, metadata, mapper):
    """Apply metadata with fallback"""
    # Try to apply in order, skip if not supported
    try: os.chmod(file_path, mapper.map_mode(metadata['mode']))
    except: pass  # Filesystem doesn't support

    try: os.chown(file_path, uid, gid)
    except: pass  # Not root

    try: apply_posix_acls(file_path, metadata['acls'])
    except: pass  # No ACL support
```

**Expected Impact:** Perfect metadata preservation, optional forced mappings for compatibility

---

## Phase 1: Core Sync Improvements (Weeks 2-3)

### 1.1 Block-Level Delta Sync Engine
**File:** `fsrsync/utils/delta_sync.py` (NEW)

Built on top of the transport protocol from Phase 0.8-0.10.

**Mechanism:**
1. Calculate rolling hash of each block (4KB blocks typical)
2. Send hashes to remote
3. Remote compares with local blocks
4. Send only differing blocks
5. Remote reconstructs file

**Benefits:**
- 1GB file with 10MB changes → send only 10MB instead of 1GB
- Works for partial file updates
- Efficient for large files being edited incrementally

---

### 1.2 Move/Rename Detection Engine
**File:** `fsrsync/utils/move_detector.py` (NEW)

Built on hash-based file identity from Phase 0.2.

**Detection:**
```
For each file in new state:
  - Calculate content hash
  - Look for same hash in old state with different path
  - If found: MOVE, not CREATE + DELETE + transfer
```

**Result:** Moved files transfer instantly (0 bandwidth)

---

### 1.3 Enhanced File State Tracking
**File:** `fsrsync/utils/filesystem.py` (UPDATED)

Integrates Phase 0.3 file state machine with existing inotify monitoring.

---

### 1.4 Sync Journal & Version Vectors
**File:** `fsrsync/utils/sync_journal.py` (NEW)

**Prevent Circular Syncs:**
- Track operations by originating host (version vector)
- Host A modifies file → host B syncs → Host B doesn't resync back to A
- Distributed operation log with ordering

---

## Phase 2: Multi-Host Orchestration (Weeks 3-4)

### 2.1-2.4 Distributed Sync, Peer Management, Conflict Resolution, Bandwidth Management

(See original plan for details)

---

## Phase 3: Parallelization (Weeks 4-5)

### 3.1-3.3 Parallel Transfer Engine, Queue Management, Thread Pool

(Uses enhanced thread pool from Phase 0.6)

---

## Phase 4: Dashboard & Monitoring (Weeks 5-6)

### 4.1-4.3 WebSocket Server, Enhanced Dashboard, Metrics

(See original plan for details)

---

## Phase 5: Testing & Validation (Weeks 6-7)

### 5.1-5.3 Docker Lab, Test Scenarios, CI/CD Integration

(See original plan for details)

---

## Expected Performance Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Sync latency** (small files) | 2-5 sec | <100ms | 25-50x |
| **Bandwidth** (moved files) | 100% | 0% | ∞ |
| **Bandwidth** (changed blocks) | 100% | 20-30% | 3-5x |
| **Multi-host throughput** | Sequential | Parallel | 3-10x |
| **Dashboard latency** | HTTP polling (2-5 sec) | WebSocket (<100ms) | 25-50x |
| **Thread overhead** | Linear per dest | Dynamic pool | 2-5x |
| **inotify overhead** | Linear with events | Coalesced | 10-100x |
| **Lock detection** | O(processes) | O(locks) | 10-100x |

---

## Implementation Strategy

### Start with Phase 0 (Foundation)
Why? Because every other phase depends on these optimizations:
- Phase 0.8-0.10 (protocol) is used by Phase 1.1 (delta sync)
- Phase 0.6 (thread pool) is used by Phase 3.1 (parallel transfers)
- Phase 0.1-0.4 (change detection) improves all phases

### Implementation Order Within Phase 0:
1. **0.8-0.10** (Protocol) - Most critical, blocking for other improvements
2. **0.6** (Thread pool) - Enables better parallelization
3. **0.1-0.4** (Change detection) - Immediate wins in efficiency
4. **0.5** (Lock-free queues) - Improves concurrency
5. **0.7** (Async integration) - Nice to have, can be gradual

### Backward Compatibility
- All existing configs work unchanged
- rsync is fallback if protocol negotiation fails
- Gradual adoption per destination

---

## Testing Strategy

### Phase 0 Testing:
- Unit tests for each new module
- Benchmark inotify events before/after coalescing
- Compare hash detection performance
- Thread pool scaling tests

### Phase 5 Docker Lab:
- 3-5 FSRsync instances syncing same folder
- Simulated network conditions (latency, packet loss)
- Real-world workloads (concurrent writes, large files, rapid changes)
- Performance benchmarks comparing old vs new implementation

---

## Success Criteria

✅ **Performance:**
- Small file sync: <100ms (was 2-5 seconds)
- Moved files: 0 bandwidth (was full transfer)
- Changed blocks: 20-30% of original (was 100%)

✅ **Reliability:**
- Zero circular syncs (version vectors)
- Perfect metadata preservation
- Graceful fallback to rsync

✅ **Scalability:**
- Support 3-10+ machines syncing same folder
- 100+ concurrent files transferring
- 1000s of files in queue

✅ **User Experience:**
- Real-time dashboard (<100ms updates)
- Clear sync status and progress
- Explicit error reporting

---

## File Structure After Implementation

```
fsrsync/
├── utils/
│   ├── inotify_engine.py        # 0.1
│   ├── change_detector.py       # 0.2
│   ├── file_state.py            # 0.3
│   ├── lock_detector.py         # 0.4
│   ├── lockfree_queues.py       # 0.5
│   ├── thread_pool.py           # 0.6 (enhanced)
│   ├── transport_protocol.py    # 0.8
│   ├── transport_server.py      # 0.9
│   ├── fs_metadata.py           # 0.12
│   ├── delta_sync.py            # 1.1
│   ├── move_detector.py         # 1.2
│   ├── sync_journal.py          # 1.4
│   ├── sync_protocol.py         # 2.1
│   ├── peer_manager.py          # 2.2
│   ├── conflict_resolver.py     # 2.3
│   ├── bandwidth_manager.py     # 2.4
│   ├── transfer_engine.py       # 3.1
│   ├── websocket_server.py      # 4.1
│   ├── metrics.py               # 4.3
│   └── [existing files]
├── templates/
│   ├── dashboard.html           # 4.2
│   ├── dashboard.js
│   └── graphs.js
├── test/
│   ├── test_scenarios/
│   │   ├── test_multi_host.py
│   │   ├── test_large_files.py
│   │   ├── test_conflicts.py
│   │   └── test_performance.py
│   └── [existing tests]
├── docker-compose.lab.yml       # 5.1
└── IMPLEMENTATION_PLAN.md       # This file
```

---

## Next Steps

1. **Review and approve** this plan ✅
2. **Start Phase 0.8-0.10** (Transport Protocol)
   - Most critical, blocking for other improvements
   - Enables all delta sync and move detection optimizations
3. **Build Docker lab** (Phase 5.1) in parallel
   - Testing infrastructure ready as we develop
4. **Iterate through phases** in order, testing each

**Ready to start? Let's begin with the transport protocol!**
