#!/usr/bin/env python3
"""Local launchd fallback: only dispatches the existing GitHub watcher."""
import fcntl
import json
import os
import subprocess
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = 'owenfff/tibo-watcher'
WORKFLOW = 'monitor.yml'
GH = os.environ.get('GH_BIN') or shutil.which('gh') or 'gh'
RUNTIME = Path.home() / 'Library' / 'Application Support' / 'tibo-watcher'
BEIJING = timezone(timedelta(hours=8))


def log(event, **details):
    print(json.dumps(dict(time=datetime.now(BEIJING).isoformat(timespec='seconds'),
                          event=event, **details), ensure_ascii=False), flush=True)


def gh(*args):
    proc = subprocess.run([GH, *args], capture_output=True, text=True, timeout=40)
    if proc.returncode:
        raise RuntimeError('GitHub CLI request failed (exit %d)' % proc.returncode)
    return proc.stdout


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def check():
    data = json.loads(gh('api', 'repos/%s/actions/workflows/%s/runs?per_page=10' % (REPO, WORKFLOW)))
    now = datetime.now(timezone.utc)
    for run in data['workflow_runs']:
        if (run['status'] in ('queued', 'in_progress', 'waiting', 'pending')
                and (now - stamp(run['created_at'])).total_seconds() < 720):
            log('skip_active_run', run_id=run['id'])
            return
    successes = [r for r in data['workflow_runs'] if r.get('conclusion') == 'success']
    if successes:
        last = max(successes, key=lambda r: r['updated_at'])
        age = (now - stamp(last['updated_at'])).total_seconds()
        if age < 540:
            log('skip_recent_success', run_id=last['id'], age_seconds=int(age))
            return
    # The workflow's concurrency group and shared original-post IDs prevent replay.
    gh('workflow', 'run', WORKFLOW, '--repo', REPO, '--ref', 'master')
    log('dispatched', repository=REPO, workflow=WORKFLOW)


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / 'dispatch.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('skip_locked')
            return 0
        try:
            check()
            return 0
        except Exception as error:
            # Do not log CLI output, credentials, or arbitrary server responses.
            log('dispatch_failed', error_type=type(error).__name__)
            return 1


if __name__ == '__main__':
    sys.exit(main())
