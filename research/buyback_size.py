# -*- coding: utf-8 -*-
"""자사주를 '방식·목적·규모'로 나누기 (2026-10-02 사용자 제안 10번).

재료: research/cache/buyback_kr.pkl(fetch_buyback_kr.py · DART 주요사항보고서 API)
  직접 취득 결정(tsstkAqDecsn): 취득예정금액(보통주) · 목적(aq_pp — '소각' 이 들어가면 소각 목적)
  신탁계약 체결(tsstkAqTrctrCnsDecsn): 계약금액
  + 공시 제목 '주식소각결정'(규모 없음)
규모 = 금액 ÷ 공시일 시가총액(%). 칸: 방식 × (전부 / 1%↑ / 3%↑ / 소각 목적) × (공시만 / 공시+20일 -10% 낙폭) × 진입 0·5·21 × 보유 20·60·120.
잣대는 event_lab 과 같다(같은 날 유니버스 대비 초과 · 학습·검증 · 본페로니).

    python research/buyback_size.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import event_lab as E

E.OUT.clear()
P = E.P


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return np.nan


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    L = E.Lab()
    D = E.disclosures()
    cmap = D.drop_duplicates("stock_code").set_index("corp_code").stock_code if "corp_code" in D else None
    import sqlite3
    c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
    cm = dict(c.execute("select corp_code, max(stock_code) from disclosure where stock_code!='' group by corp_code").fetchall())
    B = pd.read_pickle(ROOT / "cache" / "buyback_kr.pkl")
    B = B.dropna(subset=["rcept_no"])
    B["date"] = B.rcept_no.str[:8]
    B["ticker"] = B.corp_code.map(cm)
    B = B.dropna(subset=["ticker"])
    B["amt"] = np.where(B._api == "tsstkAqDecsn", B.aqpln_prc_ostk.map(num), B.ctr_prc.map(num) if "ctr_prc" in B else np.nan)
    B["burn"] = B.get("aq_pp", pd.Series("", index=B.index)).fillna("").str.contains("소각")
    A = L.A
    mc = dict(zip(A.ticker + "|" + A.date, A.marcap))
    ret20 = dict(zip(A.ticker + "|" + A.date, A.ret20))
    sd = [L.shift(d, 0) for d in B.date]
    B["sd"] = sd
    B["mc"] = [mc.get("%s|%s" % (t, d)) if d else np.nan for t, d in zip(B.ticker, B.sd)]
    B["r20"] = [ret20.get("%s|%s" % (t, d)) if d else np.nan for t, d in zip(B.ticker, B.sd)]
    B["size"] = B.amt / B.mc * 100
    P("# 자사주 — 방식·목적·규모로 나누기 · %s" % time.strftime("%Y-%m-%d")); P("")
    for api, nm in (("tsstkAqDecsn", "직접 취득"), ("tsstkAqTrctrCnsDecsn", "신탁 계약")):
        z = B[B._api == api]
        P("- %s %s건 · 규모 중앙 %.2f%% · 1%%↑ %d건 · 3%%↑ %d건 · 소각 목적 %d건" % (nm, f"{len(z):,}", z["size"].median(), (z["size"] >= 1).sum(), (z["size"] >= 3).sum(), z.burn.sum()))
    burn_t = D[D.t.str.contains("주식소각결정")]
    P("- 주식소각결정 공시 %s건(규모 없음)" % f"{len(burn_t):,}"); P("")
    groups = []
    for api, nm in (("tsstkAqDecsn", "직접 취득"), ("tsstkAqTrctrCnsDecsn", "신탁 계약")):
        z = B[B._api == api]
        groups += [(nm + " 전부", z), (nm + " 규모 1%↑", z[z["size"] >= 1]), (nm + " 규모 3%↑", z[z["size"] >= 3])]
        if api == "tsstkAqDecsn":
            groups += [(nm + " 소각 목적", z[z.burn]), (nm + " 소각 목적·1%↑", z[z.burn & (z["size"] >= 1)])]
    for nm, z in groups:
        for sub, zz in (("", z), (" + 20일 -10%", z[z.r20 <= -10])):
            e = list(zip(zz.ticker.values, zz.date.values))
            for k in (0, 5, 21):
                for h in (20, 60, 120):
                    L.cell("자사주", nm + sub, e, k, h)
    e = list(zip(burn_t.stock_code.values, burn_t.rcept_dt.values))
    for k in (0, 5, 21):
        for h in (20, 60, 120):
            L.cell("자사주", "주식소각결정 공시", e, k, h)
    G, zc = L.judge()
    G.to_pickle(ROOT / "cache" / "buyback_size.pkl")
    P("칸 %d개 · 본페로니 t ≥ %.2f · 통과 %d칸 · 근접 %d칸" % (len(G), zc, G["pass"].sum(), G.near.sum())); P("")
    P("| 사건 | 진입 | 보유 | 건수(옛·학·검) | 옛날 중앙·초과 | 학습 중앙·초과·승률 | 검증 중앙·초과·승률 | t | 양수 해 | 판정 |"); P("|---|---|---|---|---|---|---|---|---|---|")
    f = lambda v: "%+.2f" % v if v == v else "-"
    show = pd.concat([G[G["pass"] | G.near], G.sort_values("t", ascending=False).head(15)]).drop_duplicates(subset=["name", "k", "h"])
    for _, x in show.sort_values("t", ascending=False).iterrows():
        P("| %s | +%d일 | %d일 | %d·%d·%d | %s · %s | %s · %s · %s | %s · %s · %s | %s | %d/%d | %s |" % (
            x["name"], x.k, x.h, x.n0, x.n1, x.n2, f(x.med0), f(x.ex0), f(x.med1), f(x.ex1), ("%.0f%%" % x.win1) if x.win1 == x.win1 else "-",
            f(x.med2), f(x.ex2), ("%.0f%%" % x.win2) if x.win2 == x.win2 else "-", ("%.1f" % x.t) if x.t == x.t else "-", x.ypos, x.ny,
            "✅ 통과" if x["pass"] else ("△ 근접" if x.near else "")))
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("buyback_size_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(E.OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
