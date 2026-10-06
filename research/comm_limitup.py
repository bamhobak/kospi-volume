# -*- coding: utf-8 -*-
"""국장 커뮤니티 기법 셋 — 상한가 소형주 이벤트 + 일봉 (2026-10-07, comm_day 의 짝).
  18 상따(시가형) — 다음카페 stockpapa·브런치: 그날 처음 상한가(전날은 상한가 아님)에 10시 전 닿으면 상한가로 매수 →
     상한가가 풀리면(1분봉 종가가 상한가 아래) 그 종가에 손절 / 끝까지 지키면 다음날 시가 매도.
     체결 가정 둘: (낙관) 처음 닿을 때 체결 · (보수) 한 번 풀렸다 다시 닿을 때만 체결(대기열은 풀릴 때 체결된다 — 1분봉으로는 못 본다)
  19 상한가 다음날 눌림 — tilnote: 전날 상한가 마감 → 오늘 전날 종가(=상한가 가격)까지 눌렸다가 3분봉이 그 위로 다시 마감하면 매수 ·
     전날 종가 −1% 이탈 손절 · 장 끝
  22 장대양봉 갭 구간(SLR '승률 90%') — 일봉: D 몸통 +5%↑ 양봉 & 종가가 20일선 위 & 거래대금 30억↑ · D+1 이 D 종가보다 1.8%↑ 위에서 갭 출발·마감 →
     D+2~D+11 에 D+1 저가(갭 위 끝)까지 내려오면 지정가 매수(D 종가 아래로 갭 열면 시가) · +2% 익절 · 손절 없음(영상) → 10일 지나면 종가 정리 /
     넓은 판: D 종가 −3% 손절. 일봉(폐지 포함 kr_scan) 2016~.
1분봉은 이벤트 날만 토스에서 받는다(m1_event) — 폐지 종목은 못 받아 빠진다(수를 적는다). 18·19 는 2022-12~ · 이벤트 무작위 최대 4,000.
비용 0.23%(단일가·지정가) + 장중 시장가 손절 0.05%.
    python research/comm_limitup.py
"""
import sys, time, random
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import oc_day as O, m1_event as E
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
FEE, SLIP = 0.23, 0.05


def tick(p):
    for lim, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if p < lim: return t
    return 1000


def uplimit(pc):
    x = pc * 1.3; t = tick(x)
    return np.floor(x / t) * t


def stats(lab, rows):
    if not rows: P("| %s | 0 | | | |" % lab); return
    Z = pd.DataFrame(rows, columns=["date", "ret"])
    cells = []
    for a, b in (("20160101", "20221231"), ("20230101", "20991231")):
        z = Z[(Z.date >= a) & (Z.date <= b)]
        cells.append("%d건 %+.2f%% · %.0f%%" % (len(z), z.ret.mean(), (z.ret > 0).mean() * 100) if len(z) else "-")
    yr = Z.groupby(Z.date.str[:4]).ret.mean()
    P("| %s | %d | %s | %s | %d/%d |" % (lab, len(Z), cells[0], cells[1], int((yr > 0).sum()), len(yr)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A, _ = O.build("KR")
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    A["pc"] = g.close.shift(1); A["ppc"] = g.close.shift(2); A["no"] = g.open.shift(-1); A["ndate"] = g.date.shift(-1)
    x = A.pc.values * 1.3
    tk_ = np.select([x < 2000, x < 5000, x < 20000, x < 50000, x < 200000, x < 500000], [1, 5, 10, 50, 100, 500], 1000)
    A["lim"] = np.floor(x / tk_) * tk_
    P("- 일봉 %s줄 준비 %.1f분" % (f"{len(A):,}", (time.time() - t0) / 60))
    A["hit"] = A.high >= A.lim * 0.999; A["closed_lim"] = A.close >= A.lim * 0.999
    A["p_closed_lim"] = g.closed_lim.shift(1).fillna(False).astype(bool)
    P("# 국장 커뮤니티 기법 — 상따 · 상한가 다음날 눌림 · 장대양봉 갭 구간 · %s" % time.strftime("%Y-%m-%d")); P("")
    # ── 18 상따 ──
    ev = A[(A.date >= "20221201") & A.hit & ~A.p_closed_lim & A.no.notna()]
    random.seed(3); idx = random.sample(list(ev.index), min(4000, len(ev))); ev = ev.loc[idx]
    got, miss = E.ensure("KR", list(zip(ev.ticker, ev.date)))
    n_all = int((A.hit & ~A.p_closed_lim & (A.date >= "20221201") & A.no.notna()).sum())
    P("- 18 상따: 첫 상한가 닿은 날 %d건 중 무작위 %d건 · 1분봉 새로 받음 %d · 못 받음 %d(폐지 등)" % (n_all, len(ev), got, miss))
    r_opt, r_con, n10 = [], [], 0
    for t, z in ev.groupby("ticker"):
        B = E.bars("KR", t, list(z.date))
        for row in z.itertuples():
            b = B.get(row.date)
            if b is None or len(b) < 200: continue
            lim = row.lim; hm, h, c = b.hm.values, b.h.values, b.c.values
            k = np.where(h >= lim * 0.999)[0]
            if not len(k) or hm[k[0]] >= "1000": continue
            n10 += 1; k = k[0]
            # 낙관: 처음 닿을 때 체결
            br = np.where(c[k:] < lim * 0.999)[0]
            if len(br): r_opt.append((row.date, (c[k + br[0]] / lim - 1) * 100 - FEE - SLIP))
            else: r_opt.append((row.date, (row.no / lim - 1) * 100 - FEE))
            # 보수: 한 번 풀렸다(종가 < 상한가) 다시 닿을 때 체결 → 그 뒤 다시 풀리면 손절
            if len(br):
                k2 = k + br[0]; re = np.where(h[k2 + 1:] >= lim * 0.999)[0]
                if len(re):
                    k3 = k2 + 1 + re[0]; br2 = np.where(c[k3:] < lim * 0.999)[0]
                    if len(br2): r_con.append((row.date, (c[k3 + br2[0]] / lim - 1) * 100 - FEE - SLIP))
                    else: r_con.append((row.date, (row.no / lim - 1) * 100 - FEE))
    P("- 10시 전 첫 상한가 %d건" % n10); P("")
    P("| 기법 | 건수 | 2016~22 평균·승률 | 2023~ 평균·승률 | 플러스 해 |"); P("|---|---|---|---|---|")
    stats("18 상따 · 낙관(처음 닿을 때 체결)", r_opt)
    stats("18 상따 · 보수(풀렸다 다시 닿을 때만 체결)", r_con)
    # ── 19 상한가 다음날 눌림 ──
    ev = A[(A.date >= "20221201") & A.p_closed_lim]
    random.seed(4); idx = random.sample(list(ev.index), min(4000, len(ev))); ev = ev.loc[idx]
    got, miss = E.ensure("KR", list(zip(ev.ticker, ev.date)))
    r19 = []
    for t, z in ev.groupby("ticker"):
        B = E.bars("KR", t, list(z.date))
        for row in z.itertuples():
            b = B.get(row.date)
            if b is None or len(b) < 200: continue
            pc = row.pc; n = len(b)
            k3 = np.arange(n) // 3
            G = b.assign(k=k3).groupby("k").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
            to, th, tl, tc = G.o.values, G.h.values, G.l.values, G.c.values
            went = False
            for j in range(1, len(tc) - 1):
                if tl[j] <= pc: went = True
                if went and tc[j] > pc and tc[j - 1] <= pc:
                    px = tc[j]; stp = pc * 0.99; ret = None
                    for q in range(j + 1, len(tc)):
                        if tl[q] <= stp: ret = (min(stp, to[q]) / px - 1) * 100 - FEE - 2 * SLIP; break
                    if ret is None: ret = (tc[-1] / px - 1) * 100 - FEE - SLIP
                    r19.append((row.date, ret)); break
    stats("19 상한가 다음날 눌림 → 전날 종가 재돌파 (이벤트 %d · 새로 받음 %d · 못 받음 %d)" % (len(ev), got, miss), r19)
    # ── 22 장대양봉 갭 구간(일봉) ──
    A["ma20"] = g.close.transform(lambda s: s.rolling(20).mean())
    body = (A.close / A.open - 1) * 100
    A["isD"] = (body >= 5) & (A.close > A.ma20) & (A.amt20 >= 30) & (A.volume >= 5e5)
    gn = A.groupby("ticker", sort=False)
    nx = {k: gn[k].shift(-1) for k in ("open", "low", "close", "date")}
    A["d1ok"] = A.isD & (nx["open"] >= A.close * 1.018) & (nx["close"] >= A.close * 1.018) & (nx["low"] > A.close)
    r22a, r22b = [], []
    arr = {k: A[k].values for k in ("open", "high", "low", "close", "date", "ticker")}
    tk = arr["ticker"]
    for i in np.where(A.d1ok.values)[0]:
        if i + 12 >= len(A) or tk[i + 11] != tk[i]: continue
        a_, b_ = arr["close"][i], arr["low"][i + 1]
        for j in range(i + 2, i + 12):
            if arr["low"][j] <= b_:
                px = min(b_, arr["open"][j]) if arr["open"][j] >= a_ * 0.97 else None
                if px is None: break
                for lab, stop, out in (("손절 없음", None, r22a), ("D 종가 −3% 손절", a_ * 0.97, r22b)):
                    ret = None
                    for q in range(j, min(j + 10, len(A))):
                        if tk[q] != tk[i]: break
                        if stop is not None and arr["low"][q] <= stop and q > j: ret = (min(stop, arr["open"][q]) / px - 1) * 100 - FEE - SLIP; break
                        if arr["high"][q] >= px * 1.02 and q > j or (q == j and arr["close"][q] >= px * 1.02): ret = 2.0 - FEE; break
                    if ret is None: ret = (arr["close"][min(j + 9, len(A) - 1)] / px - 1) * 100 - FEE
                    out.append((arr["date"][j], ret))
                break
    stats("22 장대양봉 갭 구간 → +2% · 손절 없음(10일 정리)", r22a)
    stats("22 장대양봉 갭 구간 → +2% · D 종가 −3% 손절", r22b)
    P(""); P("(%.1f분)" % ((time.time() - t0) / 60))
    log_trials("comm_limitup_%s" % time.strftime("%Y%m%d"), 5)
    (ROOT / "reports" / ("comm_limitup_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
