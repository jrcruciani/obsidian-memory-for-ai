from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REF_VAULT = REPO_ROOT / "examples" / "v5-knowledge-factory"
EVAL_RUNNER = REPO_ROOT / "tests" / "eval" / "run_eval.py"


class V5ReferenceVaultTests(unittest.TestCase):
    def test_reference_vault_portable_tools_match_repo_tools(self) -> None:
        self.assertTrue((REF_VAULT / "tools/kf.py").is_file(), "examples/v5-knowledge-factory/tools/kf.py missing")
        repo_files = {
            p.relative_to(REPO_ROOT / "tools")
            for p in (REPO_ROOT / "tools").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        }
        vault_files = {
            p.relative_to(REF_VAULT / "tools")
            for p in (REF_VAULT / "tools").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        }
        self.assertEqual(
            repo_files,
            vault_files,
            f"bidirectional tool parity mismatch: repo_only={sorted(repo_files - vault_files)}, vault_only={sorted(vault_files - repo_files)}",
        )
        for rel in sorted(repo_files):
            py_file = REPO_ROOT / "tools" / rel
            vault_copy = REF_VAULT / "tools" / rel
            self.assertTrue(filecmp.cmp(py_file, vault_copy, shallow=False), f"drift between tools/{rel} and vault copy")

    def test_reference_vault_passes_strict_lint_and_zero_drift_double_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "ref"
            shutil.copytree(REF_VAULT, vault)
            env = dict(os.environ, KF_TODAY="2026-10-15")

            lint = subprocess.run(
                [sys.executable, "tools/kf.py", "lint", "--strict", "--json"],
                cwd=vault,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(lint.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["error_count"], 0)
            self.assertEqual(payload["data"]["warning_count"], 0)

            before = {p.relative_to(vault).as_posix(): p.read_bytes() for p in sorted((vault / "_generated").rglob("*.md"))}
            subprocess.run([sys.executable, "tools/kf.py", "rebuild"], cwd=vault, env=env, check=True, capture_output=True)
            after1 = {p.relative_to(vault).as_posix(): p.read_bytes() for p in sorted((vault / "_generated").rglob("*.md"))}
            subprocess.run([sys.executable, "tools/kf.py", "rebuild"], cwd=vault, env=env, check=True, capture_output=True)
            after2 = {p.relative_to(vault).as_posix(): p.read_bytes() for p in sorted((vault / "_generated").rglob("*.md"))}

            self.assertEqual(before, after1, "committed _generated/ artifacts drifted from canonical state")
            self.assertEqual(after1, after2, "double rebuild was not deterministic")

    def test_reference_vault_demonstrates_all_nine_canonical_types(self) -> None:
        env = dict(os.environ, KF_TODAY="2026-10-15")
        checks = [
            (["query", "facts", "--json"], "facts"),
            (["query", "events", "--json"], "events"),
            (["query", "skills", "--json"], "skills"),
            (["query", "guidance", "--json"], "guidance"),
            (["query", "decisions", "--json"], "decisions"),
            (["query", "signals", "--json"], "signals"),
            (["query", "proposals", "--json"], "proposals"),
            (["review", "list", "--json"], "reviews"),
            (["query", "receipts", "--json"], "receipts"),
        ]
        for args, key in checks:
            res = subprocess.run(
                [sys.executable, "tools/kf.py", *args],
                cwd=REF_VAULT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            items = json.loads(res.stdout)["data"][key]
            self.assertGreaterEqual(len(items), 1, f"expected >= 1 canonical {key} in reference vault")

    def test_offline_eval_suite_passes_against_reference_vault(self) -> None:
        res = subprocess.run(
            [sys.executable, str(EVAL_RUNNER), "--vault", str(REF_VAULT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("passed.", res.stdout)

    def test_docs_and_optional_guides_contain_no_broken_relative_links(self) -> None:
        import re

        link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        doc_files = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "SPEC-v5.0.md",
            *[p for p in sorted((REPO_ROOT / "docs").rglob("*.md")) if "archive" not in p.parts],
        ]
        broken: list[str] = []
        for md in doc_files:
            clean = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.DOTALL)
            for m in link_re.finditer(clean):
                target = m.group(2).strip()
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append(f"{md.relative_to(REPO_ROOT)}: {target}")
        self.assertEqual(broken, [], f"broken relative Markdown links: {broken}")

    def test_gitattributes_enforces_lf_and_quick_tour_uses_kf_today(self) -> None:
        gitattr = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
        for pattern in ("*.md text eol=lf", "*.yaml text eol=lf", "*.yml text eol=lf", "*.json text eol=lf", "*.py text eol=lf"):
            self.assertIn(pattern, gitattr)
        ref_readme = (REF_VAULT / "README.md").read_text(encoding="utf-8")
        self.assertIn("KF_TODAY=2026-10-15 python3 tools/kf.py lint --strict", ref_readme)


if __name__ == "__main__":
    unittest.main()
