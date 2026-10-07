# -*- coding: utf-8 -*-
"""유튜브 h9lOIfuTT-8 '600만원→4,000억 워뇨띠 실전 매매법 2편'(지표어때?, 2026-10-08) — 멀티 지표 동시 신호.
매수 = 아래가 **한 봉에서 동시에**:
  ① 슈퍼트렌드(ATR 10 · 3배) 상승 · ② 종가 > VWAP(장중 = 그날 누적 · 일봉 = 20일 거래량 가중) ·
  ③ 와다 아타 익스플로전 상승 폭발: t = (MACD(20,40) − 직전 MACD)×150 > 0, t > 볼린저 폭(20·2), t > 데드존(TR 100 이동평균×3.7) ·
  ④ 강한 양봉(몸통 ≥ 봉 범위 60%)
  (영상의 '수요존 근처·저항 약함' 은 사람 판단이라 빼고, '수요존 = 거래량 많던 자리' 근사로 ⑤ 그 봉 거래량 ≥ 20봉 평균 1.5배 판도 같이)
청산: 손절 = 최근 10봉 저점 아래 · 익절 1.5R(영상 최소) / 2R · 1R 오면 손절을 본전으로 · 장중은 장 끝 정리 · 일봉은 20일 정리.
표본: 5분·15분봉 = 국장 1분봉 무작위 300 · 미장 대형주(수집된 만큼) · 일봉 = 국장 폐지 포함 패널(kr_scan) 2016~.
비용: 장중 국장 0.23%+미끄러짐 0.05%×횟수 · 미장 0.20%+0.02% · 일봉 국장 패널 cost(0.58~1.38%).
    python research/yt_wonyo.py
"""
import json, sys, time, random
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import yt_scalp as Y
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def signals(o, h, l, c, v, vwap):
    n = len(c); s = pd.Series(c)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]), np.abs(l - np.r_[c[0], c[:-1]])))
    atr = pd.Series(tr).ewm(alpha=1 / 10, adjust=False).mean().values
    hl2 = (h + l) / 2; ub = hl2 + 3 * atr; lb = hl2 - 3 * atr
    fu, fl = ub.copy(), lb.copy(); up = np.ones(n, bool)
    for i in range(1, n):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        up[i] = (c[i] > fu[i - 1]) if not up[i - 1] else not (c[i] < fl[i - 1])
    macd = s.ewm(span=20, adjust=False).mean() - s.ewm(span=40, adjust=False).mean()
    t = ((macd - macd.shift(1)) * 150).values
    bbw = (2 * 2 * s.rolling(20).std()).values
    dead = pd.Series(tr).rolling(100, min_periods=30).mean().values * 3.7
    rng = h - l; body = c - o
    strong = (body > 0) & (rng > 0) & (body >= 0.6 * rng)
    sig = up & (c > vwap) & (t > 0) & (t > bbw) & (t > dead) & strong
    vol_ok = v >= 1.5 * pd.Series(v).rolling(20).mean().shift(1).values
    return sig, sig & vol_ok


def manage(o, h, l, c, i, px, stop, R, end):
    """1R 오면 본전 · 목표 R배 · end 봉 종가 정리. 반환 (수익%, 손절 미끄러짐 횟수)."""
    risk = px - stop; be = False; st = stop
    for j in range(i + 1, end + 1):
        if l[j] <= st: return (min(st, o[j]) / px - 1) * 100, 1
        if h[j] >= px + R * risk: return R * risk / px * 100, 0
        if not be and h[j] >= px + risk: st = px; be = True
    return (c[end] / px - 1) * 100, 0


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return []
    T = []
    for k in (5, 15):
        for d, g in D.groupby("date", sort=True):
            if len(g) < 300: continue
            n_ = np.arange(len(g)) // k
            b = g.assign(i=n_).groupby("i").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"))
            o, h, l, c, v = (b[x].values.astype(float) for x in ("o", "h", "l", "c", "v"))
            vw = np.cumsum(c * v) / np.maximum(np.cumsum(v), 1)
            s1, s2 = signals(o, h, l, c, v, vw)
            for lab, sg in (("4지표 동시", s1), ("4지표+거래량 1.5배", s2)):
                busy = -1
                for i in np.where(sg)[0]:
                    if i <= busy or i < 20 or i >= len(c) - 1: continue
                    stop = l[max(0, i - 10):i + 1].min() * 0.999; px = c[i]
                    if px - stop <= px * 0.001: continue
                    for R in (1.5, 2.0):
                        r, s = manage(o, h, l, c, i, px, stop, R, len(c) - 1)
                        T.append(("%d분 · %s · 익절 %.1fR" % (k, lab, R), d, r, 1 + s))
                    busy = i + 3
    return [(mk,) + x for x in T]


def daily_kr():
    import oc_day as O
    A, _ = O.build("KR")
    A = A[A.date >= "20150101"].sort_values(["ticker", "date"]).reset_index(drop=True)
    rows = []
    for t, g in A.groupby("ticker", sort=False):
        if len(g) < 150: continue
        o, h, l, c, v = (g[x].values.astype(float) for x in ("open", "high", "low", "close", "volume"))
        vw = (pd.Series(c * v).rolling(20).sum() / pd.Series(v).rolling(20).sum()).values
        s1, s2 = signals(o, h, l, c, v, np.nan_to_num(vw, nan=np.inf))
        dates = g.date.values; cost = np.full(len(g), 0.6); uni = g.uni.values      # 유동 유니버스 안 — 패널 cost 하위 구간(0.58%)
        for lab, sg in (("4지표 동시", s1), ("4지표+거래량 1.5배", s2)):
            busy = -1
            for i in np.where(sg & uni)[0]:
                if i <= busy or i < 120 or i + 21 >= len(c): continue
                px = o[i + 1]; stop = l[max(0, i - 10):i + 1].min() * 0.999
                if px - stop <= px * 0.003: continue
                for R in (1.5, 2.0):
                    r, s = manage(o, h, l, c, i, px, stop, R, i + 20)          # i+1 봉 시가에 사고 그 봉부터 본다
                    rows.append(("일봉(국장) · %s · 익절 %.1fR · 20일" % (lab, R), dates[i], r - cost[i]))
                busy = i + 20
    return pd.DataFrame(rows, columns=["s", "date", "ret"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    kr = sorted(k.split(":")[1] for k in done if k.startswith("KR:")); random.seed(7); kr = random.sample(kr, 300)
    us = sorted(k.split(":")[1] for k in done if k.startswith("US:"))
    jobs = [("KR", BASE / "data/m1/KR/bf" / (s + ".parquet")) for s in kr] + [("US", BASE / "data/m1/US/bf" / (s + ".parquet")) for s in us]
    jobs = [j for j in jobs if j[1].exists()]
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for r in ex.map(one, jobs, chunksize=4): rows += r
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip"])
    P("# 유튜브 워뇨띠 멀티 지표(슈퍼트렌드·VWAP·와다 아타·강한 양봉) 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 장중: 국장 무작위 %d · 미장 대형주 %d · 2022-12~ · 일봉: 국장 폐지 포함 패널 2016~ · 비용 뒤" % (len([j for j in jobs if j[0] == "KR"]), len([j for j in jobs if j[0] == "US"]))); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = Y.COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s 장중" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 기법 | 건수 | 비용 전 평균 | 학습 ~24: 평균·승률 | 검증 25~: 평균·승률 | 해마다(23·24·25·26) |"); P("|---|---|---|---|---|---|")
        for s, z in Z.groupby("s", sort=True):
            cell = []
            for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= b)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-")
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            P("| %s | %d | %+.3f%% | %s | %s | %s |" % (s, len(z), z.raw.mean(), cell[0], cell[1], " ".join("%+.2f" % x for x in yr.values)))
        P("")
    Dd = daily_kr()
    P("## 국장 일봉(스윙)"); P("")
    P("| 기법 | 건수 | 학습 2016~22: 평균·승률 | 검증 2023~: 평균·승률 | 해마다 플러스 |"); P("|---|---|---|---|---|")
    for s, z in Dd.groupby("s", sort=True):
        z = z[z.date >= "20160101"]
        cell = []
        for a, b in (("20160101", "20221231"), ("20230101", "20991231")):
            y = z[(z.date >= a) & (z.date <= b)]
            cell.append("%d건 %+.2f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-")
        yr = z.groupby(z.date.str[:4]).ret.mean()
        P("| %s | %d | %s | %s | %d/%d |" % (s, len(z), cell[0], cell[1], int((yr > 0).sum()), len(yr)))
    P(""); P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("yt_wonyo_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups) + Dd.s.nunique())
    (ROOT / "reports" / ("yt_wonyo_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
