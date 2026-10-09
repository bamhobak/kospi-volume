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


def fetch(item):
    """본문을 읽어 title·text 를 채운다(실패하면 빈 글)."""
    if item.get("text") is None and item.get("_fetch"):
        try:
            item["title"], item["text"] = item["_fetch"]()
        except Exception as ex:
            C.log("본문 실패", item["key"], str(ex)[:100]); item["text"] = ""
    return item
