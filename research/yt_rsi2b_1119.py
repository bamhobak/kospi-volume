# -*- coding: utf-8 -*-
"""유튜브 '로스 카메론 RSI 쌍바닥 매매법'(매매법아카이브 lxz7Csyg9bk, 2026-11-19 사용자 링크) 실측.
영상의 4단계(롱, 1시간봉·RSI 14·볼린저 20,2 기본값):
  ① RSI < 30 ② 하락 장악형 또는 음봉 3개 연속이 하단 밴드 밖에서 끝남(첫 바닥) ③ 앞 음봉을 덮는 상승 장악형
  ④ 다시 눌린 두 번째 바닥이 밴드 **안**에서 버티고 상승 장악형 → 그 봉 종가 매수 · 손절 = 두 번째 바닥 저가 · 목표 = 손절 폭 3배. 숏은 거울.
잰 곳: 비트코인 1시간봉(영상 그대로, Binance BTCUSDT 2017-08~) · 국장 1시간봉(1분봉 2022-12~ 거래대금 상위 500종목) · 국장 일봉(2016~, 변형).
변형: 첫 바닥 정의(엄격 = 영상 / 느슨 = 영상 속 지표 'RSI<30 & 밴드 밖 종가') · 목표 1·2·3배 · 숏(거울).
대조: (가) RSI<30·밴드 밖 봉 종가에 바로 사기 (나) 쌍바닥 진입 — 둘 다 같은 고정 보유로 · (다) 아무 상승 장악형에 같은 손절·목표.
    python research/memguard.py research/yt_rsi2b_1119.py → research/reports/yt_rsi2b_1119.md"""
import json, math, pickle, sys, time, urllib.request
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
TMP = Path("C:/temp/kp"); OUT = []
def P_(s=""):
    OUT.append(s); print(s, flush=True)
def t_(s):
    s = pd.Series(s).dropna()
    return s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
W1, W2 = 12, 24                                   # 첫 바닥 → 첫 장악형까지 · 첫 장악형 → 두 번째 장악형까지 기다리는 봉 수

def prep(o, h, l, c):
    cs = pd.Series(c); d = cs.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(100).where(up.notna()).values
    mid = cs.rolling(20).mean().values; sd = cs.rolling(20).std(ddof=0).values
    lo = mid - 2 * sd
    bear = c < o; bull = c > o
    pb = np.r_[False, bear[:-1]]; po = np.r_[np.nan, o[:-1]]; pc = np.r_[np.nan, c[:-1]]
    bull_eng = pb & bull & (o <= pc) & (c >= po)
    pbull = np.r_[False, bull[:-1]]
    bear_eng = pbull & bear & (o >= pc) & (c <= po)
    three = bear & pb & np.r_[False, pb[:-1]]
    out = (c < lo) & np.isfinite(lo)
    A_strict = (rsi < 30) & out & (bear_eng | three)
    A_loose = (rsi < 30) & out
    return dict(rsi=rsi, lo=lo, bull_eng=bull_eng, out=out, bear=bear, A_strict=A_strict, A_loose=A_loose)

def exit_sim(o, h, l, c, e, stop, tgt, cap):
    n = len(c)
    for t in range(e + 1, min(e + 1 + cap, n)):
        if not np.isfinite(o[t]): continue
        if o[t] <= stop: return o[t], t
        if l[t] <= stop: return stop, t
        if o[t] >= tgt: return o[t], t
        if h[t] >= tgt: return tgt, t
    t = min(e + cap, n - 1)
    return c[t], t

def run(o, h, l, c, side=1, strict=True, k=3.0, cap=60, fix=8):
    """한 시계열의 거래 목록 — (진입 색인, 수익 %, R, 고정 보유 수익 %, 손절 폭 %). side=-1 은 값에 -1 을 곱해 거울로."""
    if side < 0: o, h, l, c = -o, -l, -h, -c
    F = prep(o, h, l, c); A = F["A_strict"] if strict else F["A_loose"]
    n = len(c); res = []; naive = []; busy = -1
    idx = np.flatnonzero(A)
    for a in idx:
        if fix and a + fix < n and np.isfinite(c[a + fix]): naive.append((a, (c[a + fix] - c[a]) / abs(c[a]) * 100))
        if a <= busy: continue
        t = a + 1; b = -1; lim = a + W1
        while t < n and t <= lim:                                  # 첫 상승 장악형
            if F["bull_eng"][t]: b = t; break
            t += 1
        if b < 0: continue
        t = b + 1; lim = b + W2; had = False; e = -1; low2 = np.inf
        while t < n and t <= lim:
            low2 = min(low2, l[t])
            if F["out"][t]:                                        # 두 번째 바닥이 밴드 밖으로 나감 → 다시 첫 바닥부터
                b2 = -1; u = t + 1
                while u < n and u <= t + W1:
                    if F["bull_eng"][u]: b2 = u; break
                    u += 1
                if b2 < 0: break
                b = b2; t = b + 1; lim = b + W2; had = False; low2 = np.inf; continue
            if F["bear"][t]: had = True
            if F["bull_eng"][t] and had: e = t; break
            t += 1
        if e < 0: continue
        ent = c[e]; risk = ent - low2
        if not (risk > 0) or risk / abs(ent) < 0.001: continue
        px, x = exit_sim(o, h, l, c, e, low2, ent + k * risk, cap)
        fr = (c[e + fix] - ent) / abs(ent) * 100 if fix and e + fix < n and np.isfinite(c[e + fix]) else np.nan
        res.append((e, (px - ent) / abs(ent) * 100, (px - ent) / risk, fr, risk / abs(ent) * 100)); busy = x
    return res, naive

def plain(o, h, l, c, k=3.0, cap=60, step=7):
    """대조(다): 맥락 없이 아무 상승 장악형 — 손절 = 직전 5봉 저가, 같은 목표·같은 청산."""
    F = prep(o, h, l, c); res = []; busy = -1
    for e in np.flatnonzero(F["bull_eng"])[::step]:
        if e <= busy or e < 6: continue
        ent = c[e]; stop = np.nanmin(l[e - 4:e + 1]); risk = ent - stop
        if not (risk > 0) or risk / ent < 0.001: continue
        px, x = exit_sim(o, h, l, c, e, stop, ent + k * risk, cap)
        res.append((e, (px - ent) / ent * 100, (px - ent) / risk, np.nan, risk / ent * 100)); busy = x
    return res

# ── 자료 ─────────────────────────────────────────────────────────────
def btc():
    f = TMP / "yt_btc_1h.pkl"
    if f.exists(): return pd.read_pickle(f)
    rows = []; s = 1502928000000
    while True:
        u = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=1000&startTime=%d" % s
        j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
        if not j: break
        rows += [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in j]
        if len(j) < 1000: break
        s = j[-1][0] + 1; time.sleep(0.25)
    X = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c"]).drop_duplicates("ts")
    X["day"] = pd.to_datetime(X.ts, unit="ms").dt.strftime("%Y%m%d"); X.to_pickle(f); return X

def kr1h():
    f = TMP / "yt_kr_1h.pkl"
    if f.exists(): return pickle.load(open(f, "rb"))
    M = pd.read_pickle(BASE / "research" / "cache" / "m1_panel_KR.pkl")[["ticker", "amt", "c"]]
    g = M.groupby("ticker").agg(a=("amt", "mean"), c=("c", "last"), n=("amt", "size"))
    top = g[(g.c >= 2000) & (g.n >= 250)].sort_values("a", ascending=False).head(500).index.tolist()
    D = {}
    for k, t in enumerate(top):
        p = BASE / "data" / "m1" / "KR" / "bf" / (t + ".parquet")
        if not p.exists(): continue
        B = pd.read_parquet(p, columns=["ts", "o", "h", "l", "c", "v"]); B = B[B.v > 0]
        kk = pd.to_datetime(B.ts.values + 9 * 3600, unit="s"); mi = (kk.hour * 60 + kk.minute).values - 541
        ok = (mi >= 0) & (mi <= 390); B = B[ok]
        B = B.assign(day=kk.strftime("%Y%m%d")[ok], b=np.minimum(mi[ok] // 60, 6))
        H = B.groupby(["day", "b"], sort=True).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).reset_index()
        D[t] = H
        if k % 100 == 0: print("  1시간봉", k, t, len(H), flush=True)
    pickle.dump(D, open(f, "wb")); return D

def daily():
    P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); P = P[P.date >= "20150101"]
    return {t: g for t, g in P.groupby("ticker", sort=False) if len(g) > 300 and g.close.iloc[-1] >= 2000}

def collect(series, cost, cap, fix, split, **kw):
    """series: (이름, o,h,l,c, day 배열) 들 → 거래 표."""
    R = []; N = []
    for nm, o, h, l, c, day in series:
        for side in (1, -1):
            for strict in (True, False):
                res, naive = run(o, h, l, c, side=side, strict=strict, cap=cap, fix=fix, **kw)
                R += [(nm, side, strict, day[e], r - cost, rr, fr - cost if fr == fr else np.nan, w) for e, r, rr, fr, w in res]
                N += [(nm, side, strict, day[a], r - cost) for a, r in naive]
    T = pd.DataFrame(R, columns=["nm", "side", "strict", "day", "r", "R", "fix", "risk"]); Nv = pd.DataFrame(N, columns=["nm", "side", "strict", "day", "r"])
    return T, Nv

def line(z, col="r"):
    z = z.dropna(subset=[col])
    if len(z) < 20: return "%d | – | – | –" % len(z)
    d = z.groupby("day")[col].mean()
    return "%d | %+.2f%% (%+.2f·%.0f%%) | %+.2f%% (t%.1f) | %s" % (len(z), z[col].mean(), z[col].median(), (z[col] > 0).mean() * 100, d.mean(), t_(d), ("%+.2f" % z.R.mean()) if "R" in z and col == "r" else "–")

def report(title, T, Nv, PL, split, cost, fixlab):
    P_("\n## %s\n" % title)
    P_("비용 %.2f%% 뺀 값 · 학습 %s / 검증 %s\n" % (cost, split[0], split[1]))
    P_("| 판 | 학습 건 | 건당(중앙·승률) | 날 바구니(t) | 평균 R | 검증 건 | 건당(중앙·승률) | 날 바구니(t) | 평균 R |\n|---|---|---|---|---|---|---|---|---|")
    cut = split[2]
    def both(z, col="r"): return line(z[z.day < cut], col) + " | " + line(z[z.day >= cut], col)
    for side, sl in ((1, "롱"), (-1, "숏(거울)")):
        for strict, st in ((True, "영상 그대로"), (False, "느슨한 첫 바닥")):
            z = T[(T.side == side) & (T.strict == strict)]
            P_("| 쌍바닥 %s · %s · 손절/목표 3배 | %s |" % (sl, st, both(z)))
    z = T[(T.side == 1) & T.strict]
    P_("| (나) 쌍바닥 롱 진입 뒤 %s 고정 보유 | %s |" % (fixlab, both(z, "fix")))
    P_("| (가) RSI<30·밴드 밖 봉 종가에 바로 사서 %s 보유 | %s |" % (fixlab, both(Nv[(Nv.side == 1) & Nv.strict])))
    P_("| (다) 아무 상승 장악형 · 같은 손절/목표 3배 | %s |" % both(PL))
    z = T[(T.side == 1) & T.strict]
    if len(z): P_("\n쌍바닥 롱(영상 그대로): 손절 폭 중앙 %.2f%% · 목표 닿은 비율 %.0f%% · 손절 닿은 비율 %.0f%%" % (z.risk.median(), (z.R >= 2.99).mean() * 100, (z.R <= -0.99).mean() * 100))
    P_("\n| 해 | 건 | 건당 | 승률 | 평균 R |\n|---|---|---|---|---|")
    for y, g in z.groupby(z.day.str[:4]): P_("| %s | %d | %+.2f%% | %.0f%% | %+.2f |" % (y, len(g), g.r.mean(), (g.r > 0).mean() * 100, g.R.mean()))

def main():
    P_("# 유튜브 '로스 카메론 RSI 쌍바닥' 실측 (2026-11-19 · 영상 lxz7Csyg9bk)\n")
    P_("영상 규칙: RSI<30 → 음봉 3연속/하락 장악형이 하단 밴드 밖에서 끝남 → 상승 장악형 → 두 번째 바닥이 밴드 안 → 상승 장악형 종가 매수 · 손절 두 번째 바닥 저가 · 목표 3배.")
    B = btc(); s = [("BTC", B.o.values, B.h.values, B.l.values, B.c.values, B.day.values)]
    T, Nv = collect(s, 0.10, 72, 12, None)
    PL = pd.DataFrame([("BTC", 1, True, B.day.values[e], r - 0.10, rr, np.nan, w) for e, r, rr, fr, w in plain(B.o.values, B.h.values, B.l.values, B.c.values, cap=72, step=1)], columns=T.columns)
    report("비트코인 1시간봉 (영상 그대로 · %s~%s · %d봉)" % (B.day.iloc[0], B.day.iloc[-1], len(B)), T, Nv, PL, ("2017-08~2022", "2023~", "20230101"), 0.10, "12시간")
    for k in (1.0, 2.0):
        Tk, _ = collect(s, 0.10, 72, 0, None, k=k); z = Tk[(Tk.side == 1) & Tk.strict]
        P_("- 목표 %.0f배(롱·영상 그대로): 학습 %s || 검증 %s" % (k, line(z[z.day < "20230101"]), line(z[z.day >= "20230101"])))
    K = kr1h(); s = [(t, H.o.values.astype(float), H.h.values.astype(float), H.l.values.astype(float), H.c.values.astype(float), H.day.values) for t, H in K.items() if len(H) > 400]
    T, Nv = collect(s, 0.28, 70, 7, None)
    PL = pd.DataFrame([(nm, 1, True, day[e], r - 0.28, rr, np.nan, w) for nm, o, h, l, c, day in s for e, r, rr, fr, w in plain(o, h, l, c, cap=70, step=5)], columns=T.columns)
    report("국장 1시간봉 (거래대금 상위 %d종목 · 2022-12~)" % len(s), T, Nv, PL, ("2022-12~2024", "2025~", "20250101"), 0.28, "7봉(하루)")
    for k in (1.0, 2.0):
        Tk, _ = collect(s, 0.28, 70, 0, None, k=k); z = Tk[(Tk.side == 1) & Tk.strict]
        P_("- 목표 %.0f배(롱·영상 그대로): 학습 %s || 검증 %s" % (k, line(z[z.day < "20250101"]), line(z[z.day >= "20250101"])))
    del K
    Dy = daily(); s = [(t, g.open.values.astype(float), g.high.values.astype(float), g.low.values.astype(float), g.close.values.astype(float), g.date.values) for t, g in Dy.items()]
    s = [(nm, np.where(np.isfinite(o), o, c), np.where(np.isfinite(h), h, c), np.where(np.isfinite(l), l, c), c, d) for nm, o, h, l, c, d in s]
    T, Nv = collect(s, 0.23, 40, 5, None); T = T[T.day >= "20160101"]; Nv = Nv[Nv.day >= "20160101"]
    PL = pd.DataFrame([(nm, 1, True, day[e], r - 0.23, rr, np.nan, w) for nm, o, h, l, c, day in s for e, r, rr, fr, w in plain(o, h, l, c, cap=40, step=5)], columns=T.columns); PL = PL[PL.day >= "20160101"]
    report("국장 일봉 (변형 · 종가 2,000원↑ %d종목 · 2016~)" % len(s), T, Nv, PL, ("2016~22", "2023~", "20230101"), 0.23, "5일")
    P_("\n- 날 바구니 = 같은 날 진입을 하루 한 표본으로. 평균 R = 손절 폭을 1로 본 손익. 한 봉에서 손절·목표가 같이 닿으면 손절로 셈(보수).")
    P_("- 국장 숏은 실제로는 못 한다(거울로 재기만). 국장 1시간봉은 09~10·…·14~15·15~15:30 일곱 봉, 밤사이 갭은 다음 봉 시가로 손절·목표 처리.")
    P_("- 비트코인 비용 0.10%는 선물 시장가 왕복 기준. 영상의 '6% 수익' 장면은 잘 맞은 사례만 고른 것이다.")
    (ROOT / "reports" / "yt_rsi2b_1119.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
