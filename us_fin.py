# -*- coding: utf-8 -*-
"""SEC companyfacts 1.41GB 에서 우리가 쓸 항목만 뽑아 시점기준 표로 만든다.

한국 규칙이 쓰는 재무 재료는 셋이다 — PBR · PER · 부채비율.
그걸 만들려면 자본총계·자산·부채·순이익·주식수가 필요하다.

⚠ **시점 기준(point-in-time)이 핵심이다.** 2020년 3월에 2019년 4분기 재무를 알 수 있으려면
   그게 이미 공시돼 있어야 한다. 한국(DART)에서는 공시 지연을 손으로 맞췄지만
   (11013→0515, 11012→0815 …) SEC XBRL 은 각 값에 **filed(공시일)** 가 붙어 있어
   그대로 쓰면 된다. 미래 정보가 새지 않는다.

   같은 항목이 여러 번 정정 공시되므로 (기준일, 항목)당 **가장 먼저 공시된 값**을 쓴다.
   나중 정정본을 쓰면 그 시점에 몰랐던 숫자를 쓰는 셈이다.

출력: data/us/fin.pkl  (ticker · filed · end · 자본총계 · 자산 · 부채 · 순이익 · 주식수)
"""
import io, sys, json, time, zipfile, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd, numpy as np

OUT = Path("data/us")
ZIP = OUT / "companyfacts.zip"

# us-gaap 태그는 회사마다 다른 이름을 쓴다. 우선순위 순서로 찾는다.
WANT = {
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


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def pick(facts, names):
    """항목 하나를 (기준일, 최초공시일, 값) 목록으로 뽑는다."""
    for src in ("us-gaap", "dei"):
        g = facts.get(src, {})
        for n in names:
            u = g.get(n, {}).get("units", {})
            if not u:
                continue
            k = "USD" if "USD" in u else ("shares" if "shares" in u else
                                          ("USD/shares" if "USD/shares" in u else list(u)[0]))
            rows = []
            for x in u[k]:
                if x.get("end") and x.get("filed") and x.get("val") is not None:
                    # 분기·연간이 섞이지 않게 — 잔액 항목(자본·자산)은 시점값이라 그대로,
                    # 손익 항목은 fp/fy 로 구분되지만 여기선 최근값만 쓰므로 그대로 둔다
                    rows.append((x["end"], x["filed"], float(x["val"])))
            if rows:
                return rows
    return []


# 티커 ↔ CIK
ct = json.load(open(OUT / "company_tickers.json", encoding="utf-8"))
cik2tic = {}
for v in ct.values():
    cik2tic.setdefault(int(v["cik_str"]), []).append(v["ticker"])
log(f"티커↔CIK {len(cik2tic):,}개 회사")

use = set(pd.read_csv(OUT / "tickers.csv", dtype=str).Symbol)
log(f"우리 대상 종목 {len(use):,}개")

rows = []
n = hit = 0
t0 = time.time()
with zipfile.ZipFile(ZIP) as z:
    names = [x for x in z.namelist() if x.startswith("CIK") and x.endswith(".json")]
    log(f"압축 안 회사 파일 {len(names):,}개 — 훑기 시작")
    for i, nm in enumerate(names):
        n += 1
        try:
            cik = int(nm[3:-5])
        except Exception:
            continue
        tics = [t for t in cik2tic.get(cik, []) if t in use]
        if not tics:
            continue
        try:
            j = json.loads(z.read(nm))
        except Exception:
            continue
        f = j.get("facts", {})
        got = {k: pick(f, v) for k, v in WANT.items()}
        if not got["equity"]:
            continue
        hit += 1
        # 기준일(end)별로 묶고, 같은 end 는 **가장 먼저 공시된 값**만 남긴다
        d = {}
        for key, lst in got.items():
            for end, filed, val in lst:
                cur = d.setdefault((end,), {})
                if key not in cur or filed < cur.get(key + "_f", "9999"):
                    cur[key] = val
                    cur[key + "_f"] = filed
        for (end,), v in d.items():
            filed = max([v[k + "_f"] for k in WANT if k + "_f" in v] or ["1900-01-01"])
            for t in tics:
                rows.append((t, end, filed, v.get("equity"), v.get("assets"),
                             v.get("liab"), v.get("ni"), v.get("shares"), v.get("eps")))
        if i % 2000 == 0 and i:
            log(f"  {i:,}/{len(names):,} · 대상 회사 {hit:,} · 행 {len(rows):,} · "
                f"{time.time()-t0:.0f}초")

F = pd.DataFrame(rows, columns=["ticker", "end", "filed", "equity", "assets",
                                "liab", "ni", "shares", "eps"])
F["end"] = F.end.str.replace("-", "", regex=False)
F["filed"] = F.filed.str.replace("-", "", regex=False)
F = F.sort_values(["ticker", "filed", "end"]).drop_duplicates(["ticker", "end"], keep="first")
F.to_pickle(OUT / "fin.pkl")
log(f"저장 data/us/fin.pkl · {len(F):,}행 · 종목 {F.ticker.nunique():,}개 · "
    f"공시일 {F.filed.min()}~{F.filed.max()}")
print()
print("  항목별 유효율")
for c in ("equity", "assets", "liab", "ni", "shares", "eps"):
    print(f"    {c:<10}{F[c].notna().mean()*100:>6.1f}%")
