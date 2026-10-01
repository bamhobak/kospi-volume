# -*- coding: utf-8 -*-
"""미장 S&P 500 편출 종목 — 지수 펀드 강제 매도가 끝난 뒤 되돌림 (2026-10-02 사용자 제안 2번).

편출일 = data/us/sp500/ticker_start_end.csv(fja05680/sp500 공개 자료) 의 end_date.
**편출 뒤에도 거래되는 종목만**(인수·합병으로 사라진 건 뺀다 — 편출일 뒤 30거래일 이상 시세가 있어야).
진입 = 편출일 + k거래일(신호일)의 다음날 시가 · 보유 H · 비용 차감 · 폐지 포함 패널 us_full_2007.
잣대: 같은 날 미장 유동 유니버스(거래대금 상위 40%·$3↑) 중앙 대비 초과 · 옛날 08~15 / 학습 16~22 / 검증 23~.
대조: 같은 날 S&P 400 으로 갈 만한 체급 — 편출 종목과 시총 비슷한 종목의 평균은 따로 안 만들고 유니버스 중앙으로 본다.

    python research/sp500_del.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = [("옛날", "20080101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]

K = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")[["ticker", "date", "px", "buy", "cost", "amt20", "rawclose", "marcap"]]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
g = K.groupby("ticker", sort=False).px
HS = (20, 60, 120, 250)
for h in HS:
    K["n%d" % h] = (g.shift(-h) / K.buy - 1) * 100 - K.cost
cal = np.array(sorted(K.date.unique()))
q = K.groupby("date").amt20.rank(pct=True)
uni = (q >= 0.6) & (K.rawclose >= 3)
bench = {h: K[uni].dropna(subset=["n%d" % h]).groupby("date")["n%d" % h].median() for h in HS}
pos = {k: i for i, k in enumerate(K.ticker + "|" + K.date)}
cnt_after = K.groupby("ticker").date.apply(np.array)

T = pd.read_csv(BASE / "data" / "us" / "sp500" / "ticker_start_end.csv", dtype=str).dropna(subset=["end_date"])
T["d"] = T.end_date.str.replace("-", "")
T = T[T.d >= "20080101"]
ev = []
for t, d in zip(T.ticker, T.d):
    t2 = t.replace(".", "-")
    for tt in (t, t2, t.replace(".", "")):
        if tt in cnt_after.index:
            ds = cnt_after[tt]
            if (ds > d).sum() >= 30:
                ev.append((tt, d))
            break
P("# S&P 500 편출 뒤 · %s" % time.strftime("%Y-%m-%d")); P("")
P("편출 기록 %d건(2008~) 중 편출 뒤 30거래일 이상 거래된 종목 **%d건**(나머지는 인수·합병 등으로 사라짐)." % (len(T), len(ev))); P("")
cells = []
for k in (0, 5, 10, 21, 40):
    for h in HS:
        rows = []
        for t, d in ev:
            i = np.searchsorted(cal, d, "left") + k
            if i >= len(cal):
                continue
            ix = pos.get(t + "|" + cal[i])
            if ix is None:
                continue
            r = K["n%d" % h].values[ix]
            if r == r:
                rows.append((cal[i], t, r, K.marcap.values[ix]))
        Y = pd.DataFrame(rows, columns=["date", "ticker", "r", "mc"])
        Y["ex"] = Y.r - Y.date.map(bench[h])
        cells.append((k, h, Y))
M = len(cells); zc = norm.ppf(1 - 0.05 / M)
P("| 진입 | 보유 | 건수(옛·학·검) | 옛날 중앙·초과 | 학습 중앙·초과·승률 | 검증 중앙·초과·승률 | 2008~ 평균 | t | 양수 해 |"); P("|---|---|---|---|---|---|---|---|---|")
f = lambda v: "%+.2f" % v if v == v else "-"
for k, h, Y in cells:
    st = []
    for lab, a, b in PER:
        z = Y[(Y.date >= a) & (Y.date <= b)]
        st.append((len(z), z.r.median() if len(z) >= 10 else np.nan, z.ex.median() if len(z) >= 10 else np.nan, (z.r > 0).mean() * 100 if len(z) else np.nan))
    m = Y.groupby(Y.date.str[:6]).ex.mean()
    t = m.mean() / (m.std() / np.sqrt(len(m))) if len(m) >= 12 else np.nan
    ys = Y.groupby(Y.date.str[:4]).r.mean()
    P("| +%d일 | %d일 | %d·%d·%d | %s · %s | %s · %s · %.0f%% | %s · %s · %.0f%% | %s | %s | %d/%d |" % (
        k, h, st[0][0], st[1][0], st[2][0], f(st[0][1]), f(st[0][2]), f(st[1][1]), f(st[1][2]), st[1][3], f(st[2][1]), f(st[2][2]), st[2][3],
        f(Y.r.mean()), ("%.1f" % t) if t == t else "-", (ys > 0).sum(), len(ys)))
P(""); P("본페로니 문턱 t ≥ %.2f (칸 %d개)." % (zc, M))
(ROOT / "reports" / ("sp500_del_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
log_trials("sp500_del_%s" % time.strftime("%Y%m%d"), M)
