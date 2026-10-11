# -*- coding: utf-8 -*-
"""수집 속도 자동 조절 (2026-10-10 사용자: "유튜브 막히면 안 되니 속도 조절 · 레딧이나 다른 사이트도 낌새 보이면 그다음부터 알아서 조정").

사이트(host)마다 요청 간격(gap 초)을 따로 들고 있다 — data/factory/pace.json 에 남겨 다음 밤에도 이어 쓴다.
  막힌 낌새(429 · 403 · 'Just a moment' · captcha · unusual traffic · Sign in to confirm)  → 그 사이트 간격 2배(최대 120초)
  같은 밤에 3번 걸리면 → 그 사이트는 12시간 쉰다(blocked_until) — 무리하게 계속 두드리지 않는다
  막힘 없이 5번 성공할 때마다 → 간격을 20% 줄인다(기본값 아래로는 안 내려감 · 10-12 전엔 20번마다 10%)
기록은 data/factory/pace_log.jsonl(날짜·사이트·사건) — 후보 페이지 '수집 기록'과 점검기가 본다.
"""
import json, time, threading
import common as C

STATE = C.DATA / "pace.json"
LOG = C.DATA / "pace_log.jsonl"
DEFAULT = {"youtube": 8.0, "youtube_search": 4.0, "reddit": 5.0, "naver": 2.0, "tradingview": 3.0, "quantocracy": 2.0,
           "note": 3.0, "board": 2.0, "web": 2.0,
           "quantconnect": 3.0, "elitetrader": 3.0, "arxiv": 3.0}          # 10-11 추가 — arXiv 는 요청 간격 3초 권장
MAXGAP, HITS_TO_PAUSE, PAUSE_H = 120.0, 3, 12
SIGNS = ("429", "Too Many Requests", "Just a moment", "captcha", "CAPTCHA", "unusual traffic", "Sign in to confirm", "403", "rate limit", "ratelimit")
_lock = threading.Lock()
_S = None
_last = {}
_hits_run = {}


def _load():
    global _S
    if _S is None:
        _S = C.jload(STATE, {}) or {}
    return _S


def _save():
    C.jsave(STATE, _S)


def host_of(u):
    u = u.lower()
    for k, keys in (("youtube", ("youtube.com", "youtu.be", "googlevideo")), ("reddit", ("reddit.com",)), ("naver", ("naver.com",)),
                    ("tradingview", ("tradingview.com",)), ("quantocracy", ("quantocracy.com",)), ("note", ("note.com",)),
                    ("board", ("clien.net", "ppomppu.co.kr", "dcinside.com")),
                    ("quantconnect", ("quantconnect.com",)), ("elitetrader", ("elitetrader.com",)), ("arxiv", ("arxiv.org",))):
        if any(x in u for x in keys): return k
    # 2026-10-11: 그 밖의 블로그를 'web' 한 칸으로 묶었더니 서로 다른 블로그 3곳의 403 으로 'web' 전체가 12시간 쉬었다 → 도메인마다 따로
    import urllib.parse
    d = urllib.parse.urlparse(u).netloc
    return "web:" + (d[4:] if d.startswith("www.") else d) if d else "web"


def st(h):
    S = _load()
    if h not in S: S[h] = {"gap": DEFAULT.get(h, 2.0), "ok": 0, "until": 0, "hits": 0}
    return S[h]


def blocked(h):
    return st(h)["until"] > time.time()


def wait(h):
    with _lock:
        g = st(h)["gap"]
        t = max(time.time(), _last.get(h, 0) + g)
        _last[h] = t
    w = t - time.time()
    if w > 0: time.sleep(w)


OK_STEP, OK_MULT = 5, 0.8     # 2026-10-12: 20번마다 10% 는 너무 느렸다(유튜브 120초 → 8초에 몇 주, 하룻밤 30개에 1시간) → 5번마다 20%(이틀 밤쯤)


def ok(h):
    with _lock:
        s = st(h); s["ok"] += 1
        if s["ok"] >= OK_STEP:
            s["ok"] = 0; s["gap"] = max(DEFAULT.get(h, 2.0), round(s["gap"] * OK_MULT, 2)); _save()


def is_block(text):
    t = str(text)[:3000]
    return any(x in t for x in SIGNS)


def hit(h, why=""):
    with _lock:
        s = st(h); s["ok"] = 0; s["hits"] = s.get("hits", 0) + 1
        s["gap"] = min(MAXGAP, round(s["gap"] * 2, 2))
        _hits_run[h] = _hits_run.get(h, 0) + 1
        ev = "느리게"
        if _hits_run[h] >= HITS_TO_PAUSE:
            s["until"] = time.time() + PAUSE_H * 3600; ev = "12시간 쉼"
        _save()
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "host": h, "event": ev, "gap": s["gap"], "why": str(why)[:120]}, ensure_ascii=False) + "\n")
    C.log("속도 조절:", h, ev, "간격 %.0f초" % s["gap"], str(why)[:80])


def summary():
    S = _load()
    return {h: {"gap": s["gap"], "base": DEFAULT.get(h, 2.0), "paused": s["until"] > time.time(), "hits": s.get("hits", 0)} for h, s in S.items()}
