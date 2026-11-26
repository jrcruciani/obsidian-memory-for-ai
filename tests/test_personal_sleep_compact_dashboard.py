"""TDD tests for token-aware bootstrap, normalized contradiction scan + sleep-pack, ledger archival (OD-004), and Obsidian dashboard."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from kflib.bootstrap import build_bootstrap_with_meta
from kflib.capture import capture_event, capture_signal
from kflib.curate import dismiss_signal, scan_vault_drift
from kflib.personal import remember_fact
from kflib.rebuild import rebuild_all
from kflib.schema_check import lint_vault
from kflib.templates import init_vault


class TestSleepCurateCompactAndDashboard(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_today = os.environ.get("KF_TODAY")
        self._orig_now = os.environ.get("KF_NOW")
        os.environ["KF_TODAY"] = "2026-10-15"
        os.environ["KF_NOW"] = "2026-10-15T12:00:00Z"
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "personal-vault"
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

    def test_token_aware_bootstrap_caps_output_by_max_tokens(self) -> None:
        for i in range(15):
            remember_fact(
                self.vault,
                entity="jl",
                predicate=f"note-fact-{i}",
                value=f"Long personal preference number {i} with enough text to fill context budget nicely.",
                pinned=True,
                rebuild=False,
            )
        rebuild_all(self.vault)

        text, meta = build_bootstrap_with_meta(self.vault, profile="personal", max_tokens=200)
        # 200 tokens * 3.5 chars/token = 700 chars max
        self.assertLessEqual(len(text), 700)
        self.assertLessEqual(meta["estimated_tokens"], 200)
        self.assertGreater(meta["estimated_tokens"], 0)

    def test_normalized_contradiction_and_sleep_curation_pack(self) -> None:
        from kflib.curate import build_sleep_curation_pack

        remember_fact(
            self.vault,
            entity="jl",
            predicate="location",
            value="Madrid",
            valid_from="2026-01-01",
            rebuild=False,
        )
        # Same value with case/whitespace/accent noise MUST NOT trigger false contradiction
        capture_event(
            self.vault,
            recorded_by="agent-owner-00000001",
            event_id="evt-same-city",
            occurred_at="2026-10-16T09:00:00Z",
            summary="Confirmed location Madrid",
            entities=["jl"],
            asserts_raw=[{"entity": "jl", "predicate": "location", "value": "  madríd "}],
        )
        scan1 = scan_vault_drift(self.vault, emit_signals=False)
        contradictions1 = [d for d in scan1["detections"] if d["kind"] == "contradiction"]
        self.assertEqual(contradictions1, [], f"whitespace/case/accent variant must not false-trigger: {contradictions1}")

        # Genuine new city MUST trigger contradiction
        capture_event(
            self.vault,
            recorded_by="agent-owner-00000001",
            event_id="evt-new-city",
            occurred_at="2026-10-17T09:00:00Z",
            summary="Moved to Valencia",
            entities=["jl"],
            asserts_raw=[{"entity": "jl", "predicate": "location", "value": "Valencia"}],
        )
        pack = build_sleep_curation_pack(self.vault, emit_signals=True)
        self.assertGreaterEqual(len(pack["open_signals"]), 1)
        self.assertTrue(any(d["kind"] == "contradiction" for d in pack["detections"]))
        self.assertIn("untrusted", pack["prompt_markdown"].lower())

    def test_ledger_archival_rolls_up_old_closed_signals_and_preserves_lint(self) -> None:
        from kflib.compact import archive_ledger

        os.environ["KF_TODAY"] = "2025-03-10"
        os.environ["KF_NOW"] = "2025-03-10T10:00:00Z"
        sig = capture_signal(
            self.vault,
            emitted_by="agent-executor-00000004",
            kind="observation",
            summary="Old 2025 observation to dismiss",
        )
        dismiss_signal(
            self.vault,
            signal_id=sig["id"],
            curator_id="agent-curator-00000003",
            reason="Superseded by newer notes",
            yes=True,
            rebuild=False,
        )

        os.environ["KF_TODAY"] = "2026-10-15"
        os.environ["KF_NOW"] = "2026-10-15T12:00:00Z"
        res = archive_ledger(self.vault, before="2026-01-01", yes=True)
        self.assertGreaterEqual(res["archived_signals"], 1)
        self.assertTrue((self.vault / "factory/archive/2025-ledger-rollup.md").is_file())
        self.assertFalse((self.vault / sig["path"]).exists())

        rebuild_all(self.vault)
        findings = lint_vault(self.vault, strict=True, check_generated=True)
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [], f"lint errors after archive-ledger: {errors}")

    def test_personal_vault_generates_obsidian_dashboard_view(self) -> None:
        remember_fact(self.vault, entity="jl", predicate="goal", value="Build local personal AI memory", pinned=True)
        dash = self.vault / "_generated/views/dashboard.md"
        self.assertTrue(dash.is_file(), "personal vault should generate _generated/views/dashboard.md")
        content = dash.read_text(encoding="utf-8")
        self.assertIn("Personal Memory Dashboard", content)
        self.assertIn("[[", content)


if __name__ == "__main__":
    unittest.main()
