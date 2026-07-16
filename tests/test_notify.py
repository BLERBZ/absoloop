"""Minimal chime / banner notify helpers."""
from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import notify


class NotifyEnabled(unittest.TestCase):
    def test_disabled_by_env(self):
        with mock.patch.dict(os.environ, {"ABSOLOOP_CHIME": "0"}):
            self.assertFalse(notify.enabled())
        with mock.patch.dict(os.environ, {"ABSOLOOP_CHIME": "1"}):
            self.assertTrue(notify.enabled())

    def test_ci_defaults_off_without_explicit_flag(self):
        env = {k: v for k, v in os.environ.items() if k != "ABSOLOOP_CHIME"}
        env["CI"] = "true"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(notify.enabled())

    def test_kind_for_status(self):
        self.assertEqual(notify.kind_for_status("AWAITING_APPROVAL"), "attention")
        self.assertEqual(notify.kind_for_status("COMPLETED"), "done")
        self.assertEqual(notify.kind_for_status("BLOCKED"), "fail")

    def test_notify_noop_when_disabled(self):
        with mock.patch.dict(os.environ, {"ABSOLOOP_CHIME": "off"}):
            with mock.patch.object(notify, "_chime") as chime:
                with mock.patch.object(notify, "_banner") as banner:
                    notify.notify("t", "b", kind="attention")
                    chime.assert_not_called()
                    banner.assert_not_called()

    def test_notify_calls_chime_and_banner(self):
        with mock.patch.dict(os.environ, {"ABSOLOOP_CHIME": "1"}):
            with mock.patch.object(notify, "_chime") as chime:
                with mock.patch.object(notify, "_banner") as banner:
                    notify.notify_mission("AWAITING_APPROVAL", mission_id="ABS-1")
                    chime.assert_called_once_with("attention")
                    banner.assert_called_once()
                    self.assertIn("approval", banner.call_args[0][0].lower())


if __name__ == "__main__":
    unittest.main()
