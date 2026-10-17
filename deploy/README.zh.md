# 服务器运行说明

当前正式监控由服务器上的 systemd 定时器直接运行，不依赖 Mac、Codex 或 GitHub 定时调度。服务不监听新的网络端口。

- 定时器：tibo-watcher.timer，开机自启，每小时第 2、12、22、32、42、52 分钟检查；启动定时器后 15 秒另补检一次。
- 执行服务：tibo-watcher.service，以独立的 tibo-watcher 系统用户运行。
- 程序：/opt/tibo-watcher/current，指向已验证的版本目录。
- 去重状态：/var/lib/tibo-watcher/state.json，是切换后唯一正式状态文件。
- 密钥：/etc/tibo-watcher.env，仅 root 可读写，权限 600，由 systemd 读取后传给服务。不要提交、打印或发送它的内容。

查看状态：

```sh
systemctl status tibo-watcher.timer
systemctl list-timers tibo-watcher.timer
journalctl -u tibo-watcher.service -n 80 --no-pager
```

手动补检：`systemctl start tibo-watcher.service`。已经记录的帖子不会重发。没有新命中时不发群消息。

QQ 文案保留独立中文标题；正文先列去除网址的原文，再列对应中文译文和来源，不再重复状态、发布时间、时区换算过程或“原文译文”标签。执行时间直接使用北京时间。发送的内容去掉网址、“查看详情”和富文本。预告、疑似更新不会标成已完成。翻译服务不可用时仍保留明确的中文状态摘要。PushPlus 自身的客户端展示受其会员/渠道规则影响，程序不能移除平台自动添加的界面入口。

部署更新时先停定时器，等当前执行结束，再切换 current 到通过测试的版本，安装 deploy 下的服务和定时器，最后重新启用定时器。不要覆盖 /var/lib/tibo-watcher/state.json。可以切回上一版本目录回滚代码。

GitHub 的 watch 工作流和本机 LaunchAgent 已停用，避免多个环境各持有不同去重状态而重复推送。切回其他运行环境前，必须先停服务器定时器并同步服务器上的最新状态；不能直接拿仓库中的旧状态恢复监控。

首次导入 QQ 配置使用过一个只能执行配置导入的限时 SSH 密钥；导入后已撤销服务器公钥，删除 GitHub 的临时部署 Secrets 和本机临时私钥，并停用 configure-server 工作流。原始 SSH 登录私钥没有上传 GitHub，PushPlus Token 没有输出到聊天或日志。
