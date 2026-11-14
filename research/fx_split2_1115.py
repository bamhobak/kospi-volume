# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "1억 5천만이면? 각 비용·수익금도 비교해봐 국장 미장 따로" — fx_split_1115 에 비용·세금을 갈라 붙인 판.
원화 = acct_mix 틀(스윙 port_sig · [반대매매] · 데이 큰 판 · CMA 2.5%) · 달러 = 미장 6규칙(건당 미장 계좌 2%) · 합계 = 원화 + 달러 × 환율.
비용 나누기
  국장: 세금·수수료 = 왕복 0.23%(매도세 0.20 + 토스 0.015×2) · 체결 손해 = 스윙 패널 미끄러짐(거래대금 구간 0.20~1.00) + 금액 충격(√p) ·
        데이 T6·T5 √충격(nxt 모형) · T1 체결 손해(t1_size_liq) · [반대매매] √충격 · CMA 이자 15.4% 원천징수
  미장: 수수료 = 토스 왕복 0.202%(매수 0.1 + 매도 0.102 — 사이트 DEFFEE) — **연구 거래 목록엔 안 들어 있어 여기서 뺌** ·
        체결 손해 = 연구 패널 cost(거래대금 구간 0.10~0.60) · 양도세 = 해마다 (원화 환산 실현 차익 − 250만) × 22%(환차익 포함, 그해 끝에 뗀다고 봄)
  환전 수수료는 모름(한 번 바꿀 때만 듦) — 안 넣음.
창 = 2025-04-01 ~ 2026-06-30.
    python research/memguard.py research/fx_split2_1115.py   → research/reports/fx_split2_1115.md"""
import sys, io, contextlib, pickle, math, time, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import acct_mix_1114 as AM
A, N = AM.A, AM.N
D0, D1 = "20250401", "20260630"
SEEDS = 6; KRFEE = 0.23; USFEE = 0.202; USTAX, USDED = 0.22, 250e4
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
t0 = time.time()

# ── 미장 거래별 체결 손해(연구 패널 cost) — 무거운 파일 먼저 읽고 버린다
HOLD = {"N1": 40, "N3": 60, "N5": 60, "N6": 60, "N8": 250, "N9": 40}
ALL = pd.read_pickle(ROOT / "cache" / "us_rules_recheck.pkl")
TR = pd.concat([ALL[r].dropna(subset=["ret"]).assign(rid=r) for r in HOLD], ignore_index=True)
TR = TR[(TR.date >= D0) & (TR.date <= D1)].copy(); TR["ticker"] = TR.ticker.astype(str)
U7 = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")
U7 = U7.loc[U7.date >= "20250301", ["ticker", "date", "cost"]]; U7["ticker"] = U7.ticker.astype(str)
TR = TR.merge(U7, on=["ticker", "date"], how="left"); del U7
import gc; gc.collect()
TR["slip"] = TR.cost.fillna(0.30); TR["ret2"] = TR.ret - USFEE
print("미장 체결 손해 붙임(빈칸 %.0f%%) %.1f분" % (TR.cost.isna().mean() * 100, (time.time() - t0) / 60), flush=True)

# ── 데이
import t1_size_liq_1021 as SL
with contextlib.redirect_stdout(io.StringIO()):
    ab, cf = SL.fit(SL.liq_of_exec())
imp_d = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
E, _ = N.live_e()
T6, T5, _ = A.load(); T1 = N.t1_wide()
days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if max(A.D0, D0) <= d <= D1]
T6g, T5g = {d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}
nd = len(days); yrs = nd / 250


def run2(days, EQd, b1, p5, a6, c6, k6, rng):
    """acct_mix.run 과 같은 계산 + 비용 칸: 손익6·5·1, 쓴 돈, 세금수수료, 체결 손해"""
    ed = dict(zip(days, rng.choice(E, len(days))))
    X = T1.assign(e=T1.date.map(ed).fillna(0.41))
    X["xrel"] = X.rgap + X.e + rng.normal(0, AM.IDIO, len(X))
    X = X[X.xrel <= AM.NET].sort_values(["date", "xrel"])
    G = {d: g for d, g in X.groupby("date")}
    out = np.zeros((len(days), 6))
    for j, d in enumerate(days):
        EQ = max(0.0, EQd[j]); used6 = pnl6 = used5 = pnl5 = pnl1 = res1 = fee = slip = 0.0
        g = T6g.get(d)
        if g is not None and EQ > 0:
            amt = np.minimum(c6, k6 * g.v41.to_numpy())[:40]; amt = np.where(amt >= 30e4, amt, 0)
            cum = np.cumsum(amt); amt = np.clip(min(a6, EQ) - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0)
            ii = A.nimp(amt, g.a10.to_numpy()[:40]) + A.nimp(amt, g.v0f.to_numpy()[:40])
            r = g.g_vw.to_numpy()[:40] - ii
            used6 = amt.sum(); pnl6 = float(np.sum(amt * r / 100)); fee += used6 * KRFEE / 100; slip += float(np.sum(amt * ii / 100))
        g = T5g.get(d)
        if g is not None and EQ > 0:
            amt = np.minimum(p5 * g.k.to_numpy(), 0.10 * g.val5.to_numpy())
            cum = np.cumsum(amt); amt = np.clip(EQ - used6 - (cum - amt), 0, amt)
            ii = A.nimp(amt, g.val5.to_numpy()); r = g.r_vw.to_numpy() - ii
            used5 = amt.sum(); pnl5 = float(np.nansum(amt * r / 100)); fee += used5 * KRFEE / 100; slip += float(np.nansum(amt * ii / 100))
        g = G.get(d)
        if g is not None and EQ > 0:
            want = b1 * (-g.xrel.to_numpy()).clip(1, 3) * g.lm.to_numpy()
            cum = np.cumsum(want); amt = np.clip(EQ - used6 - used5 - (cum - want), 0, want); res1 = amt.sum()
            f = (g.rgap.to_numpy() <= AM.LIM + g.e.to_numpy()) & (amt > 0)
            a, oc, a20 = amt[f], g.oc.to_numpy()[f], g.amt20.to_numpy()[f] * 1e8
            p = a / a20 * 100; af = a * fill(p)
            pnl1 = float(np.sum(af * (oc - A.COST - imp_d(p)) / 100)); fee += float(np.sum(af)) * A.COST / 100; slip += float(np.sum(af * imp_d(p) / 100))
        out[j] = (pnl6 + pnl5 + pnl1, used6 + used5 + res1, fee, slip, pnl6, pnl1)
    return out


# ── 스윙
Z = pickle.load(open(r"C:\temp\kp\port_sig.pkl", "rb")); S, dates = Z["S"], Z["dates"]
DI = {d: i for i, d in enumerate(dates)}; ND = len(dates)
i0 = DI[min(d for d in dates if d >= D0)]; i1 = DI[max(d for d in dates if d <= D1)]
PX = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl")[["ticker", "date", "close"]]
PX = PX[(PX.date >= dates[i0 - 5]) & (PX.date <= D1)]
TK = np.array(sorted(set(PX.ticker.astype(str)) | set(S.ticker.astype(str)))); TI = {t: i for i, t in enumerate(TK)}
CL = np.full((ND, len(TK)), np.nan, np.float32)
di_ = PX.date.map(DI); ok = di_.notna().values
CL[di_.values[ok].astype(int), PX.ticker.astype(str).map(TI).values[ok]] = PX.close.values[ok]
CLf = pd.DataFrame(CL[i0 - 5:i1 + 1]).ffill().values; del CL, PX
S = S[(S.di >= i0) & (S.di <= i1)].copy(); S["ti"] = S.ticker.astype(str).map(TI)
UNIT = 1e8 if S.amt20.median() < 1e5 else 1.0
TOD = {i: g for i, g in S.groupby("di")}
imp_s = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))


def swing_sim(C, m):
    eq = C; pos = []; nav = []; inv_ = []; fee = slip = 0.0
    for i in range(i0, i1 + 1):
        still = []
        for p in pos:
            if p["x"] <= i:
                eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"] - p["imp"]) / 100
                fee += p["amt"] * KRFEE / 100; slip += p["amt"] * (p["cost"] - KRFEE + p["imp"]) / 100
            else: still.append(p)
        pos = still
        T = TOD.get(i)
        if T is not None:
            inv = sum(p["amt"] for p in pos)
            for t in T.itertuples():
                w = eq * t.pct / 100 * m
                if sum(1 for p in pos if p["rid"] == t.rid) >= t.mx or inv + w > eq or any(p["tk"] == t.ticker for p in pos): continue
                pi = w / (t.amt20 * UNIT) * 100 if t.amt20 and t.amt20 > 0 else 50
                pos.append(dict(rid=t.rid, tk=t.ticker, ti=t.ti, buy=t.buy, exit=t.exit, cost=t.cost, imp=imp_s(pi), amt=w, x=i + t.hold, d0=i))
                inv += w
        inv = sum(p["amt"] for p in pos); un = 0.0
        for p in pos:
            if i > p["d0"]:
                c = CLf[i - i0 + 5, p["ti"]]
                if c == c: un += p["amt"] * (c / p["buy"] - 1)
        nav.append(eq + un); inv_.append(inv)
    s = pd.DataFrame({"nav": nav, "inv": inv_}, index=dates[i0:i1 + 1]).reindex(days).ffill().fillna({"nav": C, "inv": 0})
    return s.nav.to_numpy() - C, s.inv.to_numpy(), fee, slip


# ── [반대매매]: mix_p9 처럼 crmap8.run 을 다시 돌려 r(0.23 뒤)·net(충격 뒤) 둘 다 받는다
src = (ROOT / "crmap8_1112.py").read_text(encoding="utf-8").replace(chr(13), "")
KEY = "    z = z[z.inv > 0].copy()" + chr(10)
assert KEY in src
src = src.split("OUT = []; P = lambda")[0].replace(KEY, KEY + "    if RET_Z: return z" + chr(10))
ns = {"__file__": str(ROOT / "crmap8_1112.py"), "__name__": "x", "RET_Z": True}
exec(compile(src, "crmap8", "exec"), ns)
P9 = {}
for key in ((200e4, 5e7), (200e4, 1e8)):
    z = ns["run"](-3, 7, key[0], key[1], False)
    P9[key] = z[["date", "sell", "inv", "r", "net", "pnl"]].reset_index(drop=True)
del ns; gc.collect()
print("데이·스윙·P9 재료 %.1f분" % ((time.time() - t0) / 60), flush=True)


def p9(key):
    z = P9[key]; z = z[(z.date >= days[0]) & (z.date <= days[-1])]
    di = {d: j for j, d in enumerate(days)}; lock = np.zeros(nd); pnl = np.zeros(nd); fee = slip = 0.0
    for r in z.itertuples():
        a = di.get(r.date); b = di.get(r.sell, nd - 1) if r.sell <= days[-1] else nd - 1
        if a is None: continue
        lock[a:b + 1] += r.inv
        if r.sell <= days[-1]:
            pnl[b] += r.pnl; fee += r.inv * KRFEE / 100; slip += r.inv * (r.r - r.net) / 100
    return np.cumsum(pnl), lock, fee, slip


BIG = (30e4, 200e4, 1e8, 1500e4, 0.10)
SWC = {}


def kr(C, m, pkey):
    if (C, m) not in SWC: SWC[(C, m)] = swing_sim(C, m)
    sp, sl, sf, ss = SWC[(C, m)]; pp, pl, pf, ps = p9(pkey)
    base = C + sp + pp
    cash = np.maximum(0, np.r_[C, base[:-1]] - sl - pl)
    dd = np.mean([run2(days, cash, *BIG, np.random.default_rng(s)) for s in range(SEEDS)], axis=0)
    dpnl = np.cumsum(dd[:, 0])
    idle = np.maximum(0, cash - dd[:, 1]); cma = np.cumsum(idle * (1.025 ** (1 / 250) - 1)) * (1 - 0.154)
    navc = C + sp + pp + dpnl + cma
    lab = "스윙 ×%g · [반대매매] 하루 %g천만 · 데이 큰 판" % (m, pkey[1] / 1e7)
    fee = sf + pf + dd[:, 2].sum(); slip = ss + ps + dd[:, 3].sum(); ctax = cma[-1] / (1 - 0.154) * 0.154
    return dict(navc=navc, lab=lab, tot=navc[-1] - C, sw=sp[-1], p9=pp[-1], day=dpnl[-1], cma=cma[-1], fee=fee, slip=slip, ctax=ctax,
                mdd=(navc / np.maximum.accumulate(navc) - 1).min() * 100)


KRC = {}


def best_kr(K):
    if K not in KRC:
        c = [kr(K, m, pk) for m in (1.0, 1.5) for pk in ((200e4, 5e7), (200e4, 1e8)) if not (pk[1] > 5e7 and K < 1.4e8)]
        KRC[K] = max(c, key=lambda r: r["tot"])
        print("  원화 %.2f억 · %.1f분" % (K / 1e8, (time.time() - t0) / 60), flush=True)
    return KRC[K]


# ── 미장 계좌(원화 금액 U 마다 양도세 문턱이 달라 금액별로 계산)
import FinanceDataReader as fdr
fx = fdr.DataReader("USD/KRW", "2025-03-01")["Close"]; fx.index = fx.index.strftime("%Y%m%d")
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay
ud = [d.strftime("%Y%m%d") for d in pd.date_range("20240101", "20280101", freq=CustomBusinessDay(calendar=USFederalHolidayCalendar()))]
UDI = {d: i for i, d in enumerate(ud)}
fxu = fx.reindex(fx.index.union(pd.Index(ud))).ffill().bfill().reindex(ud).to_numpy()
TR["i0"] = TR.date.map(lambda d: UDI.get(d, UDI[min(x for x in ud if x >= d)])); TR["i_in"] = TR.i0 + 1
TR["i_out"] = TR.i0 + TR.rid.map(HOLD)
LO, HI = UDI[min(x for x in ud if x >= D0)], UDI[max(x for x in ud if x <= D1)]
kd = pd.Index(days); fx_k = fx.reindex(fx.index.union(kd)).ffill().reindex(kd).bfill().to_numpy(); fx0 = fx_k[0]


def us_run(U, seed):
    """달러 계좌 U(원) — 원화 평가 경로·수수료·체결 손해·양도세(원). 손익은 ret2(수수료 뒤)"""
    rng = np.random.default_rng(seed)
    Zs = TR.assign(k=rng.random(len(TR))).sort_values(["i_in", "k"]); byday = {d: g for d, g in Zs.groupby("i_in")}
    eq = cash = U / fx0; open_ = []; path = {}; fee = slip = 0.0; gain_y = {}; tax = 0.0
    for d in range(LO, HI + 1):
        keep = []
        for (o, amt, r, s_, ib) in open_:
            if o <= d:
                cash += amt * (1 + r / 100); eq += amt * r / 100
                fee += amt * USFEE / 100 * fxu[d]; slip += amt * s_ / 100 * fxu[d]
                y = ud[d][:4]; gain_y[y] = gain_y.get(y, 0) + amt * (1 + r / 100) * fxu[d] - amt * fxu[ib]   # 원화 실현 차익(환차익 포함)
            else: keep.append((o, amt, r, s_, ib))
        open_ = keep
        if d in byday:
            for r in byday[d].itertuples():
                amt = 0.02 * eq
                if cash < amt: continue
                cash -= amt; open_.append((r.i_out, amt, r.ret2, r.slip, d))
        if d + 1 <= HI and ud[d][:4] != ud[d + 1][:4] or d == HI:      # 해 끝 — 양도세 뗌(달러에서 빠진다고 봄)
            y = ud[d][:4]; t = USTAX * max(0.0, gain_y.get(y, 0) - USDED); tax += t
            eq -= t / fxu[d]; cash -= t / fxu[d]
        path[ud[d]] = eq * fxu[d]
    p = pd.Series(path); p = p.reindex(p.index.union(kd)).ffill().reindex(kd).fillna(U).to_numpy()
    return p, fee, slip, tax


def us_acct(U):
    if U <= 0: return dict(nav=np.zeros(nd), tot=0, fee=0, slip=0, tax=0)
    R = [us_run(U, s) for s in range(15)]
    nav = np.median([r[0] for r in R], axis=0)
    return dict(nav=nav, tot=nav[-1] - U, fee=np.median([r[1] for r in R]), slip=np.median([r[2] for r in R]), tax=np.median([r[3] for r in R]))


P("# 원화·달러 나누기 — 비용·세금 갈라 보기 (%s~%s · %d거래일 · 값 만원 · 수익금은 비용·세금 뒤)\n" % (days[0], days[-1], nd))
P("- 국장: 세금·수수료 왕복 0.23%% · 체결 손해(미끄러짐·충격) · CMA 이자 15.4%% 원천징수 / 미장: 토스 수수료 왕복 0.202%%(연구 목록엔 없어 새로 뺌) · 체결 손해(연구 패널 0.10~0.60) · 양도세 (해마다 원화 실현 차익 − 250만) × 22%%")
P("- 원화 판 = 스윙 ×1·1.5 × [반대매매] 하루 5천만·1억(원화 1.4억↑만) 중 가장 많이 버는 것 · 데이 큰 판(T6 1억·1,500만·T5 200만) · 환전 수수료 안 넣음")
P("- 환율 %s %.0f → %s %.0f\n" % (days[0], fx0, days[-1], fx_k[-1]))
for TOT in (1e8, 1.5e8, 2e8):
    P("\n## 계좌 %g억\n" % (TOT / 1e8))
    P("| 원화 : 달러 | 국장 수익금 | 국장 비용 (세금·수수료 / 체결 손해) | 미장 수익금 | 미장 비용 (수수료 / 체결 손해 / 양도세) | **합계 수익금** | 비용 합계 | 1년 % | 최대 낙폭 | 최악의 달 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for u in (0, 0.1, 0.2, 0.3, 0.4, 0.5):
        K, U = TOT * (1 - u), TOT * u
        k = best_kr(K); us = us_acct(U)
        tot = k["navc"] + us["nav"]; g = tot[-1] - TOT
        mdd = (tot / np.maximum.accumulate(tot) - 1).min() * 100
        mon = pd.Series(np.diff(np.r_[TOT, tot]), index=[d[:6] for d in days]).groupby(level=0).sum() / 1e4
        kc = k["fee"] + k["slip"] + k["ctax"]; uc = us["fee"] + us["slip"] + us["tax"]
        P("| %d : %d%s | %+.0f | %.0f (%.0f / %.0f) | %s | %s | **%+.0f** | %.0f | %+.1f%% | %.1f%% | %+.0f |" % (
            round((1 - u) * 10), round(u * 10), " ($%s)" % format(round(U / 1336, -2), ",.0f") if U else "", k["tot"] / 1e4, kc / 1e4, (k["fee"] + k["ctax"]) / 1e4, k["slip"] / 1e4,
            "%+.0f" % (us["tot"] / 1e4) if U else "-", "%.0f (%.0f / %.0f / %.0f)" % (uc / 1e4, us["fee"] / 1e4, us["slip"] / 1e4, us["tax"] / 1e4) if U else "-",
            g / 1e4, (kc + uc) / 1e4, g / TOT / yrs * 100, mdd, mon.min()))
    P("\n원화 판: " + " · ".join("%.2g억 %s" % (K / 1e8, KRC[K]["lab"]) for K in sorted(KRC) if abs(K / TOT - round(K / TOT, 1)) < 1e-9 and K <= TOT and K >= TOT * 0.5))
(ROOT / "reports" / "fx_split2_1115.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
