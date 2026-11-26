"""Cross-platform, thread-safe cooperative write lock for Knowledge Factory vaults."""

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

_LOCAL_COND = threading.Condition()
# Maps resolved vault path -> [owner_thread_ident, reentrant_depth]
_HELD_BY_THREAD: dict[Path, list[int]] = {}


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
    """Acquire a thread-safe, re-entrant cooperative exclusive lock for vault mutations.

    - Same thread re-entering the lock increments its depth cleanly.
    - Other threads in the same process wait up to ``timeout_s`` before raising ``TimeoutError``.
    - Other OS processes are serialized via ``fcntl.flock`` / ``msvcrt.locking`` on
      ``factory/_staging/.kf.lock``.
    """
    resolved = root.resolve()
    lock_path = resolved / "factory/_staging/.kf.lock"
    wait_budget = _default_timeout() if timeout_s is None else max(0.0, float(timeout_s))
    deadline = time.monotonic() + wait_budget
    me = threading.get_ident()

    with _LOCAL_COND:
        while True:
            state = _HELD_BY_THREAD.get(resolved)
            if state is None:
                _HELD_BY_THREAD[resolved] = [me, 1]
                reentrant = False
                break
            if state[0] == me:
                state[1] += 1
                reentrant = True
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"timed out after {wait_budget:.2f}s waiting for vault write lock (held by another thread) at {lock_path}"
                )
            _LOCAL_COND.wait(timeout=min(0.05, remaining))

    if reentrant:
        try:
            yield
        finally:
            with _LOCAL_COND:
                _HELD_BY_THREAD[resolved][1] -= 1
        return

    fd: int | None = None
    os_acquired = False
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        while True:
            if _try_acquire_os_lock(fd):
                os_acquired = True
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out after {wait_budget:.2f}s waiting for vault write lock at {lock_path}"
                )
            time.sleep(0.02)
        yield
    finally:
        if os_acquired and fd is not None:
            _release_os_lock(fd)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        with _LOCAL_COND:
            _HELD_BY_THREAD.pop(resolved, None)
            _LOCAL_COND.notify_all()
