#!/bin/sh
cd /g/vscode/kospi-volume
export IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl PYTHONIOENCODING=utf-8
echo "===== 패널 재생성 (병합 버그 수정) ====="
python -u build_panel.py --from 20040601 2>&1 | grep -E "폐지 delisted|이음새|주식수 기반|저장|종목 .*행"
echo; echo "===== 2017년에 사라지는 종목 수 (수리 전 코스피 114 · 코스닥 215) ====="
python - <<'PY'
import pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for f, nm in (("data/panel_kp.pkl","코스피"),("data/panel_kq.pkl","코스닥")):
    K = pd.read_pickle(f)[["ticker","date","grp"]]
    last = K.groupby("ticker").date.max(); g = last[(last>="20170101")&(last<"20180101")]
    n18 = K[K.date>="20180101"].ticker.nunique()
    print(f"  {nm}: 2017년에 사라짐 {len(g)}개(12월 {(g.str[:6]=='201712').sum()}) · 2018~ 종목 수 {n18:,} · 폐지그룹 {K[K.grp!='생존'].ticker.nunique()}종목")
PY
echo; echo "===== 9규칙 21년 (구멍 수리 후) ====="
HIST_PER="2005~07:20050101-20071231,2008~09:20080101-20091231,2010~12:20100101-20121231,2013~17:20130101-20171231,2018~22:20180101-20221231,2023~26:20230101-20991231" HIST_YEAR=1 python measure_hist.py 2>&1 | sed -n '/규칙 /,/연도별/p' | head -13
echo; echo "===== 계좌 21년 (구멍 수리 후) ====="
python hist_portfolio.py 2>&1 | tail -13
