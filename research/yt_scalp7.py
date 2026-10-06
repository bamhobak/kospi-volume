# -*- coding: utf-8 -*-
"""유튜브 4편 (2026-10-07 사용자 링크) — 국장·미장 1분봉.
  W1 rQZyjGIzeAE '단타 3가지 비법' + W4 8jrIHIKMUpI '몇 분봉으로 매매할까':
     일봉 방향(전날 종가 > 20일선 & 20일선 5일 전보다 위) × 지금 가격이 오늘 시가 위/아래 → 시가 위면 매수(국장 10:00 · 미장 10:30) → 장 끝
     시가 되찾기: 일봉 상승 중, 시가 아래로 내려갔다가 11시(미장 11:30) 전에 5분봉이 시가 위로 마감 → 매수 · 그때까지 저점 손절 · 장 끝
     일봉 볼린저 복귀: 전날 종가가 일봉 볼린저(20·2) 하단 밖 → 오늘 10:00 에 하단 안 & 시가 위면 매수 · 그날 저점 손절 · 장 끝
  W2 qNcBzk4zzdU '시가 90분 원캔들': 첫 15분봉 범위 ≥ 일봉 ATR(14)의 33% & 첫 15분봉이 음봉 → 장 시작 90분 안에, 범위 아래 바깥에서
     5분봉 망치형(다음 봉이 망치형 직전 봉 고가를 넘을 때 매수) 또는 상승장악형(마감 때 매수) · 패턴 저점 손절 · 범위 고점 익절 · 장 끝 정리
     (ATR 조건 없음 · 첫 봉 방향 무관 판도 같이)
  W3 ddZkIwE7Qos '60분봉 최고자리': 60분봉 이평 20 이 120 을 상향 교차한 봉의 (고+저)/2 를 m 이라 하면 매수선 m×(1−2.1%), 손절 m×(1−2.23%)
     (영상 숫자 그대로) / 넓은 판 손절 m×(1−6%) · 교차 뒤 60봉(약 10일) 안에 매수선 닿으면 매수 · 익절 +5% · 30봉(약 5일) 지나면 정리 — 여러 날 보유
비용·표본은 yt_scalp 와 같음(같은 봉 손절 우선) · 여러 날 보유(W3)는 비용 같고 미끄러짐 손절만.
    python research/yt_scalp7.py
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
T10 = {"KR": ("1000", "1100", "1030"), "US": ("1030", "1130", "1100")}      # (10시 판단, 시가 되찾기 마감, 90분 끝)


def agg(g, k):
    n = np.arange(len(g)) // k
    return g.groupby(n).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), hm=("hm", "last")).reset_index(drop=True)


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return []
    days = [(d, g.reset_index(drop=True)) for d, g in D.groupby("date", sort=True) if len(g) >= (300 if mk == "KR" else 300)]
    if len(days) < 40: return []
    T = []
    dd = pd.DataFrame({"date": [d for d, _ in days], "o": [g.o.iloc[0] for _, g in days], "h": [g.h.max() for _, g in days],
                       "l": [g.l.min() for _, g in days], "c": [g.c.iloc[-1] for _, g in days]})
    dd["ma20"] = dd.c.rolling(20).mean(); dd["sd20"] = dd.c.rolling(20).std()
    dd["up"] = (dd.c > dd.ma20) & (dd.ma20 > dd.ma20.shift(5))
    dd["below_bb"] = dd.c < dd.ma20 - 2 * dd.sd20
    tr = pd.concat([dd.h - dd.l, (dd.h - dd.c.shift(1)).abs(), (dd.l - dd.c.shift(1)).abs()], axis=1).max(axis=1)
    dd["atr"] = tr.rolling(14).mean()
    prev = {k: dd[k].shift(1).values for k in ("up", "below_bb", "atr", "ma20", "sd20")}
    t10, tre, t90 = T10[mk]
    for idx, (d, g) in enumerate(days):
        if idx < 21: continue
        o, h, l, c, hm = g.o.values, g.h.values, g.l.values, g.c.values, g.hm.values
        op = o[0]; up = bool(prev["up"][idx])
        # ── W1/W4 시가 위/아래 × 일봉 방향 (10시 매수 → 장 끝) ──
        k = np.where(hm <= t10)[0]
        if len(k):
            k = k[-1]; px = c[k]
            side = "시가 위" if px > op else "시가 아래"
            r, s = Y.run_trade(o, h, l, c, k, px, -1.0, None)
            T.append(("W1·W4 일봉 %s · 10시 %s 매수 → 장 끝" % ("상승" if up else "상승 아님", side), d, r, 1))
            # 일봉 볼린저 복귀
            if bool(prev["below_bb"][idx]) and px > op and px > prev["ma20"][idx] - 2 * prev["sd20"][idx]:
                r, s = Y.run_trade(o, h, l, c, k, px, l[: k + 1].min() * 0.999, None)
                T.append(("W4 일봉 볼린저 하단 밖 → 오늘 복귀·시가 위 매수", d, r, 1 + s))
        # ── W4 시가 되찾기(일봉 상승 중) ──
        if up:
            b = agg(g, 5); bo, bh, bl, bc, bhm = b.o.values, b.h.values, b.l.values, b.c.values, b.hm.values
            went = False
            for j in range(len(bc) - 1):
                if bhm[j] > tre: break
                if bl[j] < op: went = True
                if went and bc[j] > op and bc[j - 1] <= op if j > 0 else False:
                    r, s = Y.run_trade(bo, bh, bl, bc, j, bc[j], bl[: j + 1].min() * 0.999, None)
                    T.append(("W4 일봉 상승 · 시가 밑으로 갔다 되찾음 → 장 끝", d, r, 1 + s)); break
        # ── W2 원캔들 ──
        f15 = np.where(hm <= ("0915" if mk == "KR" else "0945"))[0]
        if len(f15) >= 10:
            rh, rl = h[f15].max(), l[f15].min(); bear = c[f15[-1]] < o[0]
            atr = prev["atr"][idx]; big = (rh - rl) >= 0.33 * atr if atr == atr else False
            b = agg(g, 5); bo, bh, bl, bc, bhm = b.o.values, b.h.values, b.l.values, b.c.values, b.hm.values
            st = np.where(bhm > ("0915" if mk == "KR" else "0945"))[0]
            for j in st:
                if j < 1 or j >= len(bc) - 1 or bhm[j] > t90: continue
                if bl[j] >= rl: continue                                 # 범위 아래 바깥에서만
                body = abs(bc[j] - bo[j]); lw = min(bo[j], bc[j]) - bl[j]
                hammer = lw >= 2 * body and (bc[j] - bl[j]) >= (bh[j] - bl[j]) * 2 / 3 and bh[j] > bl[j]
                engulf = bc[j - 1] < bo[j - 1] and bc[j] > bo[j] and bo[j] <= bc[j - 1] and bc[j] >= bo[j - 1]
                ent = None
                if engulf: ent = (j, bc[j], bl[j])
                elif hammer and bh[j + 1] > bh[j - 1]: ent = (j + 1, max(bh[j - 1], bo[j + 1]), bl[j])
                if ent is None: continue
                q, px, stp = ent
                if rh <= px: break
                for lab, ok in (("ATR 33%↑ & 첫 봉 음봉(영상대로)", big and bear), ("조건 없음(범위 밖 반전만)", True)):
                    if not ok: continue
                    if q == j + 1 and bl[q] <= stp:                       # 들어간 봉에서 바로 손절
                        T.append(("W2 원캔들 %s" % lab, d, (min(stp, bo[q]) / px - 1) * 100 if px > stp else 0.0, 2)); continue
                    r, s = Y.run_trade(bo, bh, bl, bc, q, px, stp * 0.999, rh)
                    T.append(("W2 원캔들 %s" % lab, d, r, 1 + s))
                break
    # ── W3 60분봉 골든크로스 매수선 (여러 날) ──
    H = pd.concat([agg(g, 60).assign(date=d) for d, g in days], ignore_index=True)
    H["m20"] = H.c.rolling(20).mean(); H["m120"] = H.c.rolling(120).mean()
    ho, hh, hl, hc, hd = H.o.values, H.h.values, H.l.values, H.c.values, H.date.values
    cross = np.where((H.m20 > H.m120) & (H.m20.shift(1) <= H.m120.shift(1)))[0]
    for x in cross:
        m = (hh[x] + hl[x]) / 2
        for lab, bl_, sl_ in (("영상 숫자(매수 −2.1% · 손절 −2.23%)", 0.021, 0.0223), ("넓은 손절(매수 −2.1% · 손절 −6%)", 0.021, 0.06)):
            buy, stop = m * (1 - bl_), m * (1 - sl_)
            for j in range(x + 1, min(x + 61, len(hc) - 1)):
                if hl[j] <= buy:
                    px = min(buy, ho[j])
                    if hl[j] <= stop:
                        T.append(("W3 60분 최고자리 %s" % lab, hd[j], (min(stop, ho[j]) / px - 1) * 100, 1)); break
                    ret, sl = None, 0
                    for q in range(j + 1, min(j + 31, len(hc))):
                        if hl[q] <= stop: ret = (min(stop, ho[q]) / px - 1) * 100; sl = 1; break
                        if hh[q] >= px * 1.05: ret = 5.0; break
                    if ret is None: ret = (hc[min(j + 30, len(hc) - 1)] / px - 1) * 100
                    T.append(("W3 60분 최고자리 %s" % lab, hd[j], ret, sl)); break
    return [(mk,) + x for x in T]


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
        for i, r in enumerate(ex.map(one, jobs, chunksize=2)):
            rows += r
            if (i + 1) % 100 == 0: print("  %d/%d · %.1f분" % (i + 1, len(jobs), (time.time() - t0) / 60), flush=True)
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip"])
    R.to_pickle(ROOT / "cache" / "yt_scalp7.pkl")
    P("# 유튜브 4편(일봉 방향·시가·원캔들·60분 최고자리) 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 무작위 %d · 미장 대형주 %d · 비용 뒤(국장 0.23%%+미끄러짐 0.05%% · 미장 0.20%%+0.02%%) · 같은 봉 손절 우선" % (
        len([j for j in jobs if j[0] == "KR"]), len([j for j in jobs if j[0] == "US"]))); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = Y.COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 기법 | 건수 | 비용 전 평균 | 학습 ~24: 평균·승률 | 검증 25~: 평균·승률 | 해마다(23·24·25·26) |"); P("|---|---|---|---|---|---|")
        for s, z in Z.groupby("s", sort=True):
            cell = []
            for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= b)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-")
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            P("| %s | %d | %+.3f%% | %s | %s | %s |" % (s, len(z), z.raw.mean(), cell[0], cell[1], " ".join("%+.2f" % v for v in yr.values)))
        P("")
    P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("yt_scalp7_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups))
    (ROOT / "reports" / ("yt_scalp7_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
