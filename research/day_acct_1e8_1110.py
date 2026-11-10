# -*- coding: utf-8 -*-
"""데이 3규칙을 1억 계좌 하나로 같이 굴리면 금액을 어떻게 잡아야 하나(2026-11-10 사용자 "1억 기준으로 최적 조합 찾아줘").
돈이 묶이는 순서(실전 그대로): 전날 19:51 [NXT 장후 빠진 종목](T6) 매수 → 그날 08:41 [NXT 장전 되돌림](T5) 매수 → 08:53 [갭 하락 조용주](T1)
지정가를 넓은 그물 전체에 건다(안 사져도 그 돈은 묶임) → 09:00 T6·T5 시가 매도. 그래서 08:53 에 T6 + T5 + T1 주문 합 ≤ 자산.
  T6: research/nxt_* 패널(C:/temp/kp/nxt_full0_panel.pkl + nxt_v0) · 장후 19:50 ≤ -2.5% · 낮 등락 ±1% 빼기 · 깊은 순 · 금액 = min(종목 상한, 0.10×19:41~50 거래대금),
      30만↓ 안 삼 · 40종목·계좌 상한까지 · 손익 = 19:51~20:00 VWAP → 다음 날 시가 − 비용 0.23 − 사고·파는 √충격(nxt 모형)
  T5: research/newdata_pmrev5 패널(C:/temp/kp/pmrev5_panel_1103.pkl, 08:40) · 시장 대비 ≤ -3%p · 08:01~40 누적 ≤ 10.19억 · 금액 = 기준 × 1/2/3배(-3/-4/-5%p)
      · 5분 거래대금의 10% 상한 · 손익 = 08:41~45 VWAP → KRX 시가 − 0.23 − √충격(같은 모형)
  T1: data/y1_hist.pkl(KRX 일봉 재료) · 유니버스 거래대금 아래 2/3 · 갭 하위 40% · 어제 거래량 하위 30% · 그물 = 실제 시장 대비 ≤ -0.5(예상 대신)
      → 그 전부에 금액이 묶임 · 사지는 것 = ≤ -1.5 · 금액 = 기준 × 깊이(1~상한) × 거래대금 배율(0.3~3) · 깊은 순으로 남은 돈까지
      · 손익 = 시가→종가 − 0.23 − 체결 손해(t1_size_liq_1021.fit) × 체결률 × 0.89(장전 예상 오차로 놓치는 몫) · 덤(T2·T3)·T4 는 뺌
  고정 1억(번 돈은 안 넣음) · 겹치는 기간 2025-04-01 ~ 2026-10-08 · 고르기 = 달 손익 중앙값, 2025·2026 두 토막 따로 확인.
    python research/day_acct_1e8_1110.py
"""
import io, contextlib, sys, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

EQ = 1e8
D0, D1 = "20250401", "20261008"
COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def nimp(won, a):                                                    # nxt·pmrev 모형(p = 금액 ÷ 거래대금)
    p = np.clip(won / np.where(a > 0, a, np.nan), 0, None)
    return np.nan_to_num(np.maximum(0, -0.25 + 2.40 * np.sqrt(p)), nan=5.0)


def load():
    Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
    cal = sorted(pd.read_parquet(ROOT / "cache/m1_daysum.parquet", columns=["d"]).d.unique()); nx = dict(zip(cal, cal[1:]))
    Z["d1"] = Z.d.map(nx)
    Z = Z.merge(pd.read_pickle(r"C:\temp\kp\nxt_v0.pkl"), on=["t", "d1"], how="left"); Z["v0f"] = Z.v0.fillna(Z.a10)
    T6 = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].dropna(subset=["d1", "g_vw"]).copy()
    T6 = T6[(T6.d1 >= D0) & (T6.d1 <= D1)].sort_values(["d1", "AH50"])
    S = pd.read_pickle(r"C:\temp\kp\pmrev5_panel_1103.pkl")
    S = S[(S.tm == 840) & S.r_vw.notna() & (S.rpre <= -3) & (S.cum <= 1_019_060_000) & (S.d >= D0) & (S.d <= D1)].copy()
    S["k"] = np.select([S.rpre <= -5, S.rpre <= -4], [3, 2], 1)
    T5 = S.sort_values(["d", "rpre"])
    U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
    U = U[(U.date >= D0) & (U.date <= D1) & (U.liq <= 2 / 3) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= -0.5)].dropna(subset=["oc", "amt20"]).copy()
    U["lm"] = (U.amt20 / U.groupby("date").amt20.transform("median")).clip(0.3, 3)
    T1 = U.sort_values(["date", "rgap"])
    return T6, T5, T1


def sim(T6g, T5g, T1g, days, cfg, imp, fill):
    b1, dcap, p5, acct6, cap6 = cfg
    out = []
    for d in days:
        used6 = pnl6 = 0.0
        g = T6g.get(d)
        if g is not None and acct6 > 0:
            amt = np.minimum(cap6, 0.10 * g.v41.to_numpy())[:40]
            amt = np.where(amt >= 30e4, amt, 0)
            room = min(acct6, EQ); cum = np.cumsum(amt); amt = np.clip(room - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0)
            r = g.g_vw.to_numpy()[:40] - nimp(amt, g.a10.to_numpy()[:40]) - nimp(amt, g.v0f.to_numpy()[:40])
            used6 = amt.sum(); pnl6 = float(np.sum(amt * r / 100))
        used5 = pnl5 = 0.0
        g = T5g.get(d)
        if g is not None and p5 > 0:
            amt = np.minimum(p5 * g.k.to_numpy(), 0.10 * g.val5.to_numpy())
            room = EQ - used6; cum = np.cumsum(amt); amt = np.clip(room - (cum - amt), 0, amt)
            r = g.r_vw.to_numpy() - nimp(amt, g.val5.to_numpy())
            used5 = amt.sum(); pnl5 = float(np.nansum(amt * r / 100))
        res1 = pnl1 = 0.0; cut = 0
        g = T1g.get(d)
        if g is not None:
            want = b1 * (-g.rgap.to_numpy()).clip(1, dcap) * g.lm.to_numpy()
            room = EQ - used6 - used5; cum = np.cumsum(want); amt = np.clip(room - (cum - want), 0, want)
            cut = int((amt < want - 1).sum())
            res1 = amt.sum()
            f = (g.rgap.to_numpy() <= -1.5) & (amt > 0)
            a, oc, a20 = amt[f], g.oc.to_numpy()[f], g.amt20.to_numpy()[f] * 1e8
            p = a / a20 * 100
            pnl1 = float(np.sum(a * fill(p) * (oc - COST - imp(p)) / 100) * 0.89)
        out.append((d, pnl6, pnl5, pnl1, used6, used5, res1, cut, (used6 + used5 + res1) >= EQ * 0.999))
    return pd.DataFrame(out, columns=["d", "p6", "p5", "p1", "u6", "u5", "r1", "cut", "full"])


def summ(R):
    R = R.assign(p=R.p6 + R.p5 + R.p1, m=R.d.str[:6])
    pm = R.groupby("m").p.sum() / 1e4
    cum = R.p.cumsum(); dd = (cum - cum.cummax()).min() / 1e4
    h = {y: R[R.d.str[:4] == y].groupby("m").p.sum().median() / 1e4 for y in ("2025", "2026")}
    return dict(med=pm.median(), mean=pm.mean(), worst=pm.min(), pos=(pm > 0).mean() * 100, yr=pm.mean() * 12, dd=dd,
                full=R.full.mean() * 100, h25=h["2025"], h26=h["2026"],
                k6=R.p6.sum() / len(pm) / 1e4, k5=R.p5.sum() / len(pm) / 1e4, k1=R.p1.sum() / len(pm) / 1e4,
                peak=(R.u6 + R.u5 + R.r1).quantile(0.9) / 1e4)


def main():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    T6, T5, T1 = load()
    days = sorted(set(T1.date) | set(T5.d) | set(T6.d1))
    days = [d for d in days if D0 <= d <= D1]
    T6g = {d: g for d, g in T6.groupby("d1")}; T5g = {d: g for d, g in T5.groupby("d")}; T1g = {d: g for d, g in T1.groupby("date")}
    P("# 데이 3규칙 1억 계좌 · %s~%s · 거래일 %d · T6 %d건 · T5 %d건 · T1 그물 %d건(사지는 것 %d)" % (
        D0, D1, len(days), len(T6), len(T5), len(T1), (T1.rgap <= -1.5).sum()))
    P("T1 체결 손해: max(0, %.2f+%.2f√p) · 체결 1/(1+%.2fp)" % (ab[0], ab[1], cf))
    grid = list(itertools.product((20e4, 30e4, 50e4, 70e4), (2, 3), (0, 30e4, 50e4, 100e4), ((0, 0), (1000e4, 200e4), (2000e4, 300e4), (3000e4, 500e4))))
    rows = []
    for b1, dcap, p5, (a6, c6) in grid:
        s = summ(sim(T6g, T5g, T1g, days, (b1, dcap, p5, a6, c6), imp, fill))
        rows.append(dict(b1=b1, dcap=dcap, p5=p5, a6=a6, c6=c6, **s))
    R = pd.DataFrame(rows)
    R.to_pickle(BASE / "data" / "day_acct_1e8_grid.pkl")
    nm = lambda r: "T1 %d만·깊이%d | T5 %s | T6 %s" % (r.b1 / 1e4, r.dcap, "끔" if not r.p5 else "%d만" % (r.p5 / 1e4),
                                                    "끔" if not r.a6 else "%d천만·%d만" % (r.a6 / 1e7, r.c6 / 1e4))
    cols = "| 조합 | 달 중앙 | 달 평균 | 1년(평균×12) | 최악의 달 | 플러스 달 | 최대 낙폭 | 2025 달 중앙 | 2026 달 중앙 | 돈 꽉 찬 날 | 몫 T6/T5/T1(달) |"
    P("\n## 달 손익 중앙값 위 15 (만원, 고정 1억)\n"); P(cols); P("|---" * 11 + "|")
    for _, r in R.sort_values("med", ascending=False).head(15).iterrows():
        P("| %s | %+.0f | %+.0f | %+.0f | %+.0f | %.0f%% | %.0f | %+.0f | %+.0f | %.0f%% | %+.0f/%+.0f/%+.0f |" % (
            nm(r), r.med, r["mean"], r.yr, r.worst, r.pos, r.dd, r.h25, r.h26, r.full, r.k6, r.k5, r.k1))
    cur = R[(R.b1 == 50e4) & (R.dcap == 3) & (R.p5 == 100e4) & (R.a6 == 3000e4)].iloc[0]
    P("\n지금 설정(T1 50만·깊이3 | T5 100만 | T6 3천만·500만): 달 중앙 %+.0f · 평균 %+.0f · 1년 %+.0f · 최악 %+.0f · 낙폭 %.0f · 2025/2026 %+.0f/%+.0f · 꽉 찬 날 %.0f%% · 08:53 묶이는 돈 90%% %.0f만" % (
        cur.med, cur["mean"], cur.yr, cur.worst, cur.dd, cur.h25, cur.h26, cur.full, cur.peak))
    P("\n## 규칙 하나씩 빼면(나머지는 위 1등 설정)")
    best = R.sort_values("med", ascending=False).iloc[0]
    for lab, m in (("1등", (R.b1 == best.b1) & (R.dcap == best.dcap) & (R.p5 == best.p5) & (R.a6 == best.a6)),
                   ("T6 끔", (R.b1 == best.b1) & (R.dcap == best.dcap) & (R.p5 == best.p5) & (R.a6 == 0)),
                   ("T5 끔", (R.b1 == best.b1) & (R.dcap == best.dcap) & (R.p5 == 0) & (R.a6 == best.a6))):
        r = R[m].iloc[0]; P("· %s: 달 중앙 %+.0f · 평균 %+.0f · 최악 %+.0f · 2025/2026 %+.0f/%+.0f" % (lab, r.med, r["mean"], r.worst, r.h25, r.h26))
    P("\n## 두 토막 모두 위 20%% 안인 조합(과적합 확인)")
    q25, q26 = R.h25.quantile(0.8), R.h26.quantile(0.8)
    for _, r in R[(R.h25 >= q25) & (R.h26 >= q26)].sort_values("med", ascending=False).head(8).iterrows():
        P("· %s: 달 중앙 %+.0f · 2025 %+.0f · 2026 %+.0f · 최악 %+.0f" % (nm(r), r.med, r.h25, r.h26, r.worst))
    (ROOT / "day_acct_1e8_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
