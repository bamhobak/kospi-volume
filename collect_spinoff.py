# -*- coding: utf-8 -*-
"""미국 분사(스핀오프) 회사 목록 — SEC 10-12B 서류 → data/us/spinoffs.csv (2026-09-29, [분사주] N8 규칙용).

[분사주] = 분사 상장 뒤 한 달쯤 기다렸다 사서 250거래일 보유(research/spinoff*.py · 가설 H0243).
여기서는 '이 티커가 분사주인가' 만 정한다. 며칠째인지(spd)는 collect_us_daily.py 가 시세 행 수로 센다.

  · SEC 전문 검색(efts.sec.gov)에서 지난 15개월 10-12B(정정 포함) 서류 → 회사(CIK)별 **첫 제출일**
  · 티커: 검색 결과 이름 옆 괄호 + SEC 티커 목록(company_tickers.json)으로 보완
  · 백테스트와 같은 조건(첫 제출 후 365일 안에 상장)은 collect_us_daily.py 가 첫 거래일과 견줘 건다
  · 실패해도 기존 CSV 를 지킨다(덮어쓰지 않음) — 분사는 드문 사건이라 하루 늦어도 창(5일) 안이다
⚠ SEC 는 User-Agent 에 연락처를 요구한다 — 사용자 이메일이 아니라 연구용 주소를 쓴다.

    python collect_spinoff.py
"""
import json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "us" / "spinoffs.csv"
UA = {"User-Agent": "bamhobak-research contact@example.com"}


def get(url):
    for att in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode())
        except Exception as e:
            if att == 2:
                raise
            time.sleep(3 * (att + 1))


def main():
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=460)).strftime("%Y-%m-%d")
    ev = {}
    fr = 0
    try:
        while True:
            j = get("https://efts.sec.gov/LATEST/search-index?forms=10-12B&dateRange=custom&startdt=%s&enddt=%s&from=%d" % (start, end, fr))
            hits = j["hits"]["hits"]
            for h in hits:
                s = h["_source"]
                d = s.get("file_date")
                for cik, nm in zip(s.get("ciks") or [], s.get("display_names") or []):
                    c = int(cik)
                    tk = set(re.findall(r"\(([A-Z][A-Z0-9.\-]{0,6})\)", nm))
                    e = ev.setdefault(c, {"first": d, "tickers": set(), "name": nm.split("(")[0].strip()})
                    e["first"] = min(e["first"], d); e["tickers"] |= tk
            fr += len(hits)
            if not hits or fr >= j["hits"]["total"]["value"]:
                break
            time.sleep(0.3)
    except Exception as e:
        print("SEC 전문 검색 실패 — 기존 목록을 지킨다: %r" % e)
        return 0
    try:                                   # 티커 보완 — 상장 직전에야 티커가 붙는 경우가 많다
        tk = get("https://www.sec.gov/files/company_tickers.json")
        for v in tk.values():
            c = int(v["cik_str"])
            if c in ev:
                ev[c]["tickers"].add(str(v["ticker"]).upper())
    except Exception as e:
        print("SEC 티커 목록 실패(보완 없이 진행): %r" % e)
    rows = ["cik,ticker,first10,name"]
    for c, e in sorted(ev.items()):
        for t in sorted(e["tickers"]) or [""]:
            rows.append('%d,%s,%s,"%s"' % (c, t, e["first"].replace("-", ""), e["name"].replace('"', "")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("분사 목록 %d곳 · 티커 있는 곳 %d곳 → %s" % (len(ev), sum(1 for e in ev.values() if e["tickers"]), OUT.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
