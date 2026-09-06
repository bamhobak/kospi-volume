# -*- coding: utf-8 -*-
"""감사 6단계 — 2026-06-04 코스닥 88종목 동시 점프의 정체. 운영 DB(kosdaq.db)라 사이트에도 영향."""
import io, sys, sqlite3, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
c = sqlite3.connect("file:data/kosdaq.db?mode=ro", uri=True)
D = pd.read_sql("SELECT date,ticker,name,open,high,low,close,volume FROM daily WHERE date BETWEEN '20260601' AND '20260610' ORDER BY ticker,date", c)
g = D.groupby("ticker"); D["jj"] = D.close/g.close.shift(1)
J = D[(D.date=="20260604") & ((D.jj>1.32)|(D.jj<0.68))]
print(f"06-04 점프 {len(J)}종목 · 상승 {(J.jj>1.32).sum()} · 하락 {(J.jj<0.68).sum()}")
print(f"  점프 배율 중앙 {J.jj.median():.2f} · 시=종 비율 {(J.open==J.close).mean()*100:.0f}% · 거래량 0 비율 {(J.volume==0).mean()*100:.0f}%")
# 다음날 되돌아오나
nxt = D[(D.date=="20260605") & D.ticker.isin(J.ticker)]
prev = D[(D.date=="20260603") & D.ticker.isin(J.ticker)].set_index("ticker").close
back = (nxt.set_index("ticker").close / prev).dropna()
print(f"  06-05 종가 / 06-03 종가: 중앙 {back.median():.2f} → {'되돌아옴(하루짜리 데이터 오류)' if 0.85<back.median()<1.15 else '안 돌아옴(지속)'}")
print("  예시 6종목 (06-03 → 06-04 → 06-05 종가):")
for t in J.ticker.head(6):
    s = D[D.ticker==t].set_index("date").close
    print(f"    {t} {J[J.ticker==t].name.iloc[0]:<10} " + " → ".join(f"{s.get(d, float('nan')):>9,.0f}" for d in ("20260603","20260604","20260605")))
# 그날 전체 코스닥 분포 — 88개 말고 다른 종목들은 정상인가
A = D[D.date=="20260604"]
print(f"  06-04 전체 {len(A):,}종목 · 등락률 중앙 {(A.jj.median()-1)*100:+.1f}% · ±10% 넘는 종목 {((A.jj>1.1)|(A.jj<0.9)).sum()}")
# 실제 시장(FDR)과 비교 — 점프 종목 3개
import FinanceDataReader as fdr
print("  네이버(FDR) 실제값과 비교:")
for t in J.ticker.head(3):
    try:
        f = fdr.DataReader(t, "2026-06-02", "2026-06-06")["Close"]
        ours = D[D.ticker==t].set_index("date").close
        print(f"    {t}: FDR " + " / ".join(f"{d.strftime('%m-%d')} {v:,.0f}" for d,v in f.items())
              + "   |   우리 " + " / ".join(f"{d[4:6]}-{d[6:]} {v:,.0f}" for d,v in ours.items() if "20260602"<=d<="20260606"))
    except Exception as e: print(f"    {t}: FDR 실패 {e}")
# 오늘 낸 2026 코스닥 신호 중 06-03~06-05 에 난 것
import os
os.environ.update(IX_FROM="2004-06-01", DART_FROM="20040101", PANEL_KP="panel_kp.pkl", PANEL_KQ="panel_kq.pkl")
from pathlib import Path
src = Path("portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(Path("portfolio.py").resolve())}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
for rid, nm in (("D1","낙폭과대"), ("D2","저PBR 낙폭")):
    K, hold, *_ , cond = ns["RULES"][rid]
    m = cond.fillna(False) & (K.date>="20260520") & (K.date<="20260630")
    Z = K[m]
    print(f"  [{nm}] 2026-05-20~06-30 신호 {len(Z)}건 · 06-04 점프 종목이 낸 것 {Z.ticker.isin(set(J.ticker)).sum()}건"
          + (" · 날짜: " + " ".join(sorted(set(Z.date))) if len(Z) else ""))
