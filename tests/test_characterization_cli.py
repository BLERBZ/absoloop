"""Characterization tests: pin down existing `bin/absoloop` behavior before
the multi-provider harness refactor. These tests describe what the code does
today; a failure means a regression in legacy behavior, not a style opinion.
"""
from __future__ import annotations

import unittest

from tests._load import load_cli

cli = load_cli()


class ClassifyMission(unittest.TestCase):
    def test_tests_keywords(self):
        self.assertIn("tests", cli.classify_mission("Make all tests pass"))

    def test_bugfix_keywords(self):
        self.assertIn("bugfix", cli.classify_mission("Fix the crash in the parser"))

    def test_multiple_kinds(self):
        kinds = cli.classify_mission("Fix the failing tests")
        self.assertIn("tests", kinds)
        self.assertIn("bugfix", kinds)

    def test_no_match_yields_general(self):
        self.assertEqual(cli.classify_mission("zzz qqq"), ["general"])


class ThinkingLadder(unittest.TestCase):
    def test_ladder_has_four_rungs(self):
        ladder = cli.build_thinking_ladder(["tests"])
        self.assertEqual(len(ladder), 4)

    def test_base_depth_zero_starts_at_think(self):
        ladder = cli.build_thinking_ladder(["tests"])
        self.assertEqual(ladder[0]["claude_keyword"], "think")

    def test_bugfix_starts_one_rung_up(self):
        ladder = cli.build_thinking_ladder(["bugfix"])
        self.assertEqual(ladder[0]["claude_keyword"], "think hard")

    def test_ladder_caps_at_ultrathink(self):
        ladder = cli.build_thinking_ladder(["bugfix"])
        self.assertEqual(ladder[-1]["claude_keyword"], "ultrathink")

    def test_generated_ladder_validates_clean(self):
        ladder = cli.build_thinking_ladder(["perf"])
        self.assertEqual(cli.validate_thinking_ladder(ladder), [])

    def test_deescalating_ladder_is_flagged(self):
        ladder = cli.build_thinking_ladder(["tests"])
        ladder[1] = dict(ladder[1], claude_thinking_tokens=1)
        self.assertTrue(cli.validate_thinking_ladder(ladder))

    def test_non_list_ladder_is_flagged(self):
        self.assertTrue(cli.validate_thinking_ladder("nope"))


class GoalContract(unittest.TestCase):
    def _config(self, objective="Make all tests pass"):
        return cli.runtime_config(objective, "loop-test", "local")

    def test_goal_contains_objective(self):
        config = self._config()
        self.assertIn("Make all tests pass", cli.generate_goal_markdown(config))

    def test_goal_contains_constraints(self):
        text = cli.generate_goal_markdown(self._config())
        self.assertIn("Never weaken, skip, or delete tests", text)

    def test_empty_objective_fails_validation(self):
        config = self._config()
        config["objective"] = ""
        self.assertTrue(cli.validate_goal_config(config))

    def test_valid_config_passes_validation(self):
        self.assertEqual(cli.validate_goal_config(self._config()), [])

    def test_runtime_config_shape(self):
        config = self._config()
        for key in ("mission_id", "loop_id", "objective", "thinking_ladder",
                    "delivery", "max_iterations", "max_cost_usd",
                    "claude", "codex"):
            self.assertIn(key, config)


class DeliveryModes(unittest.TestCase):
    def test_git_delivery_names_branch(self):
        delivery = cli.default_delivery("git", "loop-x")
        self.assertEqual(delivery["mode"], "git")
        self.assertEqual(delivery["branch"], "absoloop/loop-x")

    def test_out_delivery_points_at_home(self):
        delivery = cli.default_delivery("out", "loop-x")
        self.assertIn("loop-x", delivery["out_dir"])


if __name__ == "__main__":
    unittest.main()
