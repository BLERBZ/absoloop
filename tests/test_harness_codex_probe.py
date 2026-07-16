"""Codex version probing and resume argv variance."""
from __future__ import annotations

import pathlib
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness.core import AgentRequest, SessionRef
from absoloop_harness.providers.codex import CodexAdapter

FAKE = pathlib.Path(__file__).resolve().parent / "fakes" / "fake_provider.py"


class CodexVersionProbe(unittest.TestCase):
    def test_version_from_fake(self):
        FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)
        adapter = CodexAdapter({"command": str(FAKE)})
        probe = adapter.probe()
        self.assertTrue(probe.available)
        self.assertEqual(probe.info.version, "9.9.9")


class CodexResumeStyles(unittest.TestCase):
    def _request(self):
        return AgentRequest(prompt="continue", cwd="/tmp/work",
                            permission_profile="edit")

    def test_default_exec_resume_shape(self):
        FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)
        adapter = CodexAdapter({"command": str(FAKE),
                                "resume_style": "exec-resume"})
        with tempfile.TemporaryDirectory() as tmp:
            argv, stdin = adapter.build_argv(
                self._request(), SessionRef("codex", "thread-1"),
                pathlib.Path(tmp))
        self.assertEqual(argv[1:4], ["exec", "resume", "thread-1"])
        self.assertIn("--json", argv)
        self.assertIn("--sandbox", argv)
        self.assertEqual(argv[-1], "-")
        self.assertEqual(stdin, "continue")

    def test_flags_then_resume_shape(self):
        adapter = CodexAdapter({"command": str(FAKE),
                                "resume_style": "exec-flags-then-resume"})
        with tempfile.TemporaryDirectory() as tmp:
            argv, _ = adapter.build_argv(
                self._request(), SessionRef("codex", "thread-1"),
                pathlib.Path(tmp))
        self.assertEqual(argv[1], "exec")
        self.assertLess(argv.index("--json"), argv.index("resume"))
        self.assertEqual(argv[argv.index("resume") + 1], "thread-1")

    def test_configured_style_survives_probe(self):
        FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)
        adapter = CodexAdapter({"command": str(FAKE),
                                "resume_style": "exec-flags-then-resume"})
        adapter.probe()
        self.assertEqual(adapter.config["resume_style"],
                         "exec-flags-then-resume")


if __name__ == "__main__":
    unittest.main()
