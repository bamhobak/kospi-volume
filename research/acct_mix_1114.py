# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "자본금 1억, 혹은 2억일 때 가장 많은 수익을 낼 수 있는 규칙들 활용 방법 비교" — 3단계: 한 계좌로 합치기.
창 = 2025-04-01~2026-10-08(데이 T5·T6 자료가 있는 구간, NXT 뒤) · 값은 만원.
  스윙  = research/mix_swing_1114 (portfolio.py 9규칙, 비중 × m, 금액 체결 손해) — 계좌 전체를 기준으로 금액을 잡는다.
  P9    = research/mix_p9_1114 ([반대매매] 갭-3%·7일, 보수 체결)
  데이  = day_acct_2e8_3e8_1110 run 그대로(T1 예상 오차·T5·T6 체결 손해), 단 그날 쓸 수 있는 돈 = 계좌 평가 − 스윙 묶인 돈 − P9 묶인 돈.
  CMA   = 그날 아무 데도 안 쓰인 돈 × 연 2.5%.
    python research/acct_mix_1114.py   → research/reports/acct_mix_1114.md"""
import io, contextlib, sys, pickle, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import day_acct_1e8_1110 as A
import day_acct_1e8_net_1110 as N
NET, LIM, IDIO, SEEDS = -1.0, -2.0, 0.7, 10
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))


def run(T6g, T5g, T1, days, EQd, b1, p5, a6, c6, k6, E, rng, imp, fill):
    ed = dict(zip(days, rng.choice(E, len(days))))
    X = T1.assign(e=T1.date.map(ed).fillna(0.41))
    X["xrel"] = X.rgap + X.e + rng.normal(0, IDIO, len(X))
    X = X[X.xrel <= NET].sort_values(["date", "xrel"])
    G = {d: g for d, g in X.groupby("date")}
    out = np.zeros((len(days), 4))
    for j, d in enumerate(days):
        EQ = max(0.0, EQd[j]); used6 = pnl6 = used5 = pnl5 = pnl1 = res1 = 0.0
        g = T6g.get(d)
        if g is not None and EQ > 0:
            amt = np.minimum(c6, k6 * g.v41.to_numpy())[:40]; amt = np.where(amt >= 30e4, amt, 0)
            cum = np.cumsum(amt); amt = np.clip(min(a6, EQ) - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0)
            r = g.g_vw.to_numpy()[:40] - A.nimp(amt, g.a10.to_numpy()[:40]) - A.nimp(amt, g.v0f.to_numpy()[:40])
            used6 = amt.sum(); pnl6 = float(np.sum(amt * r / 100))
        g = T5g.get(d)
        if g is not None and EQ > 0:
            amt = np.minimum(p5 * g.k.to_numpy(), 0.10 * g.val5.to_numpy())
            cum = np.cumsum(amt); amt = np.clip(EQ - used6 - (cum - amt), 0, amt)
            r = g.r_vw.to_numpy() - A.nimp(amt, g.val5.to_numpy()); used5 = amt.sum(); pnl5 = float(np.nansum(amt * r / 100))
        g = G.get(d)
        if g is not None and EQ > 0:
            want = b1 * (-g.xrel.to_numpy()).clip(1, 3) * g.lm.to_numpy()
            cum = np.cumsum(want); amt = np.clip(EQ - used6 - used5 - (cum - want), 0, want); res1 = amt.sum()
            f = (g.rgap.to_numpy() <= LIM + g.e.to_numpy()) & (amt > 0)
            a, oc, a20 = amt[f], g.oc.to_numpy()[f], g.amt20.to_numpy()[f] * 1e8
            p = a / a20 * 100
            pnl1 = float(np.sum(a * fill(p) * (oc - A.COST - imp(p)) / 100))
        out[j] = (pnl6, pnl5, pnl1, used6 + used5 + res1)
    return out


def main():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    E, ne = N.live_e()
    T6, T5, _ = A.load(); T1 = N.t1_wide()
    days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if A.D0 <= d <= A.D1]
    T6g, T5g = {d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}
    CAPS = [float(x) * 1e8 for x in sys.argv[1:]] or [1e8, 2e8]
    SW = {"win": {}, "long": {}}
    import glob as _g
    for f in _g.glob(r"C:\temp\kp\mix_swing*.pkl"):
        z = pickle.load(open(f, "rb")); SW["win"].update(z["win"]); SW["long"].update(z["long"])
    P9 = pickle.load(open(r"C:\temp\kp\mix_p9.pkl", "rb"))
    nd = len(days); yrs = nd / 250
    P("# %s 계좌 — 규칙 활용법 비교 (%s~%s · %d거래일 · 값 만원)" % ("·".join("%g억" % (c / 1e8) for c in CAPS), days[0], days[-1], nd)); P("")

    def swing(C, m):
        if m == 0: return np.zeros(nd), np.zeros(nd)
        r = SW["win"][(C, m)]; s = pd.DataFrame({"nav": r["nav"], "inv": r["inv"]}, index=r["d"]).reindex(days).ffill().fillna({"nav": C, "inv": 0})
        return s.nav.to_numpy() - C, s.inv.to_numpy()          # 누적 손익(평가) · 묶인 돈

    def p9(key):
        if key is None: return np.zeros(nd), np.zeros(nd)
        z = P9[key]; z = z[(z.date >= days[0]) & (z.date <= days[-1])]
        di = {d: j for j, d in enumerate(days)}; lock = np.zeros(nd); pnl = np.zeros(nd)
        for r in z.itertuples():
            a = di.get(r.date); b = di.get(r.sell, nd - 1) if r.sell <= days[-1] else nd - 1
            if a is None: continue
            lock[a:b + 1] += r.inv
            if r.sell <= days[-1]: pnl[b] += r.pnl
        return np.cumsum(pnl), lock

    DAYCFG = {"없음": None, "지금 실전(T6 5천만)": (30e4, 100e4, 5000e4, 500e4, 0.10), "큰 판(T6 1억·1,500만·T5 200만)": (30e4, 200e4, 1e8, 1500e4, 0.10),
              "더 큰 판(T6 1.5억·2,000만·T5 300만)": (30e4, 300e4, 1.5e8, 2000e4, 0.10)}

    def evals(C, m, pkey, dkey):
        sp, sl = swing(C, m); pp, pl = p9(pkey)
        base = C + sp + pp                                     # 데이 전 평가(근사: 스윙 평가 손익 포함)
        cash = np.maximum(0, np.r_[C, base[:-1]] - sl - pl)
        if DAYCFG[dkey] is None: dd = np.zeros((nd, 4))
        else:
            dd = np.mean([run(T6g, T5g, T1, days, cash, *DAYCFG[dkey], E, np.random.default_rng(s), imp, fill) for s in range(SEEDS)], axis=0)
        dpnl = np.cumsum(dd[:, :3].sum(1))
        idle = np.maximum(0, cash - dd[:, 3]); cma = np.cumsum(idle * (1.025 ** (1 / 250) - 1))
        tot = sp + pp + dpnl
        nav = C + tot; navc = nav + cma
        mdd = (navc / np.maximum.accumulate(navc) - 1).min() * 100
        mon = pd.Series(np.diff(np.r_[0, tot + cma]), index=[d[:6] for d in days]).groupby(level=0).sum() / 1e4
        return dict(tot=tot[-1] / 1e4, cma=cma[-1] / 1e4, sw=sp[-1] / 1e4, p9=pp[-1] / 1e4, day=dpnl[-1] / 1e4,
                    d6=dd[:, 0].sum() / 1e4, d5=dd[:, 1].sum() / 1e4, d1=dd[:, 2].sum() / 1e4,
                    yr=(tot[-1] + cma[-1]) / C / yrs * 100, mdd=mdd, med=mon.median(), worst=mon.min(), pos=(mon > 0).mean() * 100,
                    lock=(sl + pl).mean() / 1e4, idle=idle.mean() / 1e4, short=(cash < 1e7).mean() * 100,
                    y25=mon[mon.index.str[:4] == "2025"].sum(), y26=mon[mon.index.str[:4] == "2026"].sum())

    HD = ("| 활용법 | 합계(창 전체) | 1년 % (CMA 포함) | 스윙 / P9 / 데이 / CMA | 데이 몫 T6·T5·T1 | 달 중앙 | 최악의 달 | 플러스 달 | 최대 낙폭(매일 평가) | 스윙+P9 묶인 돈 평균 | 데이 쓸 돈 1천만↓ 날 |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|")
    for C in CAPS:
        P("\n## 계좌 %d억\n" % (C / 1e8)); P(HD)
        pk = (200e4, 5e7)
        if C >= 3e8:                                           # 11-14 사용자 "3억 5억이 자본금이라면"
            BIG, BIG2, pk1, pk3 = "큰 판(T6 1억·1,500만·T5 200만)", "더 큰 판(T6 1.5억·2,000만·T5 300만)", (200e4, 1e8), (300e4, 1e8)
            L = [("데이만 · 큰 판", 0, None, BIG), ("데이만 · 더 큰 판", 0, None, BIG2), ("스윙만 ×1(지금 비중)", 1.0, None, "없음"),
                 ("[반대매매] 하루 1억 + 데이 더 큰 판 (스윙 없음)", 0, pk1, BIG2)]
            for m in (0.5, 1.0, 1.5, 2.0):
                L.append(("스윙 ×%g + [반대매매] 하루 1억 + 데이 큰 판" % m, m, pk1, BIG))
                L.append(("스윙 ×%g + [반대매매] 하루 1억 + 데이 더 큰 판" % m, m, pk1, BIG2))
            L += [("스윙 ×1 + [반대매매] 300만·하루 1억 + 데이 더 큰 판", 1.0, pk3, BIG2),
                  ("스윙 ×1.5 + [반대매매] 300만·하루 1억 + 데이 더 큰 판", 1.5, pk3, BIG2)]
            for lab, m, pkey, dkey in L:
                r = evals(C, m, pkey, dkey)
                P("| %s | **%+.0f** | %+.1f%% | %+.0f / %+.0f / %+.0f / %+.0f | %+.0f·%+.0f·%+.0f | %+.0f | %+.0f | %.0f%% | %.1f%% | %.0f | %.0f%% |" % (
                    lab, r["tot"] + r["cma"], r["yr"], r["sw"], r["p9"], r["day"], r["cma"], r["d6"], r["d5"], r["d1"], r["med"], r["worst"], r["pos"], r["mdd"], r["lock"], r["short"]))
            continue
        L = [("데이만 · 지금 실전", 0, None, "지금 실전(T6 5천만)"), ("데이만 · 큰 판", 0, None, "큰 판(T6 1억·1,500만·T5 200만)"),
             ("스윙만 ×1(지금 비중)", 1.0, None, "없음"), ("스윙 ×1 + [반대매매]", 1.0, pk, "없음"),
             ("[반대매매] + 데이 큰 판 (스윙 없음)", 0, pk, "큰 판(T6 1억·1,500만·T5 200만)"),
             ("스윙 ×1 + [반대매매] + 데이 지금", 1.0, pk, "지금 실전(T6 5천만)"), ("스윙 ×1 + [반대매매] + 데이 큰 판", 1.0, pk, "큰 판(T6 1억·1,500만·T5 200만)"),
             ("스윙 ×0.5 + [반대매매] + 데이 큰 판", 0.5, pk, "큰 판(T6 1억·1,500만·T5 200만)"),
             ("스윙 ×1.5 + [반대매매] + 데이 큰 판", 1.5, pk, "큰 판(T6 1억·1,500만·T5 200만)"),
             ("스윙 ×2 + [반대매매] + 데이 큰 판", 2.0, pk, "큰 판(T6 1억·1,500만·T5 200만)"),
             ("스윙 ×1.5 + [반대매매] + 데이 지금", 1.5, pk, "지금 실전(T6 5천만)")]
        if C == 2e8:
            L += [("스윙 ×1 + [반대매매] 하루 1억 + 데이 큰 판", 1.0, (200e4, 1e8), "큰 판(T6 1억·1,500만·T5 200만)"),
                  ("스윙 ×1.5 + [반대매매] 하루 1억 + 데이 큰 판", 1.5, (200e4, 1e8), "큰 판(T6 1억·1,500만·T5 200만)")]
        for lab, m, pkey, dkey in L:
            r = evals(C, m, pkey, dkey)
            P("| %s | **%+.0f** | %+.1f%% | %+.0f / %+.0f / %+.0f / %+.0f | %+.0f·%+.0f·%+.0f | %+.0f | %+.0f | %.0f%% | %.1f%% | %.0f | %.0f%% |" % (
                lab, r["tot"] + r["cma"], r["yr"], r["sw"], r["p9"], r["day"], r["cma"], r["d6"], r["d5"], r["d1"], r["med"], r["worst"], r["pos"], r["mdd"], r["lock"], r["short"]))
    P("\n## 참고 — 스윙 혼자 긴 기간(2016-01~2026-10, 같은 체결 손해, 복리)\n")
    P("| 계좌 | 배율 | 끝 배수 | 2016~22 연 | 2023~ 연 | 최대 낙폭 |"); P("|---|---|---|---|---|---|")
    for (C, m), r in sorted(SW["long"].items()):
        if C not in CAPS: continue
        x =pd.Series(r["nav"], index=r["d"])
        a = x[x.index <= "20221231"]; b = x[x.index >= "20221229"]
        ya = (a.iloc[-1] / a.iloc[0]) ** (250 / len(a)) - 1; yb = (b.iloc[-1] / b.iloc[0]) ** (250 / len(b)) - 1
        P("| %d억 | ×%.1f | %.1f배 | %+.1f%% | %+.1f%% | %.1f%% |" % (C / 1e8, m, x.iloc[-1] / C, ya * 100, yb * 100, (x / x.cummax() - 1).min() * 100))
    (ROOT / "reports" / ("acct_mix_1114.md" if CAPS == [1e8, 2e8] else "acct_mix_1114_%s.md" % "_".join("%g" % (c / 1e8) for c in CAPS))).write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
