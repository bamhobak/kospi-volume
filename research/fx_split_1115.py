# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "토스에서 원화·달러가 나눠져 있잖아. 보유금 1억·2억일 때 한화로 얼마, 달러로 얼마 예치해 두는 게 좋을지".
11-14 acct_mix 는 국장(스윙 9규칙·[반대매매]·데이)만 굴렸다. 여기서는 계좌를 원화 K + 달러 U 로 나눠
  원화 = acct_mix 와 같은 틀(스윙 port_sig 신호표 다시 굴림 · P9 · 데이 run · CMA 2.5%) — K 마다 스윙 배율·P9 판을 골라 가장 많이 버는 판
  달러 = 미장 6규칙(N1·N3·N5·N6·N8·N9, us_rules_recheck 거래 목록 · 건당 그때 미장 계좌의 2% · 자리 수 없음 · 현금 모자라면 못 삼) — 청산 기준 평가
  합계(원) = 원화 평가 + 달러 평가 × 그날 환율(USD/KRW)
창 = 2025-04-01 ~ 2026-06-30 (미장 거래 목록이 끝까지 완결된 데까지 · 데이 T5·T6 자료가 있는 구간).
    python research/memguard.py research/fx_split_1115.py   → research/reports/fx_split_1115.md"""
import sys, io, contextlib, pickle, math, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import acct_mix_1114 as AM
A, N = AM.A, AM.N
D0, D1 = "20250401", "20260630"
SEEDS = 6
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
t0 = time.time()

# ── 데이 재료(acct_mix 그대로)
import t1_size_liq_1021 as SL
with contextlib.redirect_stdout(io.StringIO()):
    ab, cf = SL.fit(SL.liq_of_exec())
imp_d = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
E, _ = N.live_e()
T6, T5, _ = A.load(); T1 = N.t1_wide()
days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if max(A.D0, D0) <= d <= D1]
T6g, T5g = {d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}
nd = len(days); yrs = nd / 250
print("데이 재료 %.1f분 · %d거래일 %s~%s" % ((time.time() - t0) / 60, nd, days[0], days[-1]), flush=True)

# ── 스윙: 신호표 + 종가(factory_px) 로 mix_swing.sim 그대로
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
    eq = C; pos = []; nav = []; inv_ = []
    for i in range(i0, i1 + 1):
        still = []
        for p in pos:
            if p["x"] <= i: eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"] - p["imp"]) / 100
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
    return s.nav.to_numpy() - C, s.inv.to_numpy()


P9 = pickle.load(open(r"C:\temp\kp\mix_p9.pkl", "rb"))


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


BIG = (30e4, 200e4, 1e8, 1500e4, 0.10)      # 데이 '큰 판'(11-14 추천)
SWC = {}


def kr(C, m, pkey):
    if C <= 0: return dict(navc=np.zeros(nd), lab="-", tot=0)
    if (C, m) not in SWC: SWC[(C, m)] = swing_sim(C, m) if m > 0 else (np.zeros(nd), np.zeros(nd))
    sp, sl = SWC[(C, m)]; pp, pl = p9(pkey)
    base = C + sp + pp
    cash = np.maximum(0, np.r_[C, base[:-1]] - sl - pl)
    dd = np.mean([AM.run(T6g, T5g, T1, days, cash, *BIG, E, np.random.default_rng(s), imp_d, fill) for s in range(SEEDS)], axis=0)
    dpnl = np.cumsum(dd[:, :3].sum(1))
    idle = np.maximum(0, cash - dd[:, 3]); cma = np.cumsum(idle * (1.025 ** (1 / 250) - 1))
    navc = C + sp + pp + dpnl + cma
    lab = "스윙 ×%g + [반대매매] %s + 데이 큰 판" % (m, "하루 %g천만" % (pkey[1] / 1e7) if pkey else "없음")
    return dict(navc=navc, lab=lab, tot=navc[-1] - C, sw=sp[-1], p9=pp[-1], day=dpnl[-1], cma=cma[-1],
                mdd=(navc / np.maximum.accumulate(navc) - 1).min() * 100, lock=(sl + pl).mean())


# ── 미장: 거래 목록 · 건당 미장 계좌 2% · 청산 기준
HOLD = {"N1": 40, "N3": 60, "N5": 60, "N6": 60, "N8": 250, "N9": 40}
ALL = pd.read_pickle(ROOT / "cache" / "us_rules_recheck.pkl")
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay
ud = [d.strftime("%Y%m%d") for d in pd.date_range("20240101", "20280101", freq=CustomBusinessDay(calendar=USFederalHolidayCalendar()))]
UDI = {d: i for i, d in enumerate(ud)}
TR = []
for rid, h in HOLD.items():
    z = ALL[rid].dropna(subset=["ret"]); z = z[(z.date >= D0) & (z.date <= D1)].copy(); z["rid"] = rid
    z["i0"] = z.date.map(lambda d: UDI.get(d, UDI[min(x for x in ud if x >= d)])); z["i_in"] = z.i0 + 1; z["i_out"] = z.i0 + h
    TR.append(z)
TR = pd.concat(TR, ignore_index=True)


def us_path(seed):
    rng = np.random.default_rng(seed)
    Zs = TR.assign(k=rng.random(len(TR))).sort_values(["i_in", "k"])
    byday = {d: g for d, g in Zs.groupby("i_in")}
    lo, hi = UDI[min(x for x in ud if x >= D0)], UDI[max(x for x in ud if x <= D1)]
    eq, cash, open_, path, used = 1.0, 1.0, [], {}, []
    for d in range(lo, hi + 1):
        keep = []
        for (o, amt, r) in open_:
            if o <= d: cash += amt * (1 + r / 100); eq += amt * r / 100
            else: keep.append((o, amt, r))
        open_ = keep
        if d in byday:
            for r in byday[d].itertuples():
                amt = 0.02 * eq
                if cash < amt: continue
                cash -= amt; open_.append((r.i_out, amt, r.ret))
        path[ud[d]] = eq; used.append(1 - cash / eq)
    end_open = sum(amt * r / 100 for (o, amt, r) in open_)       # 창 끝에 들고 있는 것 — 나중 청산 값(참고)
    return pd.Series(path), np.mean(used), end_open


US = [us_path(s) for s in range(30)]
usp = pd.concat([u[0] for u in US], axis=1).median(axis=1)
us_used = np.median([u[1] for u in US]); us_open = np.median([u[2] for u in US])
import FinanceDataReader as fdr
fx = fdr.DataReader("USD/KRW", "2025-03-01")["Close"]; fx.index = fx.index.strftime("%Y%m%d")
kd = pd.Index(days)
usp_k = usp.reindex(usp.index.union(kd)).ffill().reindex(kd).fillna(1.0).to_numpy()
fx_k = fx.reindex(fx.index.union(kd)).ffill().reindex(kd).bfill().to_numpy()
fx0 = fx_k[0]
P("# 원화·달러 나누기 — 1억·2억 (%s~%s · %d거래일 · 값 만원)\n" % (days[0], days[-1], nd))
P("- 원화 = 11-14 acct_mix 와 같은 틀(스윙 9규칙 · [반대매매] · 데이 큰 판 · 남는 돈 CMA 2.5%%), 금액마다 스윙 배율 0·0.5·1·1.5 × [반대매매] 하루 5천만·1억 중 가장 많이 버는 판")
P("- 달러 = 미장 6규칙(N1·N3·N5·N6·N8·N9) · 건당 미장 계좌 2%% · 자리 수 없음 · 청산 기준(들고 있는 동안 평가 안 함 → 낙폭 덜 잡힘) · 30시드 중앙")
P("- 미장 계좌 혼자 창 수익(달러 기준) %+.1f%% · 평균 투자 비중 %.0f%% · 창 끝 들고 있는 것 나중 청산 몫 %+.1f%%(안 셈)" % ((usp_k[-1] - 1) * 100, us_used * 100, us_open * 100))
P("- 환율 %s %.0f → %s %.0f (%+.1f%%) — 달러로 들고 있으면 이만큼 원화 값이 같이 움직임\n" % (days[0], fx0, days[-1], fx_k[-1], (fx_k[-1] / fx0 - 1) * 100))
print("미장·환율 %.1f분" % ((time.time() - t0) / 60), flush=True)

KRC = {}


def best_kr(K):
    if K in KRC: return KRC[K]
    if K <= 0: KRC[K] = kr(0, 0, None); return KRC[K]
    cands = []
    for m in (0, 0.5, 1.0, 1.5):
        for pk in ((200e4, 5e7), (200e4, 1e8)):
            if pk[1] > 5e7 and K < 1.4e8: continue
            cands.append(kr(K, m, pk))
    KRC[K] = cands
    print("  원화 %.1f억 %d판 · %.1f분" % (K / 1e8, len(cands), (time.time() - t0) / 60), flush=True)
    return cands


for TOT in (1e8, 2e8):
    P("\n## 계좌 %d억\n" % (TOT / 1e8))
    P("| 원화 : 달러 | 달러 금액 | 합계(창 전체) | 1년 %% | 원화 몫 / 달러 몫(환율 몫) | 최대 낙폭 | 최악의 달 | 플러스 달 | 원화 쪽 고른 판 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for u in (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7):
        K, U = TOT * (1 - u), TOT * u
        cands = best_kr(K) if K > 0 else [kr(0, 0, None)]
        best = None
        for c in cands:
            us_nav = U * usp_k * fx_k / fx0
            tot = (c["navc"] if K > 0 else 0) + us_nav
            tot = tot if K > 0 else tot
            g = tot[-1] - TOT
            mdd = (tot / np.maximum.accumulate(tot) - 1).min() * 100
            if best is None or g > best[0]: best = (g, mdd, c, tot, us_nav)
        g, mdd, c, tot, us_nav = best
        mon = pd.Series(np.diff(np.r_[TOT, tot]), index=[d[:6] for d in days]).groupby(level=0).sum() / 1e4
        usg = us_nav[-1] - U; fxg = U * usp_k[-1] * (fx_k[-1] / fx0 - 1)
        P("| %d : %d | %s | **%+.0f** | %+.1f%% | %+.0f / %+.0f(%+.0f) | %.1f%% | %+.0f | %.0f%% | %s |" % (
            round((1 - u) * 10), round(u * 10), "$%s (≈%.0f만)" % (format(round(U / fx0), ","), U / 1e4) if U else "-", g / 1e4, g / TOT / yrs * 100,
            (c["tot"] if K > 0 else 0) / 1e4, usg / 1e4, fxg / 1e4, mdd, mon.min(), (mon > 0).mean() * 100, c["lab"] if K > 0 else "-"))
P("\n## 참고 — 원화 금액별 가장 많이 버는 판 (원화만, 같은 창)\n")
P("| 원화 | 판 | 합계 | 스윙 / P9 / 데이 / CMA | 낙폭 | 스윙+P9 묶인 돈 평균 | 앞 줄보다 늘린 원화의 1년 % |"); P("|---|---|---|---|---|---|---|")
prev = None
for K in sorted(k for k in KRC if k > 0):
    b = max(KRC[K], key=lambda c: c["tot"])
    P("| %.1f억 | %s | %+.0f | %+.0f / %+.0f / %+.0f / %+.0f | %.1f%% | %.0f | %s |" % (K / 1e8, b["lab"], b["tot"] / 1e4, b["sw"] / 1e4, b["p9"] / 1e4, b["day"] / 1e4, b["cma"] / 1e4, b["mdd"], b["lock"] / 1e4,
      "-" if prev is None else "%+.1f%%" % ((b["tot"] - prev[1]) / (K - prev[0]) / yrs * 100)))
    prev = (K, b["tot"])
P("\n미장 계좌 1년 %% (달러 기준 %+.1f%% · 원화 환산 %+.1f%%)" % (((usp_k[-1]) ** (1 / yrs) - 1) * 100, ((usp_k[-1] * fx_k[-1] / fx0) ** (1 / yrs) - 1) * 100))
(ROOT / "reports" / "fx_split_1115.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
