"""
File locking and concurrency protection for the image system.

Uses two layers:
  1. threading.RLock  — in-process safety (same Python interpreter)
  2. FileLock         — cross-process safety via .lock sentinel files
                        (Windows-compatible: no fcntl dependency)

Usage:
    with thread_lock("sqlite_writes"):
        db.execute(...)

    with safe_write(Path("output/image.png")):
        path.write_bytes(data)

    with FileLock(Path("config/routes.json")):
        ...
"""
import contextlib
import logging
import threading
import time
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# ── In-process RLock registry ─────────────────────────────────────────────────

_LOCKS: Dict[str, threading.RLock] = {}
_REGISTRY_LOCK = threading.Lock()


def get_lock(name: str) -> threading.RLock:
    """Return (creating if needed) the named RLock."""
    with _REGISTRY_LOCK:
        if name not in _LOCKS:
            _LOCKS[name] = threading.RLock()
        return _LOCKS[name]


@contextlib.contextmanager
def thread_lock(name: str):
    """Acquire the named in-process reentrant lock for the duration of the block."""
    lock = get_lock(name)
    acquired = lock.acquire(timeout=15)
    if not acquired:
        raise TimeoutError(f"Could not acquire thread lock '{name}' within 15 s")
    try:
        yield
    finally:
        lock.release()


# ── Cross-process file lock ────────────────────────────────────────────────────

class FileLock:
    """
    Cross-process file lock implemented via exclusive file creation.
    Windows-compatible: does not use fcntl or os.O_EXCL on the target file.
    Instead creates a separate <path>.lock sentinel file.
    """

    def __init__(self, path: Path, timeout: float = 10.0, poll: float = 0.05):
        self.lock_path = Path(str(path) + ".lock")
        self.timeout = timeout
        self.poll = poll
        self._fd = None

    def acquire(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                # 'x' mode = exclusive create — raises FileExistsError if file exists
                self._fd = open(self.lock_path, "x")
                logger.debug("FileLock acquired: %s", self.lock_path)
                return
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Could not acquire file lock on {self.lock_path} "
                        f"within {self.timeout} s"
                    )
                time.sleep(self.poll)

    def release(self):
        if self._fd:
            try:
                self._fd.close()
            except Exception:
                pass
            self._fd = None
        try:
            self.lock_path.unlink(missing_ok=True)
            logger.debug("FileLock released: %s", self.lock_path)
        except Exception as exc:
            logger.warning("FileLock release error: %s", exc)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


@contextlib.contextmanager
def safe_write(path: Path, timeout: float = 10.0):
    """
    Context manager that acquires a FileLock around a write operation.
    Ensures no two concurrent callers write to the same path simultaneously.

    Usage:
        with safe_write(output_path):
            output_path.write_bytes(data)
    """
    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(Path(path), timeout=timeout)
    with lock:
        yield
