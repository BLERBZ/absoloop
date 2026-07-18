"""Codex --output-schema must satisfy OpenAI Structured Outputs strict mode.

OpenAI rejects schemas missing `additionalProperties: false` on every object
node (HTTP 400 invalid_json_schema / codex_output_schema).
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests._load import load_cli, load_runner


def _assert_openai_strict(testcase: unittest.TestCase, schema: dict) -> None:
    """Recursively assert OpenAI strict-mode rules on a schema dict."""

    def walk(node, path: str) -> None:
        if not isinstance(node, dict):
            return
        is_object = node.get("type") == "object" or "properties" in node
        if is_object:
            testcase.assertIn(
                "additionalProperties", node,
                f"{path}: object missing additionalProperties",
            )
            testcase.assertIs(
                node["additionalProperties"], False,
                f"{path}: additionalProperties must be false",
            )
            props = node.get("properties") or {}
            if props:
                required = node.get("required") or []
                testcase.assertEqual(
                    set(required), set(props),
                    f"{path}: every property must be required for OpenAI strict mode",
                )
                for key, child in props.items():
                    walk(child, f"{path}.properties.{key}")
        if "items" in node:
            walk(node["items"], f"{path}.items")
        for key in ("anyOf", "oneOf", "allOf"):
            for i, child in enumerate(node.get(key) or []):
                walk(child, f"{path}.{key}[{i}]")

    walk(schema, "root")


class ResultSchemaStrict(unittest.TestCase):
    def test_canonical_result_schema_is_openai_strict(self):
        cli = load_cli()
        _assert_openai_strict(self, cli.RESULT_SCHEMA)

    def test_critic_schema_is_openai_strict(self):
        run = load_runner()
        _assert_openai_strict(self, run.CRITIC_SCHEMA)


class NormalizeHelper(unittest.TestCase):
    def test_injects_additional_properties_false(self):
        run = load_runner()
        loose = {
            "type": "object",
            "properties": {
                "done": {"type": "boolean"},
                "nested": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                },
            },
            "required": ["done"],
        }
        strict = run.openai_strict_json_schema(loose)
        _assert_openai_strict(self, strict)
        # Original left untouched.
        self.assertNotIn("additionalProperties", loose)

    def test_normalizes_stale_agent_result_shape(self):
        """Mirrors the pre-fix RESULT_SCHEMA that triggered the Codex 400."""
        run = load_runner()
        stale = {
            "type": "object",
            "properties": {
                "done": {"type": "boolean"},
                "summary": {"type": "string"},
                "changed_artifacts": {"type": "array", "items": {"type": "string"}},
                "commands_run": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["done", "summary", "changed_artifacts", "risks"],
        }
        _assert_openai_strict(self, run.openai_strict_json_schema(stale))

    def test_does_not_mutate_input(self):
        run = load_runner()
        original = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
        }
        snapshot = copy.deepcopy(original)
        run.openai_strict_json_schema(original)
        self.assertEqual(original, snapshot)


class SyncResultSchema(unittest.TestCase):
    def test_rewrites_stale_on_disk_schema(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            schema_path = target / ".absoloop" / "schemas" / "agent-result.schema.json"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_text(json.dumps({
                "type": "object",
                "properties": {"done": {"type": "boolean"}},
                "required": ["done"],
            }), encoding="utf-8")
            cli.sync_result_schema(target)
            on_disk = json.loads(schema_path.read_text(encoding="utf-8"))
            _assert_openai_strict(self, on_disk)
            self.assertEqual(on_disk, cli.RESULT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
