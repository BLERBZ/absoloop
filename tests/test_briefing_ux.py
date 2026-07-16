"""Mission Briefing UX helpers — slug, objective detection, card render."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import briefing as ux


class ObjectiveDetection(unittest.TestCase):
    def test_quoted_sentence_is_objective(self):
        self.assertTrue(ux.looks_like_objective("Make all tests pass"))

    def test_bare_slug_is_project_name(self):
        self.assertFalse(ux.looks_like_objective("my-mission"))

    def test_trailing_punct_is_objective(self):
        self.assertTrue(ux.looks_like_objective("fix-it."))


class Slug(unittest.TestCase):
    def test_slug_drops_stopwords(self):
        self.assertEqual(ux.slug_from_objective("Make all the tests pass"),
                         "tests-pass")

    def test_empty_falls_back(self):
        self.assertEqual(ux.slug_from_objective("the a an", fallback="x"), "x")


class Card(unittest.TestCase):
    def test_card_contains_objective_and_keys(self):
        brief = ux.Briefing(
            target="/tmp/demo", target_name=".", adopting=True,
            objective="Make all tests pass", delivery="local", engine="claude",
            kinds=["tests"], engines_available=("claude",))
        card = ux.render_card(brief)
        self.assertIn("MISSION BRIEFING", card)
        self.assertIn("Make all tests pass", card)
        self.assertIn("Red to green", card)
        self.assertIn("Enter", card)
        self.assertIn("claude", card)


class ReviewAbort(unittest.TestCase):
    def test_quit_returns_none(self):
        brief = ux.Briefing(
            target="/tmp/demo", target_name=".", adopting=True,
            objective="x", delivery="local", engine="claude",
            kinds=["general"], engines_available=("claude",))
        # Feed 'q' into review_loop
        import io, contextlib
        stdin = io.StringIO("q\n")
        with contextlib.redirect_stdout(io.StringIO()):
            old = sys.stdin
            sys.stdin = stdin
            try:
                result = ux.review_loop(
                    brief, engines=("claude",), engine_labels={"claude": "ok"},
                    deliveries=("local",), classify=lambda o: ["general"])
            finally:
                sys.stdin = old
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
