# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 크기 문턱 1/3 · 3/7 · 4/9 — 덤 매수([갭 하락 조용주 +] T2 · [갭 하락 조용주 ++] T3)까지 넣고 비교 (2026-10-21 사용자).
  T2 = 어제 14:00→종가 ≤ -1% (어제 1분봉 필요 → 2023~ 만) · T3 = 짝 미장으로 본 예상 갭 ≤ -0.5% (2016~)
  덤은 같은 종목을 같은 지정가로 한 번 더(둘 다면 두 번 더) — 한 종목 금액이 2~3배가 되므로 체결 손해는 합친 금액으로 계산.
  ① 덤 규칙 건당 성적 — 1/3 안 vs 넓혀서 새로 들어온 1/3~4/9 (덤이 큰 종목에도 통하나)
  ② 계좌(1천·3천·5천·무제한) 1년 손익 · 연 주문 건수 · 하루 평균 투자금 — 덤을 넓힌 범위 전체에 / 1/3 안에만
그물 = 10-21 설정(갭 하위 40% · 거래량 하위 30% · 시장 대비 -1.5) · 금액 = 50만 × 깊이(1.5~5) × 거래대금 배율(0.3~3) · 손해 모형 = t1_size_liq_1021.fit.
    python research/t1_extra_1021.py
"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import t1_size_liq_1021 as SL
import lab, feats as FT, common as C
import m1_event as ME

CUTS = [("1/3", 1 / 3), ("3/7", 3 / 7), ("4/9", 4 / 9)]
ACCTS = [1000, 3000, 5000, None]


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    H = lab.hist()[["ticker", "date", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20", "tr_pred"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9) & (H.date >= "20160101")].copy()
    W["oc"] -= FT.COST; W["a20"] = W.amt20 * 1e8
    # T2: 어제 14:00→종가 — 2023~ 만(1분봉)
    Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date"]].sort_values(["ticker", "date"])
    Px["pdate"] = Px.groupby("ticker").date.shift(1)
    W = W.merge(Px, on=["ticker", "date"], how="left").reset_index(drop=True)
    need = W[(W.date >= "20230101") & W.pdate.notna()]
    got, miss = ME.ensure("KR", list(zip(need.ticker, need.pdate)), log=lambda *a: print(*a, flush=True))
    print("어제 1분봉: 새로 받음 %d · 못 받음 %d" % (got, miss), flush=True)
    lh = pd.Series(np.nan, index=W.index)
    for t, g in need.groupby("ticker"):
        B = ME.bars("KR", t, list(g.pdate))
        for i, r in zip(g.index, g.itertuples()):
            b = B.get(r.pdate)
            if b is None or not len(b): continue
            b14 = b[b.hm <= "1400"]
            if len(b14): lh[i] = (b.c.iloc[-1] / b14.c.iloc[-1] - 1) * 100
    W["t2"] = (lh <= -1.0).values
    W["t3"] = (W.tr_pred <= -0.5).fillna(False).values
    W["v"] = W.date >= "20230101"
    print("T2 판정 가능 비율(2023~): %.0f%%\n" % (lh[W.v].notna().mean() * 100))

    P = lambda s="": print(s, flush=True)
    P("## ① 덤 규칙 건당 성적(비용 0.23 뒤, 손해 전) — 1/3 안 vs 1/3~4/9")
    P("| 덤 | 구간 | 1/3 안 | 1/3~4/9 (넓혀서 새로) |"); P("|---|---|---|---|")
    for nm, col, per in (("[갭 하락 조용주 +] T2", "t2", "v"), ("[갭 하락 조용주 ++] T3 학습 2016~22", "t3", "nv"), ("[갭 하락 조용주 ++] T3 검증 2023~", "t3", "v")):
        cells = []
        for inside in (True, False):
            z = W[(W[col]) & ((W.liq <= 1 / 3) if inside else (W.liq > 1 / 3)) & (W.v if per == "v" else ~W.v)]
            cells.append("%d건 · %+.2f%% · 승률 %.0f%%" % (len(z), z.oc.mean(), (z.oc > 0).mean() * 100) if len(z) >= 10 else "-")
        P("| %s | %s | %s |" % (nm, "2023~" if per == "v" else "2016~22", " | ".join(cells)))
    P("(참고: 덤 없는 본체 1/3 안 2023~ %+.2f%% · 1/3~4/9 %+.2f%%)\n" % (W[W.v & (W.liq <= 1 / 3)].oc.mean(), W[W.v & (W.liq > 1 / 3)].oc.mean()))

    P("## ② 계좌별 — 덤 포함 (2023~ 은 T2·T3, 2016~22 는 T3 만)")
    P("칸 = 1년 손익(만원) · 연 주문 건수 · 신호 난 날 하루 평균 투자금(만원, 계좌 한도 안)\n")
    P("| 계좌 | 문턱 | 덤 범위 | 학습 2016~22 | 검증 2023~ |"); P("|---|---|---|---|---|")
    yrs = {True: H[H.date >= "20230101"].date.nunique() / 250, False: H[(H.date >= "20160101") & (H.date < "20230101")].date.nunique() / 250}
    for A in ACCTS:
        for cn, c in CUTS:
            for scope in (("넓힌 범위 전체",) if cn == "1/3" else ("넓힌 범위 전체", "1/3 안에만")):
                S = W[W.liq <= c].copy()
                S["unit"] = 50e4 * (-S.rgap).clip(1, 5) * (S.a20 / S.groupby("date").a20.transform("median")).clip(0.3, 3)
                ok_extra = (S.liq <= 1 / 3) if scope == "1/3 안에만" else True
                S["k"] = 1 + ((S.t2 & S.v) & ok_extra).astype(int) + (S.t3 & ok_extra).astype(int)
                S["amt"] = S.unit * S.k
                S = S.sort_values(["date", "rgap"]); S["cum"] = S.groupby("date").amt.cumsum()
                K = S if A is None else S[S.cum <= A * 1e4]
                p = K.amt / K.a20 * 100
                K = K.assign(pnl=K.amt * fill(p) * (K.oc - imp(p)) / 100)
                cells = []
                for vv in (False, True):
                    z = K[K.v == vv]
                    daily = z.groupby("date").amt.sum() / 1e4
                    cells.append("%+.0f · %.0f건 · %.0f만" % (z.pnl.sum() / yrs[vv] / 1e4, z.k.sum() / yrs[vv], daily.mean()))
                P("| %s | %s | %s | %s |" % ("무제한" if A is None else "%d만" % A, cn, scope, " | ".join(cells)))


if __name__ == "__main__":
    main()
