#!/bin/sh
cd /g/vscode/kospi-volume
while ! grep -q "panel_kq.pkl" panel_rebuild2.log 2>/dev/null; do sleep 30; done
sleep 20
export IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl PYTHONIOENCODING=utf-8
echo "===== 업종 유효율 (보강 후) ====="
python - <<'PY'
import pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for f,nm in (("data/panel_kp.pkl","코스피"),("data/panel_kq.pkl","코스닥")):
    d = pd.read_pickle(f); d["_y"] = d.date.str[:4]
    r = d.groupby("_y").sr60.apply(lambda s: s.notna().mean()*100)
    print(f"  {nm}: " + " · ".join(f"{y}:{v:.0f}%" for y,v in r.items()))
PY
echo
echo "===== 9규칙 21년 재측정 (업종 보강 후) ====="
HIST_PER="2005~07:20050101-20071231,2008~09:20080101-20091231,2010~12:20100101-20121231,2013~17:20130101-20171231,2018~22:20180101-20221231,2023~26:20230101-20991231" HIST_YEAR=1 python measure_hist.py 2>&1 | tail -25
echo
echo "===== 계좌 21년 (업종 보강 후) ====="
python hist_portfolio.py 2>&1 | tail -14
