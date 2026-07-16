"""Absoloop schedule: cron math, config IO, tick skip/fire."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import schedule as sched


class CronParse(unittest.TestCase):
    def test_friday_midnight(self):
        expr = sched.CronExpr.parse("0 0 * * 5")
        # 2026-07-17 is a Friday
        fri = datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(expr.matches(fri.astimezone(
            __import__("zoneinfo").ZoneInfo("UTC"))))
        thu = datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(expr.matches(thu))

    def test_ranges_and_steps(self):
        expr = sched.CronExpr.parse("*/15 9-17 * * 1-5")
        self.assertIn(0, expr.minute)
        self.assertIn(15, expr.minute)
        self.assertIn(9, expr.hour)
        self.assertIn(17, expr.hour)
        self.assertEqual(expr.weekday, (1, 2, 3, 4, 5))

    def test_rejects_bad_field_count(self):
        with self.assertRaises(ValueError):
            sched.CronExpr.parse("0 0 * *")


class NextCronFire(unittest.TestCase):
    def test_next_friday(self):
        expr = sched.CronExpr.parse("0 0 * * 5")
        # Thursday Jul 16 2026 10:00 UTC
        after = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)
        nxt = sched.next_cron_fire(expr, after, tz_name="UTC")
        self.assertEqual(nxt.weekday(), 4)  # Friday
        self.assertEqual((nxt.hour, nxt.minute), (0, 0))


class EveryParse(unittest.TestCase):
    def test_units(self):
        self.assertEqual(sched.parse_every("6h"), 6 * 3600)
        self.assertEqual(sched.parse_every("1d"), 86400)
        self.assertEqual(sched.parse_every("30m"), 1800)

    def test_min_60s(self):
        with self.assertRaises(ValueError):
            sched.parse_every("30s")


class ScheduleIO(unittest.TestCase):
    def test_roundtrip_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            s = sched.Schedule(
                id="friday-rotate",
                kind="cron",
                expr="0 0 * * 5",
                timezone="America/New_York",
                action="extend",
                note="next Freebie",
                hours=24,
                iterations=50,
                budget=150.0,
                require_status=["COMPLETED", "BUDGET_EXHAUSTED"],
            )
            path = sched.save_schedule(root, s)
            loaded = sched.load_schedule_file(path)
            self.assertEqual(loaded.id, "friday-rotate")
            self.assertEqual(loaded.expr, "0 0 * * 5")
            self.assertEqual(loaded.timezone, "America/New_York")
            self.assertEqual(loaded.action, "extend")
            self.assertEqual(loaded.hours, 24)
            self.assertEqual(loaded.require_status,
                             ["COMPLETED", "BUDGET_EXHAUSTED"])

    def test_list_and_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            s = sched.Schedule(id="seg", kind="interval",
                               interval_seconds=3600, action="resume")
            sched.save_schedule(root, s)
            rows = sched.list_schedules(root)
            self.assertEqual(len(rows), 1)
            rows[0].enabled = False
            sched.save_schedule(root, rows[0])
            self.assertFalse(sched.list_schedules(root)[0].enabled)


class DueAndTick(unittest.TestCase):
    def test_cron_due_and_skip_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            abs_dir = root / ".absoloop"
            abs_dir.mkdir(parents=True)
            (abs_dir / "state.json").write_text(
                json.dumps({"status": "COMPLETED", "mission_id": "m"}),
                encoding="utf-8")
            s = sched.Schedule(
                id="fri", kind="cron", expr="0 0 * * 5",
                timezone="UTC", action="extend", note="go",
                require_status=["COMPLETED"],
            )
            sched.save_schedule(root, s)
            # Friday midnight UTC
            now = datetime(2026, 7, 17, 0, 0, 30, tzinfo=timezone.utc)
            due = sched.due_schedules(root, now=now)
            self.assertEqual(len(due), 1)

            with mock.patch.object(sched, "mission_is_busy", return_value=True):
                result, code = sched.fire_schedule(s, root, dry_run=False)
            self.assertEqual(result, "skipped_busy")
            self.assertEqual(code, 0)

    def test_dry_run_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            abs_dir = root / ".absoloop"
            abs_dir.mkdir(parents=True)
            (abs_dir / "state.json").write_text(
                json.dumps({"status": "READY", "mission_id": "m"}),
                encoding="utf-8")
            s = sched.Schedule(id="seg", kind="interval",
                               interval_seconds=3600, action="resume")
            with mock.patch.object(sched, "mission_is_busy", return_value=False):
                result, code = sched.fire_schedule(s, root, dry_run=True)
            self.assertEqual(result, "dry_run")
            self.assertEqual(code, 0)

    def test_skip_awaiting_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            abs_dir = root / ".absoloop"
            abs_dir.mkdir(parents=True)
            (abs_dir / "state.json").write_text(
                json.dumps({"status": "AWAITING_APPROVAL"}),
                encoding="utf-8")
            s = sched.Schedule(id="x", kind="interval",
                               interval_seconds=3600, action="resume")
            result, code = sched.fire_schedule(s, root)
            self.assertEqual(result, "skipped_gate")
            self.assertEqual(code, 3)

    def test_cli_add_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            code = sched.schedule_command([
                "add", "--id", "nightly", "--cron", "0 2 * * *",
                "--tz", "UTC", "--action", "extend", "-m", "verify",
                "-C", str(root),
            ], cwd=root)
            self.assertEqual(code, 0)
            code = sched.schedule_command(["list", "-C", str(root)], cwd=root)
            self.assertEqual(code, 0)
            code = sched.schedule_command(
                ["tick", "--dry-run", "-C", str(root)], cwd=root)
            self.assertEqual(code, 0)


class BuildArgv(unittest.TestCase):
    def test_extend_argv(self):
        s = sched.Schedule(
            id="f", kind="cron", expr="0 0 * * 5", action="extend",
            note="next game", hours=24, iterations=40, budget=100,
            engine="claude",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            argv = sched.build_fire_argv(s, root)
        self.assertIn("--extend", argv)
        self.assertIn("-m", argv)
        self.assertIn("next game", argv)
        self.assertIn("--hours", argv)
        self.assertIn("24", argv)


if __name__ == "__main__":
    unittest.main()
