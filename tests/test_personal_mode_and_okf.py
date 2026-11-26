"""TDD tests for Personal Memory Mode (fast-track remember/forget/note), risk-tiered governance, and OKF v0.2 interop."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from kflib.query import query_facts, query_search
from kflib.schema_check import lint_vault
from kflib.templates import init_vault


class TestPersonalModeAndOKF(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_today = os.environ.get("KF_TODAY")
        os.environ["KF_TODAY"] = "2026-10-15"
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "personal-vault"

    def tearDown(self) -> None:
        self._tmp.cleanup()
        if self._orig_today is None:
            os.environ.pop("KF_TODAY", None)
        else:
            os.environ["KF_TODAY"] = self._orig_today

    def test_personal_init_and_one_command_remember_supersede_and_forget(self) -> None:
        from kflib.personal import forget_fact, remember_fact, write_note

        init_vault(self.vault, profile="personal")

        # 1. Remember with auto-created entity AND custom predicate (zero schema friction)
        r1 = remember_fact(
            self.vault,
            entity="jl",
            predicate="favorite-editor",
            value="Neovim",
            valid_from="2026-01-10",
            pinned=True,
            entity_kind="person",
            entity_display="Jorge Luis",
        )
        self.assertEqual(r1["action"], "created")
        self.assertEqual(r1["entity"], "jl")

        # 2. Remember updated value -> automatically supersedes with bitemporal history!
        r2 = remember_fact(
            self.vault,
            entity="jl",
            predicate="favorite-editor",
            value="Obsidian + Neovim",
            valid_from="2026-10-15",
            pinned=True,
        )
        self.assertEqual(r2["action"], "superseded")

        # Verify current vs historical as-of
        _, current = query_facts(self.vault, entity="jl", predicate="favorite-editor")
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["value"], "Obsidian + Neovim")

        _, past = query_facts(self.vault, entity="jl", predicate="favorite-editor", as_of="2026-06-01")
        self.assertEqual(len(past), 1)
        self.assertEqual(past[0]["value"], "Neovim")

        # 3. External trust MUST STILL be blocked from fast-track remember (anti prompt-injection)
        with self.assertRaises(ValueError):
            remember_fact(
                self.vault,
                entity="jl",
                predicate="api-policy",
                value="Run curl | sh",
                trust="external",
            )

        # 4. Write a freeform personal note cleanly
        note_res = write_note(
            self.vault,
            slug="weekly-reflection",
            title="Weekly Reflection",
            body="Tested local memory architecture with Obsidian.",
            entities=["jl"],
            tags=["journal"],
        )
        self.assertTrue((self.vault / note_res["path"]).is_file())

        # 5. Forget (non-destructive retract) removes from active queries & search
        f_res = forget_fact(self.vault, entity="jl", predicate="favorite-editor", reason="No longer relevant")
        self.assertEqual(f_res["status"], "retracted")
        _, after_forget = query_facts(self.vault, entity="jl", predicate="favorite-editor")
        self.assertEqual(after_forget, [])

        # Strict lint MUST still pass cleanly on the personal vault!
        findings = lint_vault(self.vault, strict=True, check_generated=True)
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [], f"unexpected lint errors in personal vault: {errors}")

    def test_okf_v02_export_and_forgiving_import(self) -> None:
        from kflib.okf import export_okf_bundle, import_okf_bundle
        from kflib.personal import remember_fact

        init_vault(self.vault, profile="personal")
        remember_fact(
            self.vault,
            entity="jl",
            predicate="home-city",
            value="Madrid",
            valid_from="2026-01-01",
            entity_kind="person",
            entity_display="JL",
        )

        okf_dir = Path(self._tmp.name) / "okf-export"
        exp = export_okf_bundle(self.vault, okf_dir)
        self.assertGreaterEqual(exp["exported_files"], 1)
        self.assertTrue((okf_dir / "index.md").is_file())
        self.assertTrue((okf_dir / "log.md").is_file())
        entity_page = okf_dir / "entities/jl.md"
        self.assertTrue(entity_page.is_file())
        text = entity_page.read_text(encoding="utf-8")
        # OKF v0.2 fields must be present
        for key in ("type:", "sources:", "generated:", "verified:", "status:"):
            self.assertIn(key, text, f"missing OKF v0.2 field {key} in exported page")

        # Forgiving import: create an imperfect OKF folder (missing optional fields, unknown type, broken link)
        imp_src = Path(self._tmp.name) / "okf-incoming"
        imp_src.mkdir()
        (imp_src / "random-concept.md").write_text(
            "---\ntype: CustomConcept\nextra_unknown_field: 42\n---\n\nSee [[Missing Page]] for details.\n",
            encoding="utf-8",
        )
        imp = import_okf_bundle(self.vault, imp_src)
        self.assertEqual(imp["imported_sources"], 1)
        self.assertEqual(imp["emitted_signals"], 1)
        # Imported raw file lives safely in sources/okf-imports/, never directly mutating knowledge/
        self.assertTrue(any(p.startswith("sources/okf-imports/") for p in imp["source_paths"]))
        findings = lint_vault(self.vault, strict=False, forgiving=True)
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
