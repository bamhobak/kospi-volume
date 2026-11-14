# -*- coding: utf-8 -*-
"""2026-11-15 ③ [반대매매] 형제 [연말 양도세 회피 매도 되돌림] — 정보 없는 기계적 매도(대주주 판정 피하려는 개인의 12월 말 매도) → 1월 초 되돌림.
자료: investor.db flow11 개인 순매수(원) · factory_kr.pkl(amt20) · factory_px(시가·종가).
신호: 그해 마지막 5거래일 개인 순매수 합 ÷ (20일 평균 거래대금 × 5) % — 그해 유니버스(거래대금 5억↑·1,000원↑) 하위 10%(가장 많이 판 쪽).
  A) 마지막 거래일 종가 매수(그 날까지 4일 수급만 씀 — 장 끝 전에 앎) · B) 1월 첫 거래일 시가 매수(5일 다 씀) → 5·10·20거래일 뒤 종가.
시장 대비 = 같은 구간 유니버스 평균. 해마다 표(1년에 한 번이라 해 수가 표본) · 대주주 기준: ~2023 10억 → 2024~ 50억.
    python research/memguard.py research/sib_yearend_1115.py → research/reports/sib_yearend_1115.md"""
import sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK = 0.23
c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
F = pd.read_sql("SELECT ticker, date, indiv FROM flow11 WHERE substr(date,5,2) = '12' OR substr(date,5,2) = '01'", c)
F["ticker"] = F.ticker.astype(str)
U = pd.read_pickle(ROOT / "cache" / "factory_kr.pkl")[["ticker", "date", "amt20", "px"]]
U = U[(U.date.str[4:6] == "12")]; U["ticker"] = U.ticker.astype(str)
PX = pd.read_pickle(ROOT / "cache" / "factory_px.pkl")[["ticker", "date", "open", "close"]]
PX = PX[PX.date >= "20171101"].copy(); PX["ticker"] = PX.ticker.astype(str)
cal = sorted(PX.date.unique()); ci = {d: i for i, d in enumerate(cal)}
O = PX.pivot(index="date", columns="ticker", values="open").reindex(cal); C = PX.pivot(index="date", columns="ticker", values="close").reindex(cal).ffill()
rows = []
for y in sorted({d[:4] for d in F.date if d[4:6] == "12"}):
    dec = [d for d in cal if d[:4] == y and d[4:6] == "12"]
    if len(dec) < 6 or ci[dec[-1]] + 21 >= len(cal): continue
    last5, last4 = dec[-5:], dec[-5:-1]; ld = dec[-1]; j1 = cal[ci[ld] + 1]
    u = U[(U.date == ld) & (U.amt20 >= 5) & (U.px >= 1000)].set_index("ticker")
    for mode, win, buy_i, buy_px in (("A 마지막 날 종가", last4, ci[ld], "c"), ("B 1월 첫날 시가", last5, ci[j1], "o")):
        f = F[F.date.isin(win)].groupby("ticker").indiv.sum()
        x = (f.reindex(u.index) / (u.amt20 * 1e8 * len(win)) * 100).dropna()
        if len(x) < 100: continue
        cut = x.quantile(0.10); sel = x[x <= cut].index
        for h in (5, 10, 20):
            i1 = buy_i + h - (0 if buy_px == "c" else 1)
            b = (C if buy_px == "c" else O).iloc[buy_i]; e = C.iloc[i1]
            r = ((e / b - 1) * 100).replace([np.inf, -np.inf], np.nan)
            ru = r.reindex(u.index).dropna(); ru = ru[ru.abs() < 80]
            rs = ru.reindex(sel).dropna()
            rows.append(dict(y=y, mode=mode, h=h, n=len(rs), sel=rs.mean() - CK, med=rs.median() - CK, win=(rs - CK > 0).mean() * 100, uni=ru.mean(), ex=rs.mean() - ru.mean(), cut=cut))
R = pd.DataFrame(rows)
P("# [연말 양도세 회피 매도 되돌림] — [반대매매] 형제 (2026-11-15)\n")
P("- 그해 마지막 5거래일 개인 순매도가 가장 큰 10% (유니버스 거래대금 5억↑) · 비용 0.23 뒤 · 시장 대비 = 같은 구간 유니버스 평균 뺌 · 대주주 기준 ~2023 10억 → 2024~ 50억\n")
for mode in R["mode"].unique():
    P("\n## %s\n" % mode)
    P("| 보유 | " + " | ".join(sorted(R.y.unique())) + " | 평균 | 시장 대비 플러스 해 |"); P("|---" * (R.y.nunique() + 3) + "|")
    for h in (5, 10, 20):
        q = R[(R["mode"] == mode) & (R.h == h)].set_index("y")
        P("| %d일 | %s | %+.2f%% (시장 대비 %+.2f%%p) | %d/%d |" % (h, " | ".join("%+.1f (%+.1f) n%d" % (q.sel[y], q.ex[y], q.n[y]) if y in q.index else "-" for y in sorted(R.y.unique())),
          q.sel.mean(), q.ex.mean(), (q.ex > 0).sum(), len(q)))
P("\n칸 = 고른 종목 평균(비용 뒤) (시장 대비 %p) n건")
(ROOT / "reports" / "sib_yearend_1115.md").write_text("\n".join(OUT), encoding="utf-8")
