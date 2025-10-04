# FSRsync Technical Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Component Details](#component-details)
3. [Data Flow](#data-flow)
4. [Thread Safety Model](#thread-safety-model)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Performance Characteristics](#performance-characteristics)

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FSRsync System                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Main       │    │   Web        │    │   Full Sync  │      │
│  │   Event      │    │   Server     │    │   Thread     │      │
│  │   Loop       │    │   Thread     │    │   (periodic) │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                    │              │
│         └───────────────────┼────────────────────┘              │
│                             │                                   │
│                    ┌────────▼─────────┐                         │
│                    │  SyncApplication │                         │
│                    │   (Coordinator)  │                         │
│                    └────────┬─────────┘                         │
│                             │                                   │
│            ┌────────────────┼────────────────┐                 │
│            │                │                │                  │
│    ┌───────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐          │
│    │ Filesystem   │  │   Rsync     │  │  Server    │          │
│    │   Monitor    │  │  Manager    │  │   Locks    │          │
│    │  (inotify)   │  │             │  │            │          │
│    └──────────────┘  └─────────────┘  └────────────┘          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Component Interaction Diagram

```
┌─────────┐         ┌──────────────────┐         ┌─────────────┐
│ inotify │ events  │ FilesystemMonitor│  files  │ SyncApp     │
│         ├────────►│                  ├────────►│             │
└─────────┘         │ - immediate_sync │         │ - manages   │
                    │ - regular_sync   │         │   sync ops  │
                    │ - open_files     │         │ - locks     │
                    └──────────────────┘         └──────┬──────┘
                                                        │
                                                        │ rsync
                                                        ▼
                                          ┌──────────────────────┐
                                          │   RsyncManager       │
                                          │                      │
                                          │ - builds cmd         │
                                          │ - executes rsync     │
                                          │ - runs pre/post cmds │
                                          └──────────────────────┘
```

## Component Details

### 1. FilesystemMonitor

**Purpose**: Monitor filesystem events using inotify and categorize files for syncing.

**Key Data Structures**:
```python
class FilesystemMonitor:
    inotify_watcher: INotify          # Linux inotify instance
    open_files: set[File]             # Files currently open for writing
    immediate_sync: set[File]         # Files needing immediate sync
    regular_sync: set[File]           # Files needing batched sync

    # Thread safety locks
    open_files_lock: Lock
    immediate_sync_lock: Lock
    regular_sync_lock: Lock
```

**State Transitions**:
```
File Event Flow:
┌───────┐ IN_CREATE  ┌──────────────┐
│ NEW   ├───────────►│ IMMEDIATE    │
└───────┘            │ SYNC         │
                     └──────┬───────┘
┌───────┐ IN_OPEN    ┌──────▼───────┐
│ FILE  ├───────────►│ LOCKED       │
└───────┘            │ (open_files) │
                     └──────┬───────┘
                            │ IN_CLOSE_WRITE
                     ┌──────▼───────┐   synced
                     │ IMMEDIATE    ├──────────► [removed]
                     │ SYNC         │
                     └──────────────┘

Batch Flow:
┌───────┐ IN_MODIFY  ┌──────────────┐   queue full
│ FILE  ├───────────►│ REGULAR      ├──────────► [sync batch]
└───────┘            │ SYNC         │
                     └──────────────┘
```

**Event Handling Logic**:
```
handle_event(event):
  ├─ CREATE event
  │  └─► add_immediate_sync_file()
  │
  ├─ OPEN event (not directory)
  │  └─► add_to_locked_files()
  │
  ├─ CLOSE_WRITE event
  │  ├─► delete_locked_file()
  │  └─► add_immediate_sync_file()
  │
  ├─ DELETE or MOVED_FROM event
  │  ├─► delete_locked_file()
  │  ├─► delete_immediate_sync_file()
  │  └─► delete_regular_sync_file()
  │
  └─ MOVED_TO event
     └─► add_regular_sync_file()
```

### 2. SyncApplication

**Purpose**: Coordinate all sync operations, manage destinations, and handle server locks.

**Main Event Loop**:
```python
def run(self):
    for event in fs_monitor.event_generator():
        # 1. Handle event
        fs_monitor.handle_event(event)

        # 2. Check pending files
        pending_immediate = len(fs_monitor.get_immediate_sync_files())
        pending_regular = len(fs_monitor.get_regular_sync_files())

        # 3. Trigger syncs if needed
        if pending_immediate > 0 or pending_regular > 0:
            for destination in destinations:
                if not destination['locked_on_sync']:
                    thread = Thread(
                        target=manage_destination_event,
                        args=(destination,)
                    )
                    thread.start()
```

**Sync Decision Flow**:
```
manage_destination_event():
  │
  ├─► Check if destination locked
  │   └─ YES → wait or skip
  │
  ├─► Get files for this destination path
  │   ├─ immediate_sync_files
  │   └─ regular_sync_files
  │
  ├─► Filter by extensions_to_ignore
  │
  ├─► Immediate sync processing:
  │   ├─► Acquire global server lock (if needed)
  │   ├─► Build include list
  │   ├─► Run rsync with EXCLUDE_ALL + includes
  │   ├─► Release global server lock
  │   └─► Mark files as synced
  │
  └─► Regular sync processing (if queue full):
      ├─► Clear locks exceeded wait time
      ├─► Acquire global server lock (if needed)
      ├─► Build include list (exclude locked files)
      ├─► Run rsync with excludes + includes
      ├─► Release global server lock
      └─► Mark files as synced
```

### 3. Global Server Lock System

**Purpose**: Prevent bidirectional sync conflicts between servers.

**Lock Lifecycle**:
```
Server A wants to sync to Server B:

1. Server A checks if Server B is locked
   └─► GET /check_if_server_locked

2. If not locked, Server A acquires locks:
   ├─► Local: add_to_global_server_locks("server-b", path)
   └─► Remote: POST /add_to_global_server_lock

3. Server A performs sync
   └─► rsync to Server B

4. Server A releases locks:
   ├─► Local: remove_from_global_server_locks("server-b", path)
   └─► Remote: POST /remove_from_global_server_lock

Timeout handling:
  ├─► Locks expire after max_lock_time (default 30 min)
  └─► Background thread calls clear_lock_if_expired()
```

**Lock State Diagram**:
```
        request lock
┌───────┐  (not locked)  ┌────────┐
│ FREE  ├───────────────►│ LOCKED │
└───┬───┘                └───┬────┘
    │                        │
    │ ◄──────────────────────┤
    │    unlock OR timeout   │
    │                        │
    └────────────────────────┘
```

### 4. RsyncManager

**Purpose**: Execute rsync operations with proper SSH configuration and command hooks.

**Rsync Command Building**:
```python
def build_rsync_command():
    base = ["rsync"]

    # Add options (e.g., -avPrl --delete)
    base.extend(options.split())

    # Add SSH configuration if using remote
    if ssh_port:
        base.extend(["-e", f"ssh -p {ssh_port}"])

    # Add excludes
    for exclude in exclude_list:
        base.extend(["--exclude", exclude])

    # Add includes (for selective sync)
    if include_list:
        for include in include_list:
            base.extend(["--include", include])
        base.extend(["--exclude", "*"])  # Exclude everything else

    # Add source and destination
    base.extend([source_path, f"{user}@{host}:{dest_path}"])

    return base
```

**Command Execution Flow**:
```
run():
  │
  ├─► Run pre_sync_commands_local
  │   └─ Check exit codes if checkexit variant
  │
  ├─► Run pre_sync_commands_remote (via SSH)
  │   └─ Check exit codes if checkexit variant
  │
  ├─► Build rsync command
  │
  ├─► Execute rsync
  │   ├─ Capture stdout/stderr
  │   └─ Get exit code
  │
  ├─► Run post_sync_commands_remote
  │
  ├─► Run post_sync_commands_local
  │
  └─► Return (success, exit_code)
```

## Data Flow

### File Creation Flow

```
User creates file
       │
       ▼
┌─────────────┐
│   inotify   │ IN_CREATE event
│             │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ FilesystemMonitor   │
│   handle_event()    │
└──────┬──────────────┘
       │
       ├─► add_immediate_sync_file()
       │   └─ File added to immediate_sync set
       │
       ▼
┌─────────────────────┐
│   Event Loop        │
│   (main thread)     │
└──────┬──────────────┘
       │
       ├─► Spawn sync thread for destination
       │
       ▼
┌─────────────────────┐
│ manage_destination_ │
│     event()         │
└──────┬──────────────┘
       │
       ├─► Get immediate_sync_files for path
       ├─► Filter by extension
       ├─► Acquire locks
       │
       ▼
┌─────────────────────┐
│   RsyncManager      │
│      .run()         │
└──────┬──────────────┘
       │
       ├─► Build rsync command with includes
       ├─► Execute rsync
       │
       ▼
┌─────────────────────┐
│   Remote Server     │
│   (via SSH/rsync)   │
└──────┬──────────────┘
       │
       ▼
    Success
       │
       ├─► Mark file as synced
       ├─► Remove from immediate_sync
       ├─► Release locks
       └─► Update statistics
```

### Batch Sync Flow

```
Multiple file modifications
       │
       ▼
Files accumulate in regular_sync set
       │
       ▼
Queue reaches event_queue_limit
       │
       ▼
┌─────────────────────┐
│ manage_destination_ │
│     event()         │
└──────┬──────────────┘
       │
       ├─► Get regular_sync_files for path
       ├─► Clear locks exceeded wait time
       ├─► Build include list (exclude locked files)
       ├─► Acquire locks
       │
       ▼
┌─────────────────────┐
│   RsyncManager      │
│      .run()         │
└──────┬──────────────┘
       │
       ├─► Sync batch of files
       │
       ▼
    Success
       │
       ├─► Mark files as synced
       ├─► Remove from regular_sync
       ├─► Release locks
       └─► Update statistics
```

## Thread Safety Model

### Lock Hierarchy

To prevent deadlocks, always acquire locks in this order:

```
1. destinations_lock (SyncApplication)
   └─► 2. global_server_locks_lock (SyncApplication)
       └─► 3. files_lock (SyncApplication)
           └─► 4. Monitor locks (FilesystemMonitor)
                ├─► immediate_sync_lock
                ├─► regular_sync_lock
                └─► open_files_lock
```

### Critical Sections

**FilesystemMonitor Operations**:
```python
# CORRECT: Use lock for all operations
def get_immediate_sync_files(self, path_filter=None):
    with self.immediate_sync_lock:
        return [f for f in self.immediate_sync if matches(f, path_filter)]

# INCORRECT: No lock (race condition!)
def get_immediate_sync_files_bad(self, path_filter=None):
    return [f for f in self.immediate_sync if matches(f, path_filter)]
```

**Web API Operations**:
```python
# Use WebControl._lock for sync_state access
@app.get("/stats-running")
async def stats_running():
    with self._lock:  # Protects access to sync_state
        return get_statistics(sync_state)
```

### Thread Communication

```
Main Thread ──┐
              │
              ├──► spawns ──► Sync Worker Thread 1
              │                   │
              │                   └──► acquires lock
              │                   └──► syncs files
              │                   └──► releases lock
              │
              ├──► spawns ──► Sync Worker Thread 2
              │                   │
              │                   └──► waits for lock...
              │
              └──► spawns ──► Sync Worker Thread 3

Web Server Thread (daemon)
    │
    └──► handles API requests
         └──► acquires WebControl._lock
         └──► reads sync_state
         └──► releases lock

Full Sync Thread (background)
    │
    └──► periodic timer
         └──► checks last_full_sync timestamp
         └──► runs full sync if needed
```

## API Reference

See [Web API Documentation](IMPROVEMENTS.md#api-usage-examples) for detailed API examples.

### Endpoint Summary

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/` | GET | No | List all routes |
| `/health` | GET | No | Health check |
| `/dashboard` | GET | Query | Web dashboard |
| `/stats` | GET | Query | Basic statistics |
| `/stats-running` | GET | Query | Detailed runtime stats |
| `/regular_pending` | GET | Header | Get regular sync files |
| `/immediate_pending` | GET | Header | Get immediate sync files |
| `/locked_files` | GET | Header | Get locked files |
| `/pending_files_by_path` | GET | Query | Get pending files for path |
| `/add_to_global_server_lock` | POST | Header | Acquire server lock |
| `/remove_from_global_server_lock` | POST | Header | Release server lock |
| `/check_if_server_locked` | POST | Header | Check lock status |
| `/delete_file_pending_for_path` | POST | Header | Remove file from queue |
| `/trigger_sync` | POST | Header | Manually trigger sync |

## Configuration

### Destination Configuration Explained

```json
{
  "destination": "root@remote-server",
  "destination_path": "/remote/path",
  "path": "/local/path",
  "enabled": true,

  "event_queue_limit": 100,
  "time_event_delay": 5,

  "events": ["IN_MODIFY", "IN_DELETE", "IN_CREATE"],

  "extensions_to_ignore": [".tmp", ".swp"],
  "files_to_exclude": ["/local/path/.git", "*.log"],

  "use_global_server_lock": true,
  "notify_file_locks": true,
  "max_wait_locked": 60,

  "full_sync_interval": 1440,

  "control_server_host": "remote-server",
  "control_server_port": 8080,
  "control_server_secret": "shared-secret",

  "ssh_port": 22,
  "options": "-avPrl --delete",

  "pre_sync_commands_local": ["echo Starting sync"],
  "post_sync_commands_local": ["echo Sync complete"],
  "pre_sync_commands_remote": ["echo Remote ready"],
  "post_sync_commands_remote": ["echo Remote received"]
}
```

### Configuration Best Practices

1. **Event Queue Limit**: Set based on change frequency
   - High change rate: 50-100
   - Low change rate: 10-20

2. **Time Event Delay**: Time between event batches
   - Fast sync: 1-3 seconds
   - Normal: 5 seconds
   - Reduce load: 10-30 seconds

3. **Extensions to Ignore**: Add temporary files
   ```json
   [".tmp", ".swp", ".swx", ".lock", "~"]
   ```

4. **Files to Exclude**: Exclude non-essential directories
   ```json
   [".git", ".venv", "__pycache__", "node_modules"]
   ```

## Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Add file to sync | O(n) | Check for duplicates in set |
| Get files for path | O(n) | Linear scan with path filter |
| Delete file from sync | O(n) | Find and remove from set |
| Acquire lock | O(1) | Lock acquisition |
| Event processing | O(1) | Per event |

### Space Complexity

| Structure | Size | Notes |
|-----------|------|-------|
| immediate_sync | O(n) | n = pending immediate files |
| regular_sync | O(m) | m = pending regular files, ≤ max_tracked_files |
| open_files | O(k) | k = currently open files |
| statistics | O(d × s) | d = destinations, s = max_stats |

### Performance Tuning

**For High-Volume Environments**:
```json
{
  "event_queue_limit": 1000,
  "time_event_delay": 1,
  "max_tracked_files": 100000,
  "max_stats": 50
}
```

**For Low-Resource Environments**:
```json
{
  "event_queue_limit": 20,
  "time_event_delay": 10,
  "max_tracked_files": 10000,
  "max_stats": 20
}
```

## Troubleshooting

### Common Issues

**Files not syncing**:
1. Check `/pending_files_by_path` to see if files are queued
2. Check `/locked_files` for stuck locked files
3. Verify `event_queue_limit` is being reached
4. Check logs for rsync errors

**High memory usage**:
1. Reduce `max_tracked_files`
2. Reduce `max_stats`
3. Add more items to `files_to_exclude`
4. Check for file accumulation in sync queues

**Sync delays**:
1. Reduce `time_event_delay`
2. Reduce `event_queue_limit`
3. Check `use_global_server_lock` - may be waiting for locks
4. Verify network latency to remote server

### Debug Checklist

```bash
# 1. Check system health
curl http://localhost:8080/health

# 2. Check pending files
curl "http://localhost:8080/stats-running?secret=your-secret" | jq '.aggregated_events'

# 3. Check specific destination
curl "http://localhost:8080/pending_files_by_path?path=/your/path&secret=your-secret"

# 4. Check server locks
curl "http://localhost:8080/stats-running?secret=your-secret" | jq '.global_server_locks'

# 5. Check recent statistics
curl "http://localhost:8080/stats?secret=your-secret" | jq '.result[0].statistics[-5:]'
```
