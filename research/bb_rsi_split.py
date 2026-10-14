# -*- coding: utf-8 -*-
"""볼린저 하단 + RSI 35 이하 10분할 매수 · 상단 터치 일부 익절 (2026-10-15 사용자 제안) — H0336.

매수 신호: 종가 < 볼린저(20, 2σ) 하단 & RSI(14, 와일더) ≤ 35. 첫 매수는 유니버스(거래대금 상위 40%) 종목만.
매수 방식(종목당 예산 = 10칸):
  S 신호 분할  — 신호 난 날마다 다음날 시가에 1칸씩(최대 10칸) · 영상식 해석
  T 시간 분할  — 첫 신호 다음날부터 10거래일 매일 시가 1칸씩(신호 무관)
  L 한 번에    — 첫 신호 다음날 시가에 10칸 전부(비교)
매도 방식:
  E1 상단 터치 전량    — 고가 ≥ 전날 상단이면 max(시가, 상단)에 전부
  E2 상단 절반 + 중심선 — 상단 터치에 절반, 남은 건 종가 < 중심선(20일선)이면 다음날 시가
  공통: 첫 매수 뒤 250거래일이면 종가 정리 · 상단 터치(익절 시작) 뒤로는 더 안 산다.
수익 잣대 셋: 투입 대비(산 칸만) · 예산 대비(10칸 다 잡아둔 돈) · 연환산 돈-날 효율(손익 ÷ 칸×보유일 × 250)
 → 같은 기간 유니버스 동일가중 보유의 연환산과 비교(물타기 실측 교훈: 거래별 %는 노출을 지운다).
비용: 국장 칸마다 0.23% + 미끄러짐 0.05% · 미장 0.25%. 옛날 ~15 · 학습 16~22 · 검증 23~ (첫 매수일 기준).
    python research/bb_rsi_split.py KR|US
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from numba import njit
import run_spec as R

MK = sys.argv[1] if len(sys.argv) > 1 else "KR"
COST = 0.28 if MK == "KR" else 0.25
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


@njit(cache=True)
def sim(o, h, l, c, bl, bm, bu, rsi, uni, buy_mode, exit_mode, cost):
    """반환 행: (첫매수 idx, 산 칸, 투입 대비 %, 예산 대비 %, 보유일, 칸-날, 손익(칸 단위 %))."""
    n = len(c); out = []
    i = 21
    while i < n - 1:
        sig = c[i] < bl[i] and rsi[i] <= 35.0 and uni[i]
        if not sig:
            i += 1; continue
        # 포지션 시작 — 다음날 시가부터
        start = i + 1
        units = 0.0; cost_sum = 0.0; pnl = 0.0; unit_days = 0.0; bought = 0
        half_done = False; taking = False; t = start; last = start
        if buy_mode == 2:
            units = 10.0; cost_sum = 10.0 * o[start]; bought = 10
        pend = buy_mode == 0      # 신호 분할: 신호일 i 다음날 첫 칸
        tcount = 0
        while t < n:
            # 1) 오늘 시가 매수
            if not taking:
                if buy_mode == 0 and pend and bought < 10:
                    units += 1; cost_sum += o[t]; bought += 1
                elif buy_mode == 1 and tcount < 10:
                    units += 1; cost_sum += o[t]; bought += 1; tcount += 1
            pend = False
            unit_days += units
            # 2) 매도 — 상단 터치(전날 상단 기준)
            U = bu[t - 1]
            if units > 0 and U == U and h[t] >= U:
                px = max(o[t], U); avg = cost_sum / units
                q = units if (exit_mode == 0 or half_done) else units / 2.0
                if exit_mode == 1 and not half_done:
                    q = units / 2.0; half_done = True
                pnl += q * ((px / avg - 1) * 100 - cost)
                cost_sum -= q * avg; units -= q; taking = True
                if exit_mode == 0 or units < 1e-9:
                    units = 0.0; last = t; break
            # 3) 절반 판 뒤 종가 < 중심선 → 다음날 시가
            if exit_mode == 1 and half_done and units > 0 and c[t] < bm[t] and t + 1 < n:
                avg = cost_sum / units
                pnl += units * ((o[t + 1] / avg - 1) * 100 - cost)
                units = 0.0; last = t + 1; break
            # 4) 250일 정리
            if t - start >= 250 or t == n - 1:
                if units > 0:
                    avg = cost_sum / units
                    pnl += units * ((c[t] / avg - 1) * 100 - cost)
                    units = 0.0
                last = t; break
            # 오늘 종가 신호 → 내일 한 칸
            if buy_mode == 0 and c[t] < bl[t] and rsi[t] <= 35.0:
                pend = True
            t += 1
        if bought > 0:
            out.append((float(start), float(bought), pnl / bought, pnl / 10.0, float(last - start + 1), unit_days, pnl))
        i = last + 1
    return out


def main():
    A, uni, since = R.load_market(MK)
    A["uni"] = uni.values
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A = A[A.date >= ("20050101" if MK == "KR" else "20110101")].reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    m = g.close.transform(lambda s: s.rolling(20, min_periods=20).mean())
    sd = g.close.transform(lambda s: s.rolling(20, min_periods=20).std())
    A["bm"], A["bl"], A["bu"] = m, m - 2 * sd, m + 2 * sd
    d = g.close.diff()
    up = d.clip(lower=0); dn = (-d).clip(lower=0)
    au = up.groupby(A.ticker).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    ad = dn.groupby(A.ticker).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    A["rsi"] = 100 - 100 / (1 + au / ad.replace(0, np.nan))
    A["rsi"] = A.rsi.fillna(50)
    # 유니버스 동일가중 일 수익(연환산 비교용)
    A["r1"] = g.close.pct_change() * 100
    ur = A.loc[A.uni & A.r1.abs().lt(35)].groupby("date").r1.mean()
    dates = A.date.values
    rows = []
    for tk, idx in g.indices.items():
        sub = A.iloc[idx]
        arr = [sub[k].to_numpy(np.float64) for k in ("open", "high", "low", "close", "bl", "bm", "bu", "rsi")]
        u = sub.uni.to_numpy(np.bool_)
        for bmode, bnm in ((0, "S 신호 분할"), (1, "T 시간 분할"), (2, "L 한 번에")):
            for emode, enm in ((0, "E1 상단 전량"), (1, "E2 상단 절반+중심선")):
                for r in sim(*arr, u, bmode, emode, COST):
                    rows.append((bnm, enm, tk, sub.date.values[int(r[0])]) + tuple(r[1:]))
    E = pd.DataFrame(rows, columns=["buy", "exit", "ticker", "date", "units", "r_inv", "r_bud", "days", "udays", "pnl"])
    E["per"] = np.where(E.date <= "20151231", "옛날", np.where(E.date <= "20221231", "학습", "검증"))
    E.to_pickle(Path(__file__).resolve().parent / "cache" / ("bb_rsi_%s.pkl" % MK))
    PER = [("옛날", "20050101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]
    uy = {p: ur[(ur.index >= a) & (ur.index <= b)].mean() * 250 for p, a, b in PER}
    P("## %s 볼린저 하단 + RSI ≤ 35 · 10분할 · 상단 익절 (비용 %.2f%%)" % (MK, COST))
    P("유니버스 동일가중 보유 연환산(단순): 옛날 %+.1f%% · 학습 %+.1f%% · 검증 %+.1f%%" % (uy["옛날"], uy["학습"], uy["검증"]))
    for p, _, _ in PER:
        P("\n### %s (첫 매수 기준)" % p)
        P("| 매수 | 매도 | 건수 | 평균 산 칸 | 투입 대비 평균·중앙 | 승률 | 예산 대비 평균 | 보유일 | 돈-날 연환산 | 예산 연환산 |")
        P("|---|---|---|---|---|---|---|---|---|---|")
        for (bn, en), Z in E[E.per == p].groupby(["buy", "exit"]):
            eff = Z.pnl.sum() / Z.udays.sum() * 250                     # 실제 들어간 칸 기준
            bud = Z.pnl.sum() / (10 * Z.days).sum() * 250               # 10칸 다 잡아둔 돈 기준
            P("| %s | %s | %d | %.1f | %+.2f / %+.2f | %.0f%% | %+.2f | %.0f | %+.1f%% | %+.1f%% |" % (
                bn, en, len(Z), Z.units.mean(), Z.r_inv.mean(), Z.r_inv.median(), (Z.r_inv > 0).mean() * 100, Z.r_bud.mean(), Z.days.mean(), eff, bud))
    P("\n### 해마다 — S 신호 분할 · E2 (투입 대비 평균 · 돈-날 연환산 vs 유니버스 연환산)")
    P("| 해 | 건수 | 투입 대비 | 돈-날 연환산 | 유니버스 |"); P("|---|---|---|---|---|")
    Z = E[(E.buy == "S 신호 분할") & (E.exit == "E2 상단 절반+중심선")].copy(); Z["yr"] = Z.date.str[:4]
    for y, q in Z.groupby("yr"):
        uyr = ur[ur.index.str[:4] == y].mean() * 250
        P("| %s | %d | %+.2f | %+.1f%% | %+.1f%% |" % (y, len(q), q.r_inv.mean(), q.pnl.sum() / q.udays.sum() * 250, uyr))
    (Path(__file__).resolve().parent / "cache" / ("bb_rsi_%s.out" % MK)).write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
