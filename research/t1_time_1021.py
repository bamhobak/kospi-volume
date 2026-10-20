# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 후보를 몇 시에 고르면 좋은가 — 장전 시각별 예상 갭 정확도 (2026-10-21 사용자 "8:52 에 체크하는 이유? 앞이나 뒤면?").
녹화기(data/factory/auction): KRX 장전 단일가 호가 08:30:30·08:36·08:42·08:47·08:56:15 · NXT 장전 체결가 08:00~08:50 매 분.
실전(08:52) = NXT 오늘 체결가가 있으면 그것, 없으면 KRX 호가 중간값. 시각 T 의 예상가도 같은 규칙으로 T 이전 자료만 쓴다.
정답 = 실제 시가(1분봉 첫 봉 시가) · 어제 종가 = 전날 1분봉 마지막 종가. 대상 = 녹화기가 본 종목(유니버스).
잣대: 예상 갭 오차(중앙 절대) · '진짜 후보'(실제 시장 대비 -1.5%p↓ & 실제 갭 하위 40%)를 예상으로 몇 % 잡나(놓치면 못 삼) ·
      예상 후보 수(많으면 안 사질 주문이 돈을 잡아 둠).
    python research/t1_time_1021.py
"""
import glob, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

AUC = BASE / "data" / "factory" / "auction"
M1 = BASE / "data" / "m1" / "KR" / "day"


def day_oc(d):
    f = M1 / ("%s.parquet" % d)
    if not f.exists(): return None
    D = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"])
    D = D[D.v > 0].sort_values(["t", "ts"])
    g = D.groupby("t")
    return g.o.first(), g.c.last()


def main():
    days = sorted({Path(f).name.split("_")[1] for f in glob.glob(str(AUC / "KR_*_am.parquet"))})
    m1days = sorted(Path(f).stem for f in glob.glob(str(M1 / "*.parquet")))
    TIMES = [("08:36", "083600", "083600"), ("08:42", "084200", "084200"), ("08:47", "084700", "084700"),
             ("08:47 호가만(NXT 안 씀)", None, "084700"), ("08:50(NXT 끝)+08:47 호가", "085000", "084700"), ("08:56 (NXT 끝+08:56 호가)", "085000", "085615"), ("08:56 호가만(NXT 안 씀)", None, "085615")]
    R = {t[0]: [] for t in TIMES}
    used, NT = [], []
    WIDE = {}
    for d in days:
        if d not in m1days: continue
        k = m1days.index(d)
        if k == 0: continue
        oc_t, oc_p = day_oc(d), day_oc(m1days[k - 1])
        if oc_t is None or oc_p is None: continue
        op, pc = oc_t[0], oc_p[1]
        A = pd.read_parquet(AUC / ("KR_%s_am.parquet" % d))
        Nf = AUC / ("KR_%s_nxt.parquet" % d)
        N = pd.read_parquet(Nf) if Nf.exists() else pd.DataFrame(columns=["tag", "ticker", "price", "today"])
        N = N[N.today == True]
        tk = set(op.index) & set(pc.index)
        for tg in ("083600", "084200", "084700", "085615"):
            tk &= set(A[A.tag == tg].ticker)                 # 모든 시각에 녹화된 종목만 — 같은 종목으로 견준다
        tk = sorted(tk)
        if len(tk) < 200: continue
        used.append(d); NT.append(len(tk))
        act = (op.reindex(tk) / pc.reindex(tk) - 1) * 100
        arel = act - act.median()
        truth = (arel <= -1.5) & (act.rank(pct=True) <= 0.40)
        for nm, ntag, btag in TIMES:
            b = A[A.tag == btag]
            a0 = b[(b.side == "A") & (b.lvl == 0)].set_index("ticker").price
            b0 = b[(b.side == "B") & (b.lvl == 0)].set_index("ticker").price
            mid = pd.concat([a0, b0], axis=1).mean(axis=1)
            ex = mid.reindex(tk)
            if ntag:
                nx = N[N.tag <= ntag].sort_values("tag").groupby("ticker").price.last().reindex(tk)
                ex = nx.fillna(ex)
            eg = (ex / pc.reindex(tk) - 1) * 100
            ok = eg.notna()
            erel = eg - eg[ok].median()
            pred = (erel <= -1.5) & (eg.rank(pct=True) <= 0.40) & ok
            if nm.startswith("08:50"):
                for th, qq in ((-1.5, 0.40), (-1.0, 0.40), (-1.0, 0.50), (-0.5, 0.50)):
                    pw = (erel <= th) & (eg.rank(pct=True) <= qq) & ok
                    WIDE.setdefault((th, qq), []).append(((pw & truth).sum() / max(truth.sum(), 1), pw.sum(), truth.sum()))
            R[nm].append(dict(day=d, err=(eg - act)[ok].abs().median(), err_c=(eg - act)[truth & ok].abs().median(), cover=ok.mean(),
                              recall=(pred & truth).sum() / max(truth.sum(), 1), n_pred=pred.sum(), n_true=truth.sum(), prec=(pred & truth).sum() / max(pred.sum(), 1)))
    print("쓴 날: %s (%d일)\n" % (", ".join(used), len(used)))
    print("| 고르는 시각 | 예상가 있는 종목 | 갭 오차(중앙 절대, 전체) | 갭 오차(진짜 후보) | 진짜 후보 잡은 비율 | 예상 후보 수(하루) | 그중 진짜 |"); print("|---|---|---|---|---|---|---|")
    _wide(WIDE)
    print()
    for nm, *_ in TIMES:
        Z = pd.DataFrame(R[nm])
        print("| %s | %.0f%% | %.2f%%p | %.2f%%p | **%.0f%%** | %.0f개 (진짜 %.0f개) | %.0f%% |" % (nm, Z.cover.mean() * 100, Z.err.mean(), Z.err_c.mean(), Z.recall.mean() * 100, Z.n_pred.mean(), Z.n_true.mean(), Z.prec.mean() * 100))


def _wide(WIDE):
    print("\n08:50 기준, 후보 문턱을 넓히면(지정가는 그대로 실제 -1.5%p 에서만 체결)")
    print("| 예상 시장 대비 | 예상 갭 순위 | 진짜 후보 잡은 비율 | 예상 후보 수(하루) |"); print("|---|---|---|---|")
    for (th, qq), v in WIDE.items():
        a = np.array(v)
        print("| %+.1f%%p | 하위 %d%% | **%.0f%%** | %.0f개 |" % (th, qq * 100, a[:, 0].mean() * 100, a[:, 1].mean()))


if __name__ == "__main__":
    main()

