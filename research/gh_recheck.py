# -*- coding: utf-8 -*-
"""공개 GitHub 규칙 1차 통과분 재확인 (2026-10-04, 사용자 "응 해줘").
  ① 미장은 **폐지 포함 패널**(us_full_2007)로 다시 — 1차는 살아남은 종목뿐인 us_scan 이었다
  ② 같은 기간 **유니버스 동일가중 대비 초과**(조건 청산·긴 보유는 강세장 덕을 걸러야 한다)
  ③ **우리 규칙과 겹침** — 같은 종목에 우리 신호가 ±5거래일 안에 있었나, 겹치지 않는 거래만의 성적
    python research/gh_recheck.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import gh_engine as G
import gh_rules as GR
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
N = [0]


def ours(mk, cal):
    """우리 규칙 신호(겹침용): overlap.pkl(국장 portfolio.py 규칙 · 미장 N1~N5) → (종목, 거래일 번호)."""
    K, U = pd.read_pickle(ROOT / "cache" / "overlap.pkl")
    S = K if mk == "KR" else U
    pos = {d: i for i, d in enumerate(cal)}
    S = S.assign(ix=S.date.map(pos)).dropna(subset=["ix"])
    return S.groupby("ticker").ix.apply(lambda s: np.sort(s.astype(int).to_numpy())).to_dict()


def stat(z, col="r"):
    if len(z) < 30: return None
    yr = z.groupby(z.date.str[:4])[col].mean()
    return dict(n=len(z), m=z.r.mean(), med=z.r.median(), win=(z.r > 0).mean() * 100, ex=z.ex.mean(), exmed=z.ex.median(),
                yp=(z.groupby(z.date.str[:4]).ex.mean() > 0).sum(), ny=len(yr))


def fmt(s):
    if not s: return "-"
    return "%d건 · 평균 %+.2f(중앙 %+.2f) · 초과 %+.2f(중앙 %+.2f) · 초과 플러스 %d/%d해" % (s["n"], s["m"], s["med"], s["ex"], s["exmed"], s["yp"], s["ny"])


def judge(lab, Y, ov):
    N[0] += 1
    rows = [stat(Y[(Y.date >= a) & (Y.date <= b)]) for _, a, b in G.PER]
    ok = bool(rows[0] and rows[1] and rows[0]["m"] > 0 and rows[1]["m"] > 0 and rows[0]["ex"] > 0 and rows[1]["ex"] > 0
              and rows[0]["yp"] / rows[0]["ny"] >= 0.6)
    nov = Y[~ov]
    r2 = [stat(nov[(nov.date >= a) & (nov.date <= b)]) for _, a, b in G.PER[:2]]
    P("| %s | %s | %s | %s | %.0f%% | %s / %s | %s |" % (lab, fmt(rows[0]), fmt(rows[1]), fmt(rows[2]), ov.mean() * 100,
                                                     ("%+.2f" % r2[0]["ex"]) if r2[0] else "-", ("%+.2f" % r2[1]["ex"]) if r2[1] else "-", "✅" if ok else ""))
    return ok


def run(mk):
    t0 = time.time()
    A = GR.extra(G.load(mk, full=(mk == "US")))
    idx = G.ew_index(A)
    cal = sorted(A.date.unique()); pos = {d: i for i, d in enumerate(cal)}
    OS = ours(mk, cal)
    P("## %s — %s · 종목 %d · 준비 %.0f초" % ("국장" if mk == "KR" else "미장(폐지 포함)", f"{len(A):,}행", A.ticker.nunique(), time.time() - t0)); P("")
    P("| 규칙 | 학습 16~22 | 검증 23~ | 참고 05~15 | 우리 규칙과 겹침 | 겹침 뺀 초과(학습/검증) | 통과 |"); P("|---|---|---|---|---|---|---|")
    g = A.groupby("ticker", sort=False)
    S = lambda c, n=1: g[c].shift(n)
    rules = [("S10 Connors RSI2<10 & 200일선 위 → 5일선 위", dict(sig=(A.close > A.ma200) & (A.rsi2 < 10), exit="cond", exit_mask=A.close > A.ma5, maxh=30))]
    for n1, n2, m1, m2 in ((20, 20, 5, 5), (60, 120, 20, 10), (240, 240, 30, 30)):
        mx = g.close.transform(lambda s: s.rolling(n1, min_periods=n1).max())
        rules.append(("S22 낙폭 %d일 고점 -%d%% → +%d%% 또는 %d일" % (n1, m1, m2, n2), dict(sig=(mx - A.close) / mx * 100 >= m1, exit="hold", H=n2, target=m2)))
    if mk == "US":
        rules += [("S8 IBS<0.2 → IBS>0.8", dict(sig=A.ibs < 0.2, exit="cond", exit_mask=A.ibs > 0.8, maxh=60)),
                  ("S12 볼린저 %b<0.05 & II%21>0 → %b>0.95&II<0", dict(sig=(A.pctb < 0.05) & (A.ii21 > 0), exit="cond", exit_mask=(A.pctb > 0.95) & (A.ii21 < 0), maxh=120)),
                  ("S14 RSI21<30 → RSI>70", dict(sig=A.rsi21 < 30, exit="cond", exit_mask=A.rsi21 > 70, maxh=120))]
        eng = (S("close") < S("open")) & (A.close > A.open) & (A.open < A.pl) & (A.close > A.ph)
        rules.append(("S23 상승장악형(갭) 60일", dict(sig=eng, exit="hold", H=60)))
    passed = []
    for lab, kw in rules:
        sig = kw.pop("sig")
        Y = G.simulate(A, sig, mk, **kw)
        Y = G.add_excess(Y, A, idx).dropna(subset=["ex"])
        ix = Y.date.map(pos).to_numpy()
        ov = np.array([bool(len(OS.get(t, [])) and np.any(np.abs(OS[t] - i) <= 5)) for t, i in zip(Y.ticker, ix)])
        if judge(lab, Y, pd.Series(ov, index=Y.index)): passed.append(lab)
        pd.to_pickle(Y, ROOT / "cache" / ("ghre_%s_%s.pkl" % (mk, lab.split()[0] + lab.split()[2] if lab.startswith("S22") else lab.split()[0])))
    return A, passed


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    P("# 공개 GitHub 규칙 1차 통과분 재확인 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("초과 = 같은 기간 유니버스(거래대금 상위 40%) 동일가중 대비 · 통과 = 학습·검증 둘 다 건당 평균·초과 플러스 & 학습 해별 초과 플러스 60%↑ · "
      "겹침 = 우리 규칙 신호가 같은 종목 ±5거래일 안(국장 portfolio.py 규칙 · 미장 N1~N5)"); P("")
    res = {}
    for mk in ("KR", "US"):
        A, res[mk] = run(mk); del A; P("")
    log_trials("gh_recheck_%s" % time.strftime("%Y%m%d"), N[0])
    P("(칸 %d · %.0f분)" % (N[0], (time.time() - t0) / 60))
    (ROOT / "reports" / ("gh_recheck_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
