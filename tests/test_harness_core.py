"""Core types, redaction, and configuration precedence."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import toml_lite
from absoloop_harness.config import load_config
from absoloop_harness.core import (AgentEvent, AgentRequest, EventType,
                                   redact_env, redact_event, redact_text,
                                   secret_values, REDACTED)


class Redaction(unittest.TestCase):
    def test_xai_key_redacted(self):
        self.assertNotIn("xai-abcdefgh12345678",
                         redact_text("key: xai-abcdefgh12345678"))

    def test_openai_style_key_redacted(self):
        self.assertIn(REDACTED, redact_text("sk-proj-abcdef1234567890"))

    def test_github_token_redacted(self):
        self.assertIn(REDACTED, redact_text("ghp_" + "a" * 20))

    def test_bearer_header_redacted(self):
        self.assertIn(REDACTED, redact_text("Authorization: Bearer abcdefghijklmnop123"))

    def test_private_key_block_redacted(self):
        blob = "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----"
        self.assertEqual(redact_text(blob), REDACTED)

    def test_known_values_redacted(self):
        self.assertEqual(redact_text("token hunter2secret", ["hunter2secret"]),
                         f"token {REDACTED}")

    def test_plain_text_untouched(self):
        self.assertEqual(redact_text("fix the tests"), "fix the tests")

    def test_env_secret_names(self):
        env = {"MY_API_KEY": "v1", "GITHUB_TOKEN": "v2", "PATH": "/bin"}
        redacted = redact_env(env)
        self.assertEqual(redacted["MY_API_KEY"], REDACTED)
        self.assertEqual(redacted["GITHUB_TOKEN"], REDACTED)
        self.assertEqual(redacted["PATH"], "/bin")
        self.assertEqual(sorted(secret_values(env)), ["v1", "v2"])

    def test_event_redaction_recurses(self):
        event = AgentEvent(type=EventType.UNKNOWN, provider="grok",
                           text="key xai-abcdefgh12345678",
                           data={"nested": {"api_key": "boom",
                                            "note": ["xai-abcdefgh12345678"]}})
        redact_event(event)
        self.assertNotIn("xai-abcdefgh12345678", event.text)
        self.assertEqual(event.data["nested"]["api_key"], REDACTED)
        self.assertEqual(event.data["nested"]["note"], [REDACTED])


class RequestHashing(unittest.TestCase):
    def test_prompt_hash_stable(self):
        a = AgentRequest(prompt="do it", cwd=".")
        b = AgentRequest(prompt="do it", cwd="/elsewhere")
        self.assertEqual(a.prompt_hash(), b.prompt_hash())


class TomlLite(unittest.TestCase):
    def test_basic_document(self):
        doc = toml_lite.loads(
            '# comment\n[providers.grok]\ncommand = "grok"  # inline\n'
            'timeout_seconds = 900\nenabled = true\n'
            '[gates]\nrequired = ["tests", "lint"]\n')
        self.assertEqual(doc["providers"]["grok"]["command"], "grok")
        self.assertEqual(doc["providers"]["grok"]["timeout_seconds"], 900)
        self.assertTrue(doc["providers"]["grok"]["enabled"])
        self.assertEqual(doc["gates"]["required"], ["tests", "lint"])

    def test_bad_value_raises(self):
        with self.assertRaises(toml_lite.TomlError):
            toml_lite.loads("key = {inline_table = 1}")


class ConfigPrecedence(unittest.TestCase):
    def test_defaults_and_project_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "absoloop.toml").write_text(
                '[providers.grok]\ncommand = "/custom/grok"\n'
                '[permissions]\ndefault_profile = "read"\n', encoding="utf-8")
            cfg = load_config(root)
            self.assertEqual(cfg.get("providers", "grok", "command"), "/custom/grok")
            self.assertEqual(cfg.source("providers", "grok", "command"), "project")
            # untouched values remain defaults
            self.assertEqual(cfg.get("providers", "claude", "command"), "claude")
            self.assertEqual(cfg.source("providers", "claude", "command"), "default")
            self.assertEqual(cfg.get("permissions", "default_profile"), "read")

    def test_cli_overrides_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "absoloop.toml").write_text(
                '[permissions]\ndefault_profile = "read"\n', encoding="utf-8")
            cfg = load_config(root, {"permissions": {"default_profile": "full"}})
            self.assertEqual(cfg.get("permissions", "default_profile"), "full")
            self.assertEqual(cfg.source("permissions", "default_profile"), "cli")

    def test_flat_lists_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(pathlib.Path(tmp))
            rows = {key: source for key, _value, source in cfg.flat()}
            self.assertEqual(rows["workflows.planner"], "default")


if __name__ == "__main__":
    unittest.main()
