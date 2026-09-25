# -*- coding: utf-8 -*-
"""**보유 중 매도 신호** — 외국 기법·논문의 청산 신호를 우리 규칙 보유분에 걸어 본다 (2026-09-26, 외국 기법 후속 ③).

회피 신호(로또주·급등)는 시장 전체에서 이후 성적이 나빴다(avoid_scan ①). 그걸 '사지 마라' 로만 봤고
'들고 있는 걸 이때 팔아라' 로는 안 봤다. 외국 셋업의 청산 규칙도 전부 고정 보유로만 쟀다.
여기서는 우리 규칙이 산 종목을 보유하는 동안 신호가 뜨면 **다음날 시가에 판다**(원래는 보유기간 끝 종가).

청산 신호 (보유 1일째 종가부터 판정, 보유기간 마지막 날 전까지)
  급등 +10/+15/+20%   그날 상승률이 문턱 이상(로또주화 — MAX 효과 · 일본 '상승일 초대량 = 재료 소진')
  종가>전일고가        Quantitativo '2.11 Sharpe' 청산 규칙(평균회귀 청산)
  RSI2>70/80/90       Connors·브라질 IFR2 청산
  EMA9 하락 전환       브라질 셋업 9.1 청산
판정: ① 거래별(같은 거래의 원래 수익 vs 새 수익) ② 계좌 200시드 짝비교(mat_overlay 와 같은 시뮬 — 일찍 팔면 자리가 빨리 빈다).

    python research/exit_scan.py KR
    python research/exit_scan.py US
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials
import mat_overlay as MO

NS = 200
OUT = []; t0 = time.time()
P = OUT.append


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def load_paths(mk):
    if mk == "KR":
        A = pd.read_pickle(BASE / "data/kr_scan.pkl")
        A = A[((A.close >= 1000) & (~A.pref.fillna(False))).fillna(False)][["ticker", "date", "close", "high", "buy", "cost"]]
    else:
        A = pd.read_pickle(BASE / "data/us_scan.pkl")
        A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)][["ticker", "date", "close", "rng", "clv", "buy", "cost"]]
        Rg = A.rng * A.close / 100
        A["high"] = A.close - (A.clv + 1) / 2 * Rg + Rg
        A = A.drop(columns=["rng", "clv"])
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    pc = g.close.shift(1)
    r1 = (A.close / pc - 1) * 100
    up, dn = (A.close - pc).clip(lower=0), (pc - A.close).clip(lower=0)
    ew = lambda x, **k: x.groupby(A.ticker, sort=False).transform(lambda s: s.ewm(adjust=False, **k).mean())
    rsi2 = 100 * ew(up, alpha=0.5) / (ew(up, alpha=0.5) + ew(dn, alpha=0.5) + 1e-12)
    e9 = ew(A.close, span=9)
    e9l1, e9l2 = e9.groupby(A.ticker).shift(1), e9.groupby(A.ticker).shift(2)
    X = {"급등 +10%": r1 >= 10, "급등 +15%": r1 >= 15, "급등 +20%": r1 >= 20,
         "종가>전일고가": A.close > g.high.shift(1),
         "RSI2>70": rsi2 > 70, "RSI2>80": rsi2 > 80, "RSI2>90": rsi2 > 90,
         "EMA9 하락 전환": (e9 < e9l1) & (e9l1 >= e9l2)}
    X = {k: v.fillna(False).values for k, v in X.items()}
    return A, X


def apply_exit(S, A, cond, mk):
    """신호마다 보유 중 첫 발동일 j → 다음날 시가(buy[j]) 청산. 새 수익·보유일 · 발동 여부."""
    key = {}
    for t, ix in A.groupby("ticker", sort=False).indices.items():
        key[t] = (ix, A.date.values[ix])
    buyA, costA = A.buy.values, A.cost.values
    newr = np.full(len(S), np.nan); newh = S.hold.values.astype(float).copy(); hit = np.zeros(len(S), bool)
    for n, (t, d, h) in enumerate(zip(S.ticker.values, S.date.values, S.hold.values)):
        kk = key.get(t)
        if kk is None:
            continue
        ix, dates = kk
        p = np.searchsorted(dates, d)
        if p >= len(ix) or dates[p] != d or p + int(h) >= len(ix):
            continue
        c = cond[ix[p + 1: p + int(h)]]                               # 보유 1일째 ~ 마지막 전날 종가
        w = np.flatnonzero(c)
        if len(w) == 0:
            continue
        j = p + 1 + w[0]
        bj, bp = buyA[ix[j]], buyA[ix[p]]
        if not (bj == bj and bp == bp and bp > 0):
            continue
        newr[n] = (bj / bp - 1) * 100 - costA[ix[p]]
        newh[n] = j + 1 - p
        hit[n] = True
    return newr, newh, hit


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    mk = (sys.argv[1] if len(sys.argv) > 1 else "KR").upper()
    S, cols0, run, rc = MO.kr() if mk == "KR" else MO.us()
    log("보유 경로 · 청산 신호")
    A, X = load_paths(mk)
    P("# 보유 중 매도 신호 · %s · %s" % ("국내" if mk == "KR" else "미장", time.strftime("%Y-%m-%d"))); P("")
    P("## ① 거래별 — 같은 거래의 원래 수익(보유기간 끝 종가) vs 신호 뜨면 다음날 시가 청산 (비용 차감 %)"); P("")
    P("| 청산 신호 | 발동 비율 | 평균 보유(일) 원래→새 | 평균 원래→새 | 중앙 원래→새 | 절삭 원래→새 | 승률 원래→새 | 학습 16~22 평균 차 | 검증 23~ 평균 차 |")
    P("|---|---|---|---|---|---|---|---|---|")
    VAR = {}
    for nm, c in X.items():
        nr, nh, hit = apply_exit(S, A, c, mk)
        r0 = S[rc].values
        r1 = np.where(hit, nr, r0)
        VAR[nm] = (r1, nh, hit)
        z = pd.DataFrame({"d": S.date.values, "a": r0, "b": r1, "h0": S.hold.values, "h1": nh}).dropna(subset=["a"])
        tr = lambda x: x[x <= x.quantile(0.95)].mean()
        seg = lambda lo, hi: (z[(z.d >= lo) & (z.d <= hi)].b - z[(z.d >= lo) & (z.d <= hi)].a).mean()
        P("| %s | %.0f%% | %.1f→%.1f | %+.2f→%+.2f | %+.2f→%+.2f | %+.2f→%+.2f | %.0f%%→%.0f%% | %+.2f | %+.2f |" % (
            nm, hit.mean() * 100, z.h0.mean(), z.h1.mean(), z.a.mean(), z.b.mean(), z.a.median(), z.b.median(),
            tr(z.a), tr(z.b), (z.a > 0).mean() * 100, (z.b > 0).mean() * 100,
            seg("20160101", "20221231"), seg("20230101", "20991231")))
    R = {"지금 (보유기간 끝까지)": run(S[cols0].reset_index(drop=True), NS)}
    log("지금 %.2f배" % R["지금 (보유기간 끝까지)"]["nav"])
    for nm, (r1, nh, hit) in VAR.items():
        Z = S[cols0].copy()
        if mk == "KR":
            # 새 청산가 = 매수가 × (1 + (새 수익 + 비용)/100) — simulate 가 (exit/buy−1)·100 − cost 로 되돌린다
            Z["exit"] = np.where(hit, Z.buy * (1 + (r1 + Z.cost) / 100), Z.exit)
        else:
            Z["ret"] = np.where(hit, r1, Z.ret)
        Z["hold"] = np.where(hit, nh, Z.hold).astype(int)
        log(nm)
        R[nm] = run(Z.reset_index(drop=True), NS)
        log("  %.2f배" % R[nm]["nav"])
    pickle.dump({k: {a: b for a, b in v.items()} for k, v in R.items()}, open(ROOT / "cache" / ("exit_scan_%s.pkl" % mk.lower()), "wb"))
    B = R["지금 (보유기간 끝까지)"]
    P(""); P("## ② 계좌 — %d시드 짝비교(같은 날 순서 무작위)" % NS); P("")
    hdr = "| 청산 | 노출 | 자산 | 낙폭 | 시드 중앙 | 자산 이긴 시드 | 낙폭 이긴 시드 | %s학습 16~22 | 검증 23~ |" % ("홀드아웃 05~15 | " if mk == "KR" else "")
    P(hdr); P("|" + "---|" * (hdr.count("|") - 1))
    for nm, r in R.items():
        w = "—" if r is B else "%d/%d" % (int((r["navs"] > B["navs"]).sum()), NS)
        wm = "—" if r is B else "%d/%d" % (int((r["mdds"] > B["mdds"]).sum()), NS)
        P("| %s | %.0f%% | %.2f배 | %.1f%% | %.2f배 | %s | %s | %s%.2f배 | %.2f배 |" % (
            nm, r["expo"], r["nav"], r["mdd"], np.median(r["navs"]), w, wm,
            ("%.2f배 | " % r["hold"]) if mk == "KR" else "", r["mid"], r["late"]))
    P(""); P("※ 이웃 칸(급등 10·15·20, RSI2 70·80·90)이 같이 이기고 검증도 나아져야 후보. 총 %.0f분" % ((time.time() - t0) / 60))
    log_trials("exit_scan_%s_%s" % (mk.lower(), time.strftime("%Y%m%d")), len(X))
    rp = ROOT / "reports" / ("exit_scan_%s_%s.md" % (mk.lower(), time.strftime("%Y%m%d")))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
