#!/bin/sh
cd /g/vscode/kospi-volume
export PYTHONIOENCODING=utf-8
while ! grep -q "^===== 계좌" cost_chain.log 2>/dev/null; do sleep 60; done
while [ $(sed -n '/^===== 계좌/,$p' cost_chain.log | wc -l) -lt 12 ]; do sleep 30; done
sleep 10
echo "===== 새 비용 기준으로 사이트 문구 갱신 ====="
python stats_2016.py > stats_2016_new.log 2>&1 && tail -45 stats_2016_new.log
python update_desc_2016.py
python selftest.py 2>&1 | tail -6
