#!/bin/sh
cd /g/vscode/kospi-volume
while ! grep -q "^완료" seam_factor.log 2>/dev/null; do sleep 20; done
echo "===== 이음새 계수 =====" ; tail -2 seam_factor.log
echo "===== 패널 재생성 (주가 보정 포함) ====="
python -u build_panel.py --from 20040601 2>&1 | grep -E "이음새|주식수 기반|저장|밸류|보완" 
export IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl PYTHONIOENCODING=utf-8
echo; echo "===== 보정 후 남은 점프 (진짜 사건만 남아야) ====="
python - <<'PY'
import pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for f, nm in (("data/panel_kp.pkl","코스피"),("data/panel_kq.pkl","코스닥")):
    K = pd.read_pickle(f)[["ticker","date","close","grp"]].sort_values(["ticker","date"])
    jj = K.close/K.groupby("ticker").close.shift(1); J = K[(jj>1.32)|(jj<0.68)]
    print(f"  {nm}: 점프 {len(J):,}행 · 2018-01-02 {int((J.date=='20180102').sum())}행 · 폐지그룹 {(J.grp!='생존').mean()*100:.0f}%")
PY
echo; echo "===== 9규칙 21년 (보정 후) ====="
HIST_PER="2005~07:20050101-20071231,2008~09:20080101-20091231,2010~12:20100101-20121231,2013~17:20130101-20171231,2018~22:20180101-20221231,2023~26:20230101-20991231" HIST_YEAR=1 python measure_hist.py 2>&1 | tail -25
echo; echo "===== 계좌 21년 (보정 후) ====="
python hist_portfolio.py 2>&1 | tail -14
