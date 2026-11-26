"""Cross-platform cooperative write lock for Knowledge Factory vaults."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]

_LOCAL_GUARD = threading.Lock()
_HELD_COUNTS: dict[Path, int] = {}
_HELD_FDS: dict[Path, int] = {}


def _default_timeout() -> float:
    raw = os.environ.get("KF_LOCK_TIMEOUT", "10.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 10.0


def _try_acquire_os_lock(fd: int) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
    if msvcrt is not None:  # pragma: no cover - Windows
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            getattr(msvcrt, "locking")(fd, getattr(msvcrt, "LK_NBLCK"), 1)
            return True
        except OSError:
            return False
    return True


def _release_os_lock(fd: int) -> None:
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
    elif msvcrt is not None:  # pragma: no cover - Windows
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            getattr(msvcrt, "locking")(fd, getattr(msvcrt, "LK_UNLCK"), 1)
        except OSError:
            pass


@contextmanager
def vault_write_lock(root: Path, *, timeout_s: float | None = None) -> Iterator[None]:
    """Acquire a re-entrant cooperative exclusive lock for vault mutations.

    Lock file lives at ``factory/_staging/.kf.lock`` so it never touches
    canonical Markdown truth or Git history.
    """
    resolved = root.resolve()
    lock_path = resolved / "factory/_staging/.kf.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    wait_budget = _default_timeout() if timeout_s is None else max(0.0, float(timeout_s))

    with _LOCAL_GUARD:
        count = _HELD_COUNTS.get(resolved, 0)
        if count > 0:
            _HELD_COUNTS[resolved] = count + 1
            reentrant = True
        else:
            reentrant = False

    if reentrant:
        try:
            yield
        finally:
            with _LOCAL_GUARD:
                _HELD_COUNTS[resolved] -= 1
        return

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    deadline = time.monotonic() + wait_budget
    try:
        while True:
            if _try_acquire_os_lock(fd):
                acquired = True
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out after {wait_budget:.2f}s waiting for vault write lock at {lock_path}"
                )
            time.sleep(0.02)
        with _LOCAL_GUARD:
            _HELD_COUNTS[resolved] = 1
            _HELD_FDS[resolved] = fd
        yield
    finally:
        if acquired:
            with _LOCAL_GUARD:
                _HELD_COUNTS.pop(resolved, None)
                _HELD_FDS.pop(resolved, None)
            _release_os_lock(fd)
        try:
            os.close(fd)
        except OSError:
            pass
