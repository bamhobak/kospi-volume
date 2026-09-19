# -*- coding: utf-8 -*-
"""**규칙 안 스캔 통과 재료 → 미장 계좌 얹기** (2026-09-19).

규칙 안 스캔(rule_scan_us_20260919)에서 가격 낙폭 말고 통과한 재료 둘:
  · 공매도 거래 비중 20일(us_sr20, FINRA 2019~) — 높을수록 나쁘다(D -0.86, 5/5 규칙). 시장 전체 축과 같은 방향.
    → 그날 유니버스 안 **상위 20/30/40%** 신호를 뺀다. 2019 이전은 조건을 끈다.
  · 거래량 배수(vm1) — 클수록 좋다(D +1.06, 5/5). → 그날 유니버스 안 **하위 20/30/40%** 신호를 뺀다.
시뮬은 us_drop_n1.py 와 같은 6규칙(N1~N5 + N6 실적 서프라이즈) 자체 시뮬 · 300시드 짝비교.

    python research/us_overlay.py      → research/reports/us_overlay_20260919.md
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials
import features_us as FU

NS = 300; SINCE = "20160101"
OUT = []; t0 = time.time()


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


# ── N6 신호 (us_drop_n1.py 와 같은 정의) ────────────────────────────────
log("패널·N6")
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
cal = np.array(sorted(A.date.unique())); DD = {d: i for i, d in enumerate(cal)}
E["bdate"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"]); E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True); E = E[E.groupby("bdate").sur.transform("size") >= 5]
A["_k"] = A.ticker + A.date
A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
cond = ((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)
X = A[cond].dropna(subset=["n60"]); X = X[(X.buy > 0) & (X.date >= SINCE)].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
    i = DD[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 60; keep.append(ix)
Y = X.loc[keep]
PE = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values, "ret": Y.n60.astype(float).values,
                   "amt20": Y.amt20.values})

# ── 재료 백분위 (그날 유니버스 안) ─────────────────────────────────────
log("재료 백분위")
Uv = A[(A.amt_q >= 0.6) & (A.date >= SINCE)][["ticker", "date", "amt20", "vm1"]].reset_index(drop=True)
del A, X, Y
FU.attach(Uv, ["us_sr20"], cal=list(cal))
Uv["sr_p"] = Uv.groupby("date").us_sr20.rank(pct=True)
Uv["vm_p"] = Uv.groupby("date").vm1.rank(pct=True)
FEAT = Uv[["ticker", "date", "sr_p", "vm_p"]]

with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
PE = PE[PE.date.isin(set(DS))].reset_index(drop=True)
S6 = pd.concat([S5, pd.DataFrame({"date": PE.date.values, "ticker": PE.ticker.values,
                                  "di": [ADI[d] for d in PE.date.values], "rid": "N6", "pct": 5, "mx": 3,
                                  "hold": 60, "ret": PE.ret.values, "amt20": PE.amt20.values})],
               ignore_index=True).sort_values("di").reset_index(drop=True)
PCT6 = dict(PCT5); PCT6["N6"] = 5
S6 = S6.merge(FEAT, on=["ticker", "date"], how="left")
log("  신호 %s건 · 공매도 결측 %.0f%% · 거래량 결측 %.0f%%" % (f"{len(S6):,}", S6.sr_p.isna().mean() * 100,
                                                     S6.vm_p.isna().mean() * 100))


def sim(S, PCT, seed=None):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(DS))].groupby("date")}
    peak, mdd, inv, cv = 1.0, 0.0, [], []
    for d in DS:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] for k in held) / 100); cv.append((d, nav))
        gg = byd.get(d)
        if gg is None:
            continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r in gg.itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held or sum(PCT[x[0]] for x in held) / 100 + r.pct / 100 > 1.0:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    cvd = pd.DataFrame(cv, columns=["date", "nav"])
    c22 = cvd[cvd.date <= "20221231"].nav.iloc[-1]
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)) * 100, mid=c22, late=nav / c22)


CFG = [("지금 (6규칙)", None),
       ("공매도 비중 상위 20% 빼기", S6.sr_p > 0.80), ("공매도 비중 상위 30% 빼기 (원안)", S6.sr_p > 0.70),
       ("공매도 비중 상위 40% 빼기", S6.sr_p > 0.60),
       ("거래량 하위 20% 빼기", S6.vm_p < 0.20), ("거래량 하위 30% 빼기 (원안)", S6.vm_p < 0.30),
       ("거래량 하위 40% 빼기", S6.vm_p < 0.40)]
P("# 규칙 안 스캔 통과 재료 → 미장 계좌 얹기"); P("")
P("## 빠지는 신호와 그 성적 (거래 수익 · 전량 동일금액)"); P("")
P("| 구성 | 빠지는 신호 | 빠지는 쪽 중앙 | 남는 쪽 중앙 | 규칙별 빠지는 수 |"); P("|---|---|---|---|---|")
for lbl, m in CFG[1:]:
    m = m.fillna(False)
    d = S6[m]; k = S6[~m]
    P("| %s | %s | %+.2f | %+.2f | %s |" % (lbl, f"{len(d):,}", d.ret.median(), k.ret.median(),
                                         " ".join("%s:%d" % kv for kv in d.rid.value_counts().items())))
R = {}
for lbl, m in CFG:
    log(lbl)
    Z = (S6 if m is None else S6[~m.fillna(False)]).reset_index(drop=True)
    base = sim(Z, PCT6)
    base["navs"] = np.array([sim(Z, PCT6, seed=s)["nav"] for s in range(NS)])
    base["n"] = len(Z); R[lbl] = base
    log("  %.2f배" % base["nav"])
B = R[CFG[0][0]]
P(""); P("## 계좌 — %d시드 짝비교 (2016~)" % NS); P("")
P("| 구성 | 신호 | 노출 | 자산 | 낙폭 | 시드 중앙 | 시드 최악 | 자산 이긴 시드 | 학습 16~22 | 검증 23~26 |")
P("|---|---|---|---|---|---|---|---|---|---|")
for lbl, _ in CFG:
    r = R[lbl]
    w = "—" if r is B else "%d/%d" % (int((r["navs"] > B["navs"]).sum()), NS)
    P("| %s | %s | %.0f%% | %.2f배 | %.1f%% | %.2f배 | %.2f배 | %s | %.2f배 | %.2f배 |" % (
        lbl, f"{r['n']:,}", r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), r["navs"].min(), w, r["mid"], r["late"]))
P(""); P("※ 공매도 자료는 2019~ — 그 전 신호는 조건 없이 산다. 이웃 칸까지 같이 이기고 검증도 나아져야 후보.")
P("총 %.0f초" % (time.time() - t0))
log_trials("us_overlay_20260919", len(CFG) - 1)
rp = ROOT / "reports" / "us_overlay_20260919.md"; rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
print("\n".join(OUT))
