# -*- coding: utf-8 -*-
"""유튜브 매매영상 자동 수집·선별기 — 링크를 직접 주지 않아도 알아서 훑는다.

사용자 요청(2026-09-09): "유튜브에서 알아서 관련 매매영상들을 조회하고, 링크 줄 때처럼
텍스트 추출 후 매매법 실측조사하게 하려면?"

**자동화할 수 있는 것과 없는 것을 가른다.**
  자동:  검색 → 조건 거르기 → 자막 받기 → 이미 본 영상·재탕 판별 → 매매 문장 추리기 → 분류표
  수동:  말을 **측정 가능한 조건으로 번역**하는 일. 여기는 판단이 필요해 사람(또는 나)이 한다.
그래서 이 스크립트는 '실측할 값어치가 있는 새 주장' 만 골라 내놓는 데까지만 한다.
그 다음은 여느 때처럼 조건으로 옮겨 fib_test.py 같은 실측 스크립트를 쓴다.

검색은 yt-dlp 의 ytsearch 를 쓴다(API 키 불필요). 자막은 youtube_transcript_api.

  python yt_scan.py                      # 기본 키워드로 각 12개씩
  python yt_scan.py --n 20 --days 365    # 개수·기간 조정
  python yt_scan.py --q "눌림목 매매법"    # 키워드 직접 지정

결과: data/yt_seen.json(이미 처리한 영상), yt_scan_report.md(분류표),
      transcripts/<id>.txt(자막 원문)
"""
import io, sys, os, json, re, argparse, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path

BASE = Path(__file__).parent
SEEN = BASE / "data" / "yt_seen.json"
TDIR = BASE / "transcripts"
TDIR.mkdir(exist_ok=True)

# 기본 키워드 — 우리가 아직 안 재본 축이 나올 만한 쪽으로 고른다.
# (월봉 12평·볼린저·원웨이처럼 이미 기각한 주제는 재탕 판별에서 걸러진다)
QUERIES = [
    "주식 매매기법 실전", "단타 매매법 조건", "스윙 매매 기법 주식",
    "수급 매매법 외국인 기관", "거래량 매매기법", "급등주 매매법 조건",
    "공매도 매매 활용", "저평가 가치주 발굴 기준", "차트 패턴 매매법",
]
KW = ["이평", "평선", "돌파", "이탈", "지지", "저항", "거래량", "매수", "매도", "손절", "익절",
      "신고가", "신저가", "박스", "골든", "데드", "월봉", "주봉", "일봉", "분봉", "캔들", "갭",
      "외국인", "기관", "수급", "공매도", "신용", "PBR", "PER", "시가총액", "배당",
      "눌림", "반등", "낙폭", "조정", "추세", "패턴", "비중", "분할", "조건검색"]
NUMRE = re.compile(r"(\d+\s*(일|주|개월|달|퍼센트|%|배|평|선|봉))")


def load_seen():
    if SEEN.exists():
        try:
            return json.load(open(SEEN, encoding="utf-8"))
        except Exception:
            pass
    return {}


def search(q, n, days):
    """yt-dlp 로 검색. 메타데이터만 받는다(영상은 안 받는다)."""
    from yt_dlp import YoutubeDL
    opt = {"quiet": True, "skip_download": True, "extract_flat": True,
           "ignoreerrors": True, "no_warnings": True}
    with YoutubeDL(opt) as y:
        r = y.extract_info(f"ytsearch{n}:{q}", download=False)
    out = []
    for e in (r or {}).get("entries") or []:
        if not e:
            continue
        out.append(dict(id=e.get("id"), title=e.get("title") or "",
                        views=e.get("view_count") or 0,
                        dur=e.get("duration") or 0,
                        ch=e.get("channel") or e.get("uploader") or "", q=q))
    return out


def fetch_text(vid):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    tr = api.fetch(vid, languages=["ko", "en"])
    return " ".join(s.text.replace("\n", " ") for s in tr)


def sents(t):
    return [x.strip() for x in re.split(r"(?<=[.?!])\s+", t) if len(x.strip()) > 15]


def norm(x):
    return re.sub(r"\s+", "", x)


def overlap(new_txt, old_files):
    """이미 처리한 자막과 문장 단위로 얼마나 겹치나 — 같은 강사 재탕을 잡는다."""
    ns = [norm(x) for x in sents(new_txt)]
    if not ns:
        return 0.0, None
    best, who = 0.0, None
    for f in old_files:
        try:
            old = set(norm(x) for x in sents(open(f, encoding="utf-8").read()))
        except Exception:
            continue
        r = sum(x in old for x in ns) / len(ns)
        if r > best:
            best, who = r, Path(f).name
    return best, who


def score(t):
    """매매 관련 문장만 추리고 '구체성' 점수를 매긴다.
    숫자 조건(20일선·-15%·2배)이 들어간 문장이 실측 가능성이 높다."""
    picked = []
    for x in sents(t):
        k = sum(w in x for w in KW)
        if k < 2:
            continue
        num = len(NUMRE.findall(x))
        picked.append((k + num * 2, num, x))
    picked.sort(key=lambda z: -z[0])
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="키워드당 검색 개수")
    ap.add_argument("--days", type=int, default=730, help="(참고용) 최근 며칠")
    ap.add_argument("--minviews", type=int, default=30000)
    ap.add_argument("--mindur", type=int, default=240, help="너무 짧은 쇼츠 제외(초)")
    ap.add_argument("--maxdur", type=int, default=5400)
    ap.add_argument("--q", action="append", help="키워드 직접 지정(여러 번 가능)")
    a = ap.parse_args()

    qs = a.q or QUERIES
    seen = load_seen()
    old_files = sorted(str(p) for p in list(TDIR.glob("*.txt")) + list(BASE.glob("yt_transcript*.txt")))

    cand = {}
    for q in qs:
        try:
            for e in search(q, a.n, a.days):
                if e["id"] and e["id"] not in cand:
                    cand[e["id"]] = e
        except Exception as ex:
            print(f"  검색 실패 [{q}]: {ex}")
    print(f"검색 {len(qs)}개 키워드 → 후보 {len(cand)}개")

    fresh, skipped = [], {"본것": 0, "조회수": 0, "길이": 0, "자막없음": 0, "재탕": 0}
    for vid, e in cand.items():
        if vid in seen:
            skipped["본것"] += 1; continue
        if e["views"] < a.minviews:
            skipped["조회수"] += 1; continue
        if not (a.mindur <= (e["dur"] or 0) <= a.maxdur):
            skipped["길이"] += 1; continue
        try:
            t = fetch_text(vid)
        except Exception:
            skipped["자막없음"] += 1
            seen[vid] = {"title": e["title"], "why": "자막없음"}
            continue
        ov, who = overlap(t, old_files)
        p = TDIR / f"{vid}.txt"
        p.write_text(t, encoding="utf-8")
        old_files.append(str(p))
        if ov >= 0.35:
            skipped["재탕"] += 1
            seen[vid] = {"title": e["title"], "why": f"재탕 {ov:.0%} ({who})"}
            continue
        picked = score(t)
        fresh.append(dict(e, n_sent=len(sents(t)), n_pick=len(picked),
                          spec=sum(1 for s in picked if s[1] >= 1), top=picked[:14], ov=ov))
        seen[vid] = {"title": e["title"], "why": "신규", "picks": len(picked)}

    SEEN.parent.mkdir(exist_ok=True)
    json.dump(seen, open(SEEN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    fresh.sort(key=lambda z: -z["spec"])

    L = ["# 유튜브 매매영상 선별 결과", "",
         f"검색 키워드 {len(qs)}개 · 후보 {len(cand)}개 · 신규 {len(fresh)}개",
         "건너뜀: " + " · ".join(f"{k} {v}" for k, v in skipped.items()), "",
         "> 구체성 = 숫자 조건(20일선·-15%·2배 등)이 든 매매 문장 수. 높을수록 실측하기 쉽다.", ""]
    for f in fresh:
        L += [f"## {f['title']}", "",
              f"- https://youtu.be/{f['id']} · {f['ch']} · 조회 {f['views']:,} · "
              f"{f['dur']//60}분 · 검색어 「{f['q']}」",
              f"- 매매 문장 {f['n_pick']}개 · **구체성 {f['spec']}** · 기존 자막과 겹침 {f['ov']:.0%}", ""]
        for sc, num, x in f["top"]:
            L.append(f"  - {x[:200]}")
        L.append("")
    (BASE / "yt_scan_report.md").write_text("\n".join(L), encoding="utf-8")

    print("건너뜀: " + " · ".join(f"{k} {v}" for k, v in skipped.items()))
    print(f"신규 {len(fresh)}개 → yt_scan_report.md")
    for f in fresh[:10]:
        print(f"  구체성 {f['spec']:>3} · {f['title'][:52]} · https://youtu.be/{f['id']}")


if __name__ == "__main__":
    main()
