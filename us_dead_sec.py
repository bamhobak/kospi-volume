# -*- coding: utf-8 -*-
"""폐지 종목의 SEC 재무·자사주를 뽑는다 — 생존편향 없는 미장 패널용 (2026-09-23).

SEC companyfacts.zip 에는 폐지된 회사 재무도 그대로 있다. 지금까지 못 쓴 건 티커↔회사번호 표가
현재 상장사뿐이었기 때문이다. match_sec_cik.py 가 이름으로 맞춘 회사번호(tiingo_cik.pkl)로 잇는다.

뽑는 방식은 기존 도구와 **똑같이** 맞춘다(규칙 재료가 두 집단에서 같은 정의여야 비교가 된다):
  재무   us_fin.py — 자본·자산·부채·순이익·주식수·EPS, (기준일별) **가장 먼저 공시된 값**, filed 로 시점 기준
  자사주 us_buyback.py — PaymentsForRepurchaseOfCommonStock 등, USD, filed

폐지 종목은 티커가 다른 회사에 재사용될 수 있어(389개가 지금 우리 종목과 같은 티커) 이름을
`티커^D` 로 바꿔 둔다. 패널도 같은 이름을 쓴다(us_panel_full.py).

출력: data/us/fin_dead.pkl · data/us/buyback_dead.pkl
    python us_dead_sec.py
"""
import json, sys, time, zipfile
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")
US = BASE / "data" / "us"

WANT = {   # us_fin.py 와 같은 태그·같은 우선순위
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
    "liab": ["Liabilities"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "shares": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding",
               "WeightedAverageNumberOfDilutedSharesOutstanding",
               "WeightedAverageNumberOfSharesOutstandingBasic"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
}
BBTAGS = {"PaymentsForRepurchaseOfCommonStock": "spend",          # us_buyback.py 와 같은 태그
          "StockRepurchaseProgramAuthorizedAmount1": "auth",
          "StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1": "left"}


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def pick(facts, names):   # us_fin.py 의 pick 과 같다
    for src in ("us-gaap", "dei"):
        g = facts.get(src, {})
        for n in names:
            u = g.get(n, {}).get("units", {})
            if not u:
                continue
            k = "USD" if "USD" in u else ("shares" if "shares" in u else
                                          ("USD/shares" if "USD/shares" in u else list(u)[0]))
            rows = [(x["end"], x["filed"], float(x["val"])) for x in u[k]
                    if x.get("end") and x.get("filed") and x.get("val") is not None]
            if rows:
                return rows
    return []


M = pd.read_pickle(US / "tiingo_cik.pkl")
M = M[M.cik.notna()].copy()
M["id"] = M.ticker + "^D"
cik2id = {}
for c, i in zip(M.cik.astype(int), M.id):
    cik2id.setdefault(c, []).append(i)
log(f"회사번호 있는 폐지 종목 {len(M):,} · 회사 {len(cik2id):,}")

fin, bb = [], []
t0 = time.time()
with zipfile.ZipFile(US / "companyfacts.zip") as z:
    names = [x for x in z.namelist() if x.startswith("CIK") and x.endswith(".json")]
    hit = 0
    for i, nm in enumerate(names):
        try:
            cik = int(nm[3:-5])
        except Exception:
            continue
        ids = cik2id.get(cik)
        if not ids:
            continue
        try:
            j = json.loads(z.read(nm))
        except Exception:
            continue
        f = j.get("facts", {})
        hit += 1
        got = {k: pick(f, v) for k, v in WANT.items()}
        if got["equity"]:
            d = {}
            for key, lst in got.items():
                for end, filed, val in lst:
                    cur = d.setdefault(end, {})
                    if key not in cur or filed < cur.get(key + "_f", "9999"):
                        cur[key] = val
                        cur[key + "_f"] = filed
            for end, v in d.items():
                filed = max([v[k + "_f"] for k in WANT if k + "_f" in v] or ["1900-01-01"])
                for t in ids:
                    fin.append((t, end, filed, v.get("equity"), v.get("assets"), v.get("liab"),
                                v.get("ni"), v.get("shares"), v.get("eps")))
        us = f.get("us-gaap", {})
        for tag, short in BBTAGS.items():
            for unit, obs in (us.get(tag, {}).get("units", {}) or {}).items():
                if unit != "USD":
                    continue
                for o in obs:
                    if o.get("val") is None or not o.get("filed"):
                        continue
                    for t in ids:
                        bb.append((t, cik, short, o.get("start"), o.get("end"), float(o["val"]),
                                   o.get("form"), o.get("filed").replace("-", "")))
        if hit % 500 == 0:
            log(f"  회사 {hit:,} · 재무 {len(fin):,} · 자사주 {len(bb):,} · {time.time() - t0:.0f}초")

F = pd.DataFrame(fin, columns=["ticker", "end", "filed", "equity", "assets", "liab", "ni", "shares", "eps"])
F["end"] = F.end.str.replace("-", "", regex=False)
F["filed"] = F.filed.str.replace("-", "", regex=False)
F = F.sort_values(["ticker", "filed", "end"]).drop_duplicates(["ticker", "end"], keep="first")
F.to_pickle(US / "fin_dead.pkl")
B = pd.DataFrame(bb, columns=["ticker", "cik", "tag", "start", "end", "val", "form", "filed"])   # buyback.pkl 과 같은 열
B.to_pickle(US / "buyback_dead.pkl")
log(f"끝: 재무 {len(F):,}행 · {F.ticker.nunique():,}종목 · 자사주 {len(B):,}행 · {B.ticker.nunique():,}종목")
