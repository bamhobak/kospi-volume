# -*- coding: utf-8 -*-
"""S&P 500 편출 감시 — SPY 일일 보유종목 차이로 편출을 잡는다 (2026-10-02, [S&P 편출](N9) 규칙용).

공급처: SSGA 의 SPY(S&P 500 추종 ETF) 일일 보유종목 xlsx — 매일 갱신 · 'As of' 기준일 · 티커 · CUSIP(Identifier).
  · 어제 목록에 있던 CUSIP 이 오늘 목록에 없으면 = 편출(기준일 = 오늘 파일의 'As of' 날짜 = 편출 효력일)
  · 같은 CUSIP 이 다른 티커로 남아 있으면 = 이름·티커만 바뀐 것 → 편출 아님
  · 처음 실행(목록 파일이 없을 때)은 공개 이력(data/us/sp500/ticker_start_end.csv, fja05680)의 최근 200일 편출로 채운다
→ data/us/sp500/removed.csv (ticker, date, src) · data/us/sp500/spy_last.csv(직전 목록)
실패하면 기존 파일을 지킨다(편출은 드물고, 규칙은 21거래일 뒤라 하루 늦어도 괜찮다).

    python collect_sp500.py
"""
import csv, datetime as dt, io, os, sys, time
from pathlib import Path

BASE = Path(__file__).parent
D = BASE / "data" / "us" / "sp500"
URL = "https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass


def norm(t):
    return str(t).strip().upper().replace(".", "-").replace("/", "-")


def fetch():
    import pandas as pd, requests
    for att in range(3):
        try:
            r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            if r.status_code == 200 and r.content[:2] == b"PK":
                break
        except Exception:
            pass
        time.sleep(5 * (att + 1))
    else:
        raise RuntimeError("SPY 보유종목 파일을 못 받았다")
    raw = pd.read_excel(io.BytesIO(r.content), header=None)
    asof = None
    for v in raw.iloc[:6, 1].astype(str):
        if v.startswith("As of"):
            asof = dt.datetime.strptime(v.replace("As of", "").strip(), "%d-%b-%Y").strftime("%Y%m%d")
    h = raw.index[raw.iloc[:, 1].astype(str).str.strip() == "Ticker"][0]
    X = raw.iloc[h + 1:, :4]; X.columns = ["name", "ticker", "cusip", "sedol"]
    X = X[X.ticker.notna() & X.cusip.notna() & (X.ticker.astype(str).str.strip() != "-")]
    X = X[~X.name.astype(str).str.contains("CASH|FUTURE|US DOLLAR", case=False, regex=True)]
    return asof, {str(c).strip(): norm(t) for t, c in zip(X.ticker, X.cusip)}


def main():
    D.mkdir(parents=True, exist_ok=True)
    rem = D / "removed.csv"; last = D / "spy_last.csv"
    rows = []
    if rem.exists():
        with open(rem, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    else:                                                     # 처음: 공개 이력 최근 200일로 채운다
        cut = (dt.date.today() - dt.timedelta(days=200)).strftime("%Y%m%d")
        with open(D / "ticker_start_end.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                e = (r.get("end_date") or "").replace("-", "")
                if e >= cut:
                    rows.append(dict(ticker=norm(r["ticker"]), date=e, src="fja05680"))
        print("처음 실행 — 공개 이력 최근 200일 편출 %d건으로 채움" % len(rows))
    try:
        asof, cur = fetch()
    except Exception as e:
        print("SPY 목록 실패 — 기존 편출 목록을 지킨다: %r" % e)
        cur = None
    if cur:
        if last.exists():
            with open(last, encoding="utf-8") as fh:
                prev = {r["cusip"]: r["ticker"] for r in csv.DictReader(fh)}
            pasof = (last.read_text(encoding="utf-8").splitlines() or [""])[0]
            gone = [(c, t) for c, t in prev.items() if c not in cur]
            have = {(r["ticker"], r["date"]) for r in rows}
            for c, t in gone:
                if (t, asof) not in have:
                    rows.append(dict(ticker=t, date=asof, src="spy"))
            renamed = [(prev[c], cur[c]) for c in prev if c in cur and prev[c] != cur[c]]
            print("SPY %s · %d종목 · 편출 %d건 %s · 티커만 바뀜 %d건 %s" % (asof, len(cur), len(gone), [t for _, t in gone], len(renamed), renamed[:5]))
        else:
            print("SPY %s · %d종목 · 직전 목록 없음(첫날) — 내일부터 비교" % (asof, len(cur)))
        with open(last, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh); w.writerow(["cusip", "ticker"]); w.writerows(sorted(cur.items()))
    cut = (dt.date.today() - dt.timedelta(days=400)).strftime("%Y%m%d")
    rows = sorted({(r["ticker"], r["date"]): r for r in rows if r["date"] >= cut}.values(), key=lambda r: (r["date"], r["ticker"]))
    with open(rem, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "date", "src"]); w.writeheader(); w.writerows(rows)
    print("편출 목록 %d건 → %s" % (len(rows), rem.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
