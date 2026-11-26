"""TDD tests for v5.1.1 hardening (from Hefesto's operational audit):
- Thread-safe re-entrant write locking
- Fast, date-independent hybrid index digest (ignores binary sources & midnight churn)
- True `--read-only` stdio MCP mode (zero filesystem writes, no sqlite auto-build)
- Privacy-respecting `include_notes`/`include_sources` filtering in hybrid MCP search
- Per-profile `--actor` identity & role enforcement in stdio MCP server
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from kflib.hybrid_index import build_hybrid_index, hybrid_search
from kflib.locking import vault_write_lock
from kflib.personal import remember_fact, write_note
from kflib.templates import init_vault

KF_MCP = REPO_ROOT / "tools/kf_mcp.py"


class TestV511Hardening(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_today = os.environ.get("KF_TODAY")
        self._orig_now = os.environ.get("KF_NOW")
        os.environ["KF_TODAY"] = "2026-10-15"
        os.environ["KF_NOW"] = "2026-10-15T12:00:00Z"
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        init_vault(self.vault, profile="personal")

    def tearDown(self) -> None:
        self._tmp.cleanup()
        if self._orig_today is None:
            os.environ.pop("KF_TODAY", None)
        else:
            os.environ["KF_TODAY"] = self._orig_today
        if self._orig_now is None:
            os.environ.pop("KF_NOW", None)
        else:
            os.environ["KF_NOW"] = self._orig_now

    def test_thread_safe_reentrant_lock_blocks_second_thread(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        t2_errors: list[BaseException] = []
        t2_acquired = threading.Event()

        def holder() -> None:
            with vault_write_lock(self.vault, timeout_s=3.0):
                # Same-thread re-entry must succeed
                with vault_write_lock(self.vault, timeout_s=0.5):
                    entered.set()
                    release.wait(timeout=5.0)

        def contender() -> None:
            entered.wait(timeout=3.0)
            try:
                with vault_write_lock(self.vault, timeout_s=0.15):
                    t2_acquired.set()
            except BaseException as exc:
                t2_errors.append(exc)

        th1 = threading.Thread(target=holder)
        th2 = threading.Thread(target=contender)
        th1.start()
        th2.start()
        th2.join(timeout=5.0)
        release.set()
        th1.join(timeout=5.0)

        self.assertFalse(t2_acquired.is_set(), "second thread must NOT bypass lock held by first thread")
        self.assertEqual(len(t2_errors), 1, f"expected TimeoutError in second thread, got: {t2_errors}")
        self.assertIsInstance(t2_errors[0], TimeoutError)

        # After release, another thread acquires cleanly
        with vault_write_lock(self.vault, timeout_s=1.0):
            pass

    def test_hybrid_index_digest_avoids_midnight_rebuild_and_binary_reads(self) -> None:
        remember_fact(self.vault, entity="jl", predicate="tool", value="Obsidian", pinned=True)
        (self.vault / "sources/big-archive.bin").write_bytes(b"\x00" * (16 * 1024 * 1024))

        build_hybrid_index(self.vault, use_embeddings=False)

        # Advance calendar day — no fact expired or changed, so hybrid_search MUST NOT rebuild!
        os.environ["KF_TODAY"] = "2026-10-16"
        import kflib.hybrid_index as hi_mod

        with mock.patch.object(
            hi_mod,
            "build_hybrid_index",
            side_effect=AssertionError("hybrid_search must NOT rebuild on mere date rollover"),
        ):
            _, results, diags = hybrid_search(self.vault, "Obsidian", use_embeddings=False, auto_build=True)
        self.assertTrue(results)
        self.assertEqual(diags, [])

    def _run_mcp(self, extra_args: list[str], requests: list[dict]) -> dict[int, dict]:
        env = os.environ.copy()
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, str(KF_MCP), "--vault", str(self.vault), *extra_args],
            input=payload,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, f"kf_mcp failed:\nSTDERR:{proc.stderr}\nSTDOUT:{proc.stdout}")
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        return {r["id"]: r for r in responses if "id" in r}

    def test_mcp_read_only_mode_blocks_writes_and_never_creates_sqlite(self) -> None:
        remember_fact(self.vault, entity="jl", predicate="editor", value="Neovim", pinned=True)
        # Ensure search.sqlite and _staging do not exist before read-only session
        db = self.vault / "_generated/indexes/search.sqlite"
        if db.exists():
            db.unlink()
        staging = self.vault / "factory/_staging"
        if staging.exists():
            import shutil
            shutil.rmtree(staging)

        by_id = self._run_mcp(
            ["--read-only"],
            [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "kf_remember", "arguments": {"entity": "jl", "predicate": "x", "value": "y"}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kf_search", "arguments": {"query": "Neovim", "hybrid": True}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "kf_sleep_pack", "arguments": {"emit_signals": True}}},
            ],
        )

        tool_names = {t["name"] for t in by_id[1]["result"]["tools"]}
        self.assertTrue(tool_names.isdisjoint({"kf_remember", "kf_forget", "kf_note", "kf_capture_signal"}))
        self.assertIn("kf_search", tool_names)

        self.assertTrue(by_id[2]["result"]["isError"], "kf_remember must fail in --read-only mode")

        srch = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertTrue(srch["results"], "read-only kf_search must still return results via BM25 fallback")
        self.assertFalse(db.exists(), "--read-only kf_search must NOT create search.sqlite")
        self.assertFalse(staging.exists(), "--read-only mode must NOT create factory/_staging/.kf.lock")

        # kf_sleep_pack must not have emitted signals in read-only mode
        self.assertEqual(list((self.vault / "factory/signals").rglob("*.md")), [])

    def test_mcp_hybrid_search_respects_include_notes_and_include_sources(self) -> None:
        (self.vault / "sources/private-doc.md").write_text("# Private\n\nContains token xylophone9988.\n", encoding="utf-8")
        write_note(self.vault, slug="diary", title="Private Diary", body="Contains token marigold7766.")
        build_hybrid_index(self.vault, use_embeddings=False, include_notes=True, include_sources=True)

        by_id = self._run_mcp(
            [],
            [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "kf_search", "arguments": {"query": "xylophone9988", "hybrid": True, "include_sources": False}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "kf_search", "arguments": {"query": "xylophone9988", "hybrid": True, "include_sources": True}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kf_search", "arguments": {"query": "marigold7766", "hybrid": True, "include_notes": False}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "kf_search", "arguments": {"query": "marigold7766", "hybrid": True, "include_notes": True}}},
            ],
        )

        r1 = json.loads(by_id[1]["result"]["content"][0]["text"])["results"]
        r2 = json.loads(by_id[2]["result"]["content"][0]["text"])["results"]
        r3 = json.loads(by_id[3]["result"]["content"][0]["text"])["results"]
        r4 = json.loads(by_id[4]["result"]["content"][0]["text"])["results"]

        self.assertEqual(r1, [], f"include_sources=False must exclude sources/ even in hybrid mode, got: {r1}")
        self.assertTrue(any(x["path"] == "sources/private-doc.md" for x in r2))
        self.assertEqual(r3, [], f"include_notes=False must exclude notes/ even in hybrid mode, got: {r3}")
        self.assertTrue(any(x["path"] == "knowledge/notes/general/diary.md" for x in r4))

    def test_mcp_actor_flag_enforces_profile_role_separation(self) -> None:
        by_id = self._run_mcp(
            ["--actor", "agent-executor-00000004"],
            [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "kf_capture_signal", "arguments": {"kind": "gap", "summary": "Missing backup guide"}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "kf_remember", "arguments": {"entity": "jl", "predicate": "role", "value": "Admin"}}},
            ],
        )

        sig = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertEqual(sig["emitted_by"], "agent-executor-00000004")
        self.assertTrue(by_id[2]["result"]["isError"], "executor actor must be blocked from direct kf_remember")


if __name__ == "__main__":
    unittest.main()
