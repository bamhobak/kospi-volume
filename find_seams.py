# -*- coding: utf-8 -*-
"""운영 DB(kospi.db·kosdaq.db)의 '기준 이음새' 를 찾고 고친다.

배경(2026-09-06 감사): DB 이력은 수정주가로 일괄 백필됐고 그 뒤는 매일 원주가로 붙는다.
그 사이에 액면분할·병합·무상증자가 있으면 백필 경계에서 가짜 점프, 시행일에 진짜 점프가 생긴다.
(코스닥 88종목이 2026-06-04 부터 실제의 1/5~1/10 로 기록돼 있었다.)
방법: 올해 ±32% 점프가 있는 종목만 네이버 수정주가(FDR)와 최근 120거래일을 대조한다.
      우리/실제 비율이 0.9~1.1 을 벗어난 구간이 있으면 '이음새' 로 잡고, --fix 면 그 종목의
      2018-01-01 이후 시가·고가·저가·종가·거래량을 FDR 값으로 덮어쓴다(수급·시총 열은 보존).
사용: python find_seams.py [--fix] [--since 20260101]
"""
import io, sys, sqlite3, time, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
from pathlib import Path
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
FIX = "--fix" in sys.argv; SINCE = arg("--since", "20260101")
DB = {"KOSPI": BASE/"data"/"kospi.db", "KOSDAQ": BASE/"data"/"kosdaq.db"}
found = []
for mk, p in DB.items():
    con = sqlite3.connect(p, timeout=600)
    D = pd.read_sql("SELECT date,ticker,close FROM daily WHERE date>=? ORDER BY ticker,date", con, params=(SINCE,))
    g = D.groupby("ticker"); jj = D.close/g.close.shift(1)
    cands = sorted(set(D[(jj>1.32)|(jj<0.68)].ticker))
    last = D.date.max()
    print(f"{mk}: {SINCE}~ 점프 종목 {len(cands)}개 대조 중", flush=True)
    for i, t in enumerate(cands, 1):
        try:
            f = fdr.DataReader(t, "2026-01-01")
        except Exception: continue
        if f is None or not len(f): continue                    # 폐지 등 — FDR 없음
        f.index = f.index.strftime("%Y%m%d")
        o = D[D.ticker==t].set_index("date").close
        r = (o / f.Close).dropna()
        off = r[(r<0.9)|(r>1.1)]
        if len(off) >= 2:
            found.append((mk, t, off.index.min(), off.index.max(), len(off), round(off.median(),3)))
            if FIX:
                f2 = fdr.DataReader(t, "2018-01-01"); f2.index = f2.index.strftime("%Y%m%d")
                rows = [(float(x.Open), float(x.High), float(x.Low), float(x.Close), int(x.Volume), d, t)
                        for d, x in f2.iterrows() if x.Close > 0]
                con.executemany("UPDATE daily SET open=?,high=?,low=?,close=?,volume=? WHERE date=? AND ticker=?", rows)
                con.commit()
        time.sleep(0.1)
        if i % 50 == 0: print(f"  {i}/{len(cands)}", flush=True)
    con.close()
print(f"\n이음새 종목 {len(found)}개" + (" · 덮어씀" if FIX else " (--fix 로 고친다)"))
print(f"  {'시장':<7}{'종목':<8}{'시작':>10}{'끝':>10}{'일수':>5}{'우리/실제':>10}")
for r in found[:40]: print(f"  {r[0]:<7}{r[1]:<8}{r[2]:>10}{r[3]:>10}{r[4]:>5}{r[5]:>10}")
if len(found) > 40: print(f"  ... 외 {len(found)-40}개")
pd.DataFrame(found, columns=["market","ticker","from","to","days","ratio"]).to_csv(BASE/"data"/"seams_found.csv", index=False)
