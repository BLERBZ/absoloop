"""Shortcuts: chords, bindings, dispatch, Micro export."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import shortcuts as sc


class ChordNormalize(unittest.TestCase):
    def test_order_and_aliases(self):
        self.assertEqual(sc.normalize_chord("Alt+Ctrl+S"), "ctrl+alt+s")
        self.assertEqual(sc.normalize_chord("cmd+shift+enter"), "cmd+shift+enter")
        self.assertEqual(sc.normalize_chord("F13"), "f13")
        self.assertEqual(sc.normalize_chord("return"), "enter")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            sc.normalize_chord("")


class ActionForChord(unittest.TestCase):
    def test_default_f_keys(self):
        cfg = sc.ShortcutConfig(bindings=dict(sc.DEFAULT_BINDINGS))
        self.assertEqual(cfg.action_for_chord("f13"), "status")
        self.assertEqual(cfg.action_for_chord("F17"), "approve")

    def test_override_and_unbind(self):
        bindings = dict(sc.DEFAULT_BINDINGS)
        bindings["status"] = "ctrl+alt+s"
        bindings["watch"] = ""
        cfg = sc.ShortcutConfig(bindings=bindings)
        self.assertEqual(cfg.action_for_chord("ctrl+alt+s"), "status")
        self.assertIsNone(cfg.action_for_chord("f14"))  # unbound


class LoadConfig(unittest.TestCase):
    def test_project_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "absoloop.toml").write_text(
                '[shortcuts]\nstatus = "ctrl+alt+s"\nenabled = true\n',
                encoding="utf-8")
            cfg = sc.load_shortcuts(root)
            self.assertEqual(cfg.chord_for("status"), "ctrl+alt+s")
            self.assertEqual(cfg.chord_for("watch"), "f14")


class Export(unittest.TestCase):
    def test_json_has_micro_layers(self):
        cfg = sc.ShortcutConfig(bindings=dict(sc.DEFAULT_BINDINGS))
        payload = json.loads(sc.export_bundle(cfg, "json"))
        self.assertEqual(payload["device"], "work-louder-codex-micro")
        self.assertEqual(len(payload["layers"]["mission"]), 13)
        self.assertIn("status", payload["actions"])

    def test_input_recipe_mentions_layers(self):
        cfg = sc.ShortcutConfig(bindings=dict(sc.DEFAULT_BINDINGS))
        body = sc.export_bundle(cfg, "input")
        self.assertIn("Layer 0", body)
        self.assertIn("absoloop do", body)
        self.assertIn("f13", body)


class Layout(unittest.TestCase):
    def test_layout_lists_thirteen_keys(self):
        cfg = sc.ShortcutConfig(bindings=dict(sc.DEFAULT_BINDINGS))
        text = sc.render_layout(cfg, "mission")
        self.assertIn("K13", text)
        self.assertIn("status", text)


class RunAction(unittest.TestCase):
    def test_unknown_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = sc.run_action("not-a-real-action", cwd=pathlib.Path(tmp))
            self.assertEqual(code, 2)

    def test_dispatch_invokes_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch("absoloop_harness.shortcuts.subprocess.run") as run:
                run.return_value = mock.Mock(returncode=0)
                with mock.patch("absoloop_harness.shortcuts.absoloop_bin",
                                return_value=["absoloop"]):
                    code = sc.run_action("status", cwd=root, yes=True)
            self.assertEqual(code, 0)
            cmd = run.call_args[0][0]
            self.assertEqual(cmd[-1], "status")


class DoCommand(unittest.TestCase):
    def test_do_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("absoloop_harness.shortcuts.run_action",
                            return_value=0) as ra:
                code = sc.do_command(["status"], cwd=pathlib.Path(tmp))
            self.assertEqual(code, 0)
            ra.assert_called_once()
            self.assertEqual(ra.call_args[0][0], "status")


class LineProtocol(unittest.TestCase):
    def test_action_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cfg = sc.load_shortcuts(root)
            with mock.patch("absoloop_harness.shortcuts.run_action",
                            return_value=0) as ra:
                code = sc._dispatch_chord_or_action(root, cfg, "action:doctor")
            self.assertEqual(code, 0)
            self.assertEqual(ra.call_args[0][0], "doctor")

    def test_chord_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cfg = sc.load_shortcuts(root)
            with mock.patch("absoloop_harness.shortcuts.run_action",
                            return_value=0) as ra:
                code = sc._dispatch_chord_or_action(root, cfg, "chord:f13")
            self.assertEqual(code, 0)
            self.assertEqual(ra.call_args[0][0], "status")


if __name__ == "__main__":
    unittest.main()
