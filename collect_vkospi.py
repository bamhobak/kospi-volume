# -*- coding: utf-8 -*-
"""VKOSPI(코스피200 변동성지수) 전 구간 시계열 — 실측 + 소급 추정.

실측: Investing.com (KOSPI Volatility, 내부 식별자 956761) — **2013-08-06 부터**.
      KRX 는 2009-04-13 부터 산출하지만 정보데이터시스템에서 이 시계열을 꺼내는 경로를 못 찾았다
      (주가지수 검색기에 없음 · 파생 검색기엔 '변동성지수 선물' 만 · 통계 코드 스캔 전부 400).

소급: VKOSPI 원래 공식은 코스피200 **옵션 전 종목 체결가**로 모형 없는 내재변동성을 계산한다.
      과거 옵션 원장을 확보하지 못해 그 공식 그대로는 불가능하다. 대신 VKOSPI 가 재는 대상
      (향후 30일 기대 변동성)을 같은 성격의 관측치로 추정한다 —
      HAR 구조(5·20·60·120일 실현변동성) + 하방 준편차 + 일중 변동폭(파킨슨류).
      겹치는 3,209일로 적합하고, 2020~2026 을 떼어 검증했다:
        상관 0.928 · 평균 절대오차 4.13 · 최대 43.8
      독립 검증: 소급 추정의 2008-10-30 값이 88.2 로, 알려진 2008년 실제 VKOSPI 최고치(약 89)와 맞는다.

출력: data/vkospi.csv (date, close, src) · feargreed.db 테이블 vkospi(실측) · vkospi_full(전 구간)
사용: python collect_vkospi.py           (매일 돌리면 실측이 이어지고 소급분은 그대로 유지)
"""
import json, sqlite3, sys, urllib.request
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
ID = "956761"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
     "domain-id": "kr", "Referer": "https://kr.investing.com/indices/kospi-volatility-historical-data"}
X = ["rv5", "rv20", "rv60", "rv120", "dn20", "rng20"]
sys.stdout.reconfigure(encoding="utf-8")

# ── 1) 실측 VKOSPI ──────────────────────────────────────────────
u = (f"https://api.investing.com/api/financialdata/historical/{ID}"
     f"?start-date=2005-01-01&end-date=2030-12-31&time-frame=Daily&add-missing-rows=false")
rows = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=60).read().decode())["data"]
A = pd.DataFrame([{"date": x["rowDateTimestamp"][:10].replace("-", ""),
                   "close": float(x["last_closeRaw"])} for x in rows]).drop_duplicates("date").sort_values("date")
print(f"실측 VKOSPI {len(A):,}일 · {A.date.iloc[0]}~{A.date.iloc[-1]} · 평균 {A.close.mean():.2f}")

# ── 2) 설명변수(코스피 지수에서) ────────────────────────────────
px = fdr.DataReader("KS11", "2004-01-01"); px = px[px.Close > 0]; px.index = pd.to_datetime(px.index)
r = px.Close.pct_change()
D = pd.DataFrame({"date": px.index.strftime("%Y%m%d")})
for n in (5, 20, 60, 120):
    D[f"rv{n}"] = (r.rolling(n).std() * np.sqrt(252) * 100).values
D["dn20"] = (r.clip(upper=0).rolling(20).std() * np.sqrt(252) * 100).values
D["rng20"] = (np.log(px.High / px.Low).rolling(20).mean() * np.sqrt(252) / 2 * 100).values
D = D.dropna(subset=X)

# ── 3) 적합·검증·소급 ───────────────────────────────────────────
M = D.merge(A, on="date")
def fit(df):
    return np.linalg.lstsq(np.c_[np.ones(len(df)), df[X].values], df.close.values, rcond=None)[0]
def prd(df, b):
    return np.c_[np.ones(len(df)), df[X].values] @ b
tr, te = M[M.date < "20200101"], M[M.date >= "20200101"]
bt = fit(tr); p = prd(te, bt); e = p - te.close.values
print(f"검증(2020~, 학습에서 제외): 상관 {np.corrcoef(p, te.close)[0,1]:.3f} · "
      f"평균 절대오차 {np.abs(e).mean():.2f} · 편향 {e.mean():+.2f} · 최대 {np.abs(e).max():.1f}")
b = fit(M)
print("계수: " + " · ".join(f"{k} {v:+.3f}" for k, v in zip(["상수"] + X, b)))

D["est"] = np.clip(prd(D, b), 5, None)
F = D[["date", "est"]].merge(A, on="date", how="left")
F["close"] = F.close.fillna(F.est).round(2)
F["src"] = np.where(F.date.isin(set(A.date)), "실측", "추정")
F = F[["date", "close", "src"]].sort_values("date")

pre = F[F.src == "추정"]
print(f"\n전 구간 {len(F):,}일 · {F.date.iloc[0]}~{F.date.iloc[-1]} "
      f"(실측 {int((F.src=='실측').sum()):,} · 추정 {len(pre):,})")
print("  추정 구간 연평균: " + " · ".join(f"{y} {g.close.mean():.1f}" for y, g in pre.assign(y=pre.date.str[:4]).groupby("y")))
print("  추정 최고 5일: " + " · ".join(f"{d} {v:.1f}" for d, v in pre.nlargest(5, "close")[["date","close"]].values))

F.to_csv(BASE/"data"/"vkospi.csv", index=False, encoding="utf-8-sig")
con = sqlite3.connect(BASE/"data"/"feargreed.db")
con.execute("DROP TABLE IF EXISTS vkospi_full")
con.execute("CREATE TABLE vkospi_full(date TEXT PRIMARY KEY, close REAL, src TEXT)")
con.executemany("INSERT OR REPLACE INTO vkospi_full VALUES(?,?,?)", F.itertuples(index=False, name=None))
con.execute("CREATE TABLE IF NOT EXISTS vkospi(date TEXT PRIMARY KEY, close REAL, open REAL, high REAL, low REAL)")
con.executemany("INSERT OR REPLACE INTO vkospi(date,close) VALUES(?,?)",
                A[["date","close"]].itertuples(index=False, name=None))
con.commit(); con.close()
print("저장: data/vkospi.csv · feargreed.db(vkospi 실측 · vkospi_full 전구간)")
