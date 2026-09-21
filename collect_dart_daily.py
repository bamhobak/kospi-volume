# -*- coding: utf-8 -*-
"""DART 공시 **일일 증분** 수집 — 접수일 구간으로 한 번에 받는다 (2026-09-21 신설).

왜 새로 만들었나: 기존 `collect_dart.py` 는 **종목 단위 `done`** 이라 한 번 받은 종목은
기간을 바꿔 다시 돌려도 통째로 건너뛴다 — 새 공시가 들어올 길이 없다.
그래서 `disclosures.db` 가 2026-08-28 에서 멈췄고, 그걸 원천으로 삼는
`collect_insider.py` 는 파싱할 새 공시가 없어 09-04 에 말라붙었다.
매일 22시 예약 작업(`run_insider_daily.py`)은 그동안 `exit=0` 을 보고했다 —
받을 게 없으니 진짜로 정상 종료였다. **조용한 실패의 전형이다.**

이 수집기는 종목을 돌지 않는다. OpenDART `list.json` 은 회사 지정 없이
**접수일 구간**으로 전체 공시를 준다(하루 ~700건 · 8페이지). 17일치라도 140콜이면 끝난다.

무엇을 담는가: `corp_cls` 가 Y(유가증권)·K(코스닥) 이고 종목코드가 있는 공시만.
⚠ 상장사 판별에 `corp_code.json` 을 **쓰지 않는다**. 그 파일은 2026-08-30 에 뜬 스냅샷이라
그 뒤 상장한 회사(해치텍·한화머시너리앤서비스홀딩스 등)의 공시를 통째로 놓친다
(2026-08-28 하루만 재보아도 19건이 빠졌다). `corp_cls` 는 DART 가 매 응답에 실어 주므로
신규 상장사가 저절로 들어온다.

검증: 2026-08-28 을 이 방식으로 다시 받아 기존 DB 와 맞춰 보았다 —
`corp_code.json` 필터로는 700건 대 기존 701건으로 일치했고, `corp_cls` 필터는 719건으로
그 차이가 전부 위의 신규 상장사였다.

재개: 날짜 단위 `done_day`. 기존 종목 단위 `done` 과 섞이지 않는다.

사용:
    python collect_dart_daily.py                 # DB 최신 접수일 전날 ~ 오늘 (그 구간은 다시 받는다)
    python collect_dart_daily.py --days 7        # 최근 7일을 done 무시하고 다시 (정정분 반영)
    python collect_dart_daily.py --from 20260829 --to 20260921
"""
import io, os, sqlite3, sys, time, logging
import datetime as dt
from pathlib import Path
import requests

BASE = Path(__file__).parent
OUT = BASE / "data" / "dart"; OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "disclosures.db"

# 작업 스케줄러가 pythonw.exe 로 띄우면 콘솔 핸들이 없어 sys.stdout/stderr 가 None 이다.
# 그 상태로 StreamHandler 를 붙이면 로그 한 줄마다 터진다 — 있을 때만 붙인다.
_handlers = [logging.FileHandler(BASE / "dart_daily.log", encoding="utf-8")]
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    _handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=_handlers)
log = logging.getLogger()

arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
URL = "https://opendart.fss.or.kr/api/list.json"
GAP = float(arg("--gap", "0.2"))          # 콜 간격(초). DART 는 일 20,000콜.
KEEP = {"Y", "K"}                          # 유가증권 · 코스닥


def api_key():
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DART_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(".env 에 DART_API_KEY 가 없다")


def setup():
    c = sqlite3.connect(DB, timeout=600)
    c.execute("""CREATE TABLE IF NOT EXISTS disclosure(
        rcept_no TEXT PRIMARY KEY, corp_code TEXT, stock_code TEXT, corp_name TEXT,
        rcept_dt TEXT, report_nm TEXT, flr_nm TEXT, rm TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_disc_stock ON disclosure(stock_code, rcept_dt)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_disc_dt ON disclosure(rcept_dt)")
    # 날짜 단위 재개키. 기존 종목 단위 done 과 이름을 갈라 둔다.
    c.execute("CREATE TABLE IF NOT EXISTS done_day(date TEXT PRIMARY KEY, n INTEGER, at TEXT)")
    c.commit()
    return c


def fetch_day(key, day):
    """하루치 상장사 공시를 전부 받아 행 리스트로. 실패하면 예외를 올린다(그 날은 done 에 안 적는다)."""
    rows, page, total_page = [], 1, 1
    while page <= total_page:
        for attempt in range(3):
            try:
                r = requests.get(URL, params={"crtfc_key": key, "bgn_de": day, "end_de": day,
                                              "page_no": page, "page_count": 100}, timeout=40)
                j = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                log.warning("  %s p%d 재시도(%s)", day, page, str(e)[:60])
                time.sleep(2 + attempt * 3)

        st = j.get("status")
        if st == "013":                 # 조회된 데이터 없음 — 휴일이거나 접수 0건
            return []
        if st == "020":
            raise SystemExit("DART 일일 사용한도 초과 — 내일 이어서 받는다")
        if st != "000":
            raise RuntimeError("DART status=%s %s" % (st, j.get("message")))

        total_page = j.get("total_page") or 1
        for x in j.get("list") or []:
            sc = (x.get("stock_code") or "").strip()
            if not sc or x.get("corp_cls") not in KEEP:
                continue
            rows.append((x["rcept_no"], x.get("corp_code"), sc, x.get("corp_name"),
                         x.get("rcept_dt"), x.get("report_nm"), x.get("flr_nm"), x.get("rm")))
        page += 1
        time.sleep(GAP)
    return rows


def main():
    key = api_key()
    con = setup()
    today = time.strftime("%Y%m%d")

    days_back = arg("--days")
    frm, to = arg("--from"), arg("--to", today)
    if days_back:                       # 최근 N일 재수집(정정분 반영) — done 을 무시한다
        frm = (dt.date.today() - dt.timedelta(days=int(days_back) - 1)).strftime("%Y%m%d")
        force = True
    else:
        force = False
        if not frm:
            # 기본: DB 의 최신 접수일 **전날부터** 다시 받는다(그 이틀은 done 을 무시한다).
            # 예전엔 '최신 접수일 다음날부터' 였는데, 그러면 저녁에 한 번 받은 날은 그 뒤에
            # 들어온 공시를 영영 못 받는다 — 2026-09-21 19:37 에 받고 22:00 실행은
            # "받을 새 날짜가 없다" 로 끝났다. 내부자 신고는 장 마감 뒤에 몰린다.
            last = con.execute("SELECT max(rcept_dt) FROM disclosure").fetchone()[0]
            if not last:
                raise SystemExit("빈 DB 다 — --from 으로 시작일을 정해 줄 것")
            frm = (dt.datetime.strptime(last, "%Y%m%d").date() - dt.timedelta(days=1)).strftime("%Y%m%d")
            force = True                # 이 구간은 며칠 안 되므로 전부 다시 받아도 싸다

    if frm > to:
        log.info("받을 새 날짜가 없다 (최신 %s)", to)
        return 0

    done = {r[0] for r in con.execute("SELECT date FROM done_day")}
    d0 = dt.datetime.strptime(frm, "%Y%m%d").date()
    d1 = dt.datetime.strptime(to, "%Y%m%d").date()
    days = [(d0 + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range((d1 - d0).days + 1)]
    todo = [d for d in days if force or d not in done]
    log.info("DART 공시 일일 수집: %s~%s · 대상 %d일%s", frm, to, len(todo), " (재수집)" if force else "")

    t0, total = time.time(), 0
    for i, day in enumerate(todo, 1):
        rows = fetch_day(key, day)
        con.executemany("INSERT OR REPLACE INTO disclosure VALUES(?,?,?,?,?,?,?,?)", rows)
        con.execute("INSERT OR REPLACE INTO done_day VALUES(?,?,?)",
                    (day, len(rows), time.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        total += len(rows)
        log.info("  [%d/%d] %s %d건 (누적 %d · %.1f분)", i, len(todo), day, len(rows),
                 total, (time.time() - t0) / 60)

    n, a, b = con.execute("SELECT count(*), min(rcept_dt), max(rcept_dt) FROM disclosure").fetchone()
    log.info("완료: disclosure %s행 · %s~%s (이번에 %d건)", format(n, ","), a, b, total)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
