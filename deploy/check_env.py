import os
import sys

missing = [k for k in ('PUSHPLUS_TOKEN', 'PUSHPLUS_QQ_OPTION') if not os.environ.get(k)]
if missing:
    print('Missing required configuration: ' + ', '.join(missing), file=sys.stderr)
    sys.exit(1)
