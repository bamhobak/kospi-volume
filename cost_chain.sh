#!/bin/sh
cd /g/vscode/kospi-volume
export PYTHONIOENCODING=utf-8
echo "===== 패널 재생성 (거래세 0.15% 통일 · 슬리피지 절반) ====="
python -u build_panel.py --from 20040601 2>&1 | grep -E "이음새|주식수 기반|저장|폐지 delisted"
echo; echo "===== 비용 확인 ====="
python - <<'PY'
import pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for f, nm in (("data/panel_kp.pkl","코스피"),("data/panel_kq.pkl","코스닥")):
    K = pd.read_pickle(f)
    print(f"  {nm} cost: 최소 {K.cost.min():.2f}% · 중앙 {K.cost.median():.2f}% · 최대 {K.cost.max():.2f}%")
PY
echo; echo "===== 새 비용 기준 규칙 통계 ====="
python stats_2016.py 2>&1 | sed -n '1,50p'
echo; echo "===== 계좌 ====="
python hist_portfolio.py 2>&1 | tail -13
