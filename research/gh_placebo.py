# -*- coding: utf-8 -*-
"""미장 GitHub 규칙 위약 시험 (2026-10-04) — 동일가중 지수 잣대는 미장에서 너무 높게 잡힌다(우리 N3 도 -4.7%p).
같은 신호일에 같은 개수의 '아무 종목'(유니버스 · 그날 신호 종목 제외)을 **같은 청산 방식**으로 산 결과 20번과 견준다.
z = (진짜 평균 − 위약 평균의 평균) ÷ 위약 평균들의 표준편차. 우리 N3(저PBR 낙폭 · 60일)도 같은 방식으로 재서 잣대를 맞춰 본다.
    python research/gh_placebo.py
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


def day_pools(A):
    """날짜별 유니버스 행 번호 — 한 번만 만든다(1,600만 행이라 매번 만들면 느리다)."""
    d = A.date.to_numpy(); u = np.flatnonzero(A.uni.to_numpy(dtype=bool))
    return pd.Series(u).groupby(d[u]).apply(np.asarray).to_dict()


def placebo_sig(A, sig, pools, rng):
    s = sig.fillna(False).to_numpy(dtype=bool) & A.uni.to_numpy(dtype=bool)
    cnt = pd.Series(s).groupby(A.date.to_numpy()).sum()
    out = np.zeros(len(A), dtype=bool)
    for day, n in cnt[cnt > 0].items():
        pool = pools.get(day)
        if pool is None or len(pool) == 0: continue
        out[rng.choice(pool, size=min(int(n), len(pool)), replace=False)] = True
    return pd.Series(out, index=A.index)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = GR.extra(G.load("US", full=True))
    g = A.groupby("ticker", sort=False)
    rules = []
    for n1, n2, m1, m2 in ((60, 120, 20, 10), (240, 240, 30, 30)):
        mx = g.close.transform(lambda s: s.rolling(n1, min_periods=n1).max())
        rules.append(("S22 낙폭 %d일 고점 -%d%% → +%d%% 또는 %d일" % (n1, m1, m2, n2), (mx - A.close) / mx * 100 >= m1, dict(exit="hold", H=n2, target=m2)))
    rules.append(("S8 IBS<0.2 → IBS>0.8", A.ibs < 0.2, dict(exit="cond", exit_mask=A.ibs > 0.8, maxh=60)))
    # 잣대 맞추기용: 우리 N3 [저PBR 낙폭] 근사 — PBR≤0.8 & 20일 -10% 이하 · 60일 보유(국면·업종 조건 생략)
    ret20 = (A.close / g.close.shift(20) - 1) * 100
    rules.append(("(잣대) 우리 N3 근사: PBR≤0.8 & 20일 -10% · 60일", (A.PBR > 0) & (A.PBR <= 0.8) & (ret20 <= -10), dict(exit="hold", H=60)))
    P("# 미장(폐지 포함) GitHub 규칙 위약 시험 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("| 규칙 | 구간 | 진짜 건당 평균 | 위약 평균(20번) | 차이 | z |"); P("|---|---|---|---|---|---|")
    rng = np.random.default_rng(7); n = 0
    pools = day_pools(A)
    for lab, sig, kw in rules:
        Y = G.simulate(A, sig, "US", **kw)
        PL = []
        for k in range(20):
            Yp = G.simulate(A, placebo_sig(A, sig, pools, rng), "US", **kw)
            PL.append(Yp)
        for nm, a, b in G.PER:
            y = Y[(Y.date >= a) & (Y.date <= b)].r
            pm = np.array([p_[(p_.date >= a) & (p_.date <= b)].r.mean() for p_ in PL])
            if len(y) < 30: continue
            z = (y.mean() - pm.mean()) / (pm.std() if pm.std() > 0 else np.nan)
            P("| %s | %s | %+.2f%% (%d건) | %+.2f%% | %+.2f%%p | %.1f |" % (lab, nm, y.mean(), len(y), pm.mean(), y.mean() - pm.mean(), z)); n += 1
    log_trials("gh_placebo_%s" % time.strftime("%Y%m%d"), n)
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("gh_placebo_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
