import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from watcher.config import Config
from watcher.qq_diagnostic import run_requested_diagnostic
from watcher.state import StateStore


class QQDiagnostic(unittest.TestCase):
    def test_only_once_even_if_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(state_file=Path(d) / 'state.json', pushplus_token='fake', pushplus_qq_option='fake')
            StateStore(cfg.state_file).save()
            with patch('watcher.qq_diagnostic._send_qq', return_value=(False, 'code 905')) as send:
                self.assertFalse(run_requested_diagnostic(cfg))
                self.assertTrue(run_requested_diagnostic(cfg))
                send.assert_called_once()
                self.assertNotIn('http', send.call_args.args[1] + send.call_args.args[2])

    def test_missing_credentials_never_requests(self):
        with patch('watcher.qq_diagnostic._send_qq') as send:
            self.assertFalse(run_requested_diagnostic(Config()))
            send.assert_not_called()

    def test_diagnostic_does_not_create_initial_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(state_file=Path(d) / 'state.json', pushplus_token='fake', pushplus_qq_option='fake')
            with patch('watcher.qq_diagnostic._send_qq') as send:
                self.assertTrue(run_requested_diagnostic(cfg))
                send.assert_not_called()
                self.assertFalse(cfg.state_file.exists())
