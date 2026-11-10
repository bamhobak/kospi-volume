# -*- coding: utf-8 -*-
"""NXT 장후 그림자(성적표 report.md) 마이너스 vs 실전 T6 1주 매매 플러스 — 왜 다른가(2026-11-10 사용자 "둘 다 봐줘").
그림자 = data/nxt/log.csv(grp picks/big, r_ask = 19:50 매도 1호가 → 다음 날 KRX 시가, 비용 뒤)
실전 = data/day/ledger.json rid T6 (매수 체결가 → 다음 날 시가 매도 체결가, 비용 0.23)
    python research/nxt_shadow_vs_live_1110.py
"""
import json, sys
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
B = Path(__file__).resolve().parent.parent
COST = 0.23
L = json.load(open(B / "data/day/ledger.json", encoding="utf-8"))["orders"]
T = [o for o in L if o.get("rid") == "T6" and (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0]
buys = pd.DataFrame([dict(d=o["date"], t=o["t"], name=o.get("name"), bq=o["fq"], bp=o["ap"], lim=o.get("lim"), rel=o.get("rel")) for o in T if o["side"] == "BUY"])
sells = pd.DataFrame([dict(sd=o["date"], t=o["t"], sp=o["ap"]) for o in T if o["side"] == "SELL"])
G = pd.read_csv(B / "data/nxt/log.csv", dtype={"t": str, "pick_day": str, "sell_day": str})
days = sorted(set(G.pick_day) | set(buys.d))
nxt = {d: min([x for x in sorted(set(G.sell_day) | set(sells.sd)) if x > d], default=None) for d in days}
buys["sd"] = buys.d.map(nxt)
Lv = buys.merge(sells, on=["t", "sd"], how="left")
Lv["r"] = (Lv.sp / Lv.bp - 1) * 100 - COST
picks = {d: set(json.load(open(B / ("data/nxt/pick_%s.json" % d), encoding="utf-8")).get("picks") and
                [x["t"] for x in json.load(open(B / ("data/nxt/pick_%s.json" % d), encoding="utf-8"))["picks"]] or [])
         for d in days if (B / ("data/nxt/pick_%s.json" % d)).exists()}
print("| 고른 날 | 그림자 상위 절반 건·r_ask | 실전 T6 건·건당 | 실전 중 그림자에도 있는 것 | 겹친 종목: 그림자 r_ask vs 실전 |")
print("|---|---|---|---|---|")
for d in days:
    g = G[(G.pick_day == d) & (G.grp == "picks")]
    v = Lv[Lv.d == d]
    ov = v[v.t.isin(picks.get(d, set()))]
    m = ov.merge(g[["t", "r_ask"]], on="t")
    print("| %s | %d · %s | %d · %s | %d/%d | %s |" % (d, len(g), ("%+.2f" % g.r_ask.mean()) if len(g) else "-", len(v),
          ("%+.2f" % v.r.mean()) if len(v) and v.r.notna().any() else "-", len(ov), len(v),
          ("%+.2f vs %+.2f" % (m.r_ask.mean(), m.r.mean())) if len(m) else "-"))
v = Lv.dropna(subset=["r"])
print("\n실전 T6 전체 %d건 건당 %+.2f%% · 승률 %.0f%% · 날별: %s" % (len(v), v.r.mean(), (v.r > 0).mean() * 100,
      " ".join("%s %d건 %+.2f" % (d, len(x), x.r.mean()) for d, x in v.groupby("d"))))
g = G[G.grp == "picks"]
for nm, lo, hi in (("10-26~11-03(실전 전)", "20261026", "20261103"), ("11-04~11-09(실전과 같은 날)", "20261104", "20261109"), ("전체", "0", "9")):
    z = g[(g.pick_day >= lo) & (g.pick_day <= hi)]
    print("그림자 상위 절반 %s: %d건 r_ask %+.2f%% · 승률 %.0f%%" % (nm, len(z), z.r_ask.mean(), (z.r_ask > 0).mean() * 100))
# 같은 종목·같은 날 가격 맞추기 — 매수가·매도가 차이
m = Lv.merge(G[G.grp == "picks"][["pick_day", "t", "ask", "open1", "r_ask"]].rename(columns={"pick_day": "d"}), on=["d", "t"])
if len(m):
    m["buy_gap"] = (m.bp / m.ask - 1) * 100; m["sell_gap"] = (m.sp / m.open1 - 1) * 100
    print("\n겹친 %d건 — 실전 매수가 ÷ 그림자 매도1호가 중앙 %+.2f%% · 실전 매도가 ÷ 그림자 시가 중앙 %+.2f%% · 실전 %+.2f vs 그림자 %+.2f" % (
        len(m), m.buy_gap.median(), m.sell_gap.median(), m.r.mean(), m.r_ask.mean()))
    print(m[["d", "t", "name", "bp", "ask", "sp", "open1", "r", "r_ask"]].round(2).to_string(index=False))
