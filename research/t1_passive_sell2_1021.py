# -*- coding: utf-8 -*-
"""장중 위쪽 호가 걸어 팔기 — **실전 금액**(50만 × 깊이 1.5~5 × 20일 거래대금 배율 0.3~3, 그리고 덤으로 2·3배)일 때 (2026-10-21 사용자).
t1_passive_sell_1021.py 는 금액을 50만×깊이로만 보고 종가 밀림을 안 뺐다. 여기선
  · 종가 단일가 밀림 = 실행 실측(종가 봉 버그 고친 뒤)의 매도 손해를 참여율(금액 ÷ 20일 평균 거래대금)에 맞춘 모형으로 뺀다
  · 장중 지정가는 **나눠서** 팔린다: 고가가 지정가를 뚫은 분(보수) 또는 닿은 분(낙관)마다 그 분 거래량의 Q(30%) 까지만 우리 몫
    → 남은 몫은 종가 단일가(남은 금액으로 밀림 계산)
비교 = 지금(전량 종가 단일가, 밀림 포함) 대비 건당 수익 차이(금액가중) · 장중에 판 금액 비율.
    python research/t1_passive_sell2_1021.py
"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory")); sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab
import m1_event as ME
import t1_size_liq_1021 as SL
from t1_passive_sell_1021 import tick

Q = 0.30


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        E = SL.liq_of_exec()
    X = E.dropna(subset=["a20"]).copy()
    X["p"] = X.amt * 1e4 / X.a20 * 100
    X["sc"] = [r.get("cost") if isinstance(r, dict) and r.get("cost") is not None else np.nan for r in X.S1]
    X = X.dropna(subset=["sc"])
    a, b = np.linalg.lstsq(np.c_[np.ones(len(X)), np.sqrt(X.p)], X.sc.values, rcond=None)[0]
    sc = lambda p: np.maximum(0.0, a + b * np.sqrt(p))
    print("종가 단일가 매도 밀림 모형: max(0, %.2f + %.2f×√p)%% (p = 금액 ÷ 20일 평균 거래대금, %%)" % (a, b))
    for amt in (50, 100, 200, 300, 500):
        z = X[X.amt == amt]; print("  실측 %d만: 매도 밀림 %.2f%% · 참여율 중앙 %.3f%%" % (amt, z.sc.mean(), z.p.median()))

    H = lab.hist()[["ticker", "date", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["rgap", "q_gap", "liq", "amt20"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9) & (H.date >= "20230101")].copy()
    W["a20"] = W.amt20 * 1e8
    W["lm"] = (W.a20 / W.groupby("date").a20.transform("median")).clip(0.3, 3)
    W["amt"] = 50e4 * (-W.rgap).clip(1, 5) * W.lm
    rows = []
    for t, g in W.groupby("ticker"):
        B = ME.bars("KR", t, list(g.date))
        for r in g.itertuples():
            bb = B.get(r.date)
            if bb is None or len(bb) < 100: continue
            bb = bb.sort_values("hm"); o, c = bb.o.iloc[0], bb.c.iloc[-1]
            if o > 0 and c > 0: rows.append((o, c, r.amt, r.a20, bb[["hm", "h", "c", "v"]].values))
    print("\n대상 %d건(2023~) · 금액 중앙 %.0f만 · 90%% %.0f만\n" % (len(rows), np.median([x[2] for x in rows]) / 1e4, np.percentile([x[2] for x in rows], 90) / 1e4))

    def run(mult, start, k, follow, strict):
        tot_base = tot_new = tot_amt = sold_amt = 0.0
        for o, c, amt0, a20, arr in rows:
            amt = amt0 * mult; q = amt / o
            hm, h, cc, v = arr[:, 0], arr[:, 1].astype(float), arr[:, 2].astype(float), arr[:, 3].astype(float)
            base = (c * (1 - sc(amt / a20 * 100) / 100) / o - 1) * 100          # 지금: 전량 종가, 밀림 포함
            idx = np.where((hm >= start) & (hm <= "1519"))[0]; pre = np.where(hm < start)[0]
            left, val = q, 0.0
            if len(idx) and len(pre):
                lim = cc[pre[-1]] + k * tick(cc[pre[-1]])
                for j in idx:
                    if left <= 0: break
                    if h[j] > lim or (not strict and h[j] >= lim):
                        s = min(left, v[j] * Q); val += s * lim; left -= s
                    if follow: lim = cc[j] + k * tick(cc[j])
            rest_amt = left * c
            if left > 0: val += left * c * (1 - sc(rest_amt / a20 * 100) / 100)
            new = (val / q / o - 1) * 100
            tot_base += base * amt; tot_new += new * amt; tot_amt += amt; sold_amt += (q - left) * o
        return (tot_new - tot_base) / tot_amt, sold_amt / tot_amt * 100, tot_base / tot_amt

    print("칸 = 금액가중 건당 수익 차이(지금 대비, %p) · 장중에 판 비율(금액) — 보수(뚫고 지나감) / 낙관(닿기만)\n")
    for mult, nm in ((1, "실전 금액(덤 없음)"), (2, "덤 하나 붙음(2배)"), (3, "덤 둘 다(3배)")):
        b0 = run(mult, "1500", 1, False, True)[2]
        print("### %s — 지금 방식 건당 %+.2f%%(비용 0.23 전, 종가 밀림 뺌)" % (nm, b0))
        print("| 시작 | 지정가 | 따라 내리기 | 보수 | 낙관 |"); print("|---|---|---|---|---|")
        for start in ("1430", "1500", "1510"):
            for k in (1, 2, 3):
                for follow in (False, True):
                    s1 = run(mult, start, k, follow, True); s2 = run(mult, start, k, follow, False)
                    print("| %s:%s | +%d호가 | %s | **%+.2f%%p** (%.0f%%) | **%+.2f%%p** (%.0f%%) |" % (start[:2], start[2:], k, "O" if follow else "X", s1[0], s1[1], s2[0], s2[1]), flush=True)
        print()


if __name__ == "__main__":
    main()
