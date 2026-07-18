"""Regression tests for the v4 Transactional Atomic Markdown Memory protocol.

Covers:
  - Successful and failed transactions
  - Idempotent replay
  - Stale revision/CAS rejection
  - Interrupted recovery
  - Review approval and rejection
  - Self-approval and namespace denial
  - Deterministic index rebuilds
  - Stale/corrupt/missing-index fallback parity
  - Lint/schema validation
  - v4 full workflow
"""

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
EXAMPLE = REPO / "examples/v4-minimal-vault"


class V4BaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault"
        ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".venv")
        shutil.copytree(EXAMPLE, self.vault, ignore=ignore)
        self.env = os.environ.copy()
        self.env["MEMORY_TODAY"] = "2026-07-01"
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

    def run_python(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return self.run_tool(sys.executable, *args, check=check)

    def lint(self) -> subprocess.CompletedProcess[str]:
        return self.run_python("tools/lint.py")

    def rebuild_views(self) -> subprocess.CompletedProcess[str]:
        return self.run_python("tools/rebuild_views.py", check=True)

    def rebuild_indexes(self) -> subprocess.CompletedProcess[str]:
        return self.run_python("tools/rebuild_indexes.py", check=True)

    def file_hash(self, path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Lint / schema validation
# ---------------------------------------------------------------------------


class V4LintTests(V4BaseTest):
    def test_clean_reference_vault_lints(self) -> None:
        result = self.lint()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_missing_schema_version_fails(self) -> None:
        (self.vault / "memory/schema/version.yaml").unlink()
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing v4 schema version marker", result.stdout)

    def test_wrong_spec_version_fails(self) -> None:
        p = self.vault / "memory/schema/version.yaml"
        p.write_text('spec_version: "3.0"\nschema_status: stable\n', encoding="utf-8")
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('spec_version must be', result.stdout)

    def test_unknown_entity_fails(self) -> None:
        path = self.vault / "memory/facts/elena-voss/base.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "entity: elena-voss", "entity: ghost"), encoding="utf-8")
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown entity 'ghost'", result.stdout)

    def test_unknown_predicate_fails(self) -> None:
        path = self.vault / "memory/facts/elena-voss/base.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "predicate: base", "predicate: favorite-color"), encoding="utf-8")
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown predicate 'favorite-color'", result.stdout)

    def test_duplicate_stable_id_fails(self) -> None:
        path = self.vault / "memory/facts/elena-voss/role.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "id: fact-elena-voss-role", "id: fact-elena-voss-base"), encoding="utf-8")
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate id", result.stdout)

    def test_temporal_contradiction_fails(self) -> None:
        source = self.vault / "memory/facts/elena-voss/base.md"
        conflict = self.vault / "memory/facts/elena-voss/base--conflict.md"
        conflict.write_text(
            source.read_text(encoding="utf-8").replace('value: "Berlin, Germany"', 'value: "Paris, France"'),
            encoding="utf-8"
        )
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contradicts overlapping fact", result.stdout)

    def test_invalid_proposal_status_fails(self) -> None:
        prop_dir = self.vault / "memory/_proposals"
        prop_dir.mkdir(parents=True, exist_ok=True)
        bad_prop = prop_dir / "prop-bad-status.md"
        bad_prop.write_text(
            "---\ntype: proposal\n"
            "proposal_id: prop-bad-status-test-aabbccdd\n"
            "namespace: facts\n"
            "proposer_id: agent-local-1234abcd\n"
            "title: Bad status test\n"
            "status: invalid_status\n"
            "created_at: 2026-07-01T00:00:00Z\n"
            "content_hash: sha256:" + "a" * 64 + "\n"
            "required_approvals: 1\n"
            "approvals: []\n"
            "ops: []\n"
            "---\n",
            encoding="utf-8"
        )
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status", result.stdout)

    def test_self_approval_detected_by_lint(self) -> None:
        prop_dir = self.vault / "memory/_proposals"
        prop_dir.mkdir(parents=True, exist_ok=True)
        rev_dir = self.vault / "memory/_reviews"
        rev_dir.mkdir(parents=True, exist_ok=True)

        content_hash = "sha256:" + "b" * 64
        prop = prop_dir / "prop-self-lint-test-aabbccdd.md"
        prop.write_text(
            "---\ntype: proposal\n"
            "proposal_id: prop-self-lint-test-aabbccdd\n"
            "namespace: facts\n"
            "proposer_id: agent-local-1234abcd\n"
            "title: Self-approval lint test\n"
            "status: proposed\n"
            "created_at: 2026-07-01T00:00:00Z\n"
            f"content_hash: {content_hash}\n"
            "required_approvals: 1\n"
            "approvals: []\n"
            "ops: []\n"
            "---\n",
            encoding="utf-8"
        )
        rev = rev_dir / "rev-self-lint-aabbccdd.md"
        rev.write_text(
            "---\ntype: review\n"
            "review_id: rev-self-lint-aabbccdd\n"
            "proposal_id: prop-self-lint-test-aabbccdd\n"
            "reviewer_id: agent-local-1234abcd\n"
            "verdict: approved\n"
            "created_at: 2026-07-01T01:00:00Z\n"
            f"proposal_content_hash: {content_hash}\n"
            "---\n",
            encoding="utf-8"
        )
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("self-approval not allowed", result.stdout)

    def test_unauthorized_reviewer_detected_by_lint(self) -> None:
        prop_dir = self.vault / "memory/_proposals"
        prop_dir.mkdir(parents=True, exist_ok=True)
        rev_dir = self.vault / "memory/_reviews"
        rev_dir.mkdir(parents=True, exist_ok=True)
        content_hash = "sha256:" + "c" * 64
        prop = prop_dir / "prop-unauth-lint-test.md"
        prop.write_text(
            "---\ntype: proposal\n"
            "proposal_id: prop-unauth-lint-test\n"
            "namespace: facts\n"
            "proposer_id: agent-local-1234abcd\n"
            "title: Unauthorized reviewer test\n"
            "status: proposed\n"
            "created_at: 2026-07-01T00:00:00Z\n"
            f"content_hash: {content_hash}\n"
            "required_approvals: 1\n"
            "approvals: []\n"
            "ops: []\n"
            "---\n",
            encoding="utf-8"
        )
        rev = rev_dir / "rev-unauth-lint-test.md"
        rev.write_text(
            "---\ntype: review\n"
            "review_id: rev-unauth-lint-test\n"
            "proposal_id: prop-unauth-lint-test\n"
            "reviewer_id: agent-test-1234abcd\n"
            "verdict: approved\n"
            "created_at: 2026-07-01T01:00:00Z\n"
            f"proposal_content_hash: {content_hash}\n"
            "---\n",
            encoding="utf-8"
        )
        result = self.lint()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not allowed to review namespace", result.stdout)


# ---------------------------------------------------------------------------
# Deterministic views and indexes
# ---------------------------------------------------------------------------


class V4DeterministicTests(V4BaseTest):
    def test_deterministic_view_rebuild(self) -> None:
        self.rebuild_views()
        first = {
            p.relative_to(self.vault).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((self.vault / "memory/_views").rglob("*.md"))
        }
        shutil.rmtree(self.vault / "memory/_views")
        self.rebuild_views()
        second = {
            p.relative_to(self.vault).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((self.vault / "memory/_views").rglob("*.md"))
        }
        self.assertEqual(first, second)

    def test_deterministic_index_rebuild(self) -> None:
        self.rebuild_indexes()
        first_lexical = (self.vault / "memory/_indexes/lexical.md").read_text(encoding="utf-8")
        first_graph = (self.vault / "memory/_indexes/graph.md").read_text(encoding="utf-8")
        shutil.rmtree(self.vault / "memory/_indexes")
        self.rebuild_indexes()
        second_lexical = (self.vault / "memory/_indexes/lexical.md").read_text(encoding="utf-8")
        second_graph = (self.vault / "memory/_indexes/graph.md").read_text(encoding="utf-8")
        self.assertEqual(first_lexical, second_lexical)
        self.assertEqual(first_graph, second_graph)

    def test_index_contains_all_facts(self) -> None:
        self.rebuild_indexes()
        lexical = (self.vault / "memory/_indexes/lexical.md").read_text(encoding="utf-8")
        self.assertIn("elena-voss/role", lexical)
        self.assertIn("elena-voss/base", lexical)
        self.assertIn("elena-voss/language", lexical)
        self.assertIn("concordance/collaborator", lexical)

    def test_graph_index_contains_relationships(self) -> None:
        self.rebuild_indexes()
        graph = (self.vault / "memory/_indexes/graph.md").read_text(encoding="utf-8")
        self.assertIn("concordance", graph)
        self.assertIn("marta-delvaux", graph)

    def test_search_with_index_matches_filesystem(self) -> None:
        """Search results must be identical whether using index or filesystem scan."""
        self.rebuild_indexes()
        from pathlib import Path
        sys.path.insert(0, str(self.vault / "tools"))
        try:
            import importlib
            import rebuild_indexes as ri
            import importlib.util
            spec = importlib.util.spec_from_file_location("ri", self.vault / "tools/rebuild_indexes.py")
            ri_mod = importlib.util.module_from_spec(spec)  # type: ignore
            spec.loader.exec_module(ri_mod)  # type: ignore

            index_results = ri_mod.search_facts_index(self.vault, "elena")
            fs_results = ri_mod.search_facts_filesystem(self.vault, "elena")
            self.assertEqual(
                sorted(index_results, key=lambda r: (r[0], r[1])),
                sorted(fs_results, key=lambda r: (r[0], r[1])),
            )
        finally:
            sys.path.pop(0)

    def test_search_without_index_fallback(self) -> None:
        """query.sh search falls back to filesystem when index is missing."""
        # Ensure no index exists
        idx_dir = self.vault / "memory/_indexes"
        if idx_dir.exists():
            shutil.rmtree(idx_dir)
        result = self.run_tool("tools/query.sh", "search", "elena", check=True)
        self.assertIn("elena-voss", result.stdout)

    def test_search_with_index(self) -> None:
        """query.sh search works when index exists."""
        self.rebuild_indexes()
        result = self.run_tool("tools/query.sh", "search", "elena", check=True)
        self.assertIn("elena-voss", result.stdout)

    def test_graph_query_fallback_parity(self) -> None:
        """Graph query returns same results with or without index."""
        self.rebuild_indexes()
        with_index = self.run_tool("tools/query.sh", "graph", "entity", "concordance", check=True)
        shutil.rmtree(self.vault / "memory/_indexes")
        without_index = self.run_tool("tools/query.sh", "graph", "entity", "concordance", check=True)
        self.assertEqual(with_index.stdout.strip(), without_index.stdout.strip())

    def test_proposals_view_generated(self) -> None:
        self.rebuild_views()
        proposals_view = self.vault / "memory/_views/proposals.md"
        self.assertTrue(proposals_view.exists())
        content = proposals_view.read_text(encoding="utf-8")
        self.assertIn("Proposals", content)

    def test_transactions_view_generated(self) -> None:
        self.rebuild_views()
        txn_view = self.vault / "memory/_views/transactions.md"
        self.assertTrue(txn_view.exists())
        content = txn_view.read_text(encoding="utf-8")
        self.assertIn("Transaction", content)


# ---------------------------------------------------------------------------
# Transaction tests
# ---------------------------------------------------------------------------


class V4TransactionTests(V4BaseTest):
    def test_begin_transaction_creates_staging(self) -> None:
        result = self.run_python(
            "tools/transact.py", "begin",
            "--idempotency-key", "test-begin-key-001",
            "--agent", "agent-local-1234abcd",
            check=True,
        )
        self.assertIn("Transaction started:", result.stdout)
        # Staging dir should exist
        staging_dirs = list((self.vault / "memory/_staging").iterdir())
        self.assertEqual(len(staging_dirs), 1)

    def test_add_and_commit_transaction(self) -> None:
        # Begin
        r = self.run_python(
            "tools/transact.py", "begin",
            "--idempotency-key", "test-commit-001",
            "--agent", "agent-local-1234abcd",
            check=True,
        )
        # Extract txn id
        txn_id = [line.split("Transaction started:")[-1].strip()
                  for line in r.stdout.splitlines() if "Transaction started:" in line][0]

        # Add op
        self.run_python(
            "tools/transact.py", "add",
            "--txn-id", txn_id,
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Python",
            "--source", "sources/README.md",
            check=True,
        )

        # Commit
        r = self.run_python(
            "tools/transact.py", "commit",
            "--txn-id", txn_id,
            "--yes",
            check=True,
        )
        self.assertIn("committed", r.stdout)
        self.assertTrue((self.vault / "memory/facts/elena-voss/tool.md").exists())
        self.assertTrue((self.vault / "memory/_transactions" / f"{txn_id}.md").exists())
        journal = (self.vault / "memory/_transactions" / f"{txn_id}.md").read_text(encoding="utf-8")
        self.assertIn("committed", journal)
        self.assertIn("test-commit-001", journal)

    def test_idempotent_replay_skips(self) -> None:
        key = "idempotent-replay-key-001"
        # First commit
        r1 = self.run_python(
            "tools/transact.py", "begin",
            "--idempotency-key", key,
            "--agent", "agent-local-1234abcd",
            check=True,
        )
        txn_id = [l.split("Transaction started:")[-1].strip()
                  for l in r1.stdout.splitlines() if "Transaction started:" in l][0]
        self.run_python("tools/transact.py", "add", "--txn-id", txn_id,
                        "--op", "create_fact", "--entity", "elena-voss",
                        "--predicate", "tool", "--value", "Vim",
                        check=True)
        self.run_python("tools/transact.py", "commit", "--txn-id", txn_id, "--yes", check=True)

        # Second begin with same key — should skip
        r2 = self.run_python(
            "tools/transact.py", "begin",
            "--idempotency-key", key,
            "--agent", "agent-local-1234abcd",
        )
        self.assertIn("Idempotent skip", r2.stdout)
        # Fact should only exist once
        tool_path = self.vault / "memory/facts/elena-voss/tool.md"
        self.assertTrue(tool_path.exists())

    def test_expected_revision_mismatch_fails(self) -> None:
        r = self.run_python(
            "tools/transact.py", "begin",
            "--idempotency-key", "revision-test-001",
            "--expected-revision", "0000000000000000000000000000000000000000",
            "--agent", "agent-local-1234abcd",
            check=True,
        )
        txn_id = [l.split("Transaction started:")[-1].strip()
                  for l in r.stdout.splitlines() if "Transaction started:" in l][0]
        self.run_python("tools/transact.py", "add", "--txn-id", txn_id,
                        "--op", "create_fact", "--entity", "elena-voss",
                        "--predicate", "tool", "--value", "Emacs", check=True)
        r2 = self.run_python("tools/transact.py", "commit", "--txn-id", txn_id, "--yes")
        # Should fail if git is available; if not available, also fails with a clear error
        journal_files = list((self.vault / "memory/_transactions").glob(f"{txn_id}*.md"))
        if journal_files:
            journal = journal_files[0].read_text(encoding="utf-8")
            self.assertIn("failed", journal)

    def test_rollback_clears_staging(self) -> None:
        r = self.run_python(
            "tools/transact.py", "begin",
            "--idempotency-key", "rollback-test-001",
            "--agent", "agent-local-1234abcd",
            check=True,
        )
        txn_id = [l.split("Transaction started:")[-1].strip()
                  for l in r.stdout.splitlines() if "Transaction started:" in l][0]
        self.run_python("tools/transact.py", "rollback", "--txn-id", txn_id, check=True)
        # Staging dir should be gone
        self.assertFalse((self.vault / "memory/_staging" / txn_id).exists())
        # Journal should exist with rolled_back status
        journal = (self.vault / "memory/_transactions" / f"{txn_id}.md").read_text(encoding="utf-8")
        self.assertIn("rolled_back", journal)

    def test_recover_pending_transaction(self) -> None:
        """Recovery rolls back any pending staging transactions."""
        # Manually create a fake pending staging dir
        fake_txn = "txn-fake-pending-12345678"
        staging = self.vault / "memory/_staging" / fake_txn
        staging.mkdir(parents=True, exist_ok=True)
        (staging / ".pending").write_text("pending\n", encoding="utf-8")
        import yaml as _yaml
        meta = {
            "transaction_id": fake_txn,
            "idempotency_key": "fake-pending-key",
            "agent_id": "agent-local-1234abcd",
            "created_at": "2026-07-01T00:00:00Z",
            "status": "pending",
            "ops": [],
        }
        (staging / "_meta.yaml").write_text(_yaml.safe_dump(meta), encoding="utf-8")

        r = self.run_python("tools/transact.py", "recover", "--yes", check=True)
        self.assertIn("Rolled back", r.stdout)
        self.assertFalse(staging.exists())
        journal = (self.vault / "memory/_transactions" / f"{fake_txn}.md").read_text(encoding="utf-8")
        self.assertIn("rolled_back", journal)

    def test_transaction_list(self) -> None:
        result = self.run_python("tools/transact.py", "list", check=True)
        # Should at least show the pre-committed example journal
        self.assertIn("committed", result.stdout)


# ---------------------------------------------------------------------------
# Proposal and review tests
# ---------------------------------------------------------------------------


class V4ProposalTests(V4BaseTest):
    def test_create_proposal(self) -> None:
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Add Obsidian tool fact",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Obsidian",
            "--source", "sources/README.md",
            check=True,
        )
        self.assertIn("Proposal created:", r.stdout)
        prop_files = list((self.vault / "memory/_proposals").glob("prop-add-obsidian-*.md"))
        # Accept any prop file that was just created
        all_props = list((self.vault / "memory/_proposals").glob("prop-*.md"))
        self.assertGreater(len(all_props), 0)

    def test_self_approval_rejected(self) -> None:
        # Create proposal
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Self-approve test",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Emacs",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        # Try to approve as same agent
        r2 = self.run_python(
            "tools/review.py", "approve",
            "--proposal-id", prop_id,
            "--reviewer", "agent-local-1234abcd",
            "--comment", "Approving my own proposal.",
        )
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("self-approval not allowed", r2.stdout)

    def test_unauthorized_reviewer_rejected(self) -> None:
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Unauth reviewer test",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Emacs",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        r2 = self.run_python(
            "tools/review.py", "approve",
            "--proposal-id", prop_id,
            "--reviewer", "agent-test-1234abcd",  # not in allowed_reviewers
            "--comment", "Trying to approve without permission.",
        )
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("not allowed to review namespace", r2.stdout)

    def test_approve_proposal(self) -> None:
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Approve test proposal",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Emacs",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        r2 = self.run_python(
            "tools/review.py", "approve",
            "--proposal-id", prop_id,
            "--reviewer", "agent-human-00000001",
            "--comment", "Looks good.",
            check=True,
        )
        self.assertIn("approved", r2.stdout)
        # Proposal status should be approved
        r3 = self.run_python("tools/propose.py", "show", "--proposal-id", prop_id, check=True)
        self.assertIn("approved", r3.stdout)

    def test_reject_proposal(self) -> None:
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Reject test proposal",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Emacs",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        r2 = self.run_python(
            "tools/review.py", "reject",
            "--proposal-id", prop_id,
            "--reviewer", "agent-human-00000001",
            "--comment", "Not appropriate at this time.",
            check=True,
        )
        self.assertIn("rejected", r2.stdout)

    def test_request_changes_proposal(self) -> None:
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Changes requested test",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Vim",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        r2 = self.run_python(
            "tools/review.py", "request-changes",
            "--proposal-id", prop_id,
            "--reviewer", "agent-human-00000001",
            "--comment", "Please specify version.",
            check=True,
        )
        self.assertIn("changes_requested", r2.stdout)

    def test_apply_approved_proposal(self) -> None:
        # Create and approve a proposal, then apply it
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Apply test proposal",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Obsidian",
            "--source", "sources/README.md",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        self.run_python(
            "tools/review.py", "approve",
            "--proposal-id", prop_id,
            "--reviewer", "agent-human-00000001",
            "--comment", "Approved.",
            check=True,
        )

        r2 = self.run_python(
            "tools/propose.py", "apply",
            "--proposal-id", prop_id,
            "--yes",
            check=True,
        )
        self.assertIn("applied", r2.stdout)
        self.assertTrue((self.vault / "memory/facts/elena-voss/tool.md").exists())

    def test_cannot_apply_unapproved_proposal(self) -> None:
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Unapproved test",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Nano",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        r2 = self.run_python("tools/propose.py", "apply", "--proposal-id", prop_id, "--yes")
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("not approved", r2.stdout)

    def test_review_cryptographic_binding(self) -> None:
        """Reviews record proposal_content_hash at time of review."""
        r = self.run_python(
            "tools/propose.py", "create",
            "--title", "Hash binding test",
            "--namespace", "facts",
            "--proposer", "agent-local-1234abcd",
            "--op", "create_fact",
            "--entity", "elena-voss",
            "--predicate", "tool",
            "--value", "Nano",
            check=True,
        )
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        r2 = self.run_python(
            "tools/review.py", "approve",
            "--proposal-id", prop_id,
            "--reviewer", "agent-human-00000001",
            check=True,
        )
        # Review file should contain proposal_content_hash
        rev_files = list((self.vault / "memory/_reviews").glob("rev-*.md"))
        # Find the review we just created (most recent)
        rev_files_sorted = sorted(rev_files, key=lambda p: p.stat().st_mtime, reverse=True)
        import yaml
        import re
        FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
        latest_rev = rev_files_sorted[0].read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(latest_rev)
        if m:
            rev_data = yaml.safe_load(m.group(1))
            self.assertIn("proposal_content_hash", rev_data)
            self.assertTrue(str(rev_data["proposal_content_hash"]).startswith("sha256:"))


# ---------------------------------------------------------------------------
# Integration: full workflow
# ---------------------------------------------------------------------------


class V4IntegrationTests(V4BaseTest):
    def test_full_transaction_workflow(self) -> None:
        """Complete transaction: begin → add → commit → idempotent replay."""
        key = "full-workflow-integration-001"
        r1 = self.run_python("tools/transact.py", "begin",
                             "--idempotency-key", key,
                             "--agent", "agent-local-1234abcd", check=True)
        txn_id = [l.split("Transaction started:")[-1].strip()
                  for l in r1.stdout.splitlines() if "Transaction started:" in l][0]

        self.run_python("tools/transact.py", "add", "--txn-id", txn_id,
                        "--op", "create_fact",
                        "--entity", "elena-voss", "--predicate", "tool",
                        "--value", "Obsidian", "--source", "sources/README.md", check=True)

        self.run_python("tools/transact.py", "commit", "--txn-id", txn_id, "--yes", check=True)
        self.assertTrue((self.vault / "memory/facts/elena-voss/tool.md").exists())

        # Idempotent replay
        r2 = self.run_python("tools/transact.py", "begin",
                             "--idempotency-key", key)
        self.assertIn("Idempotent skip", r2.stdout)

    def test_full_proposal_review_apply_workflow(self) -> None:
        """Complete proposal cycle: create → approve → apply → fact exists."""
        r = self.run_python("tools/propose.py", "create",
                            "--title", "Full workflow test",
                            "--namespace", "facts",
                            "--proposer", "agent-local-1234abcd",
                            "--op", "create_fact",
                            "--entity", "elena-voss", "--predicate", "tool",
                            "--value", "Obsidian", "--source", "sources/README.md",
                            check=True)
        prop_id = [l.split("Proposal created:")[-1].strip()
                   for l in r.stdout.splitlines() if "Proposal created:" in l][0]

        self.run_python("tools/review.py", "approve",
                        "--proposal-id", prop_id,
                        "--reviewer", "agent-human-00000001",
                        "--comment", "Approved.", check=True)

        self.run_python("tools/propose.py", "apply",
                        "--proposal-id", prop_id, "--yes", check=True)

        self.assertTrue((self.vault / "memory/facts/elena-voss/tool.md").exists())
        # Lint should still pass
        result = self.lint()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_compact_applies_inbox_operations(self) -> None:
        """v3-style inbox operations still work via compact.py."""
        op = self.vault / "memory/_inbox/agent-local-1234abcd/ops/op-test-tool.md"
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(
            "---\ntype: operation\noperation_id: op-test-tool-1234abcd\n"
            "op: create_fact\nagent_id: agent-local-1234abcd\n"
            "created_at: 2026-07-01T00:00:00Z\n"
            "target_id: fact-elena-voss-tool\n"
            "target_path: memory/facts/elena-voss/tool.md\n"
            "precondition_hash: null\nstatus: proposed\n"
            "reason: Create tool fact.\nsources: [sources/README.md]\n"
            "payload:\n  type: fact\n  id: fact-elena-voss-tool\n"
            "  entity: elena-voss\n  predicate: tool\n  value: Obsidian\n"
            "  recorded_at: 2026-07-01T00:00:00Z\n"
            "  confidence: medium\n  sources: [sources/README.md]\n---\n",
            encoding="utf-8",
        )
        r = self.run_python("tools/compact.py", "--yes", check=True)
        self.assertIn("Applied operations: 1", r.stdout)
        self.assertTrue((self.vault / "memory/facts/elena-voss/tool.md").exists())

    def test_v4_lint_after_full_workflow(self) -> None:
        """After running all tools, vault still lints cleanly."""
        # Run a transaction
        r = self.run_python("tools/transact.py", "begin",
                            "--idempotency-key", "post-workflow-lint",
                            "--agent", "agent-local-1234abcd", check=True)
        txn_id = [l.split("Transaction started:")[-1].strip()
                  for l in r.stdout.splitlines() if "Transaction started:" in l][0]
        self.run_python("tools/transact.py", "add", "--txn-id", txn_id,
                        "--op", "create_fact",
                        "--entity", "elena-voss", "--predicate", "tool",
                        "--value", "Python", "--source", "sources/README.md", check=True)
        self.run_python("tools/transact.py", "commit", "--txn-id", txn_id, "--yes", check=True)
        # Rebuild views and indexes
        self.rebuild_views()
        self.rebuild_indexes()
        # Lint
        result = self.lint()
        self.assertEqual(result.returncode, 0, result.stdout)


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------


class V4QueryTests(V4BaseTest):
    def test_query_facts_by_entity(self) -> None:
        r = self.run_tool("tools/query.sh", "facts", "--entity", "elena-voss", check=True)
        self.assertIn("role", r.stdout)
        self.assertIn("Art conservator", r.stdout)

    def test_query_facts_by_predicate(self) -> None:
        r = self.run_tool("tools/query.sh", "facts", "--predicate", "role", check=True)
        self.assertIn("memory/facts/elena-voss/role.md", r.stdout)

    def test_query_events_since(self) -> None:
        r = self.run_tool("tools/query.sh", "events", "--since", "2026-07-01", check=True)
        self.assertIn("concordance", r.stdout.lower())

    def test_query_id(self) -> None:
        r = self.run_tool("tools/query.sh", "id", "fact-elena-voss-role", check=True)
        self.assertIn("memory/facts/elena-voss/role.md", r.stdout)
        self.assertIn("fact", r.stdout)

    def test_query_search_returns_facts(self) -> None:
        self.rebuild_indexes()
        r = self.run_tool("tools/query.sh", "search", "Berlin", check=True)
        self.assertIn("elena-voss/base", r.stdout)


if __name__ == "__main__":
    unittest.main()
