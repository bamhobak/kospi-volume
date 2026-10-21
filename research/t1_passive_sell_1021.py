# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 종가 시장가 대신 '장중에 위쪽 호가에 걸어 두고 팔리면 OK, 안 팔린 몫만 종가' (2026-10-21 사용자 제안).
과거 호가창은 없어서 1분봉으로 근사한다(2023~ · 그날 1분봉 · 실제 체결된 [갭 하락 조용주] 거래):
  · 시작 시각 T(14:30 · 15:00 · 15:10)의 체결가 c_T 를 기준으로 지정가 = c_T + k호가(k=1·2·3) — '최우선 매도 호가쯤·그보다 한 칸 아래'의 근사
  · 따라 내리기: 매 분 다시 그 분 체결가 + k호가로 고쳐 건다(누가 더 낮게 걸면 따라 내려가는 것의 근사)
  · 체결 판정(보수적): 그 뒤 15:19 까지 어떤 1분봉 **고가가 지정가보다 높고**(값을 뚫고 지나감) 그 봉 거래량 ≥ 우리 주수 → 지정가에 다 팔림
    (낙관: 고가 = 지정가여도 팔림) · 못 팔리면 종가(단일가)
  · 우리 주수 = 50만 × 깊이(1.5~5) ÷ 가격
비교 = 지금(종가 단일가) 대비 건당 수익 차이 · 장중에 팔린 비율 · 팔린 것/못 판 것 각각의 차이.
    python research/t1_passive_sell_1021.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory")); sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT
import m1_event as ME


def tick(p):
    for lim, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if p < lim: return t
    return 1000


def main():
    H = lab.hist()[["ticker", "date", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9) & (H.date >= "20230101")].copy()
    got, miss = ME.ensure("KR", list(zip(W.ticker, W.date)), log=lambda *a: print(*a, flush=True))
    print("그날 1분봉: 새로 받음 %d · 못 받음 %d" % (got, miss), flush=True)
    rows = []
    for t, g in W.groupby("ticker"):
        B = ME.bars("KR", t, list(g.date))
        for r in g.itertuples():
            b = B.get(r.date)
            if b is None or len(b) < 100: continue
            b = b.sort_values("hm")
            o = b.o.iloc[0]; c = b.c.iloc[-1]
            if not (o > 0 and c > 0): continue
            qty = max(1, int(50e4 * min(5, max(1, -r.rgap)) / o))
            rows.append((r.ticker, r.date, o, c, qty, b[["hm", "h", "c", "v"]].values))
    print("대상 %d건(2023~)\n" % len(rows), flush=True)
    base = np.array([(c / o - 1) * 100 for _, _, o, c, _, _ in rows])

    def sim(start, k, follow, strict):
        out, sold = [], []
        for _, _, o, c, q, arr in rows:
            hm, h, cc, v = arr[:, 0], arr[:, 1].astype(float), arr[:, 2].astype(float), arr[:, 3].astype(float)
            idx = np.where((hm >= start) & (hm <= "1519"))[0]
            pre = np.where(hm < start)[0]
            if not len(idx) or not len(pre): out.append(c); sold.append(False); continue
            ref = cc[pre[-1]]
            lim = ref + k * tick(ref)
            px = None
            for j in idx:
                if (h[j] > lim or (not strict and h[j] >= lim)) and v[j] >= q:
                    px = lim; break
                if follow: lim = cc[j] + k * tick(cc[j])          # 다음 분엔 지금 체결가 + k호가로 고쳐 건다
            out.append(px if px else c); sold.append(px is not None)
        out = np.array([(p / o - 1) * 100 for p, (_, _, o, _, _, _) in zip(out, rows)]); sold = np.array(sold)
        d = out - base
        return d.mean(), sold.mean() * 100, d[sold].mean() if sold.any() else np.nan, (d > 0).mean() * 100, (d < 0).mean() * 100

    print("칸 = 건당 수익 차이(지금 종가 매도 대비, %p) · 장중에 팔린 비율 · 팔린 것만의 차이 · 나아진 건 / 나빠진 건 비율\n")
    print("| 시작 | 지정가 | 따라 내리기 | 체결 판정 | 건당 차이 | 장중 팔림 | 팔린 것 차이 | 나아짐 / 나빠짐 |"); print("|---|---|---|---|---|---|---|---|")
    for start in ("1430", "1500", "1510"):
        for k in (1, 2, 3):
            for follow in (False, True):
                for strict in (True, False):
                    m, s, ms, up, dn = sim(start, k, follow, strict)
                    print("| %s:%s | 체결가+%d호가 | %s | %s | **%+.2f%%p** | %.0f%% | %+.2f%%p | %.0f%% / %.0f%% |" % (
                        start[:2], start[2:], k, "O" if follow else "X", "보수(뚫고 지나감)" if strict else "낙관(닿기만)", m, s, ms, up, dn), flush=True)
    print("\n(지금 방식 건당 평균 시가→종가 %+.2f%% · 비용 전)" % base.mean())


if __name__ == "__main__":
    main()
