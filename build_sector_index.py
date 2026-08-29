# -*- coding: utf-8 -*-
"""업종·테마 일별 지수 생성 (자체 종가 데이터로 계산 · 외부 수집 없음)
   - 편입 종목 동일가중 일별 수익률 → 누적지수
   - 파생: ret1/5/20/60, 20일선 이격, 시장(코스피 동일가중) 대비 상대강도
   결과: data/sector_index.pkl  (읽기 전용 · 메인 DB 미변경)
사용: python build_sector_index.py
"""
import pickle, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
import collect

BASE = Path(__file__).parent
con = sqlite3.connect(collect.DB, timeout=900)
sec = pd.read_sql("SELECT kind, gname, ticker FROM sector", con)
df = pd.read_sql("SELECT date, ticker, close FROM daily WHERE market='KOSPI' AND close IS NOT NULL", con)
con.close()
print(f"입력: 종가 {len(df):,}행 · {df.date.min()}~{df.date.max()} · {df.ticker.nunique()}종목")

df = df.sort_values(["ticker", "date"])
df["ret"] = df.groupby("ticker")["close"].pct_change() * 100
df = df[df.ret.abs() < 40]                      # 액면분할 등 이상치 제거
mkt = df.groupby("date")["ret"].mean().sort_index()
mktidx = (1 + mkt.fillna(0) / 100).cumprod()

def build(kind):
    m = sec[sec.kind == kind][["ticker", "gname"]].drop_duplicates()
    j = df.merge(m, on="ticker")
    j = j[j.gname != "기타"]
    cnt = j.groupby(["gname", "date"])["ret"].size().unstack(0)
    piv = j.groupby(["gname", "date"])["ret"].mean().unstack(0).sort_index()
    piv = piv[[c for c in piv.columns if cnt[c].max() >= 3]]     # 편입 3종목 미만 제외
    idx = (1 + piv.fillna(0) / 100).cumprod()
    pct = lambda s, n: (s / s.shift(n) - 1) * 100
    mk20 = pct(mktidx, 20).reindex(idx.index)
    out = {"index": idx, "ret1": piv,
           "ret5": pct(idx, 5), "ret20": pct(idx, 20), "ret60": pct(idx, 60),
           "ma20": idx / idx.rolling(20).mean() - 1,
           "rs20": pct(idx, 20).sub(mk20, axis=0),
           "members": cnt.reindex(idx.index)[idx.columns]}
    print(f"  {kind}: {idx.shape[1]}개 그룹 · {idx.shape[0]}거래일 · {idx.index.min()}~{idx.index.max()}")
    return out

print("지수 생성:")
res = {"upjong": build("upjong"), "theme": build("theme"),
       "market": {"index": mktidx, "ret1": mkt,
                  "ret5": (mktidx / mktidx.shift(5) - 1) * 100,
                  "ret20": (mktidx / mktidx.shift(20) - 1) * 100}}
p = BASE / "data" / "sector_index.pkl"
pickle.dump(res, open(p, "wb"))
print(f"저장: {p} ({p.stat().st_size/1e6:.1f}MB)")
u = res["upjong"]
last = u["index"].index[-1]
top = u["rs20"].loc[last].dropna().sort_values(ascending=False)
print(f"\n[{last}] 업종 상대강도 상위 5:")
for g, v in top.head(5).items(): print(f"   {g:22s} {v:+6.1f}%  (편입 {int(u['members'].loc[last, g])}종목)")
print(f"[{last}] 하위 3:")
for g, v in top.tail(3).items(): print(f"   {g:22s} {v:+6.1f}%")
