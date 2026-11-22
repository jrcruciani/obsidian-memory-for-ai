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

    def test_bootstrap_embeds_verified_content_sha256_within_character_budget(self) -> None:
        import hashlib
        import re

        for extra_args, cap in ((["--profile", "executor", "--budget", "650"], 650), (["--profile", "default"], 6000)):
            rendered = self.run_kf("bootstrap", *extra_args, check=True).stdout
            self.assertLessEqual(len(rendered), cap)
            first_nl = rendered.index("\n")
            banner = rendered[:first_nl]
            payload = rendered[first_nl + 1:]
            m = re.search(r"content_sha256=(sha256:[0-9a-f]{64})", banner)
            assert m is not None, f"bootstrap banner missing content_sha256: {banner}"
            expected_sha = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
            self.assertEqual(m.group(1), expected_sha)
            m_footer = re.search(r", (\d+)/(\d+) chars,", rendered)
            assert m_footer is not None
            self.assertEqual(int(m_footer.group(1)), len(rendered))
            self.assertEqual(int(m_footer.group(2)), cap)

        # Hand-editing _generated/views/bootstrap.md must fail strict lint with content_sha256 mismatch!
        boot_view = self.vault / "_generated/views/bootstrap.md"
        boot_view.write_text(boot_view.read_text(encoding="utf-8") + "<!-- tampered -->\n", encoding="utf-8")
        strict = self.run_kf("lint", "--strict")
        self.assertNotEqual(strict.returncode, 0)
        self.assertIn("content_sha256 mismatch", strict.stdout + strict.stderr)

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

    def test_temporal_visibility_bounded_expired_and_future_facts_across_surfaces(self) -> None:
        ops = [
            # 1. Bounded active fact currently valid at KF_TODAY=2026-10-15: [2026-10-01, 2026-12-31)
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "employer",
                "value": "Venice Visiting Fellowship",
                "valid_from": "2026-10-01",
                "valid_until": "2026-12-31",
                "observed_at": "2026-10-01T09:00:00Z",
                "last_confirmed": "2026-10-01",
                "confidence": 0.95,
                "assertion": "stated",
                "trust": "owner",
                "pinned": True,
            },
            # 2. Future active fact starting after KF_TODAY=2026-10-15: [2026-11-01, null)
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "base",
                "value": "Florence, Italy",
                "valid_from": "2026-11-01",
                "observed_at": "2026-10-14T09:00:00Z",
                "last_confirmed": "2026-10-14",
                "confidence": 0.9,
                "assertion": "stated",
                "trust": "owner",
                "pinned": True,
            },
            # 3. Expired bounded active fact: [2026-08-01, 2026-09-15)
            {
                "op": "create_fact",
                "entity": "concordance",
                "predicate": "status-summary",
                "value": "Summer field campaign",
                "valid_from": "2026-08-01",
                "valid_until": "2026-09-15",
                "observed_at": "2026-08-01T09:00:00Z",
                "last_confirmed": "2026-08-01",
                "confidence": 0.9,
                "assertion": "stated",
                "trust": "owner",
                "pinned": True,
            },
            # 4. Bounded active fact superseding a prior fact (must pass structural head lint!)
            {
                "op": "supersede_fact",
                "entity": "concordance",
                "predicate": "collaborator",
                "value": "Elena Voss",
                "valid_from": "2026-10-01",
                "valid_until": "2026-12-01",
                "observed_at": "2026-10-01T10:00:00Z",
                "last_confirmed": "2026-10-01",
                "confidence": 0.95,
                "assertion": "stated",
                "trust": "owner",
                "pinned": True,
            },
        ]
        ops_file = Path(self._tmp.name) / "temporal_ops.json"
        ops_file.write_text(json.dumps(ops), encoding="utf-8")
        b = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "temp-vis", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b["transaction_id"], "--ops-file", str(ops_file), check=True)
        self.run_kf("transact", "commit", "--txn-id", b["transaction_id"], "--yes", "--rebuild", check=True)

        # Structural lint passes cleanly (bounded active head superseding history is valid; misplaced active bounded fact fails)
        self.assertEqual(self.run_kf("lint", "--strict").returncode, 0)

        # Query facts at KF_TODAY=2026-10-15: bounded valid fact is visible; future & expired are NOT visible
        q_facts = self.run_kf("query", "facts", check=True).stdout
        self.assertIn("Venice Visiting Fellowship", q_facts)
        self.assertIn("concordance/collaborator = Elena Voss", q_facts)
        self.assertNotIn("Florence, Italy", q_facts)
        self.assertNotIn("Summer field campaign", q_facts)

        # Query --as-of checks boundaries accurately
        q_nov = self.run_kf("query", "facts", "--as-of", "2026-11-15", check=True).stdout
        self.assertIn("Florence, Italy", q_nov)
        self.assertIn("Venice Visiting Fellowship", q_nov)

        q_jan = self.run_kf("query", "facts", "--as-of", "2026-12-31", check=True).stdout
        self.assertNotIn("Venice Visiting Fellowship", q_jan)
        self.assertIn("Florence, Italy", q_jan)

        q_aug = self.run_kf("query", "facts", "--as-of", "2026-08-15", check=True).stdout
        self.assertIn("Summer field campaign", q_aug)

        # Search, Graph, Bootstrap, and Rebuilt Views/Indexes all honor KF_TODAY visibility
        srch = self.run_kf("query", "search", "Venice", check=True).stdout
        self.assertIn("Venice Visiting Fellowship", srch)
        srch_fut = self.run_kf("query", "search", "Florence", check=True).stdout
        self.assertNotIn("Florence, Italy", srch_fut)

        gr = self.run_kf("query", "graph", "concordance", check=True).stdout
        self.assertIn("elena-voss", gr)
        self.assertNotIn("marta-delvaux", gr)

        boot = self.run_kf("bootstrap", check=True).stdout
        self.assertIn("Venice Visiting Fellowship", boot)
        self.assertNotIn("Florence, Italy", boot)
        self.assertNotIn("Summer field campaign", boot)

        catalog = (self.vault / "_generated/views/catalog.md").read_text(encoding="utf-8")
        self.assertIn("Venice Visiting Fellowship", catalog)
        self.assertNotIn("Florence, Italy", catalog)
        self.assertNotIn("Summer field campaign", catalog)

        lexical = (self.vault / "_generated/indexes/lexical.md").read_text(encoding="utf-8")
        self.assertIn("Venice Visiting Fellowship", lexical)
        self.assertNotIn("Florence, Italy", lexical)
        self.assertNotIn("Summer field campaign", lexical)

        # Misplaced bounded active fact outside head slot MUST fail schema_check
        misplaced = self.vault / "knowledge/facts/elena-voss/employer/2026-10-01.md"
        misplaced.parent.mkdir(parents=True, exist_ok=True)
        misplaced.write_text((self.vault / "knowledge/facts/elena-voss/employer.md").read_text(encoding="utf-8").replace("fact-elena-voss-employer", "fact-elena-voss-employer-dup"), encoding="utf-8")
        bad_lint = self.run_kf("lint")
        self.assertNotEqual(bad_lint.returncode, 0)
        self.assertIn("active fact must reside at knowledge/facts/elena-voss/employer.md", bad_lint.stdout + bad_lint.stderr)

    def test_empty_or_whitespace_search_query_returns_no_records(self) -> None:
        for blank_term in ("", "   ", "///"):
            res = json.loads(self.run_kf("query", "search", blank_term, "--json", check=True).stdout)
            self.assertEqual(res["data"]["results"], [], f"blank search {blank_term!r} should not match records")
            self.assertIn("No records found", res["text"])
        res_dash = json.loads(self.run_kf("query", "search", "--", "---", "--json", check=True).stdout)
        self.assertEqual(res_dash["data"]["results"], [])



if __name__ == "__main__":
    unittest.main()
