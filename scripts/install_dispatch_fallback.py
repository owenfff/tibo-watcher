#!/usr/bin/env python3
"""Install the macOS ten-minute fallback for this repository's GitHub workflow."""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = 'com.owenfff.tibo-watcher-dispatch'


def main():
    if sys.platform != 'darwin':
        raise SystemExit('This optional fallback installer requires macOS.')
    gh = shutil.which('gh')
    if not gh or subprocess.run([gh, 'auth', 'status'], capture_output=True).returncode:
        raise SystemExit('Install GitHub CLI and sign in before installing this fallback.')
    runtime = Path.home() / 'Library' / 'Application Support' / 'tibo-watcher'
    runtime.mkdir(parents=True, exist_ok=True)
    script = runtime / 'dispatch_fallback.py'
    shutil.copy2(Path(__file__).with_name('dispatch_fallback.py'), script)
    agents = Path.home() / 'Library' / 'LaunchAgents'
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / (LABEL + '.plist')
    settings = dict(Label=LABEL, ProgramArguments=[sys.executable, str(script)],
                    WorkingDirectory=str(runtime), RunAtLoad=True, StartInterval=600,
                    EnvironmentVariables={'GH_BIN':gh, 'PATH':os.defpath + os.pathsep + str(Path(gh).parent)},
                    StandardOutPath=str(runtime / 'dispatch.log'),
                    StandardErrorPath=str(runtime / 'dispatch-errors.log'), ProcessType='Background')
    domain = 'gui/%d' % os.getuid()
    service = domain + '/' + LABEL
    loaded = subprocess.run(['launchctl', 'print', service], capture_output=True).returncode == 0
    if loaded:
        subprocess.run(['launchctl', 'bootout', service], check=True)
    plist.write_bytes(plistlib.dumps(settings))
    plist.chmod(0o600)
    subprocess.run(['launchctl', 'bootstrap', domain, str(plist)], check=True)
    print('Installed ten-minute GitHub dispatch fallback. Mac must be awake, signed in and online.')


if __name__ == '__main__':
    main()
