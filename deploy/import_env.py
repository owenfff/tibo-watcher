#!/usr/bin/python3
"""Forced-command bootstrap: import two secrets, never execute client commands."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

if os.geteuid() != 0:
    raise SystemExit('root required')
raw = sys.stdin.buffer.read(4097)
if len(raw) > 4096:
    raise SystemExit('configuration too large')
data = json.loads(raw)
keys = ('PUSHPLUS_TOKEN', 'PUSHPLUS_QQ_OPTION')
if set(data) != set(keys):
    raise SystemExit('unexpected fields')
for key in keys:
    if not isinstance(data[key], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', data[key]):
        raise SystemExit('invalid configuration format')
path = Path('/etc/tibo-watcher.env')
fd, temp = tempfile.mkstemp(prefix='.tibo-watcher-', dir='/etc')
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(''.join(key + '=' + data[key] + '\n' for key in keys))
        handle.write('QQ_AUTO_TRANSLATE=1\n')
    os.replace(temp, path)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
print('QQ configuration imported; values are not printed')
