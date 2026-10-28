# -*- coding: utf-8 -*-
"""레버리지 ETF 애프터장 +2% 매수 → 다음 정규장 시가/종가 매도 (2026-10-29 사용자 "etf(soxs soxl tqqq sqqq) 장 끝나고 애프터 장 때 2% 이상 올랐을 때 매수 후 다음 정규장 시가매도나 종가매도 실측").
자료 = Massive(구 Polygon) 1분봉 · 프리·애프터 포함(04:00~20:00 뉴욕) · 무료 요금제라 최근 2년만(2024-11~) · data/us/ah/{티커}.parquet 에 모아 둔다.
기준 = 그날 정규장 종가(15:59 봉 종가). 애프터 = 16:00~19:59 봉.
  A '처음 닿을 때': 애프터 중 고가가 기준 × (1+문턱) 이상인 첫 분 → 그 값에 산다(그 분 시가가 이미 위면 시가에)
  B '애프터 끝': 19:59 봉 종가가 기준 × (1+문턱) 이상이면 그 값에 산다
매도 = 다음 거래일 정규장 첫 봉(09:30) 시가 · 또는 그날 15:59 봉 종가. 비용 = 토스 미장 수수료 왕복 0.2%(index.html DEFFEE US) — 애프터 호가 차이(스프레드)는 안 넣음.
    python research/us_ah_etf_1029.py            (받기 + 표)
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd, requests
from dotenv import dotenv_values

KEY = dotenv_values(BASE / ".env")["MASSIVE_API_KEY"]
TICK = ("SOXL", "SOXS", "TQQQ", "SQQQ")
DIR = BASE / "data" / "us" / "ah"; DIR.mkdir(parents=True, exist_ok=True)
START, END = pd.Timestamp("2024-11-01"), pd.Timestamp("2026-10-28")
COST = 0.20
_last = [0.0]


def get(url, params=None):
    for att in range(6):
        w = 12.5 - (time.time() - _last[0])                 # 무료: 1분에 5번
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 429: time.sleep(20); continue
        r.raise_for_status(); return r.json()
    raise RuntimeError("429 계속")


def fetch(t):
    f = DIR / (t + ".parquet")
    if f.exists(): return pd.read_parquet(f)
    rows, a = [], START
    while a <= END:
        b = min(a + pd.Timedelta(days=40), END)
        j = get(f"https://api.massive.com/v2/aggs/ticker/{t}/range/1/minute/{a:%Y-%m-%d}/{b:%Y-%m-%d}",
                dict(apiKey=KEY, limit=50000, sort="asc", adjusted="true"))
        rows += j.get("results") or []
        while j.get("next_url"):
            j = get(j["next_url"], dict(apiKey=KEY)); rows += j.get("results") or []
        print(t, a.date(), "~", b.date(), len(rows), flush=True)
        a = b + pd.Timedelta(days=1)
    D = pd.DataFrame(rows)[["t", "o", "h", "l", "c", "v"]].drop_duplicates("t").sort_values("t")
    ts = pd.to_datetime(D.t, unit="ms", utc=True).dt.tz_convert("America/New_York")
    D["d"] = ts.dt.strftime("%Y%m%d"); D["hm"] = ts.dt.strftime("%H%M")
    D.to_parquet(f); return D


def events(D, thr):
    out = []
    days = sorted(D.d.unique())
    G = dict(tuple(D.groupby("d")))
    for i, d in enumerate(days[:-1]):
        g = G[d]; reg = g[(g.hm >= "0930") & (g.hm <= "1559")]; ah = g[(g.hm >= "1600") & (g.hm <= "1959")]
        n = G[days[i + 1]]; nreg = n[(n.hm >= "0930") & (n.hm <= "1559")]
        if len(reg) < 300 or not len(ah) or len(nreg) < 300: continue          # 반장·빈 날 제외
        ref = float(reg.c.iloc[-1]); lv = ref * (1 + thr / 100)
        nop, ncl = float(nreg.o.iloc[0]), float(nreg.c.iloc[-1])
        hit = ah[ah.h >= lv] if thr > 0 else ah[ah.l <= lv]
        e = dict(d=d, ref=ref, nop=nop, ncl=ncl, ahc=float(ah.c.iloc[-1]), ahv=float(ah.v.sum()))
        if len(hit):
            x = hit.iloc[0]; e["A"] = max(float(x.o), lv) if thr > 0 else min(float(x.o), lv); e["Ahm"] = x.hm
        if (thr > 0 and e["ahc"] >= lv) or (thr < 0 and e["ahc"] <= lv): e["B"] = e["ahc"]
        out.append(e)
    return pd.DataFrame(out)


def cell(r):
    r = r.dropna()
    if len(r) < 3: return "%d건" % len(r)
    return "%d건 %+.2f%% · 승 %.0f%% · 중앙 %+.2f%%" % (len(r), r.mean(), (r > 0).mean() * 100, r.median())


def main():
    D = {t: fetch(t) for t in TICK}
    print()
    for t in TICK:
        g = D[t]; print("%s 1분봉 %d개 · %s~%s" % (t, len(g), g.d.min(), g.d.max()))
    print("\n칸 = 건수 · 건당(비용 0.2% 뒤) · 승률 · 중앙 — A 애프터에서 처음 닿을 때 삼 · B 애프터 끝(19:59) 값으로 삼 · 매도 다음 날 시가 / 종가\n")
    print("| 종목 | 애프터 문턱 | A→시가 | A→종가 | B→시가 | B→종가 | 참고: 모든 날 애프터 끝→시가 |")
    print("|---|---|---|---|---|---|---|")
    for t in TICK:
        for thr in (1, 2, 3, -2):
            E = events(D[t], thr)
            r = lambda buy, sell: ((E[sell] / E[buy] - 1) * 100 - COST) if buy in E else pd.Series(dtype=float)
            base = (E.nop / E.ahc - 1) * 100 - COST
            print("| %s | %+d%% | %s | %s | %s | %s | %s |" % (t, thr, cell(r("A", "nop")), cell(r("A", "ncl")), cell(r("B", "nop")), cell(r("B", "ncl")),
                  cell(base) if thr == 1 else ""), flush=True)
    # +2% 해별·매수 시각
    print("\n+2% 해별(A→시가 / A→종가) 와 처음 닿은 시각")
    for t in TICK:
        E = events(D[t], 2); E = E[E.A.notna()]
        if not len(E): continue
        E["ro"] = (E.nop / E.A - 1) * 100 - COST; E["rc"] = (E.ncl / E.A - 1) * 100 - COST
        y = E.d.str[:4]
        print("  %s: " % t + " · ".join("%s %d건 %+.2f/%+.2f" % (yy, len(g), g.ro.mean(), g.rc.mean()) for yy, g in E.groupby(y))
              + " | 16시대 %d · 17시대 %d · 18~19시대 %d" % ((E.Ahm < "1700").sum(), ((E.Ahm >= "1700") & (E.Ahm < "1800")).sum(), (E.Ahm >= "1800").sum()))
        print("     날짜: " + ", ".join("%s(%+.1f/%+.1f)" % (d[2:], a, b) for d, a, b in zip(E.d, E.ro, E.rc)))


if __name__ == "__main__":
    main()
