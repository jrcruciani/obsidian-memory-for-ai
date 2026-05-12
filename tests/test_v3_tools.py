from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/v3-minimal-vault"


class V3ToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault"
        ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
        shutil.copytree(EXAMPLE, self.vault, ignore=ignore)
        self.env = os.environ.copy()
        self.env["MEMORY_TODAY"] = "2026-05-11"
        self.env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{self.env.get('PATH', '')}"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_tool(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=self.vault,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=check,
        )

    def lint(self) -> subprocess.CompletedProcess[str]:
        return self.run_tool(sys.executable, "tools/lint.py")

    def assert_lint_error(self, expected: str) -> None:
        result = self.lint()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stdout)

    def file_hash(self, path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def test_clean_reference_vault_lints(self) -> None:
        result = self.lint()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_missing_schema_version_fails(self) -> None:
        (self.vault / "memory/schema/version.yaml").unlink()
        self.assert_lint_error("missing v3 schema version marker")

    def test_unknown_entity_fails(self) -> None:
        path = self.vault / "memory/facts/elena-voss/base.md"
        path.write_text(path.read_text(encoding="utf-8").replace("entity: elena-voss", "entity: ghost"), encoding="utf-8")
        self.assert_lint_error("unknown entity 'ghost'")

    def test_unknown_predicate_fails(self) -> None:
        path = self.vault / "memory/facts/elena-voss/base.md"
        path.write_text(path.read_text(encoding="utf-8").replace("predicate: base", "predicate: favorite-color"), encoding="utf-8")
        self.assert_lint_error("unknown predicate 'favorite-color'")

    def test_duplicate_stable_id_fails(self) -> None:
        path = self.vault / "memory/facts/elena-voss/role.md"
        path.write_text(path.read_text(encoding="utf-8").replace("id: fact-elena-voss-role", "id: fact-elena-voss-base"), encoding="utf-8")
        self.assert_lint_error("duplicate id 'fact-elena-voss-base'")

    def test_unresolved_wikilink_fails(self) -> None:
        path = self.vault / "memory/people/elena-voss.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n[[missing-target]]\n", encoding="utf-8")
        self.assert_lint_error("unresolved wikilink: missing-target")

    def test_ambiguous_wikilink_fails(self) -> None:
        first = self.vault / "memory/context/duplicate.md"
        second = self.vault / "memory/projects/duplicate.md"
        first.write_text("---\ntype: context\ntitle: One\n---\n", encoding="utf-8")
        second.write_text("---\ntype: project\nid: duplicate\ntitle: Two\nstatus: active\n---\n", encoding="utf-8")
        target = self.vault / "memory/people/elena-voss.md"
        target.write_text(target.read_text(encoding="utf-8") + "\n[[duplicate]]\n", encoding="utf-8")
        self.assert_lint_error("ambiguous wikilink: duplicate")

    def test_temporal_contradiction_fails(self) -> None:
        source = self.vault / "memory/facts/elena-voss/base.md"
        conflict = self.vault / "memory/facts/elena-voss/base--conflict.md"
        conflict.write_text(source.read_text(encoding="utf-8").replace('value: "Berlin, Germany"', 'value: "Paris, France"'), encoding="utf-8")
        self.assert_lint_error("contradicts overlapping fact")

    def test_deterministic_view_rebuild(self) -> None:
        self.run_tool(sys.executable, "tools/rebuild_views.py", check=True)
        first = {path.relative_to(self.vault).as_posix(): path.read_text(encoding="utf-8") for path in sorted((self.vault / "memory/_views").rglob("*.md"))}
        shutil.rmtree(self.vault / "memory/_views")
        self.run_tool(sys.executable, "tools/rebuild_views.py", check=True)
        second = {path.relative_to(self.vault).as_posix(): path.read_text(encoding="utf-8") for path in sorted((self.vault / "memory/_views").rglob("*.md"))}
        self.assertEqual(first, second)

    def test_query_facts_and_events(self) -> None:
        facts = self.run_tool("tools/query.sh", "facts", "--entity", "elena-voss", "--predicate", "role", check=True)
        self.assertIn("role = Art conservator and pigment researcher", facts.stdout)
        by_predicate = self.run_tool("tools/query.sh", "facts", "--predicate", "role", check=True)
        self.assertIn("memory/facts/elena-voss/role.md", by_predicate.stdout)
        by_id = self.run_tool("tools/query.sh", "id", "fact-elena-voss-role", check=True)
        self.assertIn("memory/facts/elena-voss/role.md: fact", by_id.stdout)
        events = self.run_tool("tools/query.sh", "events", "--since", "2026-03-01", check=True)
        self.assertIn("reviewed concordance progress", events.stdout.lower())

    def test_operation_create_fact_applies(self) -> None:
        create = self.run_tool(
            sys.executable,
            "tools/ops.py",
            "create-fact",
            "--agent",
            "agent-test-1234abcd",
            "--entity",
            "elena-voss",
            "--predicate",
            "language",
            "--value",
            "Spanish",
            "--confidence",
            "high",
            "--source",
            "sources/README.md",
            "--reason",
            "Capture preferred language.",
            check=True,
        )
        self.assertIn("memory/_inbox/agent-test-1234abcd/ops/", create.stdout)
        compact = self.run_tool(sys.executable, "tools/compact.py", "--yes", check=True)
        self.assertIn("Applied operations: 1", compact.stdout)
        self.assertTrue((self.vault / "memory/facts/elena-voss/language.md").exists())
        receipts = list((self.vault / "memory/_ops/applied").glob("op-*.md"))
        self.assertEqual(len(receipts), 1)
        facts = self.run_tool("tools/query.sh", "facts", "--entity", "elena-voss", "--predicate", "language", check=True)
        self.assertIn("language = Spanish", facts.stdout)

    def test_active_claim_marks_operation_conflict(self) -> None:
        self.run_tool(
            sys.executable,
            "tools/ops.py",
            "create-fact",
            "--agent",
            "agent-test-1234abcd",
            "--entity",
            "elena-voss",
            "--predicate",
            "language",
            "--value",
            "Spanish",
            "--source",
            "sources/README.md",
            "--reason",
            "Capture preferred language.",
            check=True,
        )
        claim = self.vault / "memory/_claims/fact-elena-voss-language.yaml"
        claim.write_text(
            "\n".join(
                [
                    "type: claim",
                    "target_id: fact-elena-voss-language",
                    "operation_id: op-other-12345678",
                    "agent_id: agent-other-12345678",
                    "created_at: 2026-05-11T00:00:00Z",
                    "expires_at: 2099-01-01T00:00:00Z",
                    "heartbeat_at: 2026-05-11T00:00:00Z",
                    "status: active",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        compact = self.run_tool(sys.executable, "tools/compact.py", "--yes", check=True)
        self.assertIn("Operation conflicts: 1", compact.stdout)
        self.assertFalse((self.vault / "memory/facts/elena-voss/language.md").exists())
        conflict_query = self.run_tool("tools/query.sh", "operations", "--status", "conflict", check=True)
        self.assertIn("create_fact", conflict_query.stdout)

    def test_operation_update_fact_applies_with_precondition(self) -> None:
        target = self.vault / "memory/facts/elena-voss/role.md"
        op = self.vault / "memory/_inbox/agent-test-1234abcd/ops/op-update-role-1234abcd.md"
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(
            f"""---
type: operation
operation_id: op-update-role-1234abcd
op: update_fact
agent_id: agent-test-1234abcd
created_at: 2026-05-11T00:00:00Z
target_id: fact-elena-voss-role
target_path: memory/facts/elena-voss/role.md
precondition_hash: {self.file_hash(target)}
status: proposed
reason: "Refine role wording."
sources: ["sources/README.md"]
payload:
  type: fact
  id: fact-elena-voss-role
  entity: elena-voss
  predicate: role
  value: "Senior art conservator and pigment researcher"
  valid_from: null
  valid_to: null
  recorded_at: 2026-03-15T10:00:00Z
  confidence: high
  sources: ["sources/README.md"]
  last_reviewed: 2026-05-11
  tags: [profile]
  body: "# Role note\\n\\nUpdated by operation."
---

# Update role
""",
            encoding="utf-8",
        )
        compact = self.run_tool(sys.executable, "tools/compact.py", "--yes", check=True)
        self.assertIn("Applied operations: 1", compact.stdout)
        facts = self.run_tool("tools/query.sh", "facts", "--entity", "elena-voss", "--predicate", "role", check=True)
        self.assertIn("Senior art conservator and pigment researcher", facts.stdout)
        receipt = self.vault / "memory/_ops/applied/op-update-role-1234abcd.md"
        self.assertTrue(receipt.exists())
        self.assertIn("body:", receipt.read_text(encoding="utf-8"))
        self.assertIn("Updated by operation", target.read_text(encoding="utf-8"))

    def test_operation_update_fact_hash_mismatch_conflicts(self) -> None:
        op = self.vault / "memory/_inbox/agent-test-1234abcd/ops/op-update-role-badhash.md"
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(
            """---
type: operation
operation_id: op-update-role-badhash
op: update_fact
agent_id: agent-test-1234abcd
created_at: 2026-05-11T00:00:00Z
target_id: fact-elena-voss-role
target_path: memory/facts/elena-voss/role.md
precondition_hash: sha256:0000000000000000000000000000000000000000000000000000000000000000
status: proposed
reason: "Try stale update."
sources: ["sources/README.md"]
payload:
  type: fact
  id: fact-elena-voss-role
  entity: elena-voss
  predicate: role
  value: "Stale role"
  valid_from: null
  valid_to: null
  recorded_at: 2026-03-15T10:00:00Z
  confidence: high
  sources: ["sources/README.md"]
  last_reviewed: 2026-05-11
---

# Stale update
""",
            encoding="utf-8",
        )
        compact = self.run_tool(sys.executable, "tools/compact.py", "--yes", check=True)
        self.assertIn("Operation conflicts: 1", compact.stdout)
        facts = self.run_tool("tools/query.sh", "facts", "--entity", "elena-voss", "--predicate", "role", check=True)
        self.assertNotIn("Stale role", facts.stdout)
        self.assertIn("precondition hash mismatch", op.read_text(encoding="utf-8"))

    def test_compact_archives_expired_fact(self) -> None:
        path = self.vault / "memory/facts/elena-voss/base.md"
        text = path.read_text(encoding="utf-8").replace("valid_to: null", "valid_to: 2026-01-01")
        path.write_text(text, encoding="utf-8")
        result = self.run_tool(sys.executable, "tools/compact.py", "--yes")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(path.exists())
        self.assertTrue((self.vault / "memory/_archive/2026/facts/elena-voss/base.md").exists())


if __name__ == "__main__":
    unittest.main()
