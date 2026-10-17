#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root'; exit 1; }
for tool in python3 git systemctl flock useradd; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool"; exit 1; }
done
if ! id tibo-watcher >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/tibo-watcher --shell /usr/sbin/nologin tibo-watcher
fi
install -d -m 0755 /opt/tibo-watcher/releases
install -d -m 0700 -o tibo-watcher -g tibo-watcher /var/lib/tibo-watcher
install -m 0644 deploy/tibo-watcher.service /etc/systemd/system/tibo-watcher.service
install -m 0644 deploy/tibo-watcher.timer /etc/systemd/system/tibo-watcher.timer
systemd-analyze verify /etc/systemd/system/tibo-watcher.service /etc/systemd/system/tibo-watcher.timer
systemctl daemon-reload
printf '%s\n' 'Units installed. Configure /etc/tibo-watcher.env and seed state before enabling the timer.'
