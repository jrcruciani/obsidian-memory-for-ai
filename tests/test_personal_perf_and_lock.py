"""TDD tests for zero-copy shadow validation and cooperative write locking."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from kflib.capture import capture_signal
from kflib.templates import init_vault
from kflib.transact import validate_candidate_writes


class TestZeroCopyValidationAndLocking(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        init_vault(self.vault)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_validate_candidate_writes_does_not_copy_sources(self) -> None:
        # Place a real source note AND a large binary asset in sources/
        (self.vault / "sources/valid-note.md").write_text("# Source note\n", encoding="utf-8")
        big_file = self.vault / "sources/large-scan.bin"
        big_file.write_bytes(b"\x00" * (12 * 1024 * 1024))  # 12 MB binary asset

        shadow_had_big_file: list[bool] = []
        import kflib.transact as transact_mod

        orig_lint = transact_mod.lint_vault

        def inspecting_lint(shadow_root, *args, **kwargs):
            shadow_had_big_file.append((shadow_root / "sources/large-scan.bin").exists())
            return orig_lint(shadow_root, *args, **kwargs)

        with mock.patch.object(transact_mod, "lint_vault", side_effect=inspecting_lint):
            sig = capture_signal(
                self.vault,
                emitted_by="agent-executor-00000004",
                kind="gap",
                summary="Need protocol for large scan",
                evidence=["sources/valid-note.md"],
            )

        self.assertTrue((self.vault / sig["path"]).is_file())
        self.assertTrue(shadow_had_big_file, "expected lint_vault to be invoked during validation")
        self.assertFalse(
            any(shadow_had_big_file),
            "sources/large-scan.bin MUST NOT be copied into shadow temp directory during validation",
        )

        # Missing source evidence MUST still fail validation!
        with self.assertRaises(ValueError):
            capture_signal(
                self.vault,
                emitted_by="agent-executor-00000004",
                kind="gap",
                summary="Broken source ref should fail",
                evidence=["sources/nonexistent-file.md"],
            )

    def test_cooperative_write_lock_blocks_concurrent_process_and_allows_reentry(self) -> None:
        from kflib.locking import vault_write_lock

        # Re-entrant locking in the same process must succeed without deadlocking
        with vault_write_lock(self.vault, timeout_s=2.0):
            with vault_write_lock(self.vault, timeout_s=0.5):
                self.assertTrue((self.vault / "factory/_staging/.kf.lock").exists())

        # Concurrent external process holding the lock must cause TimeoutError on short timeout
        ready_file = Path(self._tmp.name) / "locked.ready"
        release_file = Path(self._tmp.name) / "release.go"
        holder_code = (
            f"import sys, time\n"
            f"from pathlib import Path\n"
            f"sys.path.insert(0, {str(REPO_ROOT / 'tools')!r})\n"
            f"from kflib.locking import vault_write_lock\n"
            f"with vault_write_lock(Path({str(self.vault)!r}), timeout_s=5.0):\n"
            f"    Path({str(ready_file)!r}).write_text('ok')\n"
            f"    while not Path({str(release_file)!r}).exists():\n"
            f"        time.sleep(0.02)\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", holder_code])
        try:
            deadline = time.monotonic() + 5.0
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready_file.exists(), "holder process failed to acquire lock")

            with self.assertRaises(TimeoutError):
                with vault_write_lock(self.vault, timeout_s=0.15):
                    pass

            release_file.write_text("go", encoding="utf-8")
            proc.wait(timeout=5.0)
            self.assertEqual(proc.returncode, 0)

            # Now lock can be acquired cleanly
            with vault_write_lock(self.vault, timeout_s=2.0):
                pass
        finally:
            release_file.write_text("go", encoding="utf-8")
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
