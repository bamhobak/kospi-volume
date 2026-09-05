# -*- coding: utf-8 -*-
"""VKOSPI(코스피200 변동성지수) 일별 시계열 수집.

출처: Investing.com (KOSPI Volatility, 내부 식별자 956761). **2013-08-06 부터** 제공된다.
  · KRX 가 2009-04-13 부터 산출하지만 KRX 정보데이터시스템에서 이 시계열을 꺼내는 경로를
    찾지 못했다(주가지수 검색기에 없고, 파생 검색기에는 '변동성지수 선물' 만 있다).
  · 네이버·FinanceDataReader 에는 VKOSPI 심볼이 없다.
출력: data/vkospi.csv, data/feargreed.db 테이블 vkospi
사용: python collect_vkospi.py
"""
import json, sqlite3, sys, urllib.request
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
ID = "956761"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
     "domain-id": "kr", "Referer": "https://kr.investing.com/indices/kospi-volatility-historical-data"}
sys.stdout.reconfigure(encoding="utf-8")

def pull(a, b):
    u = (f"https://api.investing.com/api/financialdata/historical/{ID}"
         f"?start-date={a}&end-date={b}&time-frame=Daily&add-missing-rows=false")
    r = urllib.request.Request(u, headers=H)
    return json.loads(urllib.request.urlopen(r, timeout=40).read().decode()).get("data") or []

rows = pull("2005-01-01", "2026-12-31")
print(f"받은 행 {len(rows):,}")
D = pd.DataFrame([{
    "date": x["rowDateTimestamp"][:10].replace("-", ""),
    "close": float(x["last_closeRaw"]), "open": float(x["last_openRaw"]),
    "high": float(x["last_maxRaw"]), "low": float(x["last_minRaw"]),
} for x in rows]).drop_duplicates("date").sort_values("date")
print(f"VKOSPI {len(D):,}일 · {D.date.iloc[0]} ~ {D.date.iloc[-1]}")
print(f"  평균 {D.close.mean():.2f} · 최저 {D.close.min():.2f}({D.loc[D.close.idxmin(),'date']}) "
      f"· 최고 {D.close.max():.2f}({D.loc[D.close.idxmax(),'date']})")
yr = D.assign(y=D.date.str[:4]).groupby("y").close.mean().round(1)
print("  연평균: " + " · ".join(f"{y} {v}" for y, v in yr.items()))

D.to_csv(BASE/"data"/"vkospi.csv", index=False, encoding="utf-8-sig")
con = sqlite3.connect(BASE/"data"/"feargreed.db")
con.execute("CREATE TABLE IF NOT EXISTS vkospi(date TEXT PRIMARY KEY, close REAL, open REAL, high REAL, low REAL)")
con.executemany("INSERT OR REPLACE INTO vkospi VALUES(?,?,?,?,?)",
                D[["date","close","open","high","low"]].itertuples(index=False, name=None))
con.commit(); con.close()
print(f"저장: data/vkospi.csv · feargreed.db(vkospi)")
