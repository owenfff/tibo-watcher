import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fallback', Path(__file__).parents[1] / 'scripts' / 'dispatch_fallback.py')
fallback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fallback)


class Fallback(unittest.TestCase):
    def run_case(self, status, conclusion, age, expected):
        date = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
        run = dict(id=123, status=status, conclusion=conclusion, created_at=date, updated_at=date)
        with patch.object(fallback, 'gh', side_effect=[json.dumps({'workflow_runs': [run]}), '']) as gh:
            fallback.check()
            self.assertEqual(gh.call_count, expected)
            if expected == 2:
                self.assertEqual(gh.call_args.args, ('workflow', 'run', 'monitor.yml', '--repo', 'owenfff/tibo-watcher', '--ref', 'master'))

    def test_healthy_cloud_run_is_not_duplicated(self):
        self.run_case('completed', 'success', 60, 1)

    def test_active_run_is_not_duplicated(self):
        self.run_case('in_progress', None, 60, 1)

    def test_stale_success_gets_dispatched(self):
        self.run_case('completed', 'success', 900, 2)

    def test_failed_cycle_gets_dispatched(self):
        self.run_case('completed', 'failure', 900, 2)
