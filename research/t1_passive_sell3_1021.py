# -*- coding: utf-8 -*-
"""장중 걸어 팔기 세 방식 비교 (2026-10-21 사용자): ① 지금까지 = 전량 종가 단일가 ② 체결가 + 2호가 ③ 최우선 매도 호가 한 칸 아래(바닥 최우선 매수 + 1칸).
⚠ 과거 장중 호가창이 없다 — ③의 최우선 매도·매수 호가는 **직전 1분봉의 고가·저가**로 대신한다(그 분에 사고판 값의 위·아래 끝).
   한 분에 값이 크게 움직이면 간격을 넓게 보는 쪽으로 틀린다. 정확한 비교는 day_alert 가 10-22~ 쌓는 실제 호가(data/day/pmbook_*.jsonl)로 다시.
실전과 같게: 14:30(또는 15:00)부터 **2분마다** 값을 고쳐 건다 · 뚫고 지나간 분(보수) / 닿은 분(낙관)에 그 분 거래량의 30% 까지 우리 몫 ·
15:19 까지 남은 몫은 종가 단일가(남은 금액으로 밀림) · 금액 = 50만 × 깊이(1.5~5) × 거래대금 배율, 덤 붙으면 2·3배.
    python research/t1_passive_sell3_1021.py
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

Q, EVERY = 0.30, 2


def tick_below(p):
    return tick(p - 1)


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        E = SL.liq_of_exec()
    X = E.dropna(subset=["a20"]).copy()
    X["p"] = X.amt * 1e4 / X.a20 * 100
    X["sc"] = [r.get("cost") if isinstance(r, dict) and r.get("cost") is not None else np.nan for r in X.S1]
    X = X.dropna(subset=["sc"])
    a, b = np.linalg.lstsq(np.c_[np.ones(len(X)), np.sqrt(X.p)], X.sc.values, rcond=None)[0]
    sc = lambda p: np.maximum(0.0, a + b * np.sqrt(p))
    H = lab.hist()[["ticker", "date", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["rgap", "q_gap", "liq", "amt20"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9) & (H.date >= "20230101")].copy()
    W["a20"] = W.amt20 * 1e8
    W["amt"] = 50e4 * (-W.rgap).clip(1, 5) * (W.a20 / W.groupby("date").a20.transform("median")).clip(0.3, 3)
    rows = []
    for t, g in W.groupby("ticker"):
        B = ME.bars("KR", t, list(g.date))
        for r in g.itertuples():
            bb = B.get(r.date)
            if bb is None or len(bb) < 100: continue
            bb = bb.sort_values("hm"); o, c = bb.o.iloc[0], bb.c.iloc[-1]
            if o > 0 and c > 0: rows.append((o, c, r.amt, r.a20, bb[["hm", "h", "l", "c", "v"]].values))
    print("대상 %d건(2023~)\n" % len(rows))

    def run(mult, start, mode, strict):
        tb = tn = ta = sa = 0.0; gap = []
        for o, c, amt0, a20, arr in rows:
            amt = amt0 * mult; q = amt / o
            hm = arr[:, 0]; h, l, cc, v = (arr[:, k].astype(float) for k in (1, 2, 3, 4))
            base = (c * (1 - sc(amt / a20 * 100) / 100) / o - 1) * 100
            idx = np.where((hm >= start) & (hm <= "1519"))[0]; pre = np.where(hm < start)[0]
            left, val = q, 0.0
            if mode and len(idx) and len(pre):
                def price(j):
                    if mode == "k2":
                        p = cc[j]
                        for _ in range(2): p += tick(p)
                        return p
                    ask, bid = h[j], l[j]                                 # 직전 분 고가·저가 = 최우선 매도·매수 근사
                    return max(bid + tick(bid), ask - tick_below(ask))
                lim = price(pre[-1]); gap.append((lim / cc[pre[-1]] - 1) * 100)
                for n_, j in enumerate(idx):
                    if left <= 0: break
                    if h[j] > lim or (not strict and h[j] >= lim):
                        s = min(left, v[j] * Q); val += s * lim; left -= s
                    if (n_ + 1) % EVERY == 0: lim = price(j)
            if left > 0: val += left * c * (1 - sc(left * c / a20 * 100) / 100)
            new = (val / q / o - 1) * 100
            tb += base * amt; tn += new * amt; ta += amt; sa += (q - left) * o
        return (tn - tb) / ta, sa / ta * 100, tb / ta, (np.median(gap) if gap else np.nan)

    print("칸 = 종가 전량 대비 건당 수익 차이(금액가중, %p) · 장중에 판 비율 — 보수(뚫고 지나감) / 낙관(닿기만)\n")
    for mult, nm in ((1, "실전 금액"), (2, "덤 하나(2배)"), (3, "덤 둘 다(3배)")):
        print("### %s — ① 전량 종가 건당 %+.2f%%(비용 0.23 전, 종가 밀림 뺌)" % (nm, run(mult, "1430", None, True)[2]))
        print("| 시작 | 방식 | 첫 지정가(체결가 대비 중앙) | 보수 | 낙관 |"); print("|---|---|---|---|---|")
        for start in ("1430", "1500"):
            for mode, mn in (("k2", "② 체결가 + 2호가"), ("ask", "③ 최우선 매도 − 1칸(분봉 근사)")):
                s1 = run(mult, start, mode, True); s2 = run(mult, start, mode, False)
                print("| %s:%s | %s | +%.2f%% | **%+.2f%%p** (%.0f%%) | **%+.2f%%p** (%.0f%%) |" % (start[:2], start[2:], mn, s1[3], s1[0], s1[1], s2[0], s2[1]), flush=True)
        print()


if __name__ == "__main__":
    main()
