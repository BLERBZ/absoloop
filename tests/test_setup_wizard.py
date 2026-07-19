"""Setup wizard — guided first-run onboarding."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import setup_wizard as sw


class SetupState(unittest.TestCase):
    def test_mark_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "setup.json"
            with mock.patch.object(sw, "SETUP_STATE", path):
                self.assertFalse(sw.is_setup_complete())
                result = sw.SetupResult(
                    completed=True, path_linked=True,
                    providers_ready=["claude"])
                written = sw.mark_setup_complete(result)
                self.assertTrue(written.is_file())
                self.assertTrue(sw.is_setup_complete())
                data = json.loads(written.read_text(encoding="utf-8"))
                self.assertEqual(data["providers_ready"], ["claude"])
                sw.reset_setup_state()
                self.assertFalse(sw.is_setup_complete())


class SetupCommandFlags(unittest.TestCase):
    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "setup.json"
            with mock.patch.object(sw, "SETUP_STATE", path):
                self.assertEqual(sw.setup_command(["--check"]), 1)
                sw.mark_setup_complete(sw.SetupResult(completed=True))
                self.assertEqual(sw.setup_command(["--check"]), 0)

    def test_yes_runs_noninteractive(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / "bin").mkdir()
            (home / "bin" / "absoloop").write_text("#!/usr/bin/env python3\n",
                                                   encoding="utf-8")
            (home / "absoloop_harness").mkdir()
            state = home / "setup.json"
            user_cfg_dir = home / "userconfig"
            # Run inside the temp dir so gitignore step cannot touch the repo.
            project = home / "proj"
            project.mkdir()
            (project / ".git").mkdir()
            with mock.patch.object(sw, "SETUP_STATE", state), \
                 mock.patch.object(sw, "tooling_home", return_value=home), \
                 mock.patch.object(sw, "_probe_providers",
                                   return_value=[("claude", "/bin/claude",
                                                  "ok")]), \
                 mock.patch.object(sw.pathlib.Path, "home",
                                   return_value=user_cfg_dir):
                # Avoid real symlink into the developer's ~/.local/bin
                with mock.patch.object(sw, "_ensure_path_link",
                                       return_value=(True, "linked (test)")):
                    old = pathlib.Path.cwd()
                    try:
                        import os
                        os.chdir(project)
                        code = sw.setup_command(["-y", "--force"])
                    finally:
                        os.chdir(old)
            self.assertIn(code, (0, 2))
            self.assertTrue(state.is_file())
            self.assertTrue((project / ".gitignore").is_file())
            self.assertIn(
                ".absoloop/",
                (project / ".gitignore").read_text(encoding="utf-8"),
            )


class WizardSteps(unittest.TestCase):
    def test_write_user_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            with mock.patch.object(sw.pathlib.Path, "home", return_value=home):
                path = sw._write_user_defaults("local")
            self.assertTrue(path.is_file())
            body = path.read_text(encoding="utf-8")
            self.assertIn("[shortcuts]", body)
            self.assertIn("absoloop setup", body)


class FirstRunGate(unittest.TestCase):
    def test_should_offer_respects_env(self):
        with mock.patch.dict("os.environ", {"ABSOLOOP_SKIP_SETUP": "1"}):
            self.assertFalse(sw.should_offer_first_run())


if __name__ == "__main__":
    unittest.main()
