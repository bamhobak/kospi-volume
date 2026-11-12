# -*- coding: utf-8 -*-
"""H0412 기각 기록 메타학습 (2026-11-12 사용자 "기억 rulefind-1112 4번 실측").

등록부 가설마다 꼬리표를 **결과·이유·상태 칸을 보지 않고**(이름·기제·자료·계열·출처 낱말만) 정해진 낱말 규칙으로 붙인다 → 사람이 결과를 알고 붙이는 낙관이 없다.
살아남음 = 채택·부분채택·후보·그림자 / 죽음 = 기각 (기록·보류·시험중 등은 뺌).
 ① 말한 그대로 판: 꼬리표 → 로지스틱(얕은 모델) · 시간순(번호순)으로 앞 가설로 배우고 뒤 가설 맞히기(AUC)
 ② 변형 판: 얕은 트리(깊이 2·3) · '덧대기'(이미 채택된 규칙 고치기) 꼬리표 빼고 · 꼬리표 하나씩 생존율 · "기각=모양 / 채택=사정" 주장 확인
 ③ 쓰임: 새 가설 사전 점수(H0411·1·3·5·7번 아이디어) · 점수 높은데 안 가 본 꼬리표 조합
    python research/meta_1112.py   → research/reports/meta_1112.md
"""
import os, re, sys, json, itertools
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import registry as R
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score

TAGS = {
    "강제": r"반대매매|신용|강제|편출|편입|투매|폭락|급락|과잉|패닉|손절|청산|만기|재조정|리밸런|매물|자사주|공개매수|락업|보호예수|의무|공매도|숏|마진|관리종목|상장폐지|폐지|경보|분사|스핀오프|어쩔 수 없이|팔아야",
    "모양": r"캔들|이평|이동평균|RSI|MACD|볼린저|돌파|신고가|눌림|패턴|지표|추세|모멘텀|골든|데드|기준봉|이격|정배열|박스|삼각|피보|일목|스토캐|ATR|채널|양봉|음봉|주봉|월봉|30분봉|15분봉|꼬리|도지|연속 (상승|하락)|\d+연속",
    "얇음": r"NXT|장전|장후|동시호가|단일가|시가|소형|작은|아래 1/|하위|얇|갭|야간|프리마켓|애프터",
    "데이": r"데이|당일|시가→종가|종가→시가|다음날 시가|다음 날 시가|하룻밤|장중|분봉|1분",
    "장기": r"60일|120일|250일|1년|6개월|3달|40일|12개월|52주",
    "특수자료": r"신용|공시|DART|KIND|1분봉|분봉|호가|내부자|13F|Form|공매도|대차|NXT|전이|검색|네이버|프로그램|기관|외인|연기금|실적|재무|PBR|배당|자금흐름|N-PORT",
    "회피": r"회피|거르|빼기|제외|매도 신호|경고|피하",
    "덧대기": r"\[(갭 하락 조용주|갭하락|조용한 신고가|조정매집|폭락반등|업종붕괴 이탈|자사주 낙폭|깊은 이격|외인 매집|낙폭과대|저PBR 낙폭|상승장 신고가|잔잔한 급등주|실적 서프라이즈|NXT 장전 되돌림|장전 되돌림|미장 폭락|분사주|자사주 신탁)|\bT[1-6]\b|\b[PND][1-9]\b|좁히기|조이기|덧조건",
    "이벤트": r"공시|발표|편입|편출|상장|분할|배당|만기|실적|이벤트|사건",
    "외부제안": r"유튜브|커뮤니티|외국|웹|GitHub|논문|기법|해외|민간|속설",
}
LIVE = {"채택", "부분채택", "후보", "그림자"}


def text(x):
    return " ".join(str(x.get(k) or "") for k in ("name", "mechanism", "data", "source")) + " " + " ".join(x.get("family") or [])


def tags(x):
    s = text(x)
    d = {k: int(bool(re.search(p, s))) for k, p in TAGS.items()}
    d["미장"] = int(x.get("market") in ("US",))
    return d


def main():
    from verdict import log_trials
    H = R.load()
    rows = []
    for x in H:
        n = int(x["id"][1:])
        rows.append(dict(id=x["id"], n=n, status=x["status"], name=x["name"][:60], **tags(x)))
    D = pd.DataFrame(rows)
    D["y"] = D.status.map(lambda s: 1 if s in LIVE else (0 if s == "기각" else np.nan))
    L = D.dropna(subset=["y"]).sort_values("n").reset_index(drop=True)
    FE = list(TAGS) + ["미장"]
    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
    P("# 기각 기록 메타학습 (H0412) · 2026-11-12"); P("")
    P("- 등록부 %d개 중 판정 난 것 %d개(살아남음 %d · 기각 %d). 꼬리표는 이름·기제·자료·계열·출처 낱말 규칙으로만(결과·이유·상태 칸 안 봄)." % (len(D), len(L), int(L.y.sum()), int((L.y == 0).sum())))
    P("- 살아남음 = 채택·부분채택·후보·그림자. ⚠ H0001~H0017 은 이미 채택된 규칙을 나중에 적어 넣은 것(기제 칸 비어 있음)"); P("")

    P("## ① 꼬리표 하나씩 — 생존율"); P("")
    P("| 꼬리표 | 붙은 가설 | 살아남음 | 생존율 | 안 붙은 쪽 생존율 |"); P("|---|---|---|---|---|")
    for f in FE:
        a, b = L[L[f] == 1], L[L[f] == 0]
        P("| %s | %d | %d | **%.1f%%** | %.1f%% |" % (f, len(a), int(a.y.sum()), a.y.mean() * 100 if len(a) else 0, b.y.mean() * 100 if len(b) else 0))
    P("")
    P("### '기각=모양 / 채택=사정' 주장 확인"); P("")
    P("| 무리 | 가설 | 살아남음 | 생존율 |"); P("|---|---|---|---|")
    for nm, m in (("모양만(강제 X)", (L["모양"] == 1) & (L["강제"] == 0)), ("강제만(모양 X)", (L["강제"] == 1) & (L["모양"] == 0)),
                  ("둘 다", (L["모양"] == 1) & (L["강제"] == 1)), ("둘 다 아님", (L["모양"] == 0) & (L["강제"] == 0)),
                  ("덧대기 빼고 · 모양만", (L["모양"] == 1) & (L["강제"] == 0) & (L["덧대기"] == 0)), ("덧대기 빼고 · 강제만", (L["강제"] == 1) & (L["모양"] == 0) & (L["덧대기"] == 0))):
        z = L[m]; P("| %s | %d | %d | %.1f%% |" % (nm, len(z), int(z.y.sum()), z.y.mean() * 100 if len(z) else 0))
    P("")

    P("## ② 시간순 맞히기 — 앞 가설로 배우고 뒤 가설 예측 (AUC, 0.5 = 동전)"); P("")
    P("| 모델 | 꼬리표 | 예측한 가설 | 그중 살아남음 | AUC | 상위 10% 생존율 | 전체 생존율 |"); P("|---|---|---|---|---|---|---|")
    START, STEP = 120, 25
    res = {}
    for mname, mk in (("로지스틱(말한 판)", lambda: LogisticRegression(C=0.5, max_iter=2000)),
                      ("얕은 트리 깊이 2", lambda: DecisionTreeClassifier(max_depth=2, min_samples_leaf=8)),
                      ("얕은 트리 깊이 3", lambda: DecisionTreeClassifier(max_depth=3, min_samples_leaf=8))):
        for fname, fe in (("전부", FE), ("덧대기 뺌", [f for f in FE if f != "덧대기"]), ("강제·모양·얇음·데이만", ["강제", "모양", "얇음", "데이"])):
            pr = []
            for k in range(START, len(L), STEP):
                tr, te = L.iloc[:k], L.iloc[k:k + STEP]
                if tr.y.nunique() < 2: continue
                m = mk().fit(tr[fe].values, tr.y.values)
                pr += list(zip(te.index, m.predict_proba(te[fe].values)[:, 1]))
            pp = pd.Series(dict(pr)); yy = L.y.loc[pp.index]
            auc = roc_auc_score(yy, pp) if yy.nunique() == 2 else float("nan")
            top = yy[pp >= pp.quantile(0.9)]
            res[(mname, fname)] = auc
            P("| %s | %s | %d | %d | **%.2f** | %.1f%% | %.1f%% |" % (mname, fname, len(pp), int(yy.sum()), auc, top.mean() * 100, yy.mean() * 100))
    P("")
    P("(번호 %d 번째 판정 가설부터 %d개씩 끊어 예측 — 앞쪽 %d개는 배우기만)" % (START, STEP, START)); P("")

    # 전체로 맞춘 모델 — 계수와 쓰임
    m = LogisticRegression(C=0.5, max_iter=2000).fit(L[FE].values, L.y.values)
    P("## ③ 전체로 맞춘 로지스틱 계수(+ = 살아남기 쉬움)"); P("")
    P("| 꼬리표 | 계수 |"); P("|---|---|")
    for f, c in sorted(zip(FE, m.coef_[0]), key=lambda z: -z[1]): P("| %s | %+.2f |" % (f, c))
    P("")
    P("## ④ 새 가설 사전 점수"); P("")
    NEW = [
        ("H0411 반대매매 발동 가격 지도(1번)", dict(name="반대매매 발동 가격 지도 신용 평균 단가 담보비율 선 D+2 시가 매수", mechanism="반대매매 강제 매도 단일가 유동성", data="신용 1분봉", source="", family=["신용", "낙폭반전"], market="KR")),
        ("3번 쌍둥이 시장(NXT ↔ 일본 PTS)", dict(name="NXT 장전 장후 효과 일본 PTS 야간 이식", mechanism="얇은 시간대 가격 왜곡 되돌림", data="NXT 장후 1분봉 녹화기", source="논문", family=["낙폭반전"], market="KR")),
        ("7번 공시 본문 숫자화(담보 계약·유상증자 용도)", dict(name="DART 공시 본문 최대주주 주식 담보 계약 유상증자 자금 용도 소송 금액", mechanism="대주주 담보 반대매매 강제 매도", data="DART 공시 본문", source="", family=["이벤트"], market="KR")),
        ("5번 대량 그림자 리그(데이 후보)", dict(name="데이 후보 100개 그림자 매일 채점 시가 종가", mechanism="", data="1분봉 호가 녹화기", source="", family=["조율"], market="KR")),
        ("비교: 흔한 모양 규칙(이평 돌파 스윙)", dict(name="20일 이평 돌파 거래량 급증 스윙 20일 보유", mechanism="추세 돌파", data="일봉", source="유튜브", family=["돌파"], market="KR")),
    ]
    P("| 가설 | 붙은 꼬리표 | 사전 점수(살아남을 확률) |"); P("|---|---|---|")
    for nm, x in NEW:
        tg = tags(x); v = np.array([[tg[f] for f in FE]])
        P("| %s | %s | **%.0f%%** |" % (nm, " ".join(f for f in FE if tg[f]), m.predict_proba(v)[0, 1] * 100))
    P("")
    P("## ⑤ 점수 높은데 안 가 본 꼬리표 조합 (덧대기 X 기준)"); P("")
    core = ["강제", "얇음", "데이", "특수자료", "모양", "미장", "회피", "이벤트"]
    combos = []
    for bits in itertools.product((0, 1), repeat=len(core)):
        tg = dict(zip(core, bits)); tg.update({"덧대기": 0, "장기": 0, "외부제안": 0})
        v = np.array([[tg.get(f, 0) for f in FE]])
        p = m.predict_proba(v)[0, 1]
        q = L.copy()
        for f in core: q = q[q[f] == tg[f]]
        q = q[q["덧대기"] == 0]
        combos.append((p, len(q), int(q.y.sum()), " + ".join(f for f in core if tg[f]) or "(아무것도)"))
    combos.sort(reverse=True)
    P("| 조합 | 사전 점수 | 지금까지 가 본 수 | 살아남음 |"); P("|---|---|---|---|")
    shown = 0
    for p, n, s, nm in combos:
        if n <= 2 and shown < 12:
            P("| %s | %.0f%% | %d | %d |" % (nm, p * 100, n, s)); shown += 1
    P(""); P("가장 많이 가 본 조합: " + " · ".join("%s %d개(산 것 %d)" % (nm, n, s) for p, n, s, nm in sorted(combos, key=lambda z: -z[1])[:6]))
    P("")
    D.to_csv("C:/temp/kp/meta_tags.csv", index=False, encoding="utf-8-sig")
    (ROOT / "reports" / "meta_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    log_trials("meta_1112", 9)


if __name__ == "__main__":
    main()
