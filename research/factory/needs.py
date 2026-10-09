# -*- coding: utf-8 -*-
"""못 옮긴 조건 모음 (2026-10-10 사용자: "재료 사전으로 안 되는 건 왜 안 되는지, 뭐가 필요한지 보고 수집할 수 있는 자료면 수집").

수집 일꾼이 번역할 때마다 needs(필요한 것·종류·이유)를 data/factory/needs.jsonl 에 적는다 → 여기서 종류별로 세고
우리가 가진 자료로 되는지(STATUS)를 붙여 밤 보고서에 싣는다. '계산 가능'이 많이 쌓이면 재료로 추가하고, '새로 모아야 함'은 수집 후보.
"""
import collections, json, time
import common as C

NEEDS = C.DATA / "needs.jsonl"
# 종류 → (지금 상태, 할 수 있는 것)
STATUS = {
    "분봉·장중 흐름": ("자료 있음·방식 없음", "1분봉 국장 2022-12~ 상위 1,000(+매일 전 종목) — '10:00 진입·VWAP 위 진입' 같은 장중 매매 방식을 추가하면 시험 가능(학습 22.12~24·검증 25~ 로 짧아짐)"),
    "호가·체결 강도": ("일부 녹화 중", "장전·마감 동시호가는 10-12부터 녹화(과거 없음 → 그림자로만). 장중 체결강도는 토스 소켓 200종목 한계라 전 종목 수집 불가"),
    "뉴스·공시·재료": ("공시만 있음", "DART 공시(disc_watch·내부자) 있음 → 공시 종류 재료 추가 가능. 뉴스 본문·'재료 좋음' 판단은 없음(LLM 분류를 새로 붙여야)"),
    "테마·업종·대장주 판단": ("있음(편향)", "네이버 테마 2026-08 한 장(th·순위) — 과거 편입 이력이 없어 과거 시험이 부풀 수 있음. 업종 분류는 있음"),
    "보조지표(일봉)": ("계산 가능", "일봉으로 바로 계산 — 많이 나오는 지표부터 재료로 추가(10-10에 RSI·볼린저·MACD·일목·120/224일선 추가함)"),
    "가격·캔들 패턴(일봉)": ("계산 가능", "일봉으로 바로 계산 — 신고가·전고점·꼬리·몸통·상한가 이력 추가함(10-10), 더 나오면 추가"),
    "수급(기관·외인·프로그램·신용)": ("자료 있음", "flow11(외인·개인·기관 11분할)·토스 프로그램·신용·대차·공매도 DB 있음 → 재료로 붙이면 됨(지금은 외인·개인만)"),
    "손절·익절·분할 매매": ("방식 없음", "일봉 고가·저가로 '보유 중 -x% 손절 / +y% 익절' 근사 가능 → 스윙 청산 방식 추가 대상(장중 순서는 1분봉 기간만 정확)"),
    "시장 국면·지수": ("자료 있음", "코스피·코스닥 지수·국면 있음 → 재료(지수 60일선 위/아래 등) 추가 가능. 지금은 유니버스 중앙 등락으로 근사"),
    "재무·실적": ("자료 있음", "PBR·PER·DART 재무 있음 → 재료 추가 가능"),
    "기타": ("확인 필요", "보고서 개념 목록을 보고 판단"),
}


def load(days=30):
    if not NEEDS.exists(): return []
    cut = time.strftime("%Y%m%d", time.localtime(time.time() - days * 86400))
    return [x for x in (json.loads(l) for l in NEEDS.read_text(encoding="utf-8").splitlines() if l.strip()) if x["date"] >= cut]


def rows(days=30, top=6):
    L = load(days)
    by = collections.defaultdict(list)
    for x in L: by[x["cat"] if x["cat"] in STATUS else "기타"].append(x)
    out = []
    for cat, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        cc = collections.Counter(x["concept"].strip()[:24] for x in xs if x.get("concept"))
        st, how = STATUS.get(cat, STATUS["기타"])
        out.append({"cat": cat, "n": len(xs), "docs": len({x["key"] for x in xs}), "status": st, "top": cc.most_common(top), "how": how})
    return out


def summary(days=30, top=6):
    R = rows(days, top)
    if not R: return ["- 아직 기록 없음(수집 일꾼이 번역할 때마다 쌓인다)"]
    out = ["| 종류 | 건수(글 수) | 지금 상태 | 자주 나온 것 | 할 수 있는 것 |", "|---|---|---|---|---|"]
    out += ["| %s | %d(%d) | %s | %s | %s |" % (r["cat"], r["n"], r["docs"], r["status"], ", ".join("%s %d" % kv for kv in r["top"]), r["how"]) for r in R]
    return out
