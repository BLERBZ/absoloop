"""Web Mission Briefing (browser Launch modal) — CLI-side handshake."""
from __future__ import annotations

import pathlib
import unittest
from unittest import mock

from tests._load import load_cli

cli = load_cli()

from absoloop_harness import briefing as ux  # noqa: E402


def _brief(**overrides) -> ux.Briefing:
    target = pathlib.Path.cwd().resolve()
    defaults = dict(
        target=str(target),
        target_name=".",
        adopting=True,
        objective="",
        delivery="local",
        engine="claude",
        model="best",
        kinds=["general"],
        engines_available=("claude",),
    )
    defaults.update(overrides)
    return ux.Briefing(**defaults)


def _zcomb_mod(outcome: dict, begin_ok: bool = True) -> mock.Mock:
    zc = mock.Mock()
    zc.DEFAULT_PORT = 3141
    zc.settings_catalog.return_value = {"engines": [
        {"id": "claude", "label": "Claude", "available": True, "models": []},
    ]}
    zc.begin_web_briefing.return_value = (
        pathlib.Path("/tmp/fake-state") if begin_ok else None)
    zc.wait_for_web_briefing.return_value = outcome
    return zc


class WebBriefingCliTests(unittest.TestCase):
    def test_submission_maps_to_confirmed_briefing(self):
        zc = _zcomb_mod({
            "status": "submitted",
            "submission": {
                "objective": "Fix the failing tests",
                "projectName": "my-mission",
                "engine": "claude",
                "model": "opus",
                "delivery": "git",
            },
        })
        status, confirmed = cli.web_briefing(_brief(), ux, zc)
        self.assertEqual(status, "launch")
        self.assertEqual(confirmed.objective, "Fix the failing tests")
        self.assertEqual(confirmed.engine, "claude")
        self.assertEqual(confirmed.model, "opus")
        self.assertEqual(confirmed.delivery, "git")
        self.assertEqual(confirmed.target_name, "my-mission")
        self.assertEqual(pathlib.Path(confirmed.target),
                         (pathlib.Path.cwd() / "my-mission").resolve())
        self.assertIn("tests", confirmed.kinds)
        zc.mark_launch_status.assert_called_once_with(
            pathlib.Path("/tmp/fake-state"), "launched")

    def test_bogus_engine_and_delivery_fall_back_to_request_defaults(self):
        zc = _zcomb_mod({
            "status": "submitted",
            "submission": {
                "objective": "Ship it",
                "projectName": ".",
                "engine": "not-an-engine",
                "delivery": "not-a-mode",
            },
        })
        status, confirmed = cli.web_briefing(_brief(), ux, zc)
        self.assertEqual(status, "launch")
        self.assertEqual(confirmed.engine, "claude")
        self.assertEqual(confirmed.delivery, "local")

    def test_cancelled_aborts(self):
        zc = _zcomb_mod({"status": "cancelled"})
        status, confirmed = cli.web_briefing(_brief(), ux, zc)
        self.assertEqual(status, "abort")
        self.assertIsNone(confirmed)

    def test_dashboard_failure_falls_back_to_terminal(self):
        zc = _zcomb_mod({}, begin_ok=False)
        status, confirmed = cli.web_briefing(_brief(), ux, zc)
        self.assertEqual(status, "fallback")
        self.assertIsNone(confirmed)

    def test_begin_exception_falls_back_to_terminal(self):
        zc = _zcomb_mod({})
        zc.begin_web_briefing.side_effect = RuntimeError("no node")
        status, confirmed = cli.web_briefing(_brief(), ux, zc)
        self.assertEqual(status, "fallback")
        self.assertIsNone(confirmed)

    def test_empty_objective_submission_falls_back(self):
        zc = _zcomb_mod({"status": "submitted",
                         "submission": {"objective": "   "}})
        status, confirmed = cli.web_briefing(_brief(), ux, zc)
        self.assertEqual(status, "fallback")
        self.assertIsNone(confirmed)
        zc.mark_launch_status.assert_called_once()
        self.assertEqual(zc.mark_launch_status.call_args[0][1], "error")


if __name__ == "__main__":
    unittest.main()
