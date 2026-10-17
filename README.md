# 🔄 tibo-watcher

监控 @thsottiaux 的 Codex / ChatGPT Work 额度重置消息、公开产品计划及 Day N 每日进展系列，支持 ntfy、Telegram、邮件及 PushPlus QQ 机器人。Python 3.10+，仅用标准库，无额外依赖。

沿用原项目的 Dayclaw 公开 X 时间线和官方 Codex changelog。无需 X Bearer Token，不调用付费 X API。公开镜像可能延迟或不可用；单个来源故障不阻塞另一个来源。GitHub Actions 保持每 10 分钟运行（GitHub 调度可能延迟）。

## 监控规则

- 保留加权关键词打分：强信号 3 分、中信号 2 分、产品词 1 分；新增 banked reset 强信号。
- 先要求存在重置、补发额度、重置券或 Codex / ChatGPT Work 公开产品计划，或 Day N 每日进展，再应用关键词评分门槛。计划消息仅来自 @thsottiaux 的 X 时间线，需有明确产品、开发/上线动作及意向或时间信号；普通讨论、没有 Day 编号的已完成普通发布、个人使用计划及纯转帖不推送。普通引用帖不推送；作者自己用 Day N 编号写的更新即便附带引用，也按每日进展处理。转帖识别使用镜像提供的元数据、作者和 RT/QT 前缀；镜像若未提供标识，无法完全识别。
- 状态为「预告 / 重置券 / 已完成 / 疑似重置」。未来时优先按预告处理；有否定、条件、推测等歧义时不说已到账。banked reset 表示可使用的重置券，不表示额度自动到账。
- `ALERT_ALL=1` / `--alert-all` 只跳过分数门槛，仍过滤非监控事件及转帖。
- 首次运行及 `--prime` 只建立基线，不发送历史消息。每轮最多推送 5 条，沿用原项目行为。
- 按稳定帖子 ID 去重，记录永久保留，不再裁剪到 1500 条。同一帖子后续修改不会再发。请保留 `watcher_state.json` 和 Actions 的持久化步骤。
- 发送前保存去重记录，不自动重试失败消息，以避免重复。失败、超出每轮上限的帖子也视为已处理；极端情况下进程中断或状态未能推回 GitHub，不能保证跨运行的绝对一次性投递。不要删除或回滚状态文件。

## QQ 机器人（PushPlus）

QQ 仅通过 PushPlus 官方机器人渠道发送，不涉及个人 QQ 登录、协议机器人、NapCat 或 Lagrange。QQ 只推送 @thsottiaux 时间线的重置事件、公开产品计划及 Day N 每日进展，changelog 继续供原来的通知渠道使用，不会冒充其发帖。

### 把机器人加入你的群

1. 登录 PushPlus，在「个人中心 → 渠道配置 → QQ机器人」扫描页面二维码，添加官方机器人为好友并绑定；已加好友而未绑定时，复制绑定码，私聊发送给机器人。
2. 用群主 QQ，在机器人资料页通过「添加到群」等入群入口，选择你管理的目标群，完成入群。
3. 在目标群的机器人管理/机器人资料设置中，为该机器人打开 **「允许主动发言」**（部分 QQ 版本称允许主动消息/主动推送）。以你客户端实际显示为准；PushPlus 建群配置前必须开启此权限。
4. 回到 PushPlus 的 QQ机器人渠道配置，新增「发到QQ群」配置，选择刚加入的群及机器人，保存并复制该条配置的 **配置编码**。这不是 QQ 群号，也不是 PushPlus 的 topic 群组码。
5. 按下表配置两个 secret。机器人绑定成功不代表已完成群配置；两项齐全才会启用 QQ。

流程依据 [PushPlus 官方 QQ机器人渠道说明](https://www.pushplus.plus/doc/channel/qq.html)。官方说明：实名非会员通常只展示标题摘要，因此标题独立表达结论；服务额度与客户端菜单以平台当前说明为准。

### GitHub Actions secrets

在本仓库 Settings → Secrets and variables → Actions → New repository secret 中填写：

| Secret | 填什么 |
|---|---|
| `PUSHPLUS_TOKEN` | PushPlus 个人中心的发送 token |
| `PUSHPLUS_QQ_OPTION` | 上述「发到QQ群」渠道配置的配置编码 |

Actions 已将这两项传给程序，cron 为等价的 `0,10,20,30,40,50 * * * *`，保持每 10 分钟运行。缺少任意一项就跳过 QQ，不影响 ntfy / Telegram / 邮件。不要把真实值写进源码、示例、日志或提交。

本地运行：复制 `.env.example` 为 `.env`，填写对应两项。`.env` 已被 Git 忽略；环境变量优先于 `.env`。

接口固定 POST `https://www.pushplus.plus/send`，JSON 仅含 `token`、`title`、`content`、`channel="qq"`、`option`、`template="txt"`。HTTP 成功且 JSON `code=200` 才记为 PushPlus 已受理；已受理不等于 QQ 最终送达。接口响应原文不写日志，避免泄密。

### QQ 文案

标题最多 40 字，不含网址或 Markdown；正文固定四行。QQ 标题和正文由固定中文文案及解析时间生成，绝不拼接原帖文本或任何长短链接。所有显示时间转为北京时间 UTC+8，精确到分钟。

```text
Codex已完成重置 北京时间10-13 13:06
状态：已完成
北京时间：10-13 13:06（原帖发布时间）
说明：Codex已确认额度自动重置或补发，无需使用重置券。
来源：@thsottiaux
```

时间表示 **原帖发布时间**，不是账户实际到账时间。不会把含糊的 “end of day” 擅自翻译为北京时间今晚；没有明确时区就不编造执行时刻。Dayclaw 未带偏移的 ISO 发布时间按 UTC 解析；缺失或仅有日期时标明未提供精确时间。

### 用一条假帖子离线干跑，不发到群里

仓库已附 `examples/reset-post.json`：

```json
{
  "body": "We have reset all Codex usage limits.",
  "created_at": "2026-10-13T05:06:00Z"
}
```

在仓库目录执行：

```bash
python3 main.py --dry-run --sample-post examples/reset-post.json
python3 main.py --dry-run --sample-post examples/reset-announcement.json
python3 main.py --dry-run --sample-post examples/banked-reset.json
python3 main.py --dry-run --sample-post examples/possible-reset.json
```

命令不抓取时间线、不发送任何通知、不写去重状态，即便已经配置真实 secrets 也不会发送。首次使用没有状态文件也能预览，不受基线抑制。输出标题应为 `Codex已完成重置 北京时间10-13 13:06`。

可修改假帖 body 为 `We will give a banked reset today.` 测预告，或 `Your Codex banked reset is now available.` 测重置券。`--sample-post` 必须搭配 `--dry-run`；干跑禁止与 `--test-notify`、`--loop`、`--prime` 混用。

## Day N 每日进展系列（重点监控）

专门匹配 @thsottiaux 的 `Day 1/`、`Day 2.4/`、`Day 11/`、`Roundup of Day 2/` 等独立行编号，覆盖 1–28 天及子更新。即便原帖没有再次提 Codex / ChatGPT Work，也没有未来时态，仍作为每日进展命中。不是只匹配未来的计划；已经交付的编号更新也会推送。

标题保留 Day 编号和中文主题，例如 `Codex Day11满载优化 北京时间10-15 23:11`。正文仍为状态、北京时间、说明、来源四行，不拼接英文原帖或链接。已知主题包括满载/任务续跑、磁盘占用、上下文、自动审批、会议纪要、决策接口、记忆及语音；未知主题标记每日进展，不臆造功能。

`Day 8/ Reset` 这类短帖没有明确到账措辞时写「疑似重置」；若原文明确已完成、将要重置或发放重置券，沿用对应状态。预告不写成已交付；同一帖只发一次，不另外重复发计划和重置通知。

```bash
python3 main.py --dry-run --sample-post examples/day-improvement.json
python3 main.py --dry-run --sample-post examples/day-reset.json
python3 main.py --dry-run --sample-post examples/day-sub-update.json
```

沿用同一个 Dayclaw 来源及永久去重状态；不补发已经处理过的老 Day 帖。镜像若延迟、缺帖或没有引用/作者标识，监控仍可能延迟或漏报。

## 公开产品计划：有新消息就推群

除额度重置之外，监控明确提到 Codex / ChatGPT Work 的开发计划、上线预告、开放范围变化及延期安排。所有消息继续使用中文短标题、四行无链接正文及北京时间；推测写「疑似计划」，预告不写成已经上线。

```text
Codex新模型上线预告 北京时间10-16 09:00
状态：时间安排
北京时间：10-16 09:00（原帖发布时间）
说明：Codex预告推出新模型，尚不代表已经上线；原帖相对时间折算预计北京时间10-16 12:00。
来源：@thsottiaux
```

计划说明先给出固定中文分类（如新模型、语音功能、Windows支持），再附加清理后的中文机翻参考，不复制含链接的原文。只有明确的「几小时/几分钟/几天后」才由发帖时刻折算北京时间；“tomorrow”“end of day”及未明确日期的时钟时间不擅自换算，写明未确认精确执行时刻。没有发帖的日子不发送空日报，也无法监控未公开的内部计划。

上线这项规则时不清空历史去重状态，不补发以前已经处理过的计划帖；同一帖子同时涉及重置和计划时，重置通知优先，只发一次。

```bash
python3 main.py --dry-run --sample-post examples/product-plan.json
python3 main.py --dry-run --sample-post examples/launch-announcement.json
python3 main.py --dry-run --sample-post examples/rollout-plan.json
python3 main.py --dry-run --sample-post examples/possible-plan.json
```

## QQ 正文自动翻译

默认 `QQ_AUTO_TRANSLATE=1`：真实 QQ 推送前，将清理过的公开英文原帖通过 MyMemory 的匿名翻译接口转换为简体中文，附在第三行「说明」后，标注「机翻参考」。无需新增密钥或付费 API，X 来源不变。具体可用性和额度以 [MyMemory 官方说明](https://mymemory.translated.net/doc/spec.php) 为准。

标题、状态及北京时间仍由本地规则确定，翻译结果不会把预告升级成已完成，也不会影响筛选和去重。发送前后均清理网址、短链及 Markdown；去掉不明确的原帖时钟时间，避免把它误当作北京时间。保留 Day 编号，正文总共仍是四行。

只将公开帖文发送给翻译服务，不发送 PushPlus Token、群配置或其他密钥。单帖最多取前 1000 字符，分段翻译；输出受 QQ 长度限制。服务不可用、额度用尽或翻译失败时，继续发送既有中文摘要，不返回英文原文、不阻塞通知。

`--dry-run --sample-post` 仍为完全离线预览，不调用翻译服务或任何推送渠道。自动化测试使用模拟译文验证正文格式和回退路径。

## 原有通知渠道

渠道可同时启用，QQ 未配置或请求失败不会阻止其他渠道。

| 环境变量 | 用途 |
|---|---|
| `NTFY_TOPIC` / `NTFY_SERVER` | ntfy 订阅主题及服务端，默认 `https://ntfy.sh` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram 机器人和会话 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | 邮件 SMTP 配置 |
| `MAIL_FROM` / `MAIL_TO` | 邮件收发地址 |

ntfy 手机客户端订阅同一个随机主题即可。原有渠道继续保留英文评分摘要、原文和来源链接；无网址的四行中文格式专用于 QQ。

## 其他配置和运行

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `TIBO_HANDLE` | `thsottiaux` | X 监控对象；QQ 仅支持此账号 |
| `INCLUDE_REPLIES` | `1` | 是否监控回复 |
| `WATCH_CHANGELOG` | `1` | 是否读取官方 changelog |
| `WATCH_INTERVAL_MIN` | `10` | 本地循环间隔分钟数 |
| `SCORE_THRESHOLD` | `3` | 关键词评分门槛 |
| `ALERT_ALL` | `0` | 是否绕过事件的评分门槛 |
| `STATE_FILE` | `watcher_state.json` | 去重状态文件 |
| `VERBOSE` | `0` | 是否输出原帖评分日志 |

```bash
python3 main.py                         # 检查一轮
python3 main.py --loop                  # 本地持续检查
python3 main.py --dry-run --verbose     # 读取真实来源，但不推送、不保存状态
python3 main.py --prime                 # 重新记录当前基线，不推送
python3 main.py --test-notify           # 真实发送测试消息到所有已配置渠道（包括 QQ）
python3 -m unittest discover -s tests -v # 离线回归测试
```

部署时直接在现有仓库应用修改，配置 secrets，在 Actions → watch → Run workflow 启动。保持工作流的 `contents: write` 权限，以便提交去重状态。

## 项目结构

```text
main.py                     入口
watcher/config.py           环境变量和 .env
watcher/sources.py          原有公开时间线及 changelog
watcher/detect.py           加权关键词打分
watcher/events.py           重置状态判断、北京时间、QQ 中文文案
watcher/notify.py           ntfy / Telegram / SMTP / PushPlus QQ
watcher/state.py            永久去重记录，原子写入
watcher/run.py              检查和循环
watcher/cli.py              CLI 及离线假帖干跑
examples/reset-post.json    无密钥的假帖
.github/workflows/watch.yml 每 10 分钟运行及持久化状态
```

非官方工具，基于公开措辞作保守判断，仍可能漏报或误判。

## License

[MIT](LICENSE)

### 免费公开监控站补充来源

保留 Dayclaw；同时读取 Codexy 的公开 `data/days.json`，并从 Twiscan / Twstalker 发现原帖 ID，再通过 FxTwitter 的免费公开接口核验作者、正文和发布时间。不需要 X Bearer Token 或额外密钥。第三方站点可能延迟、缺帖或不可用；这些问题会记录在 Actions 日志中。所有来源共用 `dayclaw:<原帖ID>` 去重键。

首次接入 Codexy 会记录已有归档，不刷历史消息；公开镜像发现的普通帖子只推最近 24 小时的新帖。`recovery-posts.json` 可列出需要补查的真实原帖 ID，仍必须核验作者并经过分类、评分和同一份去重状态；已记录的原帖不会重发。它不是假帖子测试入口。

Actions 保留每 10 分钟的 schedule；当前尚未观察到自动触发，不能视为已恢复。GitHub 定时可能延迟或丢弃；必须在 Actions 中看到 `schedule` 运行记录才算验证定时生效。手动成功不代表定时成功。日志 `DELIVERY OK qq accepted by PushPlus` 仅表示服务已受理，不保证 QQ 最终送达；`pushed` 仅统计至少一个渠道受理的帖子。

推送接口拒绝或传输失败时，CLI 返回非零退出码，Actions 显示失败，并继续保存去重状态。只记录 HTTP 状态及数字业务码，不输出可能包含密钥的响应正文。已尝试的帖子不会自动重试。

QQ 推送排错：业务码 `905` 表示 PushPlus 账号未实名认证，必须由账号本人在 PushPlus 完成认证；`903` 表示令牌不正确。购买会员不能用于判断这些错误是否已解决。`qq-diagnostic.json` 的 `request_id` 用于明确请求一次中文 QQ 通道测试，每个编号仅尝试一次；普通干跑不会触发测试。不要修改编号来反复请求受限接口。
