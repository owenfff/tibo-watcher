# 自动触发兜底（macOS）

GitHub 的定时计划保留每 10 分钟运行。本机另有一个不使用大模型的 LaunchAgent，每 600 秒检查同一个 monitor.yml 工作流。近 9 分钟已有成功运行，或近 12 分钟仍有排队/进行中的运行时跳过；否则使用现有 GitHub CLI 登录触发工作流。抓取、分类、QQ 推送及去重仍由同一个云端工作流完成。

安装或更新：`python3 scripts/install_dispatch_fallback.py`。安装器先检查 gh 已登录，再安装触发脚本和登录启动项。它不读取 PushPlus Token，PushPlus 密钥仍仅保存在 GitHub Actions Secrets。

本机服务不需要打开终端或 Codex，不消耗大模型调用。Mac 必须已登录、保持唤醒并联网；关机、注销或睡眠期间，本机兜底不能运行。GitHub 原生调度若恢复，可以独立运行。本机兜底会跳过近期成功运行。调度和 GitHub 排队可能延迟，不保证精确到秒。

脚本及日志目录：`~/Library/Application Support/tibo-watcher/`。日志 dispatch.log 中 dispatched 表示已提交触发请求，最终结果应查看 Actions；skip_recent_success / skip_active_run 表示避免重复触发。

启动项：`~/Library/LaunchAgents/com.owenfff.tibo-watcher-dispatch.plist`，正式间隔为 600 秒。

暂停：`launchctl bootout gui/$(id -u)/com.owenfff.tibo-watcher-dispatch`。再次运行安装器即可恢复。若要下次登录也不启动，停用后移走上述 plist 文件。

验证记录：北京时间 2026-10-18 01:59，系统计时器自动唤起脚本，产生成功的 Actions 运行 39056124257。这是本机自动触发的 workflow_dispatch，不能当作 GitHub 原生 schedule 恢复的证据。
