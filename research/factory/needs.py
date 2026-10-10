# -*- coding: utf-8 -*-
"""못 옮긴 조건 모음 (2026-10-10 사용자: "재료 사전으로 안 되는 건 왜 안 되는지, 뭐가 필요한지 보고 수집할 수 있는 자료면 수집").

수집 일꾼이 번역할 때마다 needs(필요한 것·종류·이유)를 data/factory/needs.jsonl 에 적는다 → 여기서 종류별로 세고
우리가 가진 자료로 되는지(STATUS)를 붙여 밤 보고서에 싣는다. '계산 가능'이 많이 쌓이면 재료로 추가하고, '새로 모아야 함'은 수집 후보.
"""
import collections, json, time
import common as C

NEEDS = C.DATA / "needs.jsonl"
# 종류 → (지금 상태, 할 수 있는 것)
STATUS = {   # 2026-10-10 저녁 기준 — 실제로 넣은 것 반영(사용자: "이것들은 왜 못 하고 있는 거야?")
    "분봉·장중 흐름": ("✅ 장중 방식 넣음", "10:00 매수→종가(m10c)·14:00 매수→종가(m14c) + 장중 재료 7개(10·14시까지 등락·VWAP 대비·거래대금·고저 위치). 1분봉 2022-12~ 라 학습 22.12~24·검증 25~. 5분봉 박스 돌파·VWAP 밴드 같은 분봉 모양 신호는 아직"),
    "호가·체결 강도": ("녹화 중", "장전·마감 동시호가 10-12부터 녹화(과거 없음 → 쌓이면 정답지·그림자로). 장중 체결강도는 토스 소켓 200종목 한계라 전 종목 수집 불가"),
    "뉴스·공시·재료": ("공시만 있음", "DART 공시 있음 → 공시 종류 재료는 다음 차례. 뉴스 본문·'재료 좋음' 판단은 LLM 분류를 새로 붙여야"),
    "테마·업종·대장주 판단": ("있음(편향)", "네이버 테마 2026-08 한 장(th) — 과거 편입 이력이 없어 과거 시험이 부풀 수 있음"),
    "보조지표(일봉)": ("✅ 넣음", "RSI·볼린저·MACD·일목·50/120/200/224일선·Supertrend·50일 회귀 기울기·60일 신고 거래량. 키움 '숫자 1' 같은 비공개 신호식만 불가"),
    "가격·캔들 패턴(일봉)": ("✅ 넣음", "52주·60일 신고가·40일 종가 신고·꼬리·몸통(도지·마루보주)·장대양봉 뒤 날수·스윕 후 복귀·장악형·상한가 이력. 지그재그 피벗만 아직"),
    "수급(기관·외인·프로그램·신용)": ("✅ 일부 넣음", "외국인·개인·기관 순매수(1·5일) 넣음. 토스 프로그램·신용·대차·공매도는 다음 차례"),
    "손절·익절·분할 매매": ("✅ 넣음", "스윙 청산: 손절 -x% · 익절 +y% · 고점 대비 추적 손절 · +x%에 절반 익절(일봉 고저로, 같은 날 둘 다면 손절). 피라미딩(추가 매수)·비중은 아직"),
    "시장 국면·지수": ("✅ 넣음", "코스피 60일선 이격(kdev) + 유니버스 중앙 등락. 미장은 S&P 국면 재료가 다음 차례"),
    "재무·실적": ("✅ 일부 넣음", "회전율(거래량÷발행 주식) 넣음. PBR·PER 은 매일 자료에 없어 보류"),
    "기타": ("확인 필요", "공매도(숏) 진입은 국장 개인이 사실상 못 해 제외 · 키움 조건검색식 원문은 비공개라 불가 · 당일 거래대금(amtt) 넣음"),
}


# 처리 끝난 종류 → 그 날짜까지 쌓인 기록은 표에서 뺀다(2026-10-10 사용자: "다 된 거면 안 보이게").
# 그 뒤 새로 나온 못 옮긴 조건은 다시 보인다. 새로 처리하면 여기 날짜를 올린다.
RESOLVED = {"보조지표(일봉)": "20261010", "손절·익절·분할 매매": "20261010", "가격·캔들 패턴(일봉)": "20261010",
            "분봉·장중 흐름": "20261010", "재무·실적": "20261010", "기타": "20261010", "시장 국면·지수": "20261010",
            "수급(기관·외인·프로그램·신용)": "20261010"}


def load(days=30):
    if not NEEDS.exists(): return []
    cut = time.strftime("%Y%m%d", time.localtime(time.time() - days * 86400))
    return [x for x in (json.loads(l) for l in NEEDS.read_text(encoding="utf-8").splitlines() if l.strip()) if x["date"] >= cut]


def rows(days=30, top=6):
    L = load(days)
    by = collections.defaultdict(list)
    for x in L:
        cat = x["cat"] if x["cat"] in STATUS else "기타"
        if x["date"] <= RESOLVED.get(cat, ""): continue                # 처리 끝난 기록은 숨긴다
        by[cat].append(x)
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
