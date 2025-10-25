"""
Move/Rename Detection Engine

Detects when files are moved or renamed by comparing their content hashes.
This allows the sync system to recognize that a file is the same (just in a
different location) and avoid retransferring it entirely.

Algorithm:
1. Calculate content hash (xxHash64) for each file
2. Build hash -> path mapping for both old and new state
3. For each file in new state:
   - Check if same hash exists in old state with different path
   - If found: this is a MOVE/RENAME operation
   - If not found: this is a NEW file or content changed
4. Return list of move operations

Result: 0 bandwidth used for moved files (just update path)

Example:
Before sync:
  /data/documents/report-2024.pdf (hash: abc123)

After sync:
  /backup/report-2024.pdf (hash: abc123)

Detection result:
  MOVE: /data/documents/report-2024.pdf -> /backup/report-2024.pdf

Benefit: No re-transfer needed, instant move on destination
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import xxhash

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class FileEntry:
    """Represents a file in the filesystem"""
    path: str                           # Relative path
    hash: str                           # Content hash
    size: int                           # File size in bytes
    mtime: float                        # Modification time

    def __hash__(self):
        return hash(self.hash)

    def __eq__(self, other):
        return self.hash == other.hash


@dataclass
class MoveOperation:
    """Represents a file move/rename"""
    source_path: str                    # Original path
    dest_path: str                      # New path
    file_hash: str                      # Content hash (unchanged)
    file_size: int                      # File size


@dataclass
class FileSystemState:
    """Snapshot of filesystem state"""
    files: Dict[str, FileEntry]         # path -> FileEntry
    hash_to_paths: Dict[str, List[str]] # hash -> [paths with this hash]

    @classmethod
    def from_file_list(cls, files: List[FileEntry]) -> 'FileSystemState':
        """Create state from list of files"""
        files_dict = {f.path: f for f in files}
        hash_map = {}

        for file in files:
            if file.hash not in hash_map:
                hash_map[file.hash] = []
            hash_map[file.hash].append(file.path)

        return cls(files=files_dict, hash_to_paths=hash_map)


# ============================================================================
# Hash Calculator
# ============================================================================

class FileHashCalculator:
    """Calculate content hashes for files"""

    CHUNK_SIZE = 65536  # 64KB chunks

    def __init__(self, logger=None):
        """Initialize calculator"""
        self.logger = logger or logging.getLogger(__name__)

    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """
        Calculate xxHash64 of file content.

        Args:
            file_path: Path to file

        Returns:
            Hex string of hash or None on error
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None

            hasher = xxhash.xxh64()

            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)

            return hasher.hexdigest()

        except Exception as e:
            self.logger.debug(f"Error calculating hash for {file_path}: {e}")
            return None


# ============================================================================
# Move Detection
# ============================================================================

class MoveDetector:
    """Detects moved/renamed files"""

    def __init__(self, logger=None):
        """Initialize detector"""
        self.logger = logger or logging.getLogger(__name__)
        self.hash_calculator = FileHashCalculator(logger=logger)

    def detect_moves(self, old_state: FileSystemState,
                    new_state: FileSystemState) -> List[MoveOperation]:
        """
        Detect moved/renamed files between two states.

        Args:
            old_state: Previous filesystem state
            new_state: Current filesystem state

        Returns:
            List of MoveOperation objects
        """
        moves = []

        # For each file in new state
        for new_path, new_file in new_state.files.items():
            # Skip if this path exists in old state (not a move)
            if new_path in old_state.files:
                continue

            # Check if same hash exists in old state with different path
            if new_file.hash in old_state.hash_to_paths:
                old_paths = old_state.hash_to_paths[new_file.hash]

                # Find the best match (prefer closest path)
                if len(old_paths) == 1:
                    old_path = old_paths[0]
                    moves.append(MoveOperation(
                        source_path=old_path,
                        dest_path=new_path,
                        file_hash=new_file.hash,
                        file_size=new_file.size
                    ))
                else:
                    # Multiple files with same hash - pick closest match
                    best_match = self._find_best_match(new_path, old_paths)
                    if best_match:
                        moves.append(MoveOperation(
                            source_path=best_match,
                            dest_path=new_path,
                            file_hash=new_file.hash,
                            file_size=new_file.size
                        ))

        if moves:
            self.logger.info(f"Detected {len(moves)} moved/renamed files")
            for move in moves:
                self.logger.debug(f"MOVE: {move.source_path} -> {move.dest_path}")

        return moves

    def _find_best_match(self, new_path: str, old_paths: List[str]) -> Optional[str]:
        """
        Find best matching path among multiple candidates.

        Uses similarity heuristics to match paths.

        Args:
            new_path: New path
            old_paths: Candidate old paths

        Returns:
            Best matching old path or None
        """
        if not old_paths:
            return None

        if len(old_paths) == 1:
            return old_paths[0]

        # Simple heuristic: pick path with longest common suffix
        best_match = old_paths[0]
        best_score = self._path_similarity(new_path, best_match)

        for old_path in old_paths[1:]:
            score = self._path_similarity(new_path, old_path)
            if score > best_score:
                best_score = score
                best_match = old_path

        return best_match

    def _path_similarity(self, path1: str, path2: str) -> int:
        """
        Calculate similarity score between two paths.

        Higher score = more similar

        Args:
            path1: First path
            path2: Second path

        Returns:
            Similarity score
        """
        # Compare path components (directories)
        parts1 = Path(path1).parts
        parts2 = Path(path2).parts

        # Count matching parts from the end
        matches = 0
        for p1, p2 in zip(reversed(parts1), reversed(parts2)):
            if p1 == p2:
                matches += 1
            else:
                break

        # Also compare filename
        name1 = Path(path1).name
        name2 = Path(path2).name
        if name1 == name2:
            matches += 10

        return matches


# ============================================================================
# Move Detector Manager
# ============================================================================

class MoveDetectorManager:
    """
    High-level manager for move detection.

    Coordinates scanning and detection of moved files.
    """

    def __init__(self, logger=None):
        """Initialize manager"""
        self.logger = logger or logging.getLogger(__name__)
        self.detector = MoveDetector(logger=logger)
        self.calculator = FileHashCalculator(logger=logger)

    def scan_directory(self, directory: str, relative_to: Optional[str] = None) -> List[FileEntry]:
        """
        Scan directory and collect file information.

        Args:
            directory: Directory to scan
            relative_to: Base path for relative paths (default: directory)

        Returns:
            List of FileEntry objects
        """
        if relative_to is None:
            relative_to = directory

        files = []
        base_path = Path(relative_to)

        try:
            for file_path in Path(directory).rglob('*'):
                if file_path.is_file():
                    try:
                        # Get relative path
                        rel_path = str(file_path.relative_to(base_path))

                        # Calculate hash
                        file_hash = self.calculator.calculate_file_hash(str(file_path))
                        if file_hash is None:
                            continue

                        # Get file info
                        stat_info = file_path.stat()

                        entry = FileEntry(
                            path=rel_path,
                            hash=file_hash,
                            size=stat_info.st_size,
                            mtime=stat_info.st_mtime
                        )
                        files.append(entry)

                    except Exception as e:
                        self.logger.debug(f"Error processing file {file_path}: {e}")
                        continue

        except Exception as e:
            self.logger.error(f"Error scanning directory {directory}: {e}")

        self.logger.debug(f"Scanned {len(files)} files in {directory}")
        return files

    def detect_moves_between_dirs(self, old_dir: str, new_dir: str) -> List[MoveOperation]:
        """
        Detect moves between two directory states.

        Args:
            old_dir: Previous directory state
            new_dir: Current directory state

        Returns:
            List of MoveOperation objects
        """
        # Scan both directories
        self.logger.info(f"Scanning {old_dir} for previous state...")
        old_files = self.scan_directory(old_dir)

        self.logger.info(f"Scanning {new_dir} for current state...")
        new_files = self.scan_directory(new_dir)

        # Build states
        old_state = FileSystemState.from_file_list(old_files)
        new_state = FileSystemState.from_file_list(new_files)

        # Detect moves
        return self.detector.detect_moves(old_state, new_state)

    def get_moves_bandwidth_savings(self, moves: List[MoveOperation]) -> int:
        """
        Calculate total bandwidth saved by detecting moves.

        Args:
            moves: List of move operations

        Returns:
            Total bytes saved
        """
        return sum(move.file_size for move in moves)


# ============================================================================
# Utility Functions
# ============================================================================

def detect_moves(old_state: FileSystemState,
                new_state: FileSystemState) -> List[MoveOperation]:
    """
    Convenience function to detect moves.

    Args:
        old_state: Previous state
        new_state: Current state

    Returns:
        List of MoveOperation objects
    """
    detector = MoveDetector()
    return detector.detect_moves(old_state, new_state)


def scan_directory(directory: str, relative_to: Optional[str] = None) -> List[FileEntry]:
    """
    Convenience function to scan directory.

    Args:
        directory: Directory to scan
        relative_to: Base path for relative paths

    Returns:
        List of FileEntry objects
    """
    manager = MoveDetectorManager()
    return manager.scan_directory(directory, relative_to)


def calculate_total_bandwidth_savings(old_dir: str, new_dir: str) -> int:
    """
    Calculate bandwidth saved by move detection.

    Args:
        old_dir: Previous directory
        new_dir: Current directory

    Returns:
        Bytes saved
    """
    manager = MoveDetectorManager()
    moves = manager.detect_moves_between_dirs(old_dir, new_dir)
    return manager.get_moves_bandwidth_savings(moves)
