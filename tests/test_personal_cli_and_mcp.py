"""End-to-end TDD tests for Personal CLI commands and stdio MCP server (`tools/kf_mcp.py`)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KF_PY = REPO_ROOT / "tools/kf.py"
KF_MCP = REPO_ROOT / "tools/kf_mcp.py"


class TestPersonalCLIAndMCP(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "my-memory"
        self.env = os.environ.copy()
        self.env["KF_TODAY"] = "2026-10-15"
        self.env["KF_NOW"] = "2026-10-15T12:00:00Z"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_kf(self, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(KF_PY), "--vault", str(self.vault), "--json", *args],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"kf.py {args} failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
        return json.loads(proc.stdout)

    def test_personal_cli_full_lifecycle(self) -> None:
        # 1. Init personal vault via CLI
        init_proc = subprocess.run(
            [sys.executable, str(KF_PY), "--json", "init", str(self.vault), "--profile", "personal"],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(init_proc.returncode, 0, init_proc.stderr)
        init_data = json.loads(init_proc.stdout)["data"]
        self.assertEqual(init_data["profile"], "personal")

        # 2. Remember, supersede, note, hybrid index, hybrid search, sleep-pack, OKF export
        rem1 = self._run_kf("remember", "--entity", "jl", "--predicate", "coffee", "--value", "Espresso doble", "--pinned")
        self.assertEqual(rem1["data"]["action"], "created")

        note = self._run_kf("note", "--slug", "ai-notes", "--title", "AI Memory Notes", "--body", "Hybrid FTS5 + Obsidian works great.", "--entities", "jl")
        self.assertIn("knowledge/notes/", note["data"]["path"])

        idx = self._run_kf("index", "build")
        self.assertGreater(idx["data"]["documents"], 0)

        srch = self._run_kf("query", "search", "espresso coffee", "--hybrid")
        self.assertTrue(srch["data"], f"expected hybrid search result, got: {srch}")

        boot = self._run_kf("bootstrap", "--profile", "personal", "--max-tokens", "400")
        self.assertLessEqual(boot["data"]["estimated_tokens"], 400)

        pack = self._run_kf("curate", "sleep-pack")
        self.assertIn("prompt_markdown", pack["data"])

        okf_out = Path(self._tmp.name) / "okf-out"
        exp = self._run_kf("export-okf", str(okf_out))
        self.assertGreaterEqual(exp["data"]["exported_files"], 1)

        fgt = self._run_kf("forget", "--entity", "jl", "--predicate", "coffee", "--reason", "Switched to tea")
        self.assertEqual(fgt["data"]["status"], "retracted")

        lint = self._run_kf("lint", "--strict")
        self.assertTrue(lint["ok"])

    def test_stdio_mcp_server_initialize_list_and_call_tools(self) -> None:
        # Prepare a personal vault first
        subprocess.run(
            [sys.executable, str(KF_PY), "init", str(self.vault), "--profile", "personal"],
            env=self.env,
            check=True,
            capture_output=True,
        )

        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "kf_remember",
                    "arguments": {"entity": "jl", "predicate": "timezone", "value": "Europe/Madrid", "pinned": True},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "kf_search",
                    "arguments": {"query": "madrid timezone", "hybrid": True},
                },
            },
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}},
            {"jsonrpc": "2.0", "id": 6, "method": "resources/read", "params": {"uri": "kf://dashboard"}},
        ]
        stdin_payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, str(KF_MCP), "--vault", str(self.vault)],
            input=stdin_payload,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, f"kf_mcp.py failed:\nSTDERR: {proc.stderr}\nSTDOUT: {proc.stdout}")
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        by_id = {r["id"]: r for r in responses if "id" in r}

        self.assertIn("serverInfo", by_id[1]["result"])
        tool_names = {t["name"] for t in by_id[2]["result"]["tools"]}
        self.assertTrue({"kf_bootstrap", "kf_search", "kf_remember", "kf_forget", "kf_query_graph", "kf_sleep_pack"} <= tool_names)

        rem_payload = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertEqual(rem_payload["action"], "created")

        srch_payload = json.loads(by_id[4]["result"]["content"][0]["text"])
        self.assertTrue(srch_payload["results"])

        res_uris = {r["uri"] for r in by_id[5]["result"]["resources"]}
        self.assertIn("kf://dashboard", res_uris)
        self.assertIn("Personal Memory Dashboard", by_id[6]["result"]["contents"][0]["text"])


if __name__ == "__main__":
    unittest.main()
