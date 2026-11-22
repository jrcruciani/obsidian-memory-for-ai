from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
KF_CLI = REPO_ROOT / "tools" / "kf.py"


class V5ConsumeAndViewsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        self.run_kf("init", str(self.vault), cwd=REPO_ROOT, check=True)
        self._seed_vault()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_kf(self, *args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, KF_TODAY="2026-10-15", KF_NOW="2026-10-15T15:00:00Z")
        return subprocess.run(
            [sys.executable, str(KF_CLI), *args],
            cwd=cwd or self.vault,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    def _seed_vault(self) -> None:
        ops = [
            {"op": "upsert_entity", "entity_id": "elena-voss", "kind": "person", "display": "Elena Voss", "aliases": ["Voss", "Éléna Voss"]},
            {"op": "upsert_entity", "entity_id": "marta-delvaux", "kind": "person", "display": "Marta Delvaux", "aliases": ["Delvaux"]},
            {"op": "upsert_entity", "entity_id": "concordance", "kind": "project", "display": "Concordance", "aliases": []},
            {
                "op": "create_event",
                "event_id": "evt-role-confirm",
                "occurred_at": "2026-07-15T10:00:00Z",
                "summary": "Elena confirmed promotion to Lead Conservator.",
                "entities": ["elena-voss", "concordance"],
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "role",
                "value": "Art conservator",
                "valid_from": "2026-03-15",
                "observed_at": "2026-03-15T09:00:00Z",
                "last_confirmed": "2026-03-15",
                "confidence": 0.85,
                "assertion": "stated",
                "trust": "owner",
                "pinned": True,
            },
            {
                "op": "create_fact",
                "entity": "concordance",
                "predicate": "collaborator",
                "value": "Marta Delvaux",
                "valid_from": "2026-04-01",
                "observed_at": "2026-04-01T09:00:00Z",
                "last_confirmed": "2026-09-01",
                "confidence": 0.95,
                "assertion": "stated",
                "trust": "owner",
                "pinned": True,
            },
            {
                "op": "create_guidance",
                "slug": "executor-no-guessing",
                "title": "Do Not Guess Missing Procedures",
                "domain": "global",
                "scope": "executor",
                "priority": "critical",
                "policy_rule": "Emit a gap signal instead of improvising conservation parameters.",
                "anti_patterns": ["Inventing XRF tube voltages"],
                "trust": "owner",
                "pinned": True,
            },
            {
                "op": "create_guidance",
                "slug": "curator-cite-evidence",
                "title": "Curator Proposals Must Cite Evidence",
                "domain": "governance",
                "scope": "curator",
                "priority": "high",
                "policy_rule": "Every curated fact or skill proposal must cite events, signals, or sources.",
                "anti_patterns": ["Proposing sourceless inferences"],
                "trust": "owner",
                "pinned": True,
            },
            {
                "op": "create_decision",
                "decision_id": "DEC-001-factory-roles",
                "title": "Separate Executor Capture From Curator Synthesis",
                "decided_at": "2026-05-11",
                "domain": "governance",
                "summary": "Executors emit signals; Curators author proposals; Reviewers publish.",
                "entities": ["concordance"],
                "pinned": True,
            },
        ]
        f1 = Path(self._tmp.name) / "ops1.json"
        f1.write_text(json.dumps(ops), encoding="utf-8")
        b1 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-1", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b1["transaction_id"], "--ops-file", str(f1), check=True)
        self.run_kf("transact", "commit", "--txn-id", b1["transaction_id"], "--yes", check=True)

        # Supersede Elena's role on 2026-07-15
        b2 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-2", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf(
            "transact", "add", "--txn-id", b2["transaction_id"],
            "--op", "supersede_fact",
            "--entity", "elena-voss",
            "--predicate", "role",
            "--value", "Lead conservator and pigment researcher",
            "--valid-from", "2026-07-15",
            "--confidence", "0.95",
            "--assertion", "stated",
            "--trust", "owner",
            "--derived-from", "knowledge/events/2026-07-15/evt-role-confirm.md",
            "--pinned",
            check=True,
        )
        self.run_kf("transact", "commit", "--txn-id", b2["transaction_id"], "--yes", check=True)

        # Capture a gap signal -> curate skill proposal -> review -> publish (plus leave one open signal for curator profile)
        sig1 = json.loads(
            self.run_kf(
                "capture", "signal",
                "--emitted-by", "agent-executor-00000004",
                "--kind", "gap",
                "--severity", "high",
                "--target-namespace", "skills",
                "--summary", "Missing XRF pigment scan workflow",
                "--entities", "concordance",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.sig1_id = sig1["id"]

        self.open_sig = json.loads(
            self.run_kf(
                "capture", "signal",
                "--emitted-by", "agent-executor-00000004",
                "--kind", "observation",
                "--severity", "medium",
                "--target-namespace", "guidance",
                "--summary", "Check UV lamp warm-up duration in cold rooms",
                "--entities", "concordance",
                "--json",
                check=True,
            ).stdout
        )["data"]

        skill_ops = [{
            "op": "create_skill",
            "slug": "xrf-pigment-scan",
            "title": "Non-Destructive XRF Pigment Scan",
            "domain": "conservation",
            "triggers": ["xrf scan", "pigment analysis"],
            "verification": ["Confirm Cu K-alpha calibration", "Verify zero surface contact"],
            "entities": ["concordance", "elena-voss"],
            "derived_from": ["knowledge/events/2026-07-15/evt-role-confirm.md", sig1["path"]],
            "trust": "agent",
            "confidence": 0.92,
            "pinned": True,
        }]
        f_sk = Path(self._tmp.name) / "skill.json"
        f_sk.write_text(json.dumps(skill_ops), encoding="utf-8")
        prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Publish XRF pigment scan skill",
                "--namespace", "skills",
                "--proposer", "agent-curator-00000003",
                "--resolves-signals", sig1["id"],
                "--ops-file", str(f_sk),
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.prop_id = prop["id"]
        rev = json.loads(
            self.run_kf("review", "approve", "--proposal-id", self.prop_id, "--reviewer", "agent-reviewer-00000002", "--comment", "Approved.", "--json", check=True).stdout
        )["data"]
        self.rev_id = rev["id"]
        pub = json.loads(
            self.run_kf("publish", "--proposal-id", self.prop_id, "--publisher", "agent-reviewer-00000002", "--yes", "--rebuild", "--json", check=True).stdout
        )["data"]
        self.rcpt_id = pub["receipt_id"]

    def test_role_aware_budgeted_bootstrap_profiles_and_strict_ceiling(self) -> None:
        exec_boot = self.run_kf("bootstrap", "--profile", "executor", check=True).stdout
        self.assertIn("Do Not Guess Missing Procedures", exec_boot)
        self.assertNotIn("Curator Proposals Must Cite Evidence", exec_boot)
        self.assertIn("Non-Destructive XRF Pigment Scan", exec_boot)
        self.assertNotIn("Check UV lamp warm-up duration", exec_boot)

        cur_boot = self.run_kf("bootstrap", "--profile", "curator", check=True).stdout
        self.assertIn("Check UV lamp warm-up duration", cur_boot)
        self.assertIn("Curator Proposals Must Cite Evidence", cur_boot)
        self.assertNotIn("Do Not Guess Missing Procedures", cur_boot)

        tight = self.run_kf("bootstrap", "--profile", "executor", "--budget", "650", check=True).stdout
        self.assertLessEqual(len(tight), 650)
        self.assertIn("/650 chars", tight)

        impossible = self.run_kf("bootstrap", "--budget", "30")
        self.assertNotEqual(impossible.returncode, 0)

    def test_queries_temporal_facts_skills_guidance_resolve_and_full_why_lineage(self) -> None:
        # Current vs historical fact
        cur = self.run_kf("query", "facts", "--entity", "elena-voss", "--predicate", "role", check=True).stdout
        self.assertIn("Lead conservator and pigment researcher", cur)
        self.assertNotIn("Art conservator\n", cur)

        past = self.run_kf("query", "facts", "--entity", "elena-voss", "--predicate", "role", "--as-of", "2026-05-01", check=True).stdout
        self.assertIn("Art conservator", past)
        self.assertNotIn("Lead conservator", past)

        hist = self.run_kf("query", "facts", "--entity", "elena-voss", "--predicate", "role", "--history", check=True).stdout
        self.assertIn("Art conservator", hist)
        self.assertIn("Lead conservator", hist)

        # Skills & Guidance queries
        sk = self.run_kf("query", "skills", "--domain", "conservation", "--trigger", "xrf", check=True).stdout
        self.assertIn("xrf-pigment-scan", sk)

        gd = self.run_kf("query", "guidance", "--scope", "executor", "--priority", "critical", check=True).stdout
        self.assertIn("executor-no-guessing", gd)
        self.assertNotIn("curator-cite-evidence", gd)

        # Entity alias resolution (case + accent insensitive)
        resolved = self.run_kf("query", "resolve", "ÉLÉNA VOSS", check=True)
        self.assertEqual(resolved.stdout.strip(), "elena-voss")

        missing = self.run_kf("query", "resolve", "nobody-known")
        self.assertEqual(missing.returncode, 2)

        # Full end-to-end Factory `why` lineage on the published skill!
        why = json.loads(self.run_kf("query", "why", "skill", "xrf-pigment-scan", "--json", check=True).stdout)["data"]
        self.assertEqual(why["record"]["slug"], "xrf-pigment-scan")
        self.assertEqual(why["receipt"]["id"], self.rcpt_id)
        self.assertEqual(why["proposal"]["id"], self.prop_id)
        self.assertIn(self.rev_id, [r["id"] for r in why["reviews"]])
        self.assertIn(self.sig1_id, [s["id"] for s in why["resolved_signals"]])

    def test_search_and_graph_parity_and_non_editable_generated_guard(self) -> None:
        search_with_idx = self.run_kf("query", "search", "Voss", check=True).stdout
        graph_with_idx = self.run_kf("query", "graph", "concordance", check=True).stdout
        self.assertIn("Lead conservator", search_with_idx)
        self.assertIn("marta-delvaux", graph_with_idx)

        # Delete _generated/indexes completely: stdout must remain byte-identical!
        shutil.rmtree(self.vault / "_generated/indexes")
        search_no_idx = self.run_kf("query", "search", "Voss", check=True).stdout
        graph_no_idx = self.run_kf("query", "graph", "concordance", check=True).stdout
        self.assertEqual(search_with_idx, search_no_idx)
        self.assertEqual(graph_with_idx, graph_no_idx)

        # Rebuild twice -> byte-identical
        self.run_kf("rebuild", check=True)
        snap1 = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in sorted((self.vault / "_generated").rglob("*.md"))}
        self.run_kf("rebuild", check=True)
        snap2 = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in sorted((self.vault / "_generated").rglob("*.md"))}
        self.assertEqual(snap1, snap2)

        # Hand-edit a generated view/index -> query warns on stderr without changing stdout, AND strict lint fails!
        lex_path = self.vault / "_generated/indexes/lexical.md"
        lex_path.write_text(lex_path.read_text(encoding="utf-8") + "\n<!-- manual edit -->\n", encoding="utf-8")

        tampered_search = self.run_kf("query", "search", "Voss", check=True)
        self.assertEqual(tampered_search.stdout, search_with_idx)
        self.assertIn("WARN", tampered_search.stderr)

        strict_lint = self.run_kf("lint", "--strict")
        self.assertNotEqual(strict_lint.returncode, 0)
        self.assertIn("hand-edited", strict_lint.stdout + strict_lint.stderr)


if __name__ == "__main__":
    unittest.main()
