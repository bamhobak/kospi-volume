# -*- coding: utf-8 -*-
"""스윙 규칙의 가격·거래량 '모양'을 1분·5분·10분봉에 옮겨 데이로 실측 (2026-10-07 사용자 "지금 스윙 규칙들 패턴으로 1·5·10분봉 데이에 대입").
옮길 수 없는 재료(자사주·실적·분사·S&P 편출 이벤트 · PBR · 외인·기관·공매도·신용 · 업종 지수)는 빼고 모양만 남긴다.
일봉 기준값은 그 종목 봉 변동성으로 환산한다 — 일봉에서 흔한 종목 하루 변동 3% 를 잣대로 'N일 x%' 를 z = x / (3%·√N) 로 바꾸고,
분봉에서는 같은 z 를 그 종목 직전 500봉 표준편차 σ·√N 에 곱한다(예: 20일 -25% → 20봉 수익률 ≤ -1.9σ√20).
시장 국면 = 지수 ETF 같은 봉 단위 이평(국장 KODEX200 069500 · 미장 SPY). 보유 = 규칙 보유일 수만큼 '봉' (하루 넘으면 그날 종가에 정리 — 데이).
매수 = 신호 봉 다음 봉 시가(시장가) · 매도 = N봉 뒤 종가(시장가) 또는 그날 마지막 봉(종가 단일가).
비용: 국장 0.23% + 시장가 한 번 0.05% · 미장 0.20% + 0.02%. 견줌 = 같은 종목·같은 봉 단위에서 아무 때나 사서 같은 봉 수 들고 있을 때 평균.
  R1 P1·N1 조용한 신고가: 지수 > 60봉 이평 · 240봉 고가 −0.2σ√240 안에 처음 진입 · 5봉 평균 거래량 ≤ 60봉의 0.8배 · 20봉 변동성 ≤ 직전 120봉 중앙 ·
     20봉 수익률 ≤ +0.4σ√20 · 종가가 5봉 이평 +0.3σ√5 안 → 40봉
  R2 P2 조정매집: 지수 < 20봉 이평 · 3봉 ≤ −1σ√3 · 10봉 ≤ 0 · 5봉 평균 거래량 ≥ 20봉의 2배 · 20봉 평균 ≤ 120봉의 0.6배 → 10봉
  R3 P3·D1·N2 낙폭과대: 지수 < 60봉 이평 · 20봉 ≤ −2σ√20 · 그 봉 거래량 ≥ 20봉 평균 1.5배 → 20봉
  R4 P4 이탈: 지수 < 60봉 이평 · 20봉 이평 이격 ≤ −0.75σ√20 · 60봉 최대낙폭 ≤ −1.7σ√60 → 5봉
  R5 P6 깊은 이격: 지수 < 60봉 이평 · 25봉 이평 이격 ≤ −2.4σ√12 → 5봉
  R6 D2·N3 낙폭(재무 뺀 골격): 지수 < 60봉 이평 · 20봉 ≤ −0.75σ√20 · 그 봉 거래량 ≥ 20봉 평균 2배 → 40봉
  R7 N5 잔잔한 급등주: 250봉 ≥ +2.5σ√250 · 60·120·250봉 모두 플러스 · 60봉 평균 |봉 등락| ≤ 직전 500봉의 30% 분위 · 처음 진입 → 60봉
  R8 P7 가격 골격: 지수 > 60봉 이평 · 250봉 고가 −0.3σ√250 안 · 250봉 저가 대비 위 · 20봉 평균 거래량이 120봉의 1.0~1.5배 → 60봉
    python research/swing2day.py
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
TFS = (1, 5, 10)
IDX = {"KR": "069500", "US": "SPY"}


def series(D, k):
    """하루 안에서만 k 분씩 묶은 봉을 날짜 순으로 이어 붙인다. last = 그날 마지막 봉."""
    D = D.copy(); D["i"] = D.groupby("date").cumcount() // k
    B = D.groupby(["date", "i"], sort=True).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"), hm=("hm", "last")).reset_index()
    B["eod"] = B.date != B.date.shift(-1)
    return B


def feats(B):
    c = B.c; r = c.pct_change()
    sig = r.rolling(500, min_periods=200).std().shift(1)
    f = {"sig": sig}
    for n in (3, 10, 20, 60, 120, 250):
        f["r%d" % n] = c / c.shift(n) - 1
    for n in (5, 20, 25, 60):
        f["ma%d" % n] = c.rolling(n).mean()
    f["hi240"] = B.h.rolling(240).max(); f["hi250"] = B.h.rolling(250).max(); f["lo250"] = B.l.rolling(250).min()
    f["v5"] = B.v.rolling(5).mean(); f["v20"] = B.v.rolling(20).mean(); f["v60"] = B.v.rolling(60).mean(); f["v120"] = B.v.rolling(120).mean()
    f["vol20"] = r.rolling(20).std(); f["vol20med"] = f["vol20"].rolling(120).median().shift(1)
    f["absm60"] = r.abs().rolling(60).mean(); f["absq30"] = r.abs().rolling(500, min_periods=200).quantile(0.3).shift(1)
    f["dd60"] = c / c.rolling(60).max() - 1
    return pd.DataFrame(f)


def rules(B, F, up60, up20):
    s = F.sig; q = lambda n: s * np.sqrt(n)
    c = B.c
    R = {}
    z1 = (c >= F.hi240 * (1 - 0.2 * q(240))) & (F.v5 <= 0.8 * F.v60) & (F.vol20 <= F.vol20med) & (F.r20 <= 0.4 * q(20)) & ((c / F.ma5 - 1).abs() <= 0.3 * q(5))
    R["R1 P1·N1 조용한 신고가"] = (z1 & ~z1.shift(1, fill_value=False) & up60, 40)
    R["R2 P2 조정매집"] = ((~up20) & (F.r3 <= -1 * q(3)) & (F.r10 <= 0) & (F.v5 >= 2 * F.v20) & (F.v20 <= 0.6 * F.v120), 10)
    R["R3 P3·D1·N2 낙폭과대"] = ((~up60) & (F.r20 <= -2 * q(20)) & (B.v >= 1.5 * F.v20), 20)
    R["R4 P4 이탈"] = ((~up60) & ((c / F.ma20 - 1) <= -0.75 * q(20)) & (F.dd60 <= -1.7 * q(60)), 5)
    R["R5 P6 깊은 이격"] = ((~up60) & ((c / F.ma25 - 1) <= -2.4 * q(12)), 5)
    R["R6 D2·N3 낙폭 골격"] = ((~up60) & (F.r20 <= -0.75 * q(20)) & (B.v >= 2 * F.v20), 40)
    z7 = (F.r250 >= 2.5 * q(250)) & (F.r60 > 0) & (F.r120 > 0) & (F.absm60 <= F.absq30)
    R["R7 N5 잔잔한 급등주"] = (z7 & ~z7.shift(1, fill_value=False), 60)
    R["R8 P7 가격 골격"] = (up60 & (c >= F.hi250 * (1 - 0.3 * q(250))) & (c > F.lo250) & (F.v20 >= F.v120) & (F.v20 <= 1.5 * F.v120), 60)
    return R


def index_regime(mk, k):
    D = Y.load(mk, BASE / "data/m1" / mk / "bf" / (IDX[mk] + ".parquet"))
    B = series(D, k)
    B["up60"] = B.c > B.c.rolling(60).mean(); B["up20"] = B.c > B.c.rolling(20).mean()
    return B.set_index(["date", "i"])[["up60", "up20"]]


_IR = {}


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return [], []
    D = D[D.groupby("date").ts.transform("size") >= 300]
    if D.date.nunique() < 30: return [], []
    T, BASEL = [], []
    for k in TFS:
        key = (mk, k)
        if key not in _IR: _IR[key] = index_regime(mk, k)
        B = series(D, k); F = feats(B)
        ir = _IR[key].reindex(pd.MultiIndex.from_arrays([B.date, B.i]))
        up60 = pd.Series(ir.up60.values, index=B.index).fillna(False).astype(bool)
        up20 = pd.Series(ir.up20.values, index=B.index).fillna(False).astype(bool)
        o, c, last, dates = B.o.values, B.c.values, B.eod.values, B.date.values
        n = len(c)
        # 그날 마지막 봉 위치
        lastpos = np.where(last)[0]; li = np.searchsorted(lastpos, np.arange(n)); dayend = lastpos[np.minimum(li, len(lastpos) - 1)]
        for name, (sig, H) in rules(B, F, up60, up20).items():
            idx = np.where(sig.fillna(False).values & F.sig.notna().values)[0]
            busy = -1
            for i in idx:
                if i <= busy or last[i] or i + 1 >= n: continue
                e = i + 1; x = min(e + H - 1, dayend[i])
                ret = (c[x] / o[e] - 1) * 100; ns = 1 + (0 if last[x] else 1)
                T.append((mk, k, name, H, dates[i], ret, ns)); busy = x
        # 견줌: 아무 봉에서나 다음 봉 시가에 사서 H 봉(그날 넘지 않게)
        for H in (5, 10, 20, 40, 60):
            e = np.arange(1, n); e = e[~last[e - 1]]
            x = np.minimum(e + H - 1, dayend[e - 1])
            rr = (c[x] / o[e] - 1) * 100; ns = 1 + (~last[x]).astype(int)
            yr = pd.Series(dates[e - 1]).str[:4].values
            for y in np.unique(yr):
                m = yr == y
                BASEL.append((mk, k, H, y, rr[m].sum(), ns[m].sum(), m.sum()))
    return T, BASEL


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    kr = sorted(k.split(":")[1] for k in done if k.startswith("KR:") and k.split(":")[1] not in ("069500", "229200")); random.seed(11); kr = random.sample(kr, 200)
    us = sorted(k.split(":")[1] for k in done if k.startswith("US:") and k.split(":")[1] not in ("SPY", "QQQ"))
    jobs = [("KR", BASE / "data/m1/KR/bf" / (s + ".parquet")) for s in kr] + [("US", BASE / "data/m1/US/bf" / (s + ".parquet")) for s in us]
    jobs = [j for j in jobs if j[1].exists()]
    rows, bl = [], []
    with ProcessPoolExecutor(6) as ex:
        for i, (r, b) in enumerate(ex.map(one, jobs, chunksize=4)):
            rows += r; bl += b
            if (i + 1) % 100 == 0: print("  %d/%d · %.1f분" % (i + 1, len(jobs), (time.time() - t0) / 60), flush=True)
    R = pd.DataFrame(rows, columns=["mk", "tf", "s", "H", "date", "raw", "nslip"])
    BL = pd.DataFrame(bl, columns=["mk", "tf", "H", "yr", "sum", "nsl", "n"])
    R.to_pickle(ROOT / "cache" / "swing2day.pkl")
    P("# 스윙 규칙 모양 → 1·5·10분봉 데이 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 무작위 %d · 미장 대형주 %d · 2022-12~2026-10 · 비용 뒤(국장 0.23%%+시장가 0.05%%×횟수 · 미장 0.20%%+0.02%%) · 학습 ~2024 / 검증 2025~" % (
        len([j for j in jobs if j[0] == "KR"]), len([j for j in jobs if j[0] == "US"])))
    P("- '아무 때나' = 같은 종목·같은 봉 단위에서 아무 봉에 사서 같은 봉 수(그날 안) 들고 있을 때 비용 뒤 평균"); P("")
    for mk in ("KR", "US"):
        fee, sl = Y.COST[mk]
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 규칙 모양 | 봉 | 건수 | 학습 ~24: 평균·승률 | 검증 25~: 평균·승률 | 해마다(23·24·25·26) | 아무 때나(같은 보유) | 판정 |"); P("|---|---|---|---|---|---|---|---|")
        for (s, tf), z in R[R.mk == mk].groupby(["s", "tf"], sort=True):
            z = z.copy(); z["ret"] = z.raw - fee - sl * z.nslip
            H = int(z.H.iloc[0]); b = BL[(BL.mk == mk) & (BL.tf == tf) & (BL.H == H)]
            base = (b["sum"].sum() - fee * b.n.sum() - sl * b.nsl.sum()) / max(b.n.sum(), 1)
            cell, mm = [], []
            for a, bb in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= bb)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-"); mm.append(y.ret.mean() if len(y) >= 30 else np.nan)
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            ok = all(m == m and m > 0 for m in mm) and (yr > 0).sum() >= len(yr) - 1
            P("| %s | %d분 | %d | %s | %s | %s | %+.3f%% | %s |" % (s, tf, len(z), cell[0], cell[1], " ".join("%+.2f" % v for v in yr.values), base, "✅ 후보" if ok else "—"))
        P("")
    P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("swing2day_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s", "tf"]).ngroups))
    (ROOT / "reports" / ("swing2day_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
