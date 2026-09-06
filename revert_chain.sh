#!/bin/sh
cd /g/vscode/kospi-volume
export PYTHONIOENCODING=utf-8
echo "===== 패널 재생성 (거래세 0.15% 통일 · 슬리피지 원복) ====="
python -u build_panel.py --from 20040601 2>&1 | grep -E "이음새|주식수 기반|저장"
echo; echo "===== 비용 확인 ====="
python - <<'PY'
import pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
K = pd.read_pickle("data/panel_kp.pkl")
print(f"  cost: 최소 {K.cost.min():.2f}% · 중앙 {K.cost.median():.2f}% · 최대 {K.cost.max():.2f}%")
PY
echo; echo "===== 규칙 통계 (기준2016~ 만) ====="
python stats_2016.py 2>&1 | grep -E "기준2016~|규칙 " 
echo; echo "===== 사이트 문구 갱신 ====="
python update_desc_2016.py && python selftest.py 2>&1 | tail -4
echo; echo "===== 계좌 ====="
python hist_portfolio.py 2>&1 | tail -6
