# -*- coding: utf-8 -*-
"""AI 수집 일꾼 (2026-10-08 사용자 아이디어 ④) — Claude API 크레딧(Max 월 지급분, Claude Code 와 별개)으로 매일 밤
새로 올라온 단타 기법을 읽고 공장 명세(JSON)로 번역해 깔때기에 넣는다.

  수집처  유튜브(최신순 검색 · 한국어 자동 자막) — 기법 영상 대부분이 여기 있다
          (네이버 블로그는 지금 키가 데이터랩 전용이라 검색 API 401 — 키에 '검색' 권한을 더하면 붙일 수 있다)
  1차 거르기  Haiku 5.5 — 제목·앞부분만 보고 '숫자가 있는 매매 조건인가' (건당 0.1원 안팎)
  번역        Sonnet 5.5 — 자막 전체 → 공장 재료 사전으로 옮길 수 있는 조건만 명세로(못 옮기는 부분은 따로 적는다)
  크레딧 기록 data/factory/llm_usage.jsonl — 호출마다 토큰·달러. `run.py usage` 로 이달 사용·한 달 예상.
  한도        .env FACTORY_LLM_MONTHLY(기본 $40) 를 넘기면 그달은 더 안 부른다(크레딧 다 써도 과금은 안 되지만 다른 앱 몫을 남긴다).
"""
import json, os, re, time, glob, shutil, tempfile, urllib.parse
from pathlib import Path

import common as C
import feats as FT

SEEN = C.DATA / "harvest_seen.json"
USAGE = C.DATA / "llm_usage.jsonl"
HV = C.DATA / "harvest"; HV.mkdir(exist_ok=True)
SCREEN_MODEL, EXTRACT_MODEL = "claude-haiku-5-5", "claude-sonnet-5-5"
# 백만 토큰당 달러: (입력, 출력, 캐시 쓰기 5분, 캐시 읽기) — platform.claude.com 가격표 2026-10-08
PRICE = {"claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01), "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.10),
         "claude-haiku-4-5-20251001": (1.0, 5.0, 1.25, 0.10), "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20)}
QUERIES = ["단타 매매법", "데이트레이딩 기법", "종가베팅 매매법", "시초가 매매 기법", "스캘핑 주식 기법", "단타 승률 높은 방법",
           "갭 매매 기법", "눌림목 단타", "상한가 따라잡기", "거래량 급증 매매"]
MAX_EXTRACT = 6            # 하룻밤 번역(비싼 쪽) 상한
MAX_SCREEN = 40


# ── 크레딧 ──────────────────────────────────────────────────────────
def cost(model, u):
    p = PRICE.get(model, PRICE["claude-sonnet-5-5"])
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0; cr = getattr(u, "cache_read_input_tokens", 0) or 0
    return (u.input_tokens * p[0] + u.output_tokens * p[1] + cw * p[2] + cr * p[3]) / 1e6


def month_spent(ym=None):
    ym = ym or time.strftime("%Y-%m")
    if not USAGE.exists(): return 0.0
    return sum(json.loads(l)["usd"] for l in USAGE.read_text(encoding="utf-8").splitlines() if l.strip() and json.loads(l)["ts"][:7] == ym)


def budget():
    try: return float(C.env().get("FACTORY_LLM_MONTHLY", "40"))
    except Exception: return 40.0


_CL = None


def ask(model, system, user, task, max_tokens=4000, think=True):
    """한 번 부르고 기록한다. 시스템 프롬프트는 캐시(같은 밤 여러 번 쓰면 읽기 값으로)."""
    global _CL
    if month_spent() >= budget():
        raise RuntimeError("이달 한도 $%.0f 다 씀" % budget())
    if _CL is None:
        import anthropic
        _CL = anthropic.Anthropic(api_key=C.env()["ANTHROPIC_API_KEY"])
    r = _CL.messages.create(model=model, max_tokens=max_tokens,
                            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                            messages=[{"role": "user", "content": user}], **({} if think else {"thinking": {"type": "disabled"}}))
    u = r.usage; usd = cost(model, u)
    with open(USAGE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, "task": task, "in": u.input_tokens, "out": u.output_tokens,
                            "cw": getattr(u, "cache_creation_input_tokens", 0) or 0, "cr": getattr(u, "cache_read_input_tokens", 0) or 0,
                            "usd": round(usd, 6)}, ensure_ascii=False) + "\n")
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def usage_report():
    import calendar, collections
    if not USAGE.exists(): return ["아직 호출 기록 없음"]
    L = [json.loads(l) for l in USAGE.read_text(encoding="utf-8").splitlines() if l.strip()]
    ym = time.strftime("%Y-%m"); M = [x for x in L if x["ts"][:7] == ym]
    tot = sum(x["usd"] for x in M)
    days = sorted({x["ts"][:10] for x in M})
    y, m = int(ym[:4]), int(ym[5:]); dim = calendar.monthrange(y, m)[1]
    per = tot / max(len(days), 1)
    by = collections.defaultdict(lambda: [0, 0.0, 0, 0])
    for x in M:
        b = by[(x["task"], x["model"])]; b[0] += 1; b[1] += x["usd"]; b[2] += x["in"] + x["cw"] + x["cr"]; b[3] += x["out"]
    out = ["이달(%s) 사용 $%.3f · 돈 쓴 날 %d일 · 하루 평균 $%.3f → 한 달 예상 약 $%.2f (한도 $%.0f)" % (ym, tot, len(days), per, per * dim, budget())]
    for (t, mo), b in sorted(by.items()):
        out.append("  %s · %s: %d번 · $%.3f · 입력 %s / 출력 %s 토큰" % (t, mo, b[0], b[1], f"{b[2]:,}", f"{b[3]:,}"))
    return out


# ── 수집 ────────────────────────────────────────────────────────────
def yt_search(q, n=8):
    import yt_dlp
    u = "https://www.youtube.com/results?search_query=%s&sp=CAI%%3D" % urllib.parse.quote(q)      # 업로드 날짜순
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "playlistend": n}) as y:
        j = y.extract_info(u, download=False) or {}
    return [e for e in (j.get("entries") or []) if e.get("id") and len(e["id"]) == 11]


def vtt_text(p):
    out, last = [], None
    for ln in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:")) or ln == last: continue
        out.append(ln); last = ln
    return " ".join(out)


def yt_text(vid):
    import yt_dlp
    d = Path(tempfile.mkdtemp(prefix="hv_"))
    try:
        opts = {"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True, "writeautomaticsub": True, "writesubtitles": True,
                "subtitleslangs": ["ko"], "subtitlesformat": "vtt", "outtmpl": str(d / "%(id)s")}
        with yt_dlp.YoutubeDL(opts) as y:
            y.download(["https://www.youtube.com/watch?v=" + vid])
        fs = glob.glob(str(d / "*.vtt"))
        return vtt_text(fs[0]) if fs else ""
    except Exception as ex:
        C.log("자막 실패", vid, str(ex)[:120]); return ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 프롬프트 ─────────────────────────────────────────────────────────
SCREEN_SYS = """너는 한국 주식 매매 기법 영상을 1차로 거르는 사람이다. 제목과 앞부분 자막을 보고 JSON 한 줄로만 답한다.
{"rule": true|false, "kind": "day"|"swing"|"none", "why": "한 줄"}
rule=true 조건: 사고파는 조건이 숫자나 명확한 기준으로 나온다(예: 갭 -3%, 거래량 3배, 전일 양봉, 5일선, 시초가 매수·종가 매도).
뉴스·종목 추천·심리·일반론·광고·강의 홍보만 있으면 false. kind=day 는 하루 안에 사고파는 기법(종가베팅·시초가 포함)."""


def extract_sys():
    fl = "\n".join("  %s — %s [%s]" % (k, v[0], v[1]) for k, v in FT.FEATS.items() if v[1] != "live")
    md = "\n".join("  %s — %s" % (k, v[0]) for k, v in FT.MODES.items())
    return """너는 매매 기법을 '시험 가능한 규칙 명세(JSON)'로 옮기는 번역가다. 우리 시험장은 국장(한국 주식) 일봉 기반이다.
할 일: 자막에서 사고파는 조건을 찾아 아래 재료 사전과 매매 방식으로만 옮긴다. 사전에 없는 것(분봉 돌파·VWAP·호가창·뉴스·테마 판단·손절 % 등)은
억지로 옮기지 말고 untestable 에 적는다. 비슷하게 근사할 수 있으면 근사하고 approx 에 어떻게 근사했는지 적는다.

매매 방식(mode):
{MODES}
재료 사전(f — 설명 [언제 아는가]): pre=어제 종가까지 확정 · open=오늘 시가(장전 예상가로 미리 보임) · close=오늘 종가 무렵(on 방식만)
{FEATS}

조건 형식: {"f": 재료, "op": "<=" 또는 ">=", "v": 숫자, "q": true/false}
  q=false → 원래 단위(%%·배·원·일수) 그대로 비교. 예: 어제 거래량 3배 이상 = {"f":"vm","op":">=","v":3}
  q=true  → 그날 유니버스(거래대금 상위 40%%) 안 백분위(0~1). 예: 갭이 하위 10%% = {"f":"gap","q":true,"op":"<=","v":0.1}
  '급등'·'거래량 터진' 처럼 숫자 없는 말은 q=true 상위 10%%(>=0.9) 같이 정하고 approx 에 적는다.
선택: "top": {"n": 하루 최대 종목 수, "by": 재료, "asc": true(낮은 순)/false}

답은 JSON 하나만:
{"summary": "기법 한 줄 요약", "specs": [{"name": "짧은 이름", "mode": "oc", "conds": [...], "approx": "근사한 부분", "untestable": "못 옮긴 부분"}]}
규칙: 명세는 최대 3개(원안 1개 + 영상이 직접 말한 변형). 영상이 말하지 않은 조건을 지어내지 않는다. 옮길 게 없으면 "specs": [].""".replace("{MODES}", md).replace("{FEATS}", fl).replace("%%", "%")


def _json(s):
    m = re.search(r"\{.*\}", s, re.S)
    return json.loads(m.group(0)) if m else None


def run(max_extract=MAX_EXTRACT):
    """하룻밤 수집 → 명세 목록(아직 깔때기에 안 넣음). 반환 (명세들, 보고 줄들)."""
    import lab
    seen = C.jload(SEEN, {})
    cand = []
    for q in QUERIES:
        try:
            for e in yt_search(q):
                if e["id"] in seen: continue
                dur = e.get("duration") or 0
                if dur and not (180 <= dur <= 3600): seen[e["id"]] = "길이"; continue
                cand.append((e["id"], e.get("title") or "", e.get("channel") or "", q))
        except Exception as ex:
            C.log("검색 실패", q, str(ex)[:120])
    uniq = {}
    for c in cand: uniq.setdefault(c[0], c)
    cand = list(uniq.values())[:MAX_SCREEN]
    specs, rep, nx = [], [], 0
    xsys = extract_sys()
    for vid, title, ch, q in cand:
        if month_spent() >= budget(): rep.append("이달 한도 다 써서 멈춤"); break
        txt = yt_text(vid)
        if len(txt) < 300:
            seen[vid] = "자막 없음"; continue
        try:
            s = _json(ask(SCREEN_MODEL, SCREEN_SYS, "제목: %s\n채널: %s\n자막 앞부분: %s" % (title, ch, txt[:2500]), "거르기", 300, think=False)) or {}
        except Exception as ex:
            C.log("거르기 실패", vid, str(ex)[:150]); continue
        if not s.get("rule") or s.get("kind") != "day":
            seen[vid] = "거름: %s" % (s.get("why") or s.get("kind")); continue
        if nx >= max_extract:
            continue                                                  # 내일 밤 다시(본 목록에 안 넣음)
        nx += 1
        (HV / ("%s.txt" % vid)).write_text("%s\n%s\n\n%s" % (title, ch, txt), encoding="utf-8")
        try:
            j = _json(ask(EXTRACT_MODEL, xsys, "영상 제목: %s\n채널: %s\n자막:\n%s" % (title, ch, txt[:30000]), "번역", 12000)) or {}
        except Exception as ex:
            C.log("번역 실패", vid, str(ex)[:150]); continue
        seen[vid] = "번역: %s" % (j.get("summary") or "")[:80]
        got = 0
        for sp in (j.get("specs") or [])[:3]:
            sp = {"name": sp.get("name") or title[:30], "origin": "harvest", "source": "https://youtu.be/%s %s" % (vid, title[:60]),
                  "mode": sp.get("mode", "oc"), "conds": sp.get("conds") or [], "approx": sp.get("approx", ""), "untestable": sp.get("untestable", "")}
            if sp.get("top") is None: sp.pop("top", None)
            err = lab.check(sp)
            if err:
                rep.append("· %s — 명세 오류: %s" % (title[:40], err)); continue
            specs.append(sp); got += 1
        rep.append("· [%s] %s — %s · 명세 %d개" % (ch[:12], title[:45], (j.get("summary") or "")[:60], got))
    C.jsave(SEEN, seen)
    C.log("수집 일꾼: 후보 %d · 번역 %d · 명세 %d" % (len(cand), nx, len(specs)))
    return specs, rep
