"""TDD tests for disposable SQLite FTS5 + optional embedding RRF hybrid index."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

REF_VAULT = REPO_ROOT / "examples/v5-knowledge-factory"


class TestHybridSearchIndex(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_today = os.environ.get("KF_TODAY")
        os.environ["KF_TODAY"] = "2026-10-15"
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        shutil.copytree(REF_VAULT, self.vault)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        if self._orig_today is None:
            os.environ.pop("KF_TODAY", None)
        else:
            os.environ["KF_TODAY"] = self._orig_today

    def test_fts5_index_build_and_search_is_disposable_and_handles_diacritics(self) -> None:
        from kflib.hybrid_index import build_hybrid_index, hybrid_search

        stats = build_hybrid_index(self.vault, use_embeddings=False)
        self.assertGreater(stats["documents"], 10)
        db_path = self.vault / "_generated/indexes/search.sqlite"
        self.assertTrue(db_path.is_file())

        text, results, diags = hybrid_search(self.vault, "xrf calibration", use_embeddings=False, limit=5)
        self.assertTrue(results, f"expected FTS5 results for 'xrf calibration', got: {text}")
        self.assertTrue(any("xrf-pigment-scan" in r["path"] for r in results))
        self.assertEqual(diags, [])

        # Accent-insensitive FTS5 lookup
        _, accent_res, _ = hybrid_search(self.vault, "Gemäldegalerie", use_embeddings=False, limit=5)
        self.assertTrue(accent_res, "expected accent-folded match for Gemäldegalerie")

        # Disposable: deleting the sqlite file and searching auto-rebuilds transparently
        db_path.unlink()
        _, rebuilt_res, _ = hybrid_search(self.vault, "xrf calibration", use_embeddings=False, auto_build=True)
        self.assertTrue(db_path.is_file())
        self.assertTrue(rebuilt_res)

    def test_hybrid_rrf_fuses_fts5_and_semantic_embeddings(self) -> None:
        from kflib.hybrid_index import build_hybrid_index, hybrid_search

        # Deterministic synthetic embedding function that maps "humidity / moisture / climate"
        # to the same vector direction even when lexical terms differ completely.
        def fake_embed(text: str) -> list[float]:
            low = text.lower()
            v0 = 1.0 if any(w in low for w in ("humidity", "rh", "moisture", "hygrometer", "tempera")) else 0.0
            v1 = 1.0 if any(w in low for w in ("xrf", "keV".lower(), "spectrometer", "pigment")) else 0.0
            v2 = 1.0 if any(w in low for w in ("berlin", "location", "base", "city")) else 0.0
            return [v0, v1, v2, 0.1]

        stats = build_hybrid_index(self.vault, use_embeddings=True, embed_fn=fake_embed)
        self.assertGreater(stats["embedded"], 0)

        # Query using synonym "moisture" which does not appear verbatim in conservation-reporting-units
        _, results, _ = hybrid_search(
            self.vault,
            "moisture hygrometer",
            use_embeddings=True,
            embed_fn=fake_embed,
            limit=5,
        )
        self.assertTrue(results, "expected semantic RRF matches for zero-lexical-overlap query")
        self.assertTrue(
            any(r.get("semantic_score", 0.0) > 0.8 for r in results),
            f"expected high semantic score in RRF results, got: {results}",
        )


if __name__ == "__main__":
    unittest.main()
