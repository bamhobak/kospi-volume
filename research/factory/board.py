# -*- coding: utf-8 -*-
"""사이트 '규칙 후보' 페이지 데이터 (2026-10-10 사용자: "새 페이지 하나 만들어서 규칙 후보군 한 번에 볼 수 있게, 언제든 볼 수 있게").

검토 대기·채택 명세의 카드 숫자(card.data) + 형제 묶음 + 못 옮긴 조건 모음 + 공장 현황 → Supabase 상태 '__factory__'.
사이트 assets/factory.html 이 읽는다(데이 후보 '__day__' 와 같은 방식). 밤 작업 끝·채택/조정 뒤에 부른다.
    python research/factory/run.py board
"""
import re, time, json
import common as C


def supa_set(pin, data):
    import requests
    js = (C.BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    H = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(f"{url}/rest/v1/rpc/kospi_state_set", headers=H, json={"p_pin": pin, "p_data": data}, timeout=60)
    r.raise_for_status()


SRC_INFO = [   # 어디서 · 어떻게 (페이지 '수집 기록' 맨 아래 설명)
    ("유튜브(한국어)", "검색어 16개(단타·종가베팅·시초가·스윙·눌림목 등) 최신순 → 한국어 자동 자막", "yt-dlp · 영상 3~60분만"),
    ("유튜브(영어·일본어·중국어)", "영어 8 · 일본어 3 · 대만 중국어 2 검색어 → 영상 원래 언어 자막", "yt-dlp"),
    ("네이버 블로그", "검색어 6개 · 최근 1주 최신순 → 글 본문(스마트에디터 문단)", "웹 검색(크롬 지문)"),
    ("게시판", "뽐뿌 증권포럼·디시 실전주식투자 제목 검색(매매법·기법·종가베팅·스윙·단타) + 클리앙 주식한당 첫 쪽 → 제목에 기법 말 있는 글만", "웹"),
    ("트레이딩뷰(영어)", "최근 올라온 전략 스크립트 12개 → 작성자 설명(원리·진입·청산)", "웹"),
    ("Quantocracy(영어)", "미국 퀀트 블로그 모음 RSS 최근 3일 → 실린 원래 블로그 글", "RSS + 웹"),
    ("note.com(일본어)", "'日本株 デイトレ 手法'·'株 スイングトレード 手法' 검색 → 무료 부분", "웹"),
    ("레딧(영어)", "r/Daytrading·swingtrading·algotrading·StockMarket 주간 인기 · 본문 400자↑ · 점수 5↑", "로그인 쿠키(.env.reddit · 2027-04 만료)"),
]


def collect_stats(days=14):
    import collections
    f = C.DATA / "harvest_stats.jsonl"
    if not f.exists(): return []
    cut = time.strftime("%Y%m%d", time.localtime(time.time() - days * 86400))
    agg = collections.defaultdict(lambda: collections.Counter())
    for l in f.read_text(encoding="utf-8").splitlines():
        if not l.strip(): continue
        x = json.loads(l)
        if x["date"] < cut: continue
        agg[(x["date"], x["src"])].update({k: x.get(k, 0) for k in ("found", "tried", "ok", "err", "blocked", "short", "passed", "xl", "specs")})
    return [dict(date=d, src=s, **dict(c)) for (d, s), c in sorted(agg.items())]


def build():
    import lab, card, needs, harvest
    from verdict import trial_count
    L = lab.load()
    act = [x for x in L if x.get("status") in ("review", "adopted")]
    cands = []
    for x in act:
        d = card.data(x, L)
        card.make(x, d)
        cands.append(d)
    order = {"adopted": 0, "review": 1}
    cands.sort(key=lambda d: (order.get(d["status"], 9), -((d["res"].get("va") or {}).get("mean") or 0)))
    by = {}
    for x in L: by[x.get("status")] = by.get(x.get("status"), 0) + 1
    return {"updated": time.strftime("%Y-%m-%d %H:%M"), "cands": cands,
            "counts": by, "trials": trial_count("factory"), "usage": harvest.usage_report()[0],
            "needs": needs.rows(), "shadow": [{"id": x["id"], "desc": x.get("desc"), "fwd": x.get("fwd") or {}} for x in L if x.get("status") in ("shadow", "propose")],
            "collect": {"methods": [{"name": a, "how": b, "via": c} for a, b, c in SRC_INFO], "stats": collect_stats(), "pace": _pace()}}


def _pace():
    try:
        import pace
        P = pace.summary()
        ev = []
        if pace.LOG.exists():
            ev = [json.loads(l) for l in pace.LOG.read_text(encoding="utf-8").splitlines()[-15:] if l.strip()]
        return {"hosts": P, "events": ev}
    except Exception:
        return {}


def publish():
    D = build()
    supa_set("__factory__", D)
    C.jsave(C.DATA / "board.json", D)
    C.log("후보 페이지 갱신: 후보 %d" % len(D["cands"]))
    return D
