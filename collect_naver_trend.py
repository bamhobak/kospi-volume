# -*- coding: utf-8 -*-
"""네이버 데이터랩 **검색어 트렌드** — 종목명 일별 검색량(상대값) 수집 → data/naver_trend.db (2026-09-29).

용도: '관심 없는 매집' 가설(외인·기관은 사는데 대중은 모르는 종목) — 검색량을 자기 과거 대비로만 쓴다.
API: NAVER API HUB(네이버 클라우드) POST https://naverapihub.apigw.ntruss.com/search-trend/v1/search
     헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY (.env NAVER_HUB_CLIENT_ID / NAVER_HUB_CLIENT_SECRET)
     한 번 호출 = 한 종목 2016-01-01~어제 일별 전체(값은 그 기간 최대 = 100 인 상대값).

⚠ **월 3만 건이 기본 무료**(3만~5만은 한시적 무료) — 사용자 지시로 **월 2만 5천 건에서 멈춘다**(data/naver_trend_quota.json).
   멈추면 텔레그램으로 알린다. 종목끼리 값이 섞이지 않게 **한 호출에 한 종목**만 넣는다.
종목: 2016년 이후 거래된 국내 보통주(코스피·코스닥·상장폐지 DB) · 우선주·스팩 제외.
      이름을 바꾼 회사는 그 기간에 쓴 이름을 전부 한 묶음 키워드로 넣는다(최대 20개, 합산 검색량).

    python collect_naver_trend.py            # 안 받은 종목만
    python collect_naver_trend.py --refresh  # 전 종목 다시(월 갱신)
    python collect_naver_trend.py --limit 50
"""
import json, os, sqlite3, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                     # pythonw 예약작업에선 stdout 이 None
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "naver_trend.db"
QUOTA = BASE / "data" / "naver_trend_quota.json"
URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
MONTH_CAP = 25000
START = "2016-01-01"


def env():
    e = dict(os.environ)
    p = BASE / ".env"
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1); e.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return e


E = env()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def telegram(msg):
    t, c = E.get("TELEGRAM_BOT_TOKEN"), E.get("TELEGRAM_CHAT_ID")
    if not (t and c):
        return
    try:
        d = json.dumps({"chat_id": c, "text": msg}).encode()
        urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % t, data=d,
                                                      headers={"Content-Type": "application/json"}), timeout=15)
    except Exception:
        pass


def quota():
    m = datetime.now().strftime("%Y-%m")
    q = json.loads(QUOTA.read_text(encoding="utf-8")) if QUOTA.exists() else {}
    return m, q


def bump(n=1):
    m, q = quota(); q[m] = q.get(m, 0) + n
    QUOTA.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
    return q[m]


def targets():
    """2016년 이후 거래된 보통주 → {ticker: [이름들]}"""
    names = {}
    for db in ("kospi.db", "kosdaq.db", "delisted.db", "delisted_kd.db"):
        p = BASE / "data" / db
        if not p.exists():
            continue
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        for t, n in c.execute("SELECT DISTINCT ticker, name FROM daily WHERE date >= '20160101'"):
            if not t or not n or not str(t).endswith("0") or "스팩" in n or "기업인수목적" in n:
                continue
            names.setdefault(t, set()).add(n.strip())
        c.close()
    return {t: sorted(v)[:20] for t, v in names.items()}


def fetch(kw, end):
    body = {"startDate": START, "endDate": end, "timeUnit": "date",
            "keywordGroups": [{"groupName": kw[0][:50], "keywords": kw}]}
    req = urllib.request.Request(URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"X-NCP-APIGW-API-KEY-ID": E["NAVER_HUB_CLIENT_ID"],
                                          "X-NCP-APIGW-API-KEY": E["NAVER_HUB_CLIENT_SECRET"],
                                          "Content-Type": "application/json"})
    for att in range(4):
        try:
            j = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
            return j["results"][0]["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log("  429 한도 — 60초 쉰다"); time.sleep(60); continue
            if e.code in (500, 502, 503, 504):
                time.sleep(5 * (att + 1)); continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (att + 1))
    raise RuntimeError("4번 실패")


def main():
    refresh = "--refresh" in sys.argv
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    c = sqlite3.connect(DB, timeout=60)
    c.execute("CREATE TABLE IF NOT EXISTS trend(ticker TEXT, date TEXT, ratio REAL, PRIMARY KEY(ticker, date))")
    c.execute("CREATE TABLE IF NOT EXISTS meta(ticker TEXT PRIMARY KEY, keywords TEXT, fetched TEXT, n INTEGER)")
    done = {t for (t,) in c.execute("SELECT ticker FROM meta")}
    T = targets()
    todo = [t for t in sorted(T) if refresh or t not in done]
    if lim:
        todo = todo[:lim]
    end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    m, q = quota()
    log("대상 %d종목(전체 %d) · 이번 달 사용 %d건 / 한도 %d" % (len(todo), len(T), q.get(m, 0), MONTH_CAP))
    ok = fail = 0
    for i, t in enumerate(todo, 1):
        m, q = quota()
        if q.get(m, 0) >= MONTH_CAP:
            msg = "[검색량 수집] 이번 달 %d건 도달 — 멈춤(남은 %d종목은 다음 달)" % (q[m], len(todo) - i + 1)
            log(msg); telegram(msg); break
        try:
            d = fetch(T[t], end); bump()
        except Exception as e:
            bump(); fail += 1; log("  %s %s 실패: %r" % (t, T[t][0], e)); continue
        c.execute("DELETE FROM trend WHERE ticker=?", (t,))
        c.executemany("INSERT INTO trend VALUES (?,?,?)", [(t, x["period"].replace("-", ""), float(x["ratio"])) for x in d])
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?)", (t, json.dumps(T[t], ensure_ascii=False),
                                                                 datetime.now().strftime("%Y-%m-%d %H:%M"), len(d)))
        ok += 1
        if i % 100 == 0:
            c.commit(); log("  %d/%d · 성공 %d · 실패 %d · 이번 달 %d건" % (i, len(todo), ok, fail, quota()[1].get(quota()[0], 0)))
        time.sleep(0.4)
    c.commit(); c.close()
    log("끝 · 성공 %d · 실패 %d · 이번 달 사용 %d건" % (ok, fail, quota()[1].get(quota()[0], 0)))


if __name__ == "__main__":
    main()
