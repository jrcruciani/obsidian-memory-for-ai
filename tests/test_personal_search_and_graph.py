"""TDD tests for BM25 multi-term search, fast index staleness check, and multi-hop temporal graph."""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from kflib.query import query_graph, query_search, query_skills
from kflib.rebuild import rebuild_all
from kflib.templates import init_vault

REF_VAULT = REPO_ROOT / "examples/v5-knowledge-factory"


class TestSearchAndGraphUpgrades(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_today = os.environ.get("KF_TODAY")
        os.environ["KF_TODAY"] = "2026-10-15"

    def tearDown(self) -> None:
        if self._orig_today is None:
            os.environ.pop("KF_TODAY", None)
        else:
            os.environ["KF_TODAY"] = self._orig_today

    def test_multi_term_bm25_search_matches_non_adjacent_terms(self) -> None:
        text, items, diags = query_search(REF_VAULT, "xrf calibration")
        self.assertTrue(items, f"expected matches for 'xrf calibration', got none: {text}")
        slugs_or_paths = [it.get("path", "") for it in items]
        self.assertTrue(
            any("xrf-pigment-scan" in p for p in slugs_or_paths),
            f"expected xrf-pigment-scan skill in results, got: {slugs_or_paths}",
        )

        # Multi-term entity + attribute query across facts
        _, elena_items, _ = query_search(REF_VAULT, "elena berlin")
        self.assertTrue(elena_items, "expected matches for 'elena berlin'")
        self.assertEqual(elena_items[0]["path"], "knowledge/facts/elena-voss/base.md")

    def test_search_can_include_notes_and_sources_and_respects_limit(self) -> None:
        _, items_notes, _ = query_search(REF_VAULT, "venice panel", include_notes=True, include_sources=True, limit=3)
        self.assertLessEqual(len(items_notes), 3)
        self.assertTrue(
            any(it["type"] in {"source", "note"} for it in items_notes),
            f"expected at least one source or note result, got: {items_notes}",
        )

    def test_query_search_does_not_rebuild_all_indexes_for_staleness_check(self) -> None:
        import kflib.query as query_mod

        with mock.patch.object(
            query_mod,
            "build_all_indexes",
            side_effect=AssertionError("query_search must not call build_all_indexes() on every query"),
        ):
            _, items, diags = query_search(REF_VAULT, "Voss")
        self.assertTrue(items)
        self.assertEqual(diags, [])

    def test_multi_term_skill_trigger_matching(self) -> None:
        _, skills = query_skills(REF_VAULT, trigger="xrf keV")
        self.assertTrue(
            any(s["slug"] == "xrf-pigment-scan" for s in skills),
            f"expected xrf-pigment-scan for multi-term trigger, got: {skills}",
        )

    def test_graph_multihop_and_shortest_path(self) -> None:
        # In ref vault: elena-voss -> gemaeldegalerie, concordance -> marta-delvaux, etc.
        _, depth2, _ = query_graph(REF_VAULT, "elena-voss", depth=2)
        self.assertTrue(
            any(e.get("hop", 1) == 2 for e in depth2),
            f"expected hop=2 edges in depth=2 graph query, got: {depth2}",
        )

        # Shortest path from elena-voss to marta-delvaux (via concordance)
        text, path_edges, _ = query_graph(REF_VAULT, "elena-voss", target_node="marta-delvaux", depth=3)
        self.assertTrue(path_edges, f"expected path between elena-voss and marta-delvaux, got: {text}")
        endpoints = {e["from"] for e in path_edges} | {e["to"] for e in path_edges}
        self.assertIn("elena-voss", endpoints)
        self.assertIn("marta-delvaux", endpoints)


if __name__ == "__main__":
    unittest.main()
