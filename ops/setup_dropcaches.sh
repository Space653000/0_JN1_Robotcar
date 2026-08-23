#!/usr/bin/env bash
# 一勞永逸解決 Jetson「頁面快取吃光 RAM → CUDA OOM」:裝一個每 60 秒自動清頁面快取的計時器。
# 在 Jetson 上跑一次(需 sudo):  bash ops/setup_dropcaches.sh
# 移除:  sudo systemctl disable --now robotcar-dropcaches.timer && sudo rm /etc/systemd/system/robotcar-dropcaches.*
set -e
sudo bash -c 'printf "[Unit]\nDescription=robotcar drop page cache\n\n[Service]\nType=oneshot\nExecStart=/usr/sbin/sysctl -q vm.drop_caches=1\n" > /etc/systemd/system/robotcar-dropcaches.service && printf "[Unit]\nDescription=robotcar drop cache timer\n\n[Timer]\nOnBootSec=30s\nOnUnitActiveSec=60s\n\n[Install]\nWantedBy=timers.target\n" > /etc/systemd/system/robotcar-dropcaches.timer && systemctl daemon-reload && systemctl enable --now robotcar-dropcaches.timer && /usr/sbin/sysctl -q vm.drop_caches=1'
echo "drop-caches timer 已裝好並啟用。"
