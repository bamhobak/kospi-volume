# -*- coding: utf-8 -*-
"""규칙 공장 공용 — 경로·로그·텔레그램·토스 호출·장 달력 (2026-10-08 사용자 "규칙 공장 깔때기 … 해줘").

공장 전체 그림(research/factory/run.py 가 시간대별로 부른다):
  07:50 morning  미장 밤사이 → 국장 아침 전이표(transfer) → 장전 동시호가 녹화(auction, 08:00~09:00)
  15:18 close    마감 동시호가 녹화(15:19~15:31)
  16:45 evening  전 종목 일봉(live) → 정답지 역추적(answer) → 그림자 전진 성적(fshadow) → 텔레그램
  01:30 night    AI 수집 일꾼(harvest) → 정답지 후보 → 규칙 진화기(evolve) → 깔때기(lab · 뒤집기 짝) → 보고서·텔레그램
기록은 전부 data/factory/(깃에 안 올림), 보고서는 research/reports/factory/.
"""
import io, json, os, sys, time, datetime as dt
from pathlib import Path

for _n in ("stdout", "stderr"):                     # 예약작업 pythonw 는 stdout 이 None — 첫 줄 즉사 방지(2026-09-21 사고)
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
BASE = RESEARCH.parent
for p in (str(HERE), str(RESEARCH), str(BASE)):
    if p not in sys.path: sys.path.insert(1, p)

DATA = BASE / "data" / "factory"; DATA.mkdir(parents=True, exist_ok=True)
REP = RESEARCH / "reports" / "factory"; REP.mkdir(parents=True, exist_ok=True)
CACHE = RESEARCH / "cache"; CACHE.mkdir(exist_ok=True)
LOG = DATA / "run.log"
KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST)


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    try: print(s, flush=True)
    except Exception: pass


def env():
    e = {}
    for f in (BASE / ".env", BASE.parent / ".claude_api.env"):     # 클로드 API 키는 G:\vscode\.claude_api.env(공용·깃 밖)
        if f.exists():
            for ln in f.read_text(encoding="utf-8").splitlines():
                if "=" in ln and not ln.strip().startswith("#"):
                    k, v = ln.split("=", 1); e.setdefault(k.strip(), v.strip())
    return e


def tg(text):
    """텔레그램 — autotrade.tg_send(다시 하기·못 보낸 건 쌓아 두기)를 같이 쓴다. 4,000자 넘으면 자른다."""
    try:
        import autotrade as AT
        e = env()
        for i in range(0, len(text), 3800):
            AT.tg_send(e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID"), text[i:i + 3800])
    except Exception as ex:
        log("텔레그램 실패:", repr(ex)[:200])


def jload(p, default=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return default


def jsave(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)


# ── 토스 시세 호출 — collect_m1.get(속도 조절·재시도·토큰 공용)을 쓰되 속도는 공장 몫으로 낮춘다 ──
_M = None


def toss(rate=7.0):
    """collect_m1 모듈을 돌려준다. rate = 이 프로세스의 초당 호출 상한(토스 한도 20/초를 다른 작업과 나눠 쓴다)."""
    global _M
    if _M is None:
        import collect_m1 as M
        _M = M
    _M.GAP = 1.0 / rate
    return _M


class Busy:
    """1분봉 과거 채우기를 쉬게 하는 표시 — data/m1/.busy_<이름>. day_alert 의 .busy 와 따로 둬서 서로 지우지 않는다."""
    def __init__(self, name):
        self.p = BASE / "data" / "m1" / (".busy_" + name)

    def __enter__(self):
        try: self.p.write_text(str(os.getpid()))
        except Exception: pass
        return self

    def __exit__(self, *a):
        try: self.p.unlink()
        except Exception: pass


def kr_session():
    """오늘 국장 (날짜, 직전 거래일) — 휴장이면 (None, None)."""
    M = toss()
    cal = M.get("/api/v1/market-calendar/KR") or {}
    it = (cal.get("today") or {}).get("integrated")
    if not it: return None, None
    return cal["today"]["date"].replace("-", ""), cal["previousBusinessDay"]["date"].replace("-", "")


def sleep_until(t):
    w = (t - now()).total_seconds()
    if w > 0: time.sleep(w)


def at(h, m, s=0):
    return now().replace(hour=h, minute=m, second=s, microsecond=0)
