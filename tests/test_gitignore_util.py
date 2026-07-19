"""Tests for Absoloop .gitignore helpers."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import gitignore_util as gi


class GitignoreUtilTests(unittest.TestCase):
    def test_already_ignores_variants(self):
        self.assertTrue(gi.already_ignores_absoloop(".absoloop/\n"))
        self.assertTrue(gi.already_ignores_absoloop("node_modules\n.absoloop\n"))
        self.assertTrue(gi.already_ignores_absoloop("/.absoloop/\n"))
        self.assertFalse(gi.already_ignores_absoloop(".absoloop/tmp/\n"))
        self.assertFalse(gi.already_ignores_absoloop("out/\n"))

    def test_ensure_adds_with_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
            status = gi.ensure_absoloop_gitignore(root, yes=True, ask_user=False)
            self.assertEqual(status, "added")
            body = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".absoloop/", body)
            self.assertIn("Absoloop mission state", body)
            # Idempotent
            self.assertEqual(
                gi.ensure_absoloop_gitignore(root, yes=True, ask_user=False),
                "exists",
            )

    def test_ensure_declined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch.object(gi, "ask", return_value="n"), \
                 mock.patch("sys.stdin.isatty", return_value=True), \
                 mock.patch("sys.stdout.isatty", return_value=True):
                status = gi.ensure_absoloop_gitignore(
                    root, yes=False, ask_user=True)
            self.assertEqual(status, "declined")
            self.assertFalse((root / ".gitignore").is_file())


if __name__ == "__main__":
    unittest.main()
