"""
Distributed Consensus Engine for FSRsync

Implements Raft-inspired consensus mechanism with:
- Leader election
- Log replication
- State machine
- Snapshot management
- Term tracking
- Heartbeat mechanism
- Log compaction

## Consensus States

FOLLOWER: Passive participant, accepts leader decisions
CANDIDATE: Competing for leadership
LEADER: Active coordinator, proposes changes
DEAD: Crashed node
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class ConsensusState(Enum):
    """Node state in consensus"""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    DEAD = "dead"


@dataclass
class LogEntry:
    """Entry in distributed log"""
    term: int
    index: int
    command: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    committed: bool = False


@dataclass
class SnapshotMetadata:
    """Snapshot metadata"""
    snapshot_id: str
    term: int
    last_included_index: int
    timestamp: float = field(default_factory=time.time)
    state_size: int = 0
    checksum: Optional[str] = None


class ConsensusEngine:
    """
    Raft-inspired distributed consensus engine.

    Coordinates cluster-wide agreement on state changes
    with automatic leader election and log replication.
    """

    def __init__(self, node_id: str, cluster_nodes: List[str],
                 logger_instance=None):
        """
        Initialize consensus engine.

        Args:
            node_id: This node's identifier
            cluster_nodes: List of all cluster node IDs
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.node_id = node_id
        self.cluster_nodes = set(cluster_nodes)

        # Persistent state (on all servers)
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []

        # Volatile state (on all servers)
        self.state = ConsensusState.FOLLOWER
        self.commit_index = 0
        self.last_applied = 0

        # Volatile state (on leaders)
        self.next_index: Dict[str, int] = {
            node: len(self.log) for node in self.cluster_nodes
        }
        self.match_index: Dict[str, int] = {
            node: 0 for node in self.cluster_nodes
        }

        # Timeouts
        self.election_timeout = self._random_election_timeout()
        self.heartbeat_interval = 0.1  # 100ms
        self.last_heartbeat_time = time.time()
        self.last_election_time = time.time()

        # State machine
        self.state_machine: Dict[str, Any] = {}
        self.snapshots: Dict[str, SnapshotMetadata] = {}

        # Statistics
        self.elections_won = 0
        self.elections_lost = 0
        self.log_replications_succeeded = 0
        self.log_replications_failed = 0

        self.logger.info(
            f"ConsensusEngine initialized: node={node_id}, "
            f"cluster_size={len(cluster_nodes)}"
        )

    def _random_election_timeout(self) -> float:
        """Generate random election timeout"""
        import random
        return 1.5 + random.random() * 1.0  # 1.5s to 2.5s

    def append_entry(self, command: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Append entry to log (leader only).

        Args:
            command: Command to execute
            data: Command data

        Returns:
            True if entry appended
        """
        try:
            if self.state != ConsensusState.LEADER:
                self.logger.warning(
                    f"Cannot append entry: node is not leader "
                    f"(state={self.state.value})"
                )
                return False

            entry = LogEntry(
                term=self.current_term,
                index=len(self.log),
                command=command,
                data=data or {}
            )

            self.log.append(entry)
            self.match_index[self.node_id] = len(self.log) - 1

            self.logger.debug(
                f"Appended entry to log: index={entry.index}, "
                f"term={entry.term}, command={command}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error appending entry: {e}")
            return False

    def request_vote(self, candidate_id: str, term: int,
                    last_log_index: int, last_log_term: int) -> Tuple[bool, int]:
        """
        Handle vote request (RequestVote RPC).

        Args:
            candidate_id: Candidate requesting vote
            term: Candidate's term
            last_log_index: Index of candidate's last log entry
            last_log_term: Term of candidate's last log entry

        Returns:
            Tuple of (vote_granted, current_term)
        """
        try:
            # If term > current_term, update term and convert to follower
            if term > self.current_term:
                self.current_term = term
                self.voted_for = None
                self.state = ConsensusState.FOLLOWER

            current_term = self.current_term

            # Deny vote if term < current_term
            if term < current_term:
                return False, current_term

            # Check if can vote for this candidate
            if self.voted_for is not None and self.voted_for != candidate_id:
                return False, current_term

            # Check if candidate's log is at least as up-to-date
            last_log_idx = len(self.log) - 1
            last_log_term_local = self.log[last_log_idx].term if self.log else 0

            if last_log_term < last_log_term_local:
                return False, current_term

            if (last_log_term == last_log_term_local and
                last_log_index < last_log_idx):
                return False, current_term

            # Grant vote
            self.voted_for = candidate_id
            self.last_election_time = time.time()

            self.logger.info(f"Voted for candidate {candidate_id} in term {term}")
            return True, current_term

        except Exception as e:
            self.logger.error(f"Error handling vote request: {e}")
            return False, self.current_term

    def append_entries(self, leader_id: str, term: int, prev_log_index: int,
                      prev_log_term: int, entries: List[Dict[str, Any]],
                      leader_commit: int) -> Tuple[bool, int]:
        """
        Handle append entries request (AppendEntries RPC).

        Args:
            leader_id: ID of leader
            term: Leader's term
            prev_log_index: Index of previous log entry
            prev_log_term: Term of previous log entry
            entries: Entries to append
            leader_commit: Leader's commit index

        Returns:
            Tuple of (success, current_term)
        """
        try:
            # If term > current_term, update state
            if term > self.current_term:
                self.current_term = term
                self.state = ConsensusState.FOLLOWER
                self.voted_for = None

            # Deny if term < current_term
            if term < self.current_term:
                return False, self.current_term

            # Update election timeout
            self.last_election_time = time.time()
            self.last_heartbeat_time = time.time()

            # Check log matching
            if prev_log_index > 0:
                if prev_log_index >= len(self.log):
                    return False, self.current_term

                if self.log[prev_log_index].term != prev_log_term:
                    return False, self.current_term

            # Append new entries
            for i, entry_data in enumerate(entries):
                entry = LogEntry(
                    term=term,
                    index=prev_log_index + 1 + i,
                    command=entry_data.get('command', ''),
                    data=entry_data.get('data', {})
                )

                if entry.index < len(self.log):
                    if self.log[entry.index].term != term:
                        # Delete conflicting entries
                        self.log = self.log[:entry.index]
                        self.log.append(entry)
                else:
                    self.log.append(entry)

            # Update commit index
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log) - 1)

            self.logger.debug(
                f"Appended {len(entries)} entries from leader {leader_id}"
            )

            return True, self.current_term

        except Exception as e:
            self.logger.error(f"Error handling append entries: {e}")
            return False, self.current_term

    def start_election(self) -> bool:
        """
        Start leader election.

        Returns:
            True if election started
        """
        try:
            self.current_term += 1
            self.state = ConsensusState.CANDIDATE
            self.voted_for = self.node_id
            self.election_timeout = self._random_election_timeout()
            self.last_election_time = time.time()

            self.logger.info(
                f"Starting election in term {self.current_term}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error starting election: {e}")
            return False

    def become_leader(self) -> bool:
        """
        Transition to leader state.

        Returns:
            True if became leader
        """
        try:
            self.state = ConsensusState.LEADER
            self.last_heartbeat_time = time.time()

            # Initialize leader state
            for node in self.cluster_nodes:
                if node != self.node_id:
                    self.next_index[node] = len(self.log)
                    self.match_index[node] = 0

            self.elections_won += 1

            self.logger.info(
                f"Became leader in term {self.current_term}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error becoming leader: {e}")
            return False

    def commit_entries(self) -> List[LogEntry]:
        """
        Commit entries that have been replicated to majority.

        Returns:
            List of newly committed entries
        """
        try:
            committed_entries = []

            if self.state != ConsensusState.LEADER:
                return committed_entries

            # Find highest index replicated on majority
            replicated_indices = sorted(
                [self.match_index[node] for node in self.cluster_nodes],
                reverse=True
            )

            majority_index = replicated_indices[len(self.cluster_nodes) // 2]

            # Commit entries up to majority index
            while self.commit_index < majority_index:
                self.commit_index += 1

                if self.commit_index < len(self.log):
                    entry = self.log[self.commit_index]

                    if entry.term == self.current_term:
                        entry.committed = True
                        committed_entries.append(entry)

                        # Apply to state machine
                        self._apply_entry(entry)

            return committed_entries

        except Exception as e:
            self.logger.error(f"Error committing entries: {e}")
            return []

    def _apply_entry(self, entry: LogEntry) -> None:
        """Apply log entry to state machine"""
        try:
            # Execute command on state machine
            if entry.command == "set":
                key = entry.data.get('key')
                value = entry.data.get('value')
                if key:
                    self.state_machine[key] = value

            elif entry.command == "delete":
                key = entry.data.get('key')
                if key and key in self.state_machine:
                    del self.state_machine[key]

            self.last_applied = max(self.last_applied, entry.index)

            self.logger.debug(
                f"Applied entry: index={entry.index}, "
                f"command={entry.command}"
            )

        except Exception as e:
            self.logger.error(f"Error applying entry: {e}")

    def create_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """
        Create state machine snapshot.

        Args:
            snapshot_id: Unique snapshot identifier

        Returns:
            Snapshot metadata if created
        """
        try:
            import json
            import hashlib

            state_json = json.dumps(self.state_machine, sort_keys=True)
            checksum = hashlib.sha256(state_json.encode()).hexdigest()

            metadata = SnapshotMetadata(
                snapshot_id=snapshot_id,
                term=self.current_term,
                last_included_index=self.last_applied,
                state_size=len(state_json),
                checksum=checksum
            )

            self.snapshots[snapshot_id] = metadata

            self.logger.info(
                f"Created snapshot {snapshot_id} at index {self.last_applied}"
            )

            return metadata

        except Exception as e:
            self.logger.error(f"Error creating snapshot: {e}")
            return None

    def should_trigger_election(self) -> bool:
        """Check if election timeout has elapsed"""
        elapsed = time.time() - self.last_election_time
        return elapsed > self.election_timeout

    def should_send_heartbeat(self) -> bool:
        """Check if heartbeat interval has elapsed"""
        if self.state != ConsensusState.LEADER:
            return False

        elapsed = time.time() - self.last_heartbeat_time
        return elapsed > self.heartbeat_interval

    def get_consensus_status(self) -> Dict[str, Any]:
        """Get consensus engine status"""
        try:
            return {
                'node_id': self.node_id,
                'state': self.state.value,
                'current_term': self.current_term,
                'voted_for': self.voted_for,
                'log_length': len(self.log),
                'commit_index': self.commit_index,
                'last_applied': self.last_applied,
                'elections_won': self.elections_won,
                'elections_lost': self.elections_lost,
                'log_replications_succeeded': self.log_replications_succeeded,
                'log_replications_failed': self.log_replications_failed,
                'state_machine_size': len(self.state_machine),
                'snapshots_count': len(self.snapshots)
            }

        except Exception as e:
            self.logger.error(f"Error getting consensus status: {e}")
            return {}
