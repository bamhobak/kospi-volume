# -*- coding: utf-8 -*-
"""공시 시각 수집 — KIND 상세검색 하루치 전체(2026-11-07 사용자 "응" — 자료 보강 ②).

DART(data/dart/disclosures.db)는 공시 '날짜'만 있다. KIND 는 분 단위 시각이 있고 접수번호(acptno)가 DART rcept_no 와 같다
→ rcept_no 로 붙이면 모든 공시 규칙의 "장중(15:20 전)에 알 수 있었나"를 판정할 수 있다.

  python collect_kind_time.py backfill [시작 YYYYMMDD]   오늘부터 거꾸로 2016-01-01(또는 시작)까지 — 이어받기
  python collect_kind_time.py daily                     어제·오늘 다시(늦은 공시·정정 반영) — run.py night 가 부름
  python collect_kind_time.py stat                      쌓인 양
저장 data/dart/kind_time.db
  kind(acptno PK, dt 'YYYY-MM-DD HH:MM', day, hm, kcode KIND 회사코드, corp, market 유가/코스닥/코넥스/'', title, src 제출인)
  done_day(day PK, n, at)
KRX 쪽이라 저속·순차(1.2초에 1번). 하루 약 600~1,000건 = 6~10쪽.
"""
import sys, re, time, html, sqlite3, datetime as dt, urllib.request, urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "data" / "dart" / "kind_time.db"
LOG = BASE / "data" / "dart" / "kind_time.log"
GAP = 1.2
URL = "https://kind.krx.co.kr/disclosure/details.do"
_last = [0.0]
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def db():
    c = sqlite3.connect(DB, timeout=60)
    c.execute("""CREATE TABLE IF NOT EXISTS kind(acptno TEXT PRIMARY KEY, dt TEXT, day TEXT, hm TEXT, kcode TEXT, corp TEXT,
                 market TEXT, title TEXT, src TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS done_day(day TEXT PRIMARY KEY, n INTEGER, at TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS kind_day ON kind(day)")
    return c


def fetch(d, page):
    """d = 'YYYY-MM-DD' → html. 실패하면 3번까지 쉬었다 다시."""
    q = dict(method="searchDetailsSub", currentPageSize=100, pageIndex=page, orderMode=1, orderStat="D", forward="details_sub",
             reportNm="", repIsuSrtCd="", fromDate=d, toDate=d)
    for k in range(4):
        w = _last[0] + GAP - time.time()
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            rq = urllib.request.Request(URL, data=urllib.parse.urlencode(q).encode(), headers={"User-Agent": "Mozilla/5.0"})
            h = urllib.request.urlopen(rq, timeout=40).read().decode("utf-8", "replace")
            if "페이지 오류" in h or "잠시 후 다시" in h: raise RuntimeError("KIND 오류 페이지")
            return h
        except Exception as ex:
            if k == 3: raise
            log("다시", d, page, repr(ex)[:100]); time.sleep(10 * (k + 1))


TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)


def parse(h):
    out, first = [], None
    for tr in TR.findall(h):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 5: continue
        tm = re.search(r"(20\d\d-\d\d-\d\d) (\d\d:\d\d)", tds[1])
        ac = re.search(r"openDisclsViewer\('(\d{14})'", tds[3])
        if not tm or not ac: continue
        if first is None:
            try: first = int(re.sub(r"\D", "", tds[0]) or 0)
            except Exception: first = 0
        kc = re.search(r"companysummary_open\('([0-9A-Z]+)'", tds[2])
        mk = re.search(r"alt='([^']+)'", tds[2])
        corp = re.search(r"title='([^']*)'", tds[2])
        ti = re.search(r"title='([^']*)'", tds[3])
        out.append((ac.group(1), "%s %s" % tm.groups(), tm.group(1).replace("-", ""), tm.group(2).replace(":", ""),
                    kc.group(1) if kc else "", html.unescape(corp.group(1)).strip() if corp else "",
                    mk.group(1) if mk else "", html.unescape(ti.group(1)).strip() if ti else "",
                    html.unescape(re.sub(r"<[^>]+>", "", tds[4])).strip()))
    return out, first or 0


def one_day(c, day):
    """day YYYYMMDD 하루치 전부 → 건수."""
    d = "%s-%s-%s" % (day[:4], day[4:6], day[6:])
    rows, total = parse(fetch(d, 1))
    pages = max(1, -(-total // 100))
    for p in range(2, pages + 1):
        r, _ = parse(fetch(d, p)); rows += r
    rows = [r for r in rows if r[2] == day]      # 혹시 섞인 다른 날
    c.executemany("INSERT OR REPLACE INTO kind VALUES (?,?,?,?,?,?,?,?,?)", rows)
    c.execute("INSERT OR REPLACE INTO done_day VALUES (?,?,?)", (day, len(rows), time.strftime("%Y-%m-%d %H:%M:%S")))
    c.commit()
    if total and len({r[0] for r in rows}) < total * 0.98:
        log("모자람", day, "받은 %d / 목록 %d" % (len(rows), total))
    return len(rows)


def days_back(start, end):
    d = dt.date(int(start[:4]), int(start[4:6]), int(start[6:]))
    e = dt.date(int(end[:4]), int(end[4:6]), int(end[6:]))
    while d >= e:
        yield d.strftime("%Y%m%d"); d -= dt.timedelta(days=1)


def backfill(stop="20160101"):
    c = db()
    done = {r[0] for r in c.execute("SELECT day FROM done_day")}
    today = dt.date.today().strftime("%Y%m%d")
    todo = [d for d in days_back(today, stop) if d not in done or d >= (dt.date.today() - dt.timedelta(days=2)).strftime("%Y%m%d")]
    log("밀린 날", len(todo), todo[:1], todo[-1:])
    t0, n = time.time(), 0
    for i, day in enumerate(todo):
        try: n += one_day(c, day)
        except Exception as ex:
            log("실패", day, repr(ex)[:150]); time.sleep(60); continue
        if i % 20 == 0:
            log("%s 까지 %d/%d일 · %d건 · %.0f분" % (day, i + 1, len(todo), n, (time.time() - t0) / 60))
    log("끝 — %d일 %d건 %.0f분" % (len(todo), n, (time.time() - t0) / 60))


def daily():
    c = db()
    for k in (1, 0):
        day = (dt.date.today() - dt.timedelta(days=k)).strftime("%Y%m%d")
        try: log("매일", day, one_day(c, day), "건")
        except Exception as ex: log("매일 실패", day, repr(ex)[:150])


def stat():
    c = db()
    n, a, b = c.execute("SELECT count(*), min(day), max(day) FROM kind").fetchone()
    nd = c.execute("SELECT count(*) FROM done_day").fetchone()[0]
    print("공시 %d건 · %s~%s · 받은 날 %d" % (n, a, b, nd))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stat"
    try:
        if cmd == "backfill": backfill(sys.argv[2] if len(sys.argv) > 2 else "20160101")
        elif cmd == "daily": daily()
        else: stat()
    except Exception:
        import traceback; log("오류", traceback.format_exc()[-600:])
