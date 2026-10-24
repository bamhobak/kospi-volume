# -*- coding: utf-8 -*-
"""⑪ 2차 — NXT 장후 '마지막 한 건' 착시 걷어내기 (2026-10-25).
1차(nxt_after.py): 장후 -1%↓ 빠진 대형주를 장후 종가에 사서 다음 날 KRX 시가에 팔면 비용 뒤 학습 +0.21·검증 +0.97.
그런데 토스 일봉 종가 = 장후 마지막 한 건 → 얇은 호가의 싼 체결 한 건이면 시가 '되돌림'은 호가 튕김 착시일 수 있다.
그래서 장후 1분봉(토스 1m 에 16:41~20:00 봉이 있다)으로:
  신호  = 19:50 봉 종가 / KRX 종가 - 1 (AH50) · rel50 = AH50 - 그날 표본 대형주 평균
  매수  = ① 19:51~20:00 VWAP  ② 같은 구간 최고가(가장 비싸게 산 경우)
  매도  = 다음 날 KRX 시가(1분봉 첫 봉 시가)  · 비용 왕복 0.23%
표본: 1차 대형주 120종목 중 일봉 장후 ≤ -0.5% 인 날 전부 + 대조로 나머지에서 무작위 3,000(같은 잣대로 '아무 날').
    python research/nxt_after2.py
"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
import collect_m1 as M
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CK = 0.23
TR, VA = ("20250301", "20251231"), ("20260101", "20991231")
NC = [0]
CACHE = ROOT / "cache" / "ah_m1.parquet"


def bars(t, d):
    b = "%s-%s-%sT20:01:00.000+09:00" % (d[:4], d[4:6], d[6:])
    c = (M.get("/api/v1/candles", symbol=t, interval="1m", count=200, before=b) or {}).get("candles") or []
    out = []
    for x in c:
        ts = x["timestamp"]
        if ts[:10].replace("-", "") != d: continue
        hm = int(ts[11:13]) * 100 + int(ts[14:16])
        if hm < 1541: continue
        out.append((t, d, hm, float(x["highPrice"]), float(x["closePrice"]), float(x["volume"])))
    return out


def cell(x, cost):
    x = pd.Series(x).dropna() - cost
    if len(x) < 15: return "%d건" % len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return "%+.3f (%d%% · %d · t%.1f)" % (x.mean(), (x > 0).mean() * 100, len(x), t)


def row(lab, df, col, cost=CK):
    NC[0] += 1
    a = df[(df.d >= TR[0]) & (df.d <= TR[1])]; b = df[df.d >= VA[0]]
    P("| %s | %s | %s |" % (lab, cell(a[col], cost), cell(b[col], cost)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")
    T = pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet")
    X = D[["t", "d", "o", "c"]].merge(T, on=["t", "d"]).sort_values(["t", "d"])
    X = X[X.d >= "20250301"].copy()
    X["AH"] = (X.tc / X.c - 1) * 100
    X["o1"] = X.groupby("t").o.shift(-1)
    X = X.dropna(subset=["o1"]).copy()
    sig = X[X.AH <= -0.5]
    rest = X[X.AH > -0.5].sample(n=min(3000, (X.AH > -0.5).sum()), random_state=7)
    need = pd.concat([sig, rest])[["t", "d"]].drop_duplicates()
    have = pd.read_parquet(CACHE) if CACHE.exists() else pd.DataFrame(columns=["t", "d", "hm", "h", "c", "v"])
    done = set(zip(have.t, have.d))
    todo = [(t, d) for t, d in zip(need.t, need.d) if (t, d) not in done]
    print("장후 1분봉 받기 %d건(있음 %d)" % (len(todo), len(done)), flush=True)
    rows = []
    for i, (t, d) in enumerate(todo):
        try:
            rows += bars(t, d)
        except Exception as e:
            print("실패", t, d, e, flush=True)
        if i % 300 == 299:
            have = pd.concat([have, pd.DataFrame(rows, columns=have.columns)], ignore_index=True); rows = []
            have.to_parquet(CACHE); print("%d/%d %.0fs" % (i + 1, len(todo), time.time() - t0), flush=True)
    if rows:
        have = pd.concat([have, pd.DataFrame(rows, columns=have.columns)], ignore_index=True); have.to_parquet(CACHE)
    B = have.copy()
    B["hm"] = B.hm.astype(int)
    p50 = B[B.hm <= 1950].sort_values("hm").groupby(["t", "d"]).c.last().rename("p50")
    L = B[(B.hm >= 1951) & (B.hm <= 2000)]
    vw = (L.c * L.v).groupby([L.t, L.d]).sum() / L.v.groupby([L.t, L.d]).sum().replace(0, np.nan)
    hi = L.groupby(["t", "d"]).h.max()
    v10 = (L.c * L.v).groupby([L.t, L.d]).sum()
    F = pd.concat([p50, vw.rename("vw"), hi.rename("hi"), v10.rename("amt10")], axis=1).reset_index()
    Z = X.merge(F, on=["t", "d"], how="inner")
    Z["AH50"] = (Z.p50 / Z.c - 1) * 100
    Z["rel50"] = Z.AH50 - Z.groupby("d").AH50.transform("mean")
    Z["r_vw"] = (Z.o1 / Z.vw - 1) * 100
    Z["r_hi"] = (Z.o1 / Z.hi - 1) * 100
    Z["r_last"] = (Z.o1 / Z.tc - 1) * 100
    ctrl = Z.merge(rest[["t", "d"]], on=["t", "d"])
    P("# ⑪ 2차 — NXT 장후 1분봉으로 다시 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 표본 %d행(장후 ≤ -0.5%% 날 %d + 대조 무작위 %d) · 19:51~20:00 거래대금 중앙 %.0f만원 · 칸 = 비용 뒤 %% (승률 · 건수 · t)" % (
        len(Z), len(sig), len(rest), Z.amt10.median() / 1e4)); P("")
    P("| 조건 · 매수가 | 학습 2025-03~12 | 검증 2026~ |"); P("|---|---|---|")
    row("대조 · 아무 날 · VWAP 매수", ctrl, "r_vw")
    row("대조 · 아무 날 · 최고가 매수", ctrl, "r_hi")
    for th in (1.0, 1.5, 2.0):
        z = Z[Z.AH50 <= -th]
        row("19:50 에 KRX 종가 대비 -%.1f%%↓ · 마지막 체결(1차와 같음)" % th, z, "r_last")
        row("　└ 19:51~20:00 VWAP 매수", z, "r_vw")
        row("　└ 19:51~20:00 최고가 매수(가장 비싸게)", z, "r_hi")
        z = Z[Z.rel50 <= -th]
        row("19:50 에 표본 평균보다 %.1f%%p↓ · VWAP" % th, z, "r_vw")
        row("　└ 최고가 매수", z, "r_hi")
    z = Z[(Z.AH50 <= -1.0) & (Z.amt10 >= 5e7)]
    row("-1%%↓ & 마지막 10분 거래대금 5천만↑ · VWAP", z, "r_vw")
    row("　└ 최고가 매수", z, "r_hi")
    P("")
    zz = Z[Z.AH50 <= -1.0]
    m = zz.groupby(zz.d.str[:6]).r_vw.agg(["mean", "size"])
    P("월별(-1%↓ · VWAP · 비용 전): " + " · ".join("%s %+.2f(%d)" % (k[2:], r["mean"], r["size"]) for k, r in m.iterrows())); P("")
    P("(칸 %d · %.1f분)" % (NC[0], (time.time() - t0) / 60))
    log_trials("nxt_after2_%s" % time.strftime("%Y%m%d"), NC[0])
    (ROOT / "reports" / ("nxt_after2_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
