"""Engine model catalog — defaults to best available per engine."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness.models import (
    default_model,
    models_for,
    resolve_model,
)


class Defaults(unittest.TestCase):
    def test_claude_defaults_to_best(self):
        self.assertEqual(default_model("claude"), "best")

    def test_codex_defaults_to_sol(self):
        self.assertEqual(default_model("codex"), "gpt-5.6-sol")

    def test_grok_defaults_to_build(self):
        self.assertEqual(default_model("grok"), "grok-build-0.1")

    def test_resolve_keeps_explicit(self):
        self.assertEqual(resolve_model("claude", "sonnet"), "sonnet")

    def test_resolve_falls_back_to_best(self):
        self.assertEqual(resolve_model("claude", ""), "best")
        self.assertEqual(resolve_model("claude", "  "), "best")

    def test_resolve_remaps_claude_alias_for_codex(self):
        self.assertEqual(resolve_model("codex", "best"), "gpt-5.6-sol")
        self.assertEqual(resolve_model("codex", "sonnet"), "gpt-5.6-sol")

    def test_resolve_remaps_codex_id_for_claude(self):
        self.assertEqual(resolve_model("claude", "gpt-5.6-sol"), "best")

    def test_resolve_keeps_unknown_custom(self):
        self.assertEqual(resolve_model("codex", "o3"), "o3")

    def test_catalog_nonempty(self):
        for engine in ("claude", "codex", "grok"):
            self.assertTrue(models_for(engine))
            self.assertEqual(models_for(engine)[0], default_model(engine))


if __name__ == "__main__":
    unittest.main()
