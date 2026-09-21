# -*- coding: utf-8 -*-
"""로컬 연구용 수집의 신선도 점검 — 조용히 죽는 것을 막는다 (2026-09-21 신설).

왜 필요한가: `check_fresh.py` 는 **사이트가 쓰는 실전 데이터**를 지킨다(CI 안에서 돈다).
이 PC 에 쌓이는 연구용 보조 데이터(신용잔고·11분할·밸류에이션·공매도·공시·내부자)는
지켜 주는 것이 아무것도 없었다. 그래서 2026-09-06 에 `run_daily_research.py` 가
첫 줄에서 죽기 시작한 뒤 **16일치가 통째로 빠지도록 아무도 몰랐다**.
같은 기간 내부자 쪽은 매일 `exit=0` 을 보고하고 있었다 — 원천이 말라 받을 게 없었을 뿐이다.

무엇을 견주나: 각 저장소의 최신 날짜를 **국내 일봉 CSV(data/YYYY-MM.csv)의 거래일 달력**과
견주어 '몇 거래일 밀렸나' 를 센다. 그 CSV 자체의 신선도는 CI 의 `check_fresh.py` 가 지킨다.

**서로 감시**: `run_daily_research.py`(20:30)와 `run_insider_daily.py`(22:00)가 둘 다
끝에 이걸 부른다. 한쪽이 죽어도 살아 있는 쪽이 그 사실을 본다 — 죽은 쪽의 로그 파일이
낡은 것으로 잡히기 때문이다.

알림: TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID 가 환경(또는 .env)에 있으면 보낸다.
없으면 `data/research_status.json` 에만 적고 종료코드로 알린다.
⚠ 로컬 .env 에는 아직 텔레그램 값이 없다(CI 의 Secrets 에만 있다). 넣어 두면 폰으로 온다.

사용: python research_health.py [--always]   (--always 면 멀쩡해도 보낸다)
종료코드: 0 정상 · 1 밀린 자료 있음
"""
import io, json, os, sqlite3, sys, time
import datetime as dt
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
ALWAYS = "--always" in sys.argv

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OUT = []
def say(m):
    OUT.append(m)
    if sys.stdout is not None:
        print(m, flush=True)


# ── 기준 달력: 국내 일봉 CSV 의 거래일 ──────────────────────────────
def trading_days():
    import csv
    days = set()
    for f in sorted(DATA.glob("20??-??.csv"))[-4:]:
        try:
            with open(f, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    d = r.get("date")
                    if d:
                        days.add(d)
        except Exception:
            continue
    return sorted(days)


def lag(days, value):
    """value(YYYYMMDD) 가 달력의 마지막 거래일보다 몇 거래일 뒤처졌나. 모르면 None."""
    if not days or not value:
        return None
    later = [d for d in days if d > value]
    return len(later)


# ── 점검 대상: (이름, DB, 테이블, 날짜열, 허용 거래일) ─────────────
STORES = [
    ("신용잔고",     "kis/market.db",        "credit",        "date",     3),
    ("공매도",       "kis/market.db",        "short_sale",    "date",     3),
    ("밸류에이션",   "krx_daily.db",         "fundamental",   "date",     3),
    ("공매도잔고",   "krx_daily.db",         "short_balance", "date",     6),   # KRX 가 늦게 낸다
    ("공매도거래량", "krx_daily.db",         "short_volume",  "date",     3),
    ("11분할",       "investor.db",          "flow11",        "date",     3),
    ("토스수급",     "toss.db",              "investor",      "date",     3),
    ("프로그램매매", "toss.db",              "program",       "date",     3),
    ("대차잔고",     "toss.db",              "lending",       "date",     3),
    ("공시",         "dart/disclosures.db",  "disclosure",    "rcept_dt", 2),
    ("내부자",       "dart/insider.db",      "tx",            "rcept_dt", 4),
    # 월초 스냅샷이라 한 달치(~21거래일)는 정상이다. 그 달을 건너뛰면 25 를 넘어 걸린다.
    ("지수편입",     "index_members.db",     "members",       "date",     25),
]

# 매일 돌아야 하는 작업의 흔적(로그 파일 mtime). 시간 단위.
HEARTBEATS = [
    ("연구용 일일 갱신", "daily_research.log", 30),
    ("내부자 일일 작업", "insider_task.log",   30),
]


def telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):                       # .env 에 있으면 그걸 쓴다
        env = BASE / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = token or line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    chat = chat or line.split("=", 1)[1].strip()
    if not (token and chat):
        say("  (텔레그램 미설정 — .env 에 TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID 를 넣으면 폰으로 온다)")
        return False
    try:
        import requests
        r = requests.post("https://api.telegram.org/bot%s/sendMessage" % token,
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
        return r.ok
    except Exception as e:
        say("  텔레그램 실패: %s" % str(e)[:80])
        return False


def main():
    days = trading_days()
    asof = days[-1] if days else None
    say("── 연구용 수집 점검 ── 기준 거래일 %s" % asof)

    bad, status = [], {"checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "asof": asof, "stores": {}}

    for name, db, tb, col, allow in STORES:
        p = DATA / db
        if not p.exists():
            bad.append("%s: DB 없음" % name)
            status["stores"][name] = {"latest": None, "lag": None, "ok": False}
            say("  ✗ %-12s DB 없음 (%s)" % (name, db))
            continue
        try:
            c = sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=60)
            latest = c.execute("SELECT max(%s) FROM %s" % (col, tb)).fetchone()[0]
            c.close()
        except Exception as e:
            bad.append("%s: 읽기 실패" % name)
            status["stores"][name] = {"latest": None, "lag": None, "ok": False}
            say("  ✗ %-12s 읽기 실패 %s" % (name, str(e)[:60]))
            continue
        L = lag(days, latest)
        ok = L is not None and L <= allow
        status["stores"][name] = {"latest": latest, "lag": L, "ok": ok}
        if ok:
            say("  ✓ %-12s %s (%d거래일)" % (name, latest, L or 0))
        else:
            bad.append("%s %s (%s거래일 밀림)" % (name, latest, L))
            say("  ✗ %-12s %s — %s거래일 밀림 (허용 %d)" % (name, latest, L, allow))

    for name, logname, hours in HEARTBEATS:
        p = BASE / logname
        age = (time.time() - p.stat().st_mtime) / 3600 if p.exists() else None
        ok = age is not None and age <= hours
        status.setdefault("tasks", {})[name] = {"age_h": round(age, 1) if age else None, "ok": ok}
        if ok:
            say("  ✓ %-12s %.1f시간 전 실행" % (name, age))
        else:
            bad.append("%s 실행 기록 %s" % (name, ("%.0f시간 전" % age) if age else "없음"))
            say("  ✗ %-12s 실행 기록 %s" % (name, ("%.0f시간 전" % age) if age else "없음"))

    status["ok"] = not bad
    try:
        (DATA / "research_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass

    if bad:
        say("→ 밀린 것 %d건" % len(bad))
        telegram("⚠️ <b>연구용 수집이 밀렸다</b> (기준 %s)\n\n" % asof + "\n".join("· " + b for b in bad)
                 + "\n\n복구: <code>python run_daily_research.py --days 25</code>")
        return 1
    say("→ 전부 최신")
    if ALWAYS:
        telegram("✅ 연구용 수집 정상 (기준 %s)" % asof)
    return 0


if __name__ == "__main__":
    sys.exit(main())
