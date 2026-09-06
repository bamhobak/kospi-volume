# -*- coding: utf-8 -*-
"""감사 7단계 — 2026-06-04 코스닥 가격 오류: 어느 기간, 어느 배율, 어느 수집기가 썼나, 사이트에 지금 보이나."""
import io, sys, sqlite3, warnings, json, glob, os
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
c = sqlite3.connect("file:data/kosdaq.db?mode=ro", uri=True)
print("kosdaq.db daily 열:", [r[1] for r in c.execute("PRAGMA table_info(daily)")])
D = pd.read_sql("SELECT date,ticker,name,close,volume FROM daily WHERE date>='20260520' ORDER BY ticker,date", c)
g = D.groupby("ticker"); D["jj"] = D.close/g.close.shift(1)
bad = sorted(set(D[(D.date=="20260604") & ((D.jj>1.32)|(D.jj<0.68))].ticker))
print(f"06-04 점프 종목 {len(bad)}개")
# 그중 12개를 FDR 과 날짜별로 비교 — 배율이 언제부터 언제까지 몇 배인가
rows = []
for t in bad[:12]:
    try: f = fdr.DataReader(t, "2026-05-20", "2026-08-31")["Close"]
    except Exception: continue
    f.index = f.index.strftime("%Y%m%d")
    o = D[D.ticker==t].set_index("date").close
    r = (o / f).dropna()
    off = r[(r<0.9)|(r>1.1)]
    if len(off):
        rows.append((t, D[D.ticker==t].name.iloc[0], off.index.min(), off.index.max(), len(off), round(off.median(),3), round(r[r.index>off.index.max()].median() if (r.index>off.index.max()).any() else float('nan'),3)))
    else: rows.append((t, D[D.ticker==t].name.iloc[0], "-", "-", 0, 1.0, 1.0))
print(f"  {'종목':<8}{'이름':<10}{'오류 시작':>10}{'오류 끝':>10}{'일수':>5}{'우리/실제':>10}{'그 뒤':>7}")
for r in rows: print(f"  {r[0]:<8}{r[1]:<10}{r[2]:>10}{r[3]:>10}{r[4]:>5}{r[5]:>10}{r[6]:>7}")
# 배율 분포 (전체 88)
rat = []
for t in bad:
    try: f = fdr.DataReader(t, "2026-06-04", "2026-06-04")["Close"]
    except Exception: continue
    if len(f):
        o = D[(D.ticker==t)&(D.date=="20260604")].close
        if len(o): rat.append(o.iloc[0]/f.iloc[0])
rat = pd.Series(rat)
print(f"  06-04 우리/실제 배율 분포(전체 {len(rat)}개): " + " · ".join(f"{k}:{((rat/k).sub(1).abs()<0.08).sum()}" for k in (0.1,0.2,0.5,1,2,5,10)))
# 사이트가 지금 쓰는 데이터에 이 종목이 어떻게 보이나
cands = [p for p in glob.glob("data/*.json")+glob.glob("*.json") if os.path.getsize(p) > 100000]
print("  사이트 데이터 후보:", cands[:6])
for p in cands[:3]:
    try:
        J = json.load(open(p, encoding="utf-8"))
        items = J if isinstance(J, list) else J.get("rows") or J.get("data") or list(J.values())[0]
        hit = [x for x in items if isinstance(x, dict) and x.get("t") in bad[:3]]
        for x in hit[:3]: print(f"    {p}: {x.get('t')} {x.get('n')} 종가 {x.get('c')} (updated {J.get('updated') if isinstance(J,dict) else '-'})")
    except Exception as e: print(f"    {p}: 읽기 실패 {type(e).__name__}")
# 수집 로그에서 06-04 흔적
for lg in sorted(glob.glob("*.log"))[:40]:
    try:
        s = open(lg, encoding="utf-8", errors="ignore").read()
        if "20260604" in s or "2026-06-04" in s:
            i = s.find("20260604") if "20260604" in s else s.find("2026-06-04")
            print(f"  로그 {lg}: ...{s[max(0,i-80):i+120].replace(chr(10),' | ')}...")
    except Exception: pass
