# -*- coding: utf-8 -*-
"""Tiingo 종목 ↔ SEC 회사번호(CIK) 짝 맞추기 — 회사 이름·옛 이름으로 (2026-09-23).

SEC 는 폐지 회사의 티커를 지운다. 그래서 **정식 회사명**(Tiingo)을 SEC 의 현재 이름·옛 이름과
정규화해서 맞춘다. 같은 이름이 여러 회사면 **SEC 마지막 공시일이 Tiingo 거래 종료일에 가까운 쪽**을 고른다.

정확도는 정답을 아는 종목으로 먼저 잰다: 지금 상장사는 SEC company_tickers.json 에 티커↔CIK 가
있으니, 같은 방식으로 이름만 보고 맞춘 CIK 가 정답과 같은지 본다(--check).

입력  data/us/sec_cik.pkl(build_sec_cik.py) · data/us/tiingo_fund_meta.pkl · tiingo_dead.db names/meta
출력  data/us/tiingo_cik.pkl — ticker · name · cik · how(name/former) · cands(후보 수)
    python match_sec_cik.py --check     # 정확도만
    python match_sec_cik.py             # 폐지 종목 짝 맞추기
"""
import json, re, sqlite3, sys
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")
US = BASE / "data" / "us"

SUFFIX = r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|LP|L P|HOLDINGS?|GROUP|THE|" \
         r"CLASS [A-C]\d?|CL [A-C]|COMMON STOCK|COMMON SHARES|ORDINARY SHARES|ADR|ADS|COM|NEW|DEL|DE|" \
         r"NV|SA|AG|SE|TRUST|BANCORP|UNITS?|WARRANTS?|RIGHTS?)\b"


def norm(s):
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.upper().replace("&", " AND ")
    s = re.sub(r"\(.*?\)", " ", s)            # (THE) · (DE) 같은 괄호
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(SUFFIX, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


S = pd.read_pickle(US / "sec_cik.pkl")
idx = {}                                         # 정규화 이름 → [(cik, how, last_filed)]
for r in S.itertuples():
    k = norm(r.name)
    if k:
        idx.setdefault(k, []).append((r.cik, "name", r.last_filed))
    for f in r.former:
        k = norm(f)
        if k:
            idx.setdefault(k, []).append((r.cik, "former", r.last_filed))


def match(name, end=None):
    k = norm(name)
    c = idx.get(k) if k else None
    if not c:
        return None, None, 0
    ciks = {x[0] for x in c}
    if len(ciks) == 1:
        x = c[0]
        return x[0], x[1], 1
    # 여러 회사가 같은 이름을 쓴다(ALCOA: 지금 알코아 + 옛 이름이 ALCOA 인 옛 회사).
    #   ① 현재 상장사면 현재 이름으로 맞는 회사가 하나뿐일 때 그쪽 — 옛 이름은 다른 회사가 물려받았을 수 있다
    cur = {x[0] for x in c if x[1] == "name"}
    if len(cur) == 1 and not end:
        return cur.pop(), "name", len(ciks)
    #   ② 폐지 종목이면 SEC 마지막 공시일이 거래 종료일에 가장 가까운 회사,
    #      현재 상장사면 가장 최근까지 공시한 회사
    e = pd.Timestamp(str(end)[:10]) if end else pd.Timestamp.today()
    best = min(c, key=lambda x: abs(pd.Timestamp(x[2] or "1990-01-01") - e).days)
    return best[0], best[1] + "~", len(ciks)


if "--check" in sys.argv:
    F = pd.read_pickle(US / "tiingo_fund_meta.pkl")
    F = F[F.isActive & F.name.notna()]
    ct = json.load(open(US / "company_tickers.json", encoding="utf-8"))
    truth = {v["ticker"].upper(): int(v["cik_str"]) for v in ct.values()}
    F = F[F.ticker.isin(truth)]
    got = [match(n) for n in F.name]
    F["cik"] = [g[0] for g in got]
    F["cands"] = [g[2] for g in got]
    F["ok"] = F.cik == F.ticker.map(truth)
    hit = F.cik.notna()
    print(f"정답 아는 상장사 {len(F):,}곳")
    print(f"  짝 찾음 {hit.mean() * 100:.1f}% · 찾은 것 중 정답 {F[hit].ok.mean() * 100:.1f}% · "
          f"후보 여러 개라 보류 {(F.cands > 1).sum():,}")
    print("  틀린 예:", F[hit & ~F.ok][["ticker", "name"]].head(8).values.tolist())
    sys.exit(0)

c = sqlite3.connect(f"file:{US / 'tiingo_dead.db'}?mode=ro", uri=True, timeout=600)
M = pd.read_sql("select m.ticker, m.grp, m.endDate, n.name from meta m left join names n using(ticker)", c)
M = M[M.name.notna()]
got = [match(n, e) for n, e in zip(M.name, M.endDate)]
M["cik"] = [g[0] for g in got]
M["how"] = [g[1] for g in got]
M["cands"] = [g[2] for g in got]
M.to_pickle(US / "tiingo_cik.pkl")
print(f"이름 있는 폐지 대상 {len(M):,} · 회사번호 찾음 {M.cik.notna().sum():,} ({M.cik.notna().mean() * 100:.0f}%)")
print(M.groupby("grp").cik.apply(lambda s: f"{s.notna().sum():,}/{len(s):,}").to_string())
print("방식:", M.how.value_counts().to_dict())
