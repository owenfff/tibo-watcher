from __future__ import annotations

import json
import re
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime

from .config import Config
from .fetch import http_post
from .model import Post
from .translate import add_translation, compact_qq_body
from .daily import classify_daily
from .followups import classify_time_reply
from .plans import classify_plan
from .events import BEIJING, classify_reset, format_qq

SHORT_PREVIEW = 350
LONG_PREVIEW = 1200


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def format_alert(cfg: Config, post: Post, score_total: int, score_hits: str,
                 *, long: bool = False) -> str:
    where = "X @%s" % cfg.handle if post.source == "x" else "Codex changelog"
    when = post.created_at or "unknown time"
    limit = LONG_PREVIEW if long else SHORT_PREVIEW
    kind = "Codex daily update" if classify_daily(post.body) else "Codex product plan" if not classify_reset(post.body) and classify_plan(post.body) else "Codex limits"
    return (
        f"Possible {kind} signal (score {score_total}: {score_hits})\n"
        f"Source: {where} | {when}\n"
        f"{post.url}\n"
        f"---\n"
        f"{_clip(post.body, limit)}"
    )


def format_title(post: Post) -> str:
    kind = "Codex daily updates" if classify_daily(post.body) else "Codex plans" if not classify_reset(post.body) and classify_plan(post.body) else "Codex limits"
    return f"{kind} watch: {_clip(post.title, 80)}"


def _send_ntfy(cfg: Config, title: str, body: str, url: str) -> tuple[bool, str]:
    endpoint = f"{cfg.ntfy_server.rstrip('/')}/{cfg.ntfy_topic}"
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": "high",
        "Tags": "arrow_counter_clockwise",
        "Click": url.encode("utf-8"),
    }
    status, response = http_post(endpoint, body.encode("utf-8"), headers=headers)
    return status == 200, f"ntfy [{status}] {_clip(response, 120)}"


def _send_telegram(cfg: Config, title: str, body: str, url: str) -> tuple[bool, str]:
    endpoint = f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage"
    payload = json.dumps({
        "chat_id": cfg.telegram_chat_id,
        "text": f"*{title}*\n\n{body}",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    status, response = http_post(endpoint, payload,
                                 headers={"Content-Type": "application/json"})
    ok = status == 200 and '"ok":true' in response.replace(" ", "")
    return ok, f"telegram [{status}] {_clip(response, 120)}"


def _send_email(cfg: Config, title: str, body: str) -> tuple[bool, str]:
    message = EmailMessage()
    message["Subject"] = title
    message["From"] = cfg.mail_from or cfg.smtp_user
    message["To"] = cfg.mail_to
    message.set_content(body)
    try:
        if cfg.smtp_port == 465:
            server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=25,
                                      context=ssl.create_default_context())
            with server:
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(message)
        else:
            server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=25)
            with server:
                server.starttls(context=ssl.create_default_context())
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(message)
        return True, "email sent"
    except (smtplib.SMTPException, OSError) as error:
        return False, f"email failed: {error}"


def _send_qq(cfg: Config, title: str, body: str) -> tuple[bool, str]:
    # Never retry an ambiguous response: duplicate group messages are worse
    # than a missed alert. Never log response text (it may echo the token).
    payload = json.dumps({
        "token": cfg.pushplus_token, "title": title, "content": body,
        "channel": "qq", "option": cfg.pushplus_qq_option, "template": "txt",
    }, ensure_ascii=False).encode("utf-8")
    try:
        status, response = http_post(
            "https://www.pushplus.plus/send", payload,
            headers={"Content-Type": "application/json"})
        result = json.loads(response)
        ok = status == 200 and isinstance(result, dict) and result.get("code") == 200
        code = result.get("code") if isinstance(result, dict) else None
        safe_code = str(code) if type(code) is int else "unknown"
        # Classify errors into fixed labels; never copy provider response text.
        reason = "未分类错误"
        msg = result.get("msg", "") if isinstance(result, dict) else ""
        if isinstance(msg, str):
            for words, label in [(("实名",), "需要实名认证"),
                                 (("token", "令牌"), "令牌相关错误"),
                                 (("主动",), "机器人主动消息权限相关错误"),
                                 (("配置", "option"), "QQ渠道配置相关错误"),
                                 (("机器人", "群组", "QQ群"), "QQ机器人或群绑定相关错误"),
                                 (("会员",), "会员权限相关错误"),
                                 (("积分", "余额"), "积分或余额相关错误"),
                                 (("次数", "频率", "受限"), "请求额度或频率相关错误")]:
                if any(word.lower() in msg.lower() for word in words):
                    reason = label
                    break
        if not ok and code == 999 and isinstance(msg, str):
            # Only Chinese error words survive; redact configured values first.
            for secret in (cfg.pushplus_token, cfg.pushplus_qq_option):
                if secret:
                    msg = msg.replace(secret, "")
            detail = re.sub(r"[^\u4e00-\u9fff，。；：！？、（） ]", "", msg)
            detail = " ".join(detail.split())[:120]
            if detail:
                reason += "：" + detail
        return ok, "qq accepted by PushPlus" if ok else f"qq rejected [HTTP {status}, code {safe_code}, {reason}]"
    except (OSError, ValueError):
        return False, "qq request failed (no automatic retry)"


def _isolated(sender, *args) -> tuple[bool, str]:
    try:
        return sender(*args)
    except Exception:
        # Transport errors must not stop delivery to the remaining channels.
        return False, "notification channel transport failed"


def send_alert(cfg: Config, post: Post, score_total: int, score_hits: str) -> list[tuple[bool, str]]:
    title = format_title(post)
    short = format_alert(cfg, post, score_total, score_hits)
    long_form = format_alert(cfg, post, score_total, score_hits, long=True)
    logs = []
    if cfg.ntfy_topic:
        logs.append(_isolated(_send_ntfy, cfg, title, short, post.url))
    if cfg.telegram_token and cfg.telegram_chat_id:
        logs.append(_isolated(_send_telegram, cfg, title, long_form, post.url))
    if cfg.smtp_host and cfg.mail_to:
        logs.append(_isolated(_send_email, cfg, title, long_form))
    if (cfg.pushplus_token and cfg.pushplus_qq_option and post.source == "x"
            and cfg.handle.lower() == "thsottiaux" and not post.is_repost
            and (not post.is_quote or classify_daily(post.body) or classify_time_reply(post))
            and (classify_reset(post.body) or classify_daily(post.body) or classify_plan(post.body) or classify_time_reply(post))):
        qq_title, qq_body = format_qq(post)
        if cfg.qq_auto_translate:
            qq_body = add_translation(qq_body, post.body)
        qq_body = compact_qq_body(qq_body)
        logs.append(_send_qq(cfg, qq_title, qq_body))
    return logs


def send_test(cfg: Config) -> list[tuple[bool, str]]:
    title = "tibo-watcher test ping"
    body = ("If you can read this on your phone, the notification pipeline "
            "works. Real alerts will look similar.")
    logs = []
    if cfg.ntfy_topic:
        logs.append(_send_ntfy(cfg, title, body, "https://x.com/" + cfg.handle))
    if cfg.telegram_token and cfg.telegram_chat_id:
        logs.append(_send_telegram(cfg, title, body, "https://x.com/" + cfg.handle))
    if cfg.smtp_host and cfg.mail_to:
        logs.append(_send_email(cfg, title, body))
    if cfg.pushplus_token and cfg.pushplus_qq_option:
        when = datetime.now(BEIJING).strftime("%m-%d %H:%M")
        logs.append(_send_qq(cfg, f"Codex监控测试 北京时间{when}",
                             f"状态：测试（非真实重置通知）\n北京时间：{when}\n"
                             "说明：手动渠道测试，不表示自动重置或发放重置券。\n来源：@thsottiaux"))
    return logs
