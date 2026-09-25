# -*- coding: utf-8 -*-
"""외국 기법 지표 재료 → **계좌 얹기** (2026-09-25).

avoid_scan(규칙 안 스캔)과 mat_ctrl(낙폭 통제)을 둘 다 통과한 재료만 올린다.
  국내  m_shinob(시노하라 B · 26일 매수/매도 에너지 비) · m_rsiw(주봉 RSI 근사)        — 낮을수록 좋다
  미장  m_rsiw · m_fisher(피셔 변환) · m_shinob · m_lrsi(라게르 RSI)                     — 낮을수록 좋다
방법: **규칙마다** 학습 구간(~2022) 신호의 재료 분포로 문턱을 정하고, 나쁜 쪽(높은 쪽) 20/30/40% 를 뺀다.
     결측(재료 없음)은 산다. 계좌는 국내 portfolio.py simulate · 미장 us_overlay.py 와 같은 6규칙 시뮬.
     200시드 짝비교(같은 날 순서 무작위) · 구간 나눠 봄. 이웃 칸(20·30·40)이 같이 이기고 검증도 나아져야 후보.

    python research/mat_overlay.py KR
    python research/mat_overlay.py US
"""
import glob, os, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials
import avoid_scan as AV

NS = 200
MAT = {"KR": ["m_shinob", "m_rsiw"], "US": ["m_rsiw", "m_fisher", "m_shinob", "m_lrsi"]}
QS = (0.20, 0.30, 0.40)
OUT = []; t0 = time.time()


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def drop_mask(S, col, q):
    """규칙별로 학습 구간(~2022) 신호의 (1-q) 분위 위를 뺀다. 결측은 산다."""
    th = S[S.date <= "20221231"].groupby("rid")[col].quantile(1 - q)
    t = S.rid.map(th)
    return (S[col] > t).fillna(False)


# ══════════════════════════════════════════════════════════════════════
def kr():
    log("portfolio.py 재구성")
    SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
    HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
    MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
    os.environ["SKIP"] = ""
    real = sys.stdout; ns = {"__file__": str(BASE / "portfolio.py")}
    exec(compile(HEAD, "portfolio.py", "exec"), ns); exec(compile(MID, "portfolio.py", "exec"), ns)
    globals()["_keep"] = sys.stdout; sys.stdout = real
    S0 = ns["S"].copy(); simf = ns["simulate"]; cols0 = list(S0.columns)
    log("재료 계산(kr_scan)")
    A = AV.features("KR")
    S0 = S0.merge(A[["date", "ticker"] + MAT["KR"]], on=["date", "ticker"], how="left"); del A
    S0["r"] = (S0.exit / S0.buy - 1) * 100 - S0.cost

    def run(Z, seeds):
        ns["S"] = Z
        C, _ = simf(1.0, 1.0, "", quiet=True)
        c15 = C[C.date <= "20151231"].nav.iloc[-1]; c22 = C[C.date <= "20221231"].nav.iloc[-1]
        out = dict(nav=C.nav.iloc[-1], mdd=((C.nav / C.nav.cummax()) - 1).min() * 100, expo=C.expo.mean() * 100,
                   hold=c15, mid=c22 / c15, late=C.nav.iloc[-1] / c22, n=len(Z))
        navs, mdds = [], []
        for s in range(seeds):
            ns["S"] = Z.sample(frac=1.0, random_state=s).sort_values("di", kind="stable").reset_index(drop=True)
            Cs = simf(1.0, 1.0, "", quiet=True)[0]
            navs.append(Cs.nav.iloc[-1]); mdds.append(((Cs.nav / Cs.nav.cummax()) - 1).min() * 100)
        out["navs"], out["mdds"] = np.array(navs), np.array(mdds)
        return out
    return S0, cols0, run, "r"


def us():
    log("미장 신호·N6")
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
    A["peadq"] = (A.ticker + A.date).map(dict(zip(E.ticker + E.bdate, E.q)))
    A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
    X = A[((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)].dropna(subset=["n60"])
    X = X[(X.buy > 0) & (X.date >= "20160101")].sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + 60; keep.append(ix)
    Y = X.loc[keep]
    PE = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values, "ret": Y.n60.astype(float).values,
                       "amt20": Y.amt20.values})
    del A, X, Y
    with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
        C = pickle.load(f)
    S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
    PE = PE[PE.date.isin(set(DS))].reset_index(drop=True)
    S6 = pd.concat([S5, pd.DataFrame({"date": PE.date.values, "ticker": PE.ticker.values,
                                      "di": [ADI[d] for d in PE.date.values], "rid": "N6", "pct": 5, "mx": 3,
                                      "hold": 60, "ret": PE.ret.values, "amt20": PE.amt20.values})],
                   ignore_index=True).sort_values("di").reset_index(drop=True)
    PCT6 = dict(PCT5); PCT6["N6"] = 5
    cols0 = list(S6.columns)
    log("재료 계산(us_scan)")
    A = AV.features("US")
    S6 = S6.merge(A[["date", "ticker"] + MAT["US"]], on=["date", "ticker"], how="left"); del A
    if S6.ret.abs().median() < 1:
        S6["r"] = S6.ret * 100
    else:
        S6["r"] = S6.ret
    DSS = set(DS)

    def sim(S, seed=None):
        rng = np.random.default_rng(seed) if seed is not None else None
        nav, held, cnt = 1.0, {}, {}
        byd = {d: gg for d, gg in S[S.date.isin(DSS)].groupby("date")}
        peak, mdd, inv, cv = 1.0, 0.0, [], []
        for d in DS:
            di = ADI[d]
            for k in [k for k, v in held.items() if v[0] <= di]:
                nav *= 1 + held.pop(k)[1] / 100
                cnt[k[0]] = cnt.get(k[0], 0) - 1
            peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
            inv.append(sum(PCT6[k[0]] for k in held) / 100); cv.append((d, nav))
            gg = byd.get(d)
            if gg is None:
                continue
            gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
                  else gg.sort_values("amt20", ascending=False, na_position="last"))
            for r in gg.itertuples():
                if cnt.get(r.rid, 0) >= r.mx:
                    continue
                k = (r.rid, r.ticker, d)
                if k in held or sum(PCT6[x[0]] for x in held) / 100 + r.pct / 100 > 1.0:
                    continue
                held[k] = (di + int(r.hold), r.ret * r.pct / 100)
                cnt[r.rid] = cnt.get(r.rid, 0) + 1
        for v in held.values():
            nav *= 1 + v[1] / 100
        cvd = pd.DataFrame(cv, columns=["date", "nav"])
        c22 = cvd[cvd.date <= "20221231"].nav.iloc[-1]
        return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)) * 100, hold=np.nan, mid=c22, late=nav / c22)

    def run(Z, seeds):
        out = sim(Z); out["n"] = len(Z)
        rs = [sim(Z, seed=s) for s in range(seeds)]
        out["navs"] = np.array([x["nav"] for x in rs]); out["mdds"] = np.array([x["mdd"] for x in rs])
        return out
    return S6, cols0, run, "r"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    mk = (sys.argv[1] if len(sys.argv) > 1 else "KR").upper()
    S, cols0, run, rc = kr() if mk == "KR" else us()
    CFG = [("지금 (그대로)", None)]
    for m in MAT[mk]:
        for q in QS:
            CFG.append(("%s 높은 쪽 %d%% 빼기(규칙별)" % (m, q * 100), drop_mask(S, m, q)))
    P("# 외국 기법 지표 재료 → %s 계좌 얹기 · %s" % ("국내" if mk == "KR" else "미장", time.strftime("%Y-%m-%d"))); P("")
    P("재료 결측률: " + " · ".join("%s %.0f%%" % (m, S[m].isna().mean() * 100) for m in MAT[mk])); P("")
    P("## 빠지는 신호와 그 성적 (전량 동일금액 거래 수익)"); P("")
    P("| 구성 | 빠지는 신호 | 빠지는 쪽 중앙 | 남는 쪽 중앙 | 빠지는 쪽 검증(23~) 중앙 | 남는 쪽 검증 중앙 |"); P("|---|---|---|---|---|---|")
    for lbl, msk in CFG[1:]:
        d, k = S[msk], S[~msk]
        P("| %s | %s | %+.2f | %+.2f | %+.2f | %+.2f |" % (lbl, f"{len(d):,}", d[rc].median(), k[rc].median(),
                                                     d[d.date >= "20230101"][rc].median(), k[k.date >= "20230101"][rc].median()))
    R = {}
    for lbl, msk in CFG:
        log(lbl)
        Z = (S if msk is None else S[~msk])[cols0].reset_index(drop=True)
        R[lbl] = run(Z, NS)
        log("  %.2f배" % R[lbl]["nav"])
    import pickle as _pk                      # 표를 찍다 죽어도 계산은 남게(2026-09-25 서식 오류로 두 시간을 날렸다)
    _pk.dump({k: {a: b for a, b in v.items()} for k, v in R.items()},
             open(ROOT / "cache" / ("mat_overlay_%s.pkl" % mk.lower()), "wb"))
    B = R[CFG[0][0]]
    P(""); P("## 계좌 — %d시드 짝비교" % NS); P("")
    hdr = "| 구성 | 신호 | 노출 | 자산 | 낙폭 | 시드 중앙 | 자산 이긴 시드 | 낙폭 이긴 시드 | %s학습 16~22 | 검증 23~ |" % ("홀드아웃 05~15 | " if mk == "KR" else "")
    P(hdr); P("|" + "---|" * (hdr.count("|") - 1))
    for lbl, _ in CFG:
        r = R[lbl]
        w = "—" if r is B else "%d/%d" % (int((r["navs"] > B["navs"]).sum()), NS)
        wm = "—" if r is B else "%d/%d" % (int((r["mdds"] > B["mdds"]).sum()), NS)
        P("| %s | %s | %.0f%% | %.2f배 | %.1f%% | %.2f배 | %s | %s | %s%.2f배 | %.2f배 |" % (
            lbl, f"{r['n']:,}", r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), w, wm,
            ("%.2f배 | " % r["hold"]) if mk == "KR" else "", r["mid"], r["late"]))
    P(""); P("※ 이웃 칸(20·30·40)이 같이 이기고(시드 60%%↑) 검증 23~ 도 나아져야 후보. 한 칸만 이기면 운. 총 %.0f분" % ((time.time() - t0) / 60))
    log_trials("mat_overlay_%s_%s" % (mk.lower(), time.strftime("%Y%m%d")), len(CFG) - 1)
    rp = ROOT / "reports" / ("mat_overlay_%s_%s.md" % (mk.lower(), time.strftime("%Y%m%d")))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
