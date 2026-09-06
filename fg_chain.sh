#!/bin/sh
cd /g/vscode/kospi-volume
export PYTHONIOENCODING=utf-8
while ! grep -q "^\[.*완료" stock_fg.log 2>/dev/null; do sleep 60; done
echo "===== 계산 로그 ====="; cat stock_fg.log
echo; echo "===== 실측 ====="
python -u stock_fg_test.py 2>&1
