# -*- coding: utf-8 -*-
"""수급 급증 — 기간을 늘려서 (2026-10-02 사용자: "기간 늘려서 돌려봐", 1일판 H0277~H0279 기각 뒤).

재료(investor.db flow11 · 2018~ · 장 마감 뒤 확정 → 다음날 시가 매수):
  누적:  cN = 최근 N일 순매수 합 ÷ (그 앞 20일 |순매수| 하루 평균 × N)   N = 3·5·10 · 문턱 k = 2·3·5
  연속:  최근 N일 매일 순매수(개인은 매일 순매도) & 누적 cN ≥ 2           N = 3·5·7
  주체:  외국인 순매수 / 개인 순매도 / 둘 다
판정: 거래대금 상위 40% 유니버스 · 보유 10·20·40일 · 비용 차감 · 같은 종목 보유 중 재신호 무시(run_spec.Judge)
  학습 2018~22 · 검증 2023~ — 중앙·승률·같은 날 유니버스 대비 초과(중앙). 통과 = 둘 다 중앙>0·초과>0 & 학습 해별 중앙 플러스 60%↑.
    python research/flow_multi.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import run_spec as R
from verdict import log_trials

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def feats():
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, indiv, frgn FROM flow11", c).sort_values(["ticker", "date"]).reset_index(drop=True)
    F["isell"] = -F.indiv                                      # 개인 순매도(양수 = 판 것)
    g = F.groupby("ticker", sort=False)
    out = F[["ticker", "date"]].copy()
    for who, col in (("f", "frgn"), ("i", "isell")):
        for N in (3, 5, 7, 10):
            s = g[col].transform(lambda z: z.rolling(N, min_periods=N).sum())
            base = g[col].transform(lambda z: z.abs().shift(N).rolling(20, min_periods=20).mean())
            out["%s_c%d" % (who, N)] = s / (base * N).replace(0, np.nan)
            pos = (F[col] > 0).astype(float)
            out["%s_run%d" % (who, N)] = pos.groupby(F.ticker, sort=False).transform(lambda z: z.rolling(N, min_periods=N).sum()) == N
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A, uni, since = R.load_market("KR")
    X = feats()
    m = A[["ticker", "date"]].merge(X, on=["ticker", "date"], how="left")
    for c in X.columns[2:]:
        A[c] = m[c].values
    J = R.Judge(A, uni, "20180101")
    cells = []
    def add(lab, cond):
        for h in (10, 20, 40):
            Y = J.run(pd.Series(cond, index=A.index).fillna(False).astype(bool), h)
            Y["ex"] = Y.r - Y.date.map(J.bench(h))
            cells.append((lab, h, Y))
    for N in (3, 5, 10):
        for k in (2, 3, 5):
            add("외국인 %d일 누적 ≥ %d배" % (N, k), A["f_c%d" % N] >= k)
            add("개인 %d일 누적 순매도 ≥ %d배" % (N, k), A["i_c%d" % N] >= k)
            add("둘 다 %d일 누적 ≥ %d배" % (N, k), (A["f_c%d" % N] >= k) & (A["i_c%d" % N] >= k))
    for N in (3, 5, 7):
        cN = "f_c%d" % N if N != 7 else "f_c7"
        add("외국인 %d일 연속 순매수 & 누적 ≥ 2배" % N, (A["f_run%d" % N] == True) & (A[cN] >= 2))
        add("개인 %d일 연속 순매도 & 누적 ≥ 2배" % N, (A["i_run%d" % N] == True) & (A["i_c%d" % N] >= 2))
        add("둘 다 %d일 연속 & 누적 ≥ 2배" % N, (A["f_run%d" % N] == True) & (A[cN] >= 2) & (A["i_run%d" % N] == True) & (A["i_c%d" % N] >= 2))
    rows = []
    for lab, h, Y in cells:
        tr = Y[(Y.date >= "20180101") & (Y.date <= "20221231")]; va = Y[Y.date >= "20230101"]
        ys = tr.groupby(tr.date.str[:4]).r.median()
        ok = len(tr) >= 30 and len(va) >= 15 and tr.r.median() > 0 and va.r.median() > 0 and tr.ex.median() > 0 and va.ex.median() > 0 \
            and (ys > 0).mean() >= 0.6
        rows.append(dict(lab=lab, h=h, ntr=len(tr), nva=len(va), trm=tr.r.median(), trw=(tr.r > 0).mean() * 100, trx=tr.ex.median(),
                         vam=va.r.median(), vaw=(va.r > 0).mean() * 100, vax=va.ex.median(), ypos="%d/%d" % ((ys > 0).sum(), len(ys)), ok=ok))
    G = pd.DataFrame(rows)
    G.to_pickle(ROOT / "cache" / "flow_multi.pkl")
    P("# 수급 급증 — 기간 늘려서 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("칸 %d개 · 통과(학습·검증 둘 다 중앙·초과 플러스 & 학습 해별 60%%↑) **%d칸**" % (len(G), G.ok.sum())); P("")
    P("| 조건 | 보유 | 학습 18~22 건수 · 중앙 · 승률 · 초과 | 검증 23~ 건수 · 중앙 · 승률 · 초과 | 학습 플러스 해 | 판정 |"); P("|---|---|---|---|---|---|")
    G["score"] = G[["trx", "vax"]].min(axis=1)
    for _, x in G.sort_values("score", ascending=False).iterrows():
        P("| %s | %d일 | %d · %+.2f · %.0f%% · %+.2f | %d · %+.2f · %.0f%% · %+.2f | %s | %s |" % (
            x.lab, x.h, x.ntr, x.trm, x.trw, x.trx, x.nva, x.vam, x.vaw, x.vax, x.ypos, "✅" if x.ok else ""))
    log_trials("flow_multi_%s" % time.strftime("%Y%m%d"), len(G))
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("flow_multi_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
