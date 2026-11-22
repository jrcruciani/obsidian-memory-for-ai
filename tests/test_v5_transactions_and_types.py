from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
KF_CLI = REPO_ROOT / "tools" / "kf.py"


class V5TransactionsAndTypesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        self.run_kf("init", str(self.vault), cwd=REPO_ROOT, check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_kf(self, *args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, KF_TODAY="2026-10-15", KF_NOW="2026-10-15T12:00:00Z")
        return subprocess.run(
            [sys.executable, str(KF_CLI), *args],
            cwd=cwd or self.vault,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_executor_and_curator_cannot_run_direct_transactions(self) -> None:
        for actor in ("agent-executor-00000004", "agent-curator-00000003"):
            res = self.run_kf("transact", "begin", "--idempotency-key", f"key-{actor}", "--actor", actor)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("direct_transact", res.stdout + res.stderr)

    def test_owner_cannot_direct_transact_external_trust_fact(self) -> None:
        ops_file = self.vault / "_ops_ext.json"
        ops_file.write_text(json.dumps([
            {"op": "upsert_entity", "entity_id": "concordance", "kind": "project", "display": "Concordance", "aliases": []},
            {
                "op": "create_fact",
                "entity": "concordance",
                "predicate": "tool",
                "value": "Unverified XRF",
                "trust": "external",
                "confidence": 0.6,
                "assertion": "stated",
            },
        ]), encoding="utf-8")
        begin = self.run_kf("transact", "begin", "--idempotency-key", "ext-test", "--actor", "agent-owner-00000001", "--json", check=True)
        txn_id = json.loads(begin.stdout)["data"]["transaction_id"]
        add = self.run_kf("transact", "add", "--txn-id", txn_id, "--ops-file", str(ops_file))
        ops_file.unlink()
        if add.returncode == 0:
            commit = self.run_kf("transact", "commit", "--txn-id", txn_id, "--yes")
            self.assertNotEqual(commit.returncode, 0)
            self.assertIn("external", commit.stdout + commit.stderr)
        else:
            self.assertIn("external", add.stdout + add.stderr)

    def test_full_canonical_types_lifecycle_and_supersession(self) -> None:
        # 1. Seed entities, event, initial fact, skill, guidance, decision via owner transaction
        ops_seed = [
            {
                "op": "upsert_entity",
                "entity_id": "elena-voss",
                "kind": "person",
                "display": "Elena Voss",
                "aliases": ["Voss", "Éléna Voss"],
            },
            {
                "op": "upsert_entity",
                "entity_id": "concordance",
                "kind": "project",
                "display": "Concordance Pigment Atlas",
                "aliases": ["Concordance"],
            },
            {
                "op": "create_event",
                "event_id": "evt-kickoff",
                "occurred_at": "2026-03-15T09:00:00Z",
                "summary": "Elena joined Concordance as pigment researcher.",
                "entities": ["elena-voss", "concordance"],
                "sources": ["sources/README.md"],
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "role",
                "value": "Pigment researcher",
                "valid_from": "2026-03-15",
                "confidence": 0.9,
                "assertion": "stated",
                "trust": "owner",
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "pinned": True,
            },
            {
                "op": "create_skill",
                "slug": "xrf-calibration",
                "title": "XRF Spectrum Calibration",
                "domain": "conservation",
                "triggers": ["calibrate xrf", "pigment scan"],
                "inputs": ["raw spectrum file"],
                "outputs": ["calibrated spectrum summary"],
                "verification": ["Confirm copper K-alpha peak within +/- 0.02 keV"],
                "entities": ["concordance"],
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "trust": "owner",
                "confidence": 0.95,
                "pinned": True,
                "body": "## Procedure\n\n1. Warm tube for 120s.\n2. Check copper reference.",
            },
            {
                "op": "create_guidance",
                "slug": "metric-units-only",
                "title": "ISO Metric Units in Conservation Logs",
                "domain": "conservation",
                "scope": "executor",
                "priority": "critical",
                "policy_rule": "Express all pigment dimensions, wavelengths, and masses in SI metric units.",
                "anti_patterns": ["Using inches or Fahrenheit in lab summaries"],
                "entities": ["concordance"],
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "trust": "owner",
                "pinned": True,
                "body": "## Rationale\n\nCross-lab reproducibility requires SI units.",
            },
            {
                "op": "create_decision",
                "decision_id": "DEC-001-si-units",
                "title": "Mandate SI Metric Units Across Concordance",
                "decided_at": "2026-03-15",
                "domain": "conservation",
                "summary": "All measurements in Concordance records use SI units.",
                "entities": ["concordance"],
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "consequences": ["Legacy imperial notes require explicit conversion annotations"],
                "pinned": True,
                "body": "## Context\n\nPartner labs operate in Berlin and Venice.",
            },
        ]
        seed_path = Path(self._tmp.name) / "seed.json"
        seed_path.write_text(json.dumps(ops_seed), encoding="utf-8")

        b1 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-001", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b1["transaction_id"], "--ops-file", str(seed_path), check=True)
        c1 = json.loads(self.run_kf("transact", "commit", "--txn-id", b1["transaction_id"], "--yes", "--rebuild", "--json", check=True).stdout)["data"]
        self.assertEqual(c1["status"], "committed")
        self.assertTrue((self.vault / "factory/receipts" / f"{c1['receipt_id']}.md").is_file())

        # Idempotent replay with same key does not create a second receipt
        replay = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-001", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.assertEqual(replay["status"], "committed")

        # 2. Supersede fact, skill, guidance, decision + retract another fact
        ops_evolve = [
            {
                "op": "create_event",
                "event_id": "evt-promotion",
                "occurred_at": "2026-07-15T10:00:00Z",
                "summary": "Elena appointed Lead Conservator.",
                "entities": ["elena-voss"],
            },
            {
                "op": "supersede_fact",
                "entity": "elena-voss",
                "predicate": "role",
                "value": "Lead conservator",
                "valid_from": "2026-07-15",
                "confidence": 0.98,
                "assertion": "stated",
                "trust": "owner",
                "derived_from": ["knowledge/events/2026-07-15/evt-promotion.md"],
                "pinned": True,
            },
            {
                "op": "supersede_skill",
                "slug": "xrf-calibration",
                "title": "XRF Spectrum Calibration v2",
                "domain": "conservation",
                "triggers": ["calibrate xrf", "pigment scan", "panel xrf"],
                "verification": ["Confirm Cu K-alpha within +/- 0.01 keV", "Log ambient RH%"],
                "trust": "owner",
                "confidence": 0.99,
                "body": "## Procedure v2\n\n1. Warm tube 120s.\n2. Record ambient RH%.\n3. Verify Cu reference.",
            },
            {
                "op": "supersede_guidance",
                "slug": "metric-units-only",
                "title": "SI Metric Units & Uncertainty Bounds",
                "domain": "conservation",
                "scope": "executor",
                "priority": "critical",
                "policy_rule": "Express all measurements in SI units with explicit +/- uncertainty.",
                "anti_patterns": ["Imperial units", "Point estimates without instrument tolerance"],
                "trust": "owner",
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "language",
                "value": "French",
                "confidence": 0.5,
                "assertion": "inferred",
                "trust": "owner",
                "derived_from": ["knowledge/events/2026-07-15/evt-promotion.md"],
            },
        ]
        evolve_path = Path(self._tmp.name) / "evolve.json"
        evolve_path.write_text(json.dumps(ops_evolve), encoding="utf-8")
        b2 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "evolve-002", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b2["transaction_id"], "--ops-file", str(evolve_path), check=True)
        self.run_kf("transact", "commit", "--txn-id", b2["transaction_id"], "--yes", "--rebuild", check=True)

        self.assertTrue((self.vault / "knowledge/facts/elena-voss/role/2026-03-15.md").is_file())
        self.assertTrue((self.vault / "knowledge/skills/xrf-calibration/2026-10-15.md").is_file())
        self.assertTrue((self.vault / "knowledge/guidance/metric-units-only/2026-10-15.md").is_file())

        # Retract the mistaken inferred language fact
        b3 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "retract-003", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf(
            "transact", "add", "--txn-id", b3["transaction_id"],
            "--op", "retract_fact",
            "--entity", "elena-voss",
            "--predicate", "language",
            "--reason", "Owner withdrew unverified language inference.",
            check=True,
        )
        self.run_kf("transact", "commit", "--txn-id", b3["transaction_id"], "--yes", "--rebuild", check=True)

        # Entire vault passes strict lint!
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def test_rollback_and_crash_recovery(self) -> None:
        b = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "pending-txn", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        txn_id = b["transaction_id"]
        self.assertTrue((self.vault / "factory/_staging" / txn_id).is_dir())
        rec = self.run_kf("transact", "recover", "--yes", "--json", check=True)
        payload = json.loads(rec.stdout)["data"]
        self.assertIn(txn_id, payload["recovered"])
        self.assertFalse((self.vault / "factory/_staging" / txn_id).exists())

    def test_multiple_same_day_supersessions_generate_distinct_ids_and_history_paths(self) -> None:
        # Seed entity + v1 of fact, skill, guidance, and decision on 2026-10-15
        seed_ops = [
            {"op": "upsert_entity", "entity_id": "elena-voss", "kind": "person", "display": "Elena Voss", "aliases": []},
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "base",
                "value": "Berlin",
                "valid_from": "2026-01-10",
                "confidence": 0.9,
                "assertion": "stated",
                "trust": "owner",
            },
            {
                "op": "create_skill",
                "slug": "raman-check",
                "title": "Raman Check v1",
                "domain": "conservation",
                "triggers": ["raman"],
                "verification": ["check peak 1"],
                "trust": "owner",
                "confidence": 0.9,
            },
            {
                "op": "create_guidance",
                "slug": "rh-guard",
                "title": "RH Guard v1",
                "domain": "conservation",
                "scope": "executor",
                "priority": "high",
                "policy_rule": "Keep RH <= 60%.",
                "trust": "owner",
            },
            {
                "op": "create_decision",
                "decision_id": "DEC-010",
                "title": "Initial RH Ceiling 60%",
                "decided_at": "2026-10-15",
                "domain": "conservation",
                "summary": "Initial ceiling 60%.",
            },
        ]
        seed_file = Path(self._tmp.name) / "seed_multi.json"
        seed_file.write_text(json.dumps(seed_ops), encoding="utf-8")
        b0 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "multi-0", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b0["transaction_id"], "--ops-file", str(seed_file), check=True)
        self.run_kf("transact", "commit", "--txn-id", b0["transaction_id"], "--yes", check=True)

        # Perform 3 consecutive same-day supersessions (2026-10-15) across all 4 living types:
        # round 1 in its own transaction, and rounds 2 + 3 bundled together in one transaction!
        def make_round_ops(n: int) -> list[dict[str, object]]:
            return [
                {
                    "op": "supersede_fact",
                    "entity": "elena-voss",
                    "predicate": "base",
                    "value": f"Location-{n}",
                    "valid_from": "2026-10-15",
                    "confidence": 0.95,
                    "assertion": "stated",
                    "trust": "owner",
                },
                {
                    "op": "supersede_skill",
                    "slug": "raman-check",
                    "title": f"Raman Check round {n}",
                    "verification": [f"check peak {n + 1}"],
                    "trust": "owner",
                },
                {
                    "op": "supersede_guidance",
                    "slug": "rh-guard",
                    "policy_rule": f"Keep RH <= {58 - n}%.",
                    "trust": "owner",
                },
                {
                    "op": "supersede_decision",
                    "decision_id": "DEC-010",
                    "summary": f"Updated ceiling round {n}.",
                },
            ]

        f1 = Path(self._tmp.name) / "round1.json"
        f1.write_text(json.dumps(make_round_ops(1)), encoding="utf-8")
        b1 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "multi-1", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b1["transaction_id"], "--ops-file", str(f1), check=True)
        self.run_kf("transact", "commit", "--txn-id", b1["transaction_id"], "--yes", check=True)

        f23 = Path(self._tmp.name) / "round23.json"
        f23.write_text(json.dumps([*make_round_ops(2), *make_round_ops(3)]), encoding="utf-8")
        b23 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "multi-23", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b23["transaction_id"], "--ops-file", str(f23), check=True)
        self.run_kf("transact", "commit", "--txn-id", b23["transaction_id"], "--yes", "--rebuild", check=True)

        # Verify distinct archive files exist for all 3 supersessions of each type
        self.assertTrue((self.vault / "knowledge/facts/elena-voss/base/2026-01-10.md").is_file())
        self.assertTrue((self.vault / "knowledge/facts/elena-voss/base/2026-10-15.md").is_file())
        self.assertTrue((self.vault / "knowledge/facts/elena-voss/base/2026-10-15-2.md").is_file())

        for folder in (
            "knowledge/skills/raman-check",
            "knowledge/guidance/rh-guard",
            "knowledge/decisions/DEC-010",
        ):
            self.assertTrue((self.vault / f"{folder}/2026-10-15.md").is_file())
            self.assertTrue((self.vault / f"{folder}/2026-10-15-2.md").is_file())
            self.assertTrue((self.vault / f"{folder}/2026-10-15-3.md").is_file())

        # Verify 3-hop supersedes chain via `query why` for all 4 types
        for args in (
            ("query", "why", "fact", "elena-voss", "base", "--json"),
            ("query", "why", "skill", "raman-check", "--json"),
            ("query", "why", "guidance", "rh-guard", "--json"),
            ("query", "why", "decision", "DEC-010", "--json"),
        ):
            why = json.loads(self.run_kf(*args, check=True).stdout)["data"]
            self.assertEqual(len(why["supersedes_chain"]), 3, f"expected 3 prior versions for {args}")

        # Strict lint passes with zero duplicate IDs and zero interval errors
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def test_retracted_facts_never_resurrect_historically_replace_without_deadlock_and_forbid_confirm(self) -> None:
        # 1. Seed entity + two active facts + active skill + active guidance
        seed_ops = [
            {"op": "upsert_entity", "entity_id": "elena-voss", "kind": "person", "display": "Elena Voss", "aliases": []},
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "language",
                "value": "Erroneous French",
                "valid_from": "2026-03-01",
                "confidence": 0.6,
                "assertion": "inferred",
                "trust": "owner",
                "derived_from": ["sources/README.md"],
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "tool",
                "value": "Mistaken Late Tool",
                "valid_from": "2026-10-10",
                "confidence": 0.6,
                "assertion": "inferred",
                "trust": "owner",
                "derived_from": ["sources/README.md"],
            },
            {
                "op": "create_skill",
                "slug": "bad-proc",
                "title": "Flawed Procedure v1",
                "domain": "conservation",
                "triggers": ["flawed"],
                "verification": ["step 1"],
                "trust": "owner",
            },
            {
                "op": "create_guidance",
                "slug": "bad-rule",
                "title": "Flawed Rule v1",
                "domain": "conservation",
                "scope": "executor",
                "priority": "normal",
                "policy_rule": "Obsolete rule.",
                "trust": "owner",
            },
        ]
        sf = Path(self._tmp.name) / "ret_seed.json"
        sf.write_text(json.dumps(seed_ops), encoding="utf-8")
        b0 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "ret-0", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b0["transaction_id"], "--ops-file", str(sf), check=True)
        self.run_kf("transact", "commit", "--txn-id", b0["transaction_id"], "--yes", check=True)

        # 2. Retract all four records
        retract_ops = [
            {"op": "retract_fact", "entity": "elena-voss", "predicate": "language", "reason": "False inference"},
            {"op": "retract_fact", "entity": "elena-voss", "predicate": "tool", "reason": "Wrong date and instrument"},
            {"op": "retract_skill", "slug": "bad-proc", "reason": "Unsafe calibration"},
            {"op": "retract_guidance", "slug": "bad-rule", "reason": "Withdrawn policy"},
        ]
        rf = Path(self._tmp.name) / "ret_all.json"
        rf.write_text(json.dumps(retract_ops), encoding="utf-8")
        b1 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "ret-1", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b1["transaction_id"], "--ops-file", str(rf), check=True)
        self.run_kf("transact", "commit", "--txn-id", b1["transaction_id"], "--yes", check=True)

        # 3. Improper confirm_fact and double retract_fact on a retracted fact MUST fail (in transact and propose)
        b_bad = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "ret-bad-confirm", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b_bad["transaction_id"], "--op", "confirm_fact", "--entity", "elena-voss", "--predicate", "language", check=True)
        bad_commit = self.run_kf("transact", "commit", "--txn-id", b_bad["transaction_id"], "--yes")
        self.assertNotEqual(bad_commit.returncode, 0)
        self.assertIn("retracted", (bad_commit.stdout + bad_commit.stderr).lower())
        self.run_kf("transact", "rollback", "--txn-id", b_bad["transaction_id"], check=True)

        bad_prop_confirm = self.run_kf(
            "propose", "create",
            "--title", "Confirm retracted fact",
            "--namespace", "facts",
            "--proposer", "agent-curator-00000003",
            "--op", "confirm_fact",
            "--entity", "elena-voss",
            "--predicate", "language",
        )
        self.assertNotEqual(bad_prop_confirm.returncode, 0)

        bad_prop_retract_again = self.run_kf(
            "propose", "create",
            "--title", "Retract already retracted fact",
            "--namespace", "facts",
            "--proposer", "agent-curator-00000003",
            "--op", "retract_fact",
            "--entity", "elena-voss",
            "--predicate", "language",
            "--reason", "Second retraction",
        )
        self.assertNotEqual(bad_prop_retract_again.returncode, 0)

        # 4. Replace retracted facts/skill/guidance WITHOUT deadlock:
        #    - supersede_fact on 'language' (2026-10-15) must NOT resurrect 'Erroneous French' at --as-of 2026-05-01!
        #    - create_fact on 'tool' with earlier valid_from='2026-01-01' (< '2026-10-10') must NOT deadlock!
        #    - create_skill and create_guidance on retracted slots archive retracted history cleanly!
        replace_ops = [
            {
                "op": "supersede_fact",
                "entity": "elena-voss",
                "predicate": "language",
                "value": "German",
                "valid_from": "2026-10-15",
                "confidence": 0.95,
                "assertion": "stated",
                "trust": "owner",
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "tool",
                "value": "Bruker Tracer 5g",
                "valid_from": "2026-01-01",
                "confidence": 0.95,
                "assertion": "stated",
                "trust": "owner",
            },
            {
                "op": "create_skill",
                "slug": "bad-proc",
                "title": "Corrected Procedure v2",
                "domain": "conservation",
                "triggers": ["calibrated"],
                "verification": ["verify standard"],
                "trust": "owner",
            },
            {
                "op": "create_guidance",
                "slug": "bad-rule",
                "title": "Corrected Rule",
                "domain": "conservation",
                "scope": "executor",
                "priority": "high",
                "policy_rule": "Verified rule.",
                "trust": "owner",
            },
        ]
        rep_file = Path(self._tmp.name) / "ret_replace.json"
        rep_file.write_text(json.dumps(replace_ops), encoding="utf-8")
        b2 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "ret-2", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b2["transaction_id"], "--ops-file", str(rep_file), check=True)
        self.run_kf("transact", "commit", "--txn-id", b2["transaction_id"], "--yes", "--rebuild", check=True)

        # Historical query MUST NOT resurrect retracted 'Erroneous French' or 'Mistaken Late Tool'!
        as_of_may = self.run_kf("query", "facts", "--entity", "elena-voss", "--as-of", "2026-05-01", check=True).stdout
        self.assertNotIn("Erroneous French", as_of_may)
        self.assertIn("Bruker Tracer 5g", as_of_may)

        as_of_oct12 = self.run_kf("query", "facts", "--entity", "elena-voss", "--as-of", "2026-10-12", check=True).stdout
        self.assertNotIn("Mistaken Late Tool", as_of_oct12)
        self.assertIn("Bruker Tracer 5g", as_of_oct12)

        # --history preserves full non-destructive audit trail with status=retracted
        hist_lang = self.run_kf("query", "facts", "--entity", "elena-voss", "--predicate", "language", "--history", check=True).stdout
        self.assertIn("status=retracted", hist_lang)
        self.assertIn("status=active", hist_lang)
        self.assertNotIn("status=superseded", hist_lang)

        # Strict lint passes cleanly
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
