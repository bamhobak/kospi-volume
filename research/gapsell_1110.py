# -*- coding: utf-8 -*-
"""H0402 스윙 보유 종목이 크게 떠서 열리면 그 시가에 팔기 (2026-11-10 사용자 "이것도 살펴봐").
근거(H0399 부산물): 갭 +7%p↑ 로 열린 종목은 그날 시가→종가 -3% 안팎. 보유분에 쓰면 이득인가?
방법: 국장 스윙 9규칙의 실제 거래(stats_2016.take — 보유 중 재진입 없음)마다 보유 2일째~끝 날 사이 '시가 갭 ≥ X%' 가 처음 난 날 그 시가에 판다.
  손절·트레일 규칙은 원래 청산일 전의 갭만 본다. 비용은 거래마다 패널 cost. 갈아탄 돈을 다시 굴리는 효과는 안 넣는다(자리 수 없음 — 신호 나면 산다).
판정: 거래당 차이(바꾼 값 − 원래 값) · 걸린 거래만의 차이 · 학습 16~22 / 검증 23~ · 규칙별.
    python research/gapsell_1110.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(BASE), str(ROOT)]
src = (BASE / "stats_2016.py").read_text(encoding="utf-8").split("OUT = {}")[0]
ns = {"__file__": str(BASE / "stats_2016.py"), "__name__": "x"}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src, "stats_2016.py", "exec"), ns)
sys.stdout = real; sys.stdout.reconfigure(encoding="utf-8")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
XS = (5, 7, 10, 15, 20)
rows = []; SKIP = []
for rid in ns["ORDER"]:
    K, hold, stop, pct, mx, cond = ns["RULES"][rid]
    t = ns["TRAIL"].get(rid)
    if "open" not in K.columns:
        print(rid, "패널에 시가 열이 없어 건너뜀", flush=True); SKIP.append(ns["NAME"][rid]); continue
    Z, hold, stop = ns["take"](rid)
    pos = K.index.get_indexer(Z.index)
    tk = K.ticker.to_numpy(); n = len(K)

    def sh(col, i):
        a = K[col].to_numpy(dtype=float); out = np.full(len(pos), np.nan)
        j = pos + i; ok = (j < n); ok &= (tk[np.minimum(j, n - 1)] == tk[pos])
        out[ok] = a[j[ok]]; return out
    buy = K.buy.to_numpy(dtype=float)[pos]; cost = K.cost.to_numpy(dtype=float)[pos]
    O = np.column_stack([sh("open", i) for i in range(1, hold + 1)]); C = np.column_stack([sh("close", i) for i in range(1, hold + 1)])
    Lw = np.column_stack([sh("low", i) for i in range(1, hold + 1)])
    exd = np.full(len(pos), hold)                                      # 원래 청산일(보유 며칠째)
    if t:
        run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
        hit = C <= run * (1 - t); exd = np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, hold)
    elif stop:
        hit = Lw <= (buy * (1 - stop))[:, None]; exd = np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, hold)
    gap = np.full(O.shape, np.nan); gap[:, 1:] = (O[:, 1:] / C[:, :-1] - 1) * 100       # 2일째부터(1일째 시가는 매수가)
    dayi = np.arange(1, hold + 1)[None, :]
    base = Z._r.to_numpy(dtype=float)
    for X in XS:
        ev = (gap >= X) & (dayi <= exd[:, None]) & (gap < 29.5)
        has = ev.any(axis=1); fi = ev.argmax(axis=1)
        var = base.copy()
        var[has] = (O[has, fi[has]] / buy[has] - 1) * 100 - cost[has]
        for j in np.flatnonzero(has):
            rows.append((rid, ns["NAME"][rid], X, Z.date.values[j], base[j], var[j], int(fi[j] + 1), hold))
    for j in range(len(base)): rows.append((rid, ns["NAME"][rid], 0, Z.date.values[j], base[j], base[j], 0, hold))
    print(rid, len(Z), flush=True)
R = pd.DataFrame(rows, columns=["rid", "name", "X", "date", "base", "var", "day", "hold"])
R.to_pickle("C:/temp/kp/kind/gapsell.pkl")
A = R[R.X == 0]
P("# H0402 스윙 보유 종목 갭 급등 시가 매도 · 2026-11-10"); P("")
P("- 국장 스윙 9규칙 거래 %d건(2005~, 패널 끝 %s) · '걸린 거래' = 보유 2일째 이후 시가 갭이 문턱 이상으로 처음 뜬 거래" % (len(A), ns["RULES"][ns["ORDER"][0]][0].date.max())); P("")
PER = (("옛날 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
if SKIP: P("- 시가 자료가 없어 뺀 규칙: " + ", ".join("[%s]" % x for x in SKIP)); P("")
P("## 전 규칙 합침"); P("")
P("| 갭 문턱 | 구간 | 거래 | 걸린 거래 | 걸린 거래: 원래 → 시가 매도 | 걸린 거래 차이(중앙) · 이긴 비율 | **전체 거래당 차이** | 걸린 날 평균(보유 며칠째) |"); P("|---|---|---|---|---|---|---|---|")
for X in XS:
    for nm, a, b in PER:
        tot = A[(A.date >= a) & (A.date <= b)]; g = R[(R.X == X) & (R.date >= a) & (R.date <= b)]
        if not len(tot) or not len(g): continue
        d = g["var"] - g.base
        P("| +%d%% | %s | %d | %d (%.0f%%) | %+.2f → %+.2f | %+.2f (%+.2f) · %.0f%% | **%+.2f%%p** | %.1f |" % (X, nm, len(tot), len(g), len(g) / len(tot) * 100, g.base.mean(), g["var"].mean(),
          d.mean(), d.median(), (d > 0).mean() * 100, d.sum() / len(tot), g.day.mean()))
P(""); P("## 규칙별 — 갭 +7% · +10%"); P("")
P("| 규칙 | 보유일 | 갭 | 거래 | 걸린 거래 | 원래 → 시가 매도(걸린 거래) | 차이 학습 16~22 | 차이 검증 23~ | 전체 거래당 차이 |"); P("|---|---|---|---|---|---|---|---|---|")
for rid in ns["ORDER"]:
    tot = A[A.rid == rid]
    for X in (7, 10):
        g = R[(R.X == X) & (R.rid == rid)]
        if not len(g): continue
        d = g["var"] - g.base

        def f(a, b):
            m = (g.date >= a) & (g.date <= b)
            return ("%+.2f (%d)" % (d[m].mean(), m.sum())) if m.sum() else "—"
        P("| [%s] | %d | +%d%% | %d | %d (%.0f%%) | %+.2f → %+.2f | %s | %s | %+.2f%%p |" % (tot.name.iloc[0], tot.hold.iloc[0], X, len(tot), len(g), len(g) / len(tot) * 100, g.base.mean(), g["var"].mean(),
          f("20160101", "20221231"), f("20230101", "20991231"), d.sum() / len(tot)))
P(""); P("(칸 %d)" % (len(XS) * 3 + 18))
(ROOT / "reports" / "gapsell_1110.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
from verdict import log_trials
log_trials("gapsell_1110", len(XS) * 3 + 18)
