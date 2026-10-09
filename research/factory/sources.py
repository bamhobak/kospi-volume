# -*- coding: utf-8 -*-
"""웹 수집처 (2026-10-10 사용자: "유튜브에서만 가져오지 말고 다양한 커뮤니티 웹페이지도").

실측(10-10): 열리는 곳 = 네이버 블로그 검색(검색어당 최근 1주 글 ~30개) · 클리앙 주식한당 · 뽐뿌 증권포럼 · 디시 실전주식투자 마이너갤
            막힌 곳 = 레딧(403) · 다음/티스토리 검색(스크립트로만 그림) · 디시 주식갤(정치 잡담)
  네이버는 TLS 지문으로 막으므로 curl_cffi(크롬 흉내) 필수([[naver-tls-fingerprint]]). 요청 사이 1초 쉰다.
  게시판은 잡담이 대부분 → 제목에 기법 말(KEYS)이 있는 글만 연다.
반환: dict(key, src, title, url, text) — key 는 본 목록(harvest_seen) 중복 막기용.
"""
import html, re, time, urllib.parse

import common as C

KEYS = re.compile(r"매매법|기법|매매 ?전략|단타|스윙|종가 ?베팅|종가 ?배팅|시초가|눌림|돌파|승률|매수 ?타점|매수 ?조건|상한가 ?따라|스캘핑|데이 ?트레이딩|추세 ?추종|역추세|패턴")


def _get(u, **kw):
    from curl_cffi import requests as cr
    time.sleep(1.0)
    r = cr.get(u, impersonate="chrome", timeout=25, **kw)
    r.raise_for_status()
    return r.text


def clean(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def naver_blog(query, n=30):
    """네이버 블로그 검색(최근 1주·최신순) → 글 본문(스마트에디터 문단)."""
    u = "https://search.naver.com/search.naver?ssc=tab.blog.all&query=%s&sm=tab_opt&nso=so%%3Add%%2Cp%%3A1w" % urllib.parse.quote(query)
    t = _get(u)
    links = list(dict.fromkeys(re.findall(r"https?://blog\.naver\.com/([A-Za-z0-9_-]+)/(\d{9,})", t)))[:n]
    out = []
    for b, no in links:
        out.append(dict(key="nb:%s/%s" % (b, no), src="네이버 블로그", url="https://blog.naver.com/%s/%s" % (b, no), title=None, text=None,
                        _fetch=lambda b=b, no=no: naver_post(b, no)))
    return out


def naver_post(b, no):
    t = _get("https://blog.naver.com/PostView.naver?blogId=%s&logNo=%s" % (b, no))
    ti = re.search(r'<meta property="og:title" content="([^"]*)"', t)
    ps = re.findall(r'<p class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>', t, re.S)
    body = clean(" ".join(ps)) if ps else clean((re.search(r'id="postViewArea"(.*?)</div>', t, re.S) or [None, ""])[1] if re.search(r'id="postViewArea"', t) else "")
    return (html.unescape(ti.group(1)) if ti else ""), body


BOARDS = {
    "클리앙 주식한당": ("https://www.clien.net/service/board/cm_stock", r'href="(/service/board/cm_stock/\d+)[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,90})',
                    "https://www.clien.net%s", r'<div class="post_article[^"]*">(.*?)<div class="post_(?:ccls|tag|button)'),
    "뽐뿌 증권포럼": ("https://www.ppomppu.co.kr/zboard/zboard.php?id=stock", r'href="(view\.php\?id=stock[^"]*?no=\d+)[^"]*"[^>]*>(?:<[^>]+>)*\s*([^<]{3,90})',
                  "https://www.ppomppu.co.kr/zboard/%s", r"<td class='board-contents'[^>]*>(.*?)</td>"),
    "디시 실전주식투자": ("https://gall.dcinside.com/mgallery/board/lists/?id=jusik&exception_mode=recommend",
                   r'href="(/mgallery/board/view/\?id=jusik&(?:amp;)?no=\d+)[^"]*"[^>]*>\s*(?:<em[^>]*></em>)?\s*([^<]{3,90})',
                   "https://gall.dcinside.com%s", r'<div class="write_div"[^>]*>(.*?)</div>'),
}


SEARCH = {   # 제목 검색(잡담 많은 게시판에서 기법 글만) — 클리앙은 검색 주소가 안 먹어 첫 쪽만
    "뽐뿌 증권포럼": lambda kw: "https://www.ppomppu.co.kr/zboard/zboard.php?id=stock&search_type=subject&keyword=%s" % urllib.parse.quote(kw.encode("euc-kr")),
    "디시 실전주식투자": lambda kw: "https://gall.dcinside.com/mgallery/board/lists/?id=jusik&s_type=search_subject_memo&s_keyword=%s" % urllib.parse.quote(kw),
}
SEARCH_KW = ["매매법", "기법", "종가베팅", "스윙", "단타"]


def boards():
    out = []
    seen = set()
    for name, (lst, pat, view, body) in BOARDS.items():
        pages = [lst] + ([SEARCH[name](k) for k in SEARCH_KW] if name in SEARCH else [])
        t = ""
        for u in pages:
            try: t += _get(u)
            except Exception as ex: C.log("게시판 실패", name, str(ex)[:100])
        for path, title in re.findall(pat, t):
            path = html.unescape(path); title = clean(title)
            nums = re.findall(r"no=(\d+)|/(\d{5,})", path)
            no = "".join(nums[-1]) if nums else path
            if (name, no) in seen or not KEYS.search(title): continue
            seen.add((name, no))
            out.append(dict(key="%s:%s" % (name, no), src=name, url=view % path, title=title, text=None,
                            _fetch=lambda u=view % path, body=body, title=title: (title, _post(u, body))))
    return out


def _post(u, body):
    m = re.search(body, _get(u), re.S)
    return clean(m.group(1)) if m else ""


# ── 해외 (2026-10-10 사용자: "해외 커뮤에서도") — 레딧은 로그인 벽(403/HTML)·Medium·SSRN 은 Cloudflare 로 막힘 ──
def article(u):
    """일반 블로그 글 본문 — <article> 우선, 없으면 <p> 를 모은다."""
    t = _get(u)
    ti = re.search(r'<meta property="og:title" content="([^"]*)"', t) or re.search(r"<title[^>]*>([^<]*)", t)
    a = re.search(r"<article.*?</article>", t, re.S)
    body = clean(a.group(0)) if a else clean(" ".join(re.findall(r"<p[^>]*>(.*?)</p>", t, re.S)))
    return (html.unescape(ti.group(1)).strip() if ti else u), body


def tradingview(n=12):
    """트레이딩뷰 전략 스크립트(최근) — 작성자 설명(전략 원리·진입·청산)."""
    t = _get("https://www.tradingview.com/scripts/?script_type=strategies&sort=recent")
    paths = list(dict.fromkeys(re.sub(r"#.*", "", p) for p in re.findall(r'(/script/[A-Za-z0-9]{6,10}-[^"\\ ?#]{3,90}/)', t)))[:n]
    out = []
    for p in paths:
        sid = p.split("/")[2].split("-")[0]
        out.append(dict(key="tv:" + sid, src="트레이딩뷰(영어)", url="https://www.tradingview.com" + p, title=None, text=None, _fetch=lambda p=p: _tv(p)))
    return out


def _tv(p):
    t = _get("https://www.tradingview.com" + p)
    j = re.findall(r'"description":"((?:[^"\\]|\\.){100,})"', t)
    body = j[0].encode().decode("unicode_escape", errors="ignore") if j else ""
    try: body = body.encode("latin-1").decode("utf-8")
    except Exception: pass
    return p.split("/")[2].split("-", 1)[-1].replace("-", " "), body


def quantocracy(days=3):
    """Quantocracy(미국 퀀트 블로그 모음) — 최근 요약 글에 실린 원래 블로그 글들."""
    f = _get("https://quantocracy.com/feed/")
    out = []
    for link in re.findall(r"<item>.*?<link>(.*?)</link>", f, re.S)[:days]:
        p = _get(link)
        for u, ti in re.findall(r'<a[^>]+href="(https?://(?!quantocracy|www\.quantocracy|twitter|x\.com|facebook|linkedin)[^"]+)"[^>]*>([^<]{12,160})</a>', p):
            out.append(dict(key="qc:" + u[:120], src="Quantocracy(영어)", url=u, title=html.unescape(ti), text=None, _fetch=lambda u=u: article(u)))
    return list({x["key"]: x for x in out}.values())


def note_jp(queries=("日本株 デイトレ 手法", "株 スイングトレード 手法"), n=10):
    """일본 note.com — 무료 부분만 읽힌다(유료 글은 앞부분)."""
    out = []
    for q in queries:
        t = _get("https://note.com/search?q=%s&context=note&mode=search" % urllib.parse.quote(q))
        for u in list(dict.fromkeys(re.findall(r"https://note\.com/[A-Za-z0-9_]+/n/n[0-9a-f]+", t)))[:n]:
            out.append(dict(key="note:" + u.rsplit("/", 1)[-1], src="note.com(일본어)", url=u, title=None, text=None, _fetch=lambda u=u: _note(u)))
    return out


def _note(u):
    t = _get(u)
    ti = re.search(r'<meta property="og:title" content="([^"]*)"', t)
    b = re.search(r'<div[^>]+class="[^"]*note-common-styles__textnote-body[^"]*"[^>]*>(.*?)</div>\s*</div>', t, re.S)
    body = clean(b.group(1)) if b else clean((re.search(r'<meta property="og:description" content="([^"]*)"', t) or [None, ""])[1] or "")
    return (html.unescape(ti.group(1)) if ti else u), body


REDDIT_SUBS = ["Daytrading", "swingtrading", "algotrading", "StockMarket"]


def reddit(n=25):
    """레딧(2026-10-10 사용자: 로그인 방식) — 앱 등록이 막혀(2025-11~ 사전 승인제) 로그인된 크롬 세션 쿠키(.env REDDIT_SESSION)로 읽는다.
    하룻밤 게시판 목록 4번뿐(목록 응답에 본문이 같이 와서 글마다 안 연다). 쿠키가 없으면 건너뛴다. 만료되면 로그에 '레딧 실패' → 점검기."""
    v = C.env().get("REDDIT_SESSION")
    if not v: return []
    from curl_cffi import requests as cr
    out = []
    for sub in REDDIT_SUBS:
        time.sleep(3)
        r = cr.get("https://old.reddit.com/r/%s/top.json?t=week&limit=%d" % (sub, n), impersonate="chrome", timeout=25, cookies={"reddit_session": v})
        try: j = r.json()
        except Exception:
            C.log("레딧 실패(로그인 쿠키 만료? HTML 받음)", sub, r.status_code); continue
        for c in (j.get("data") or {}).get("children") or []:
            d = c.get("data") or {}
            txt = d.get("selftext") or ""
            if len(txt) < 400 or (d.get("score") or 0) < 5 or d.get("over_18"): continue
            out.append(dict(key="rd:" + d.get("id", ""), src="레딧 r/%s(영어)" % sub, url="https://www.reddit.com" + d.get("permalink", ""),
                            title=d.get("title", ""), text=d.get("title", "") + "\n\n" + txt))
    return out


def overseas():
    out = []
    for fn in (tradingview, quantocracy, note_jp, reddit):
        try: out += fn()
        except Exception as ex: C.log("해외 수집 실패", fn.__name__, str(ex)[:120])
    return out


def fetch(item):
    """본문을 읽어 title·text 를 채운다(실패하면 빈 글)."""
    if item.get("text") is None and item.get("_fetch"):
        try:
            item["title"], item["text"] = item["_fetch"]()
        except Exception as ex:
            C.log("본문 실패", item["key"], str(ex)[:100]); item["text"] = ""
    return item
