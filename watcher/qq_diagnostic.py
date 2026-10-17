"""One-shot QQ diagnostics requested by a reviewed repository file."""
import json
from datetime import datetime
from pathlib import Path

from .events import BEIJING
from .notify import _send_qq
from .state import StateStore


def run_requested_diagnostic(cfg):
    request = Path(__file__).resolve().parent.parent / 'qq-diagnostic.json'
    if not request.is_file():
        return True
    data = json.loads(request.read_text())
    nonce = data.get('request_id')
    if not isinstance(nonce, str) or not nonce or len(nonce) > 100:
        raise ValueError('invalid QQ diagnostic request')
    if not cfg.pushplus_token or not cfg.pushplus_qq_option:
        print('QQ DIAGNOSTIC: missing PUSHPLUS_TOKEN or PUSHPLUS_QQ_OPTION', flush=True)
        return False
    store = StateStore(cfg.state_file)
    if store.fresh_file:
        print('QQ DIAGNOSTIC: waiting for normal first-run baseline', flush=True)
        return True
    key = 'diagnostic:qq:' + nonce
    if store.is_seen(key):
        return True
    store.mark_seen(key)
    store.save()  # Persist before sending; never repeat an ambiguous request.
    when = datetime.now(BEIJING).strftime('%m-%d %H:%M')
    ok, note = _send_qq(cfg, f'Codex监控通道测试 北京时间{when}',
                        f'状态：通道测试\n北京时间：{when}\n说明：检查QQ推送是否正常，不代表额度重置。\n来源：监控程序')
    print('QQ DIAGNOSTIC: ' + ('OK ' if ok else 'FAILED ') + note, flush=True)
    return ok
