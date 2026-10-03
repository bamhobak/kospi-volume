# -*- coding: utf-8 -*-
"""데이 2단계 (2026-10-03, 사용자: "다 돌려줘") — 일봉 2005~2026.
  1) [갭 하락 조용주](T1, H0285) 다듬기 — 갭 원인(공시 유무·종류) · 시장 전체 갭 vs 혼자 · 코스피/코스닥 · 조건 하나 더 · 갭 크기 · 요일
  2) 국장 오버나이트 — 종가 단일가 매수 → 다음날 시가 단일가 매도(재료는 **오늘** 값 — 15:20 단일가 접수 때 거의 다 보인다)
  3) 미장 [갭 하락 조용주] — 국장 조합(중소형·갭 하위 10%·어제 거래량 하위 30%)을 그대로
판정은 oc_day 와 같다: 하루 평균(하루 = 한 표) · 학습 2016~22 / 검증 2023~ / 참고 2005~15 · 비용 국장 0.22% · 미장 0.25%
    python research/day2.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import oc_day as O
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = (("20160101", "20221231"), ("20230101", "20991231"), ("20050101", "20151231"))
N = [0]


def fmt(s):
    return ("%+.3f · %d/%d해 · t%.1f" % (s["m"], s["ypos"], s["ny"], s["t"])) if s else "-"


def row(lab, S, col="oc"):
    N[0] += 1
    st = [O.stat(S[(S.date >= a) & (S.date <= b)].groupby("date")[col].mean()) for a, b in PER]
    v = S[S.date >= "20230101"]
    n = len(v) / max(v.date.nunique(), 1)
    ok = bool(st[0] and st[1] and st[0]["m"] > 0 and st[1]["m"] > 0 and st[0]["t"] >= 3 and st[0]["ypos"] / st[0]["ny"] >= 0.6)
    P("| %s | %s | %s | %s | %.1f | %s |" % (lab, fmt(st[0]), fmt(st[1]), fmt(st[2]), n, "✅" if ok else ""))
    return st


def head(t):
    P(""); P("### " + t); P("")
    P("| 조건 | 학습 16~22 (하루 평균% · 플러스 해 · t) | 검증 23~ | 참고 05~15 | 하루 종목 | 통과 |"); P("|---|---|---|---|---|---|")


def part1(A):
    P("## 1) [갭 하락 조용주] 다듬기 (국장)")
    for f in ("gap", "vm", "r20", "d5", "rng", "r1", "fh", "fr", "ir", "r5"):
        A["q_" + f] = A.groupby("date")[f].rank(pct=True)
    A["liq"] = A.groupby("date").amt20.rank(pct=True)
    A["mgap"] = A.groupby("date").gap.transform("median")
    B = A[(A.liq <= 2 / 3) & (A.q_gap <= 0.10) & (A.q_vm <= 0.30)].copy()
    # 공시: 어제(장 마감 뒤 포함) 또는 오늘 접수 — 접수 시각이 없어 '오늘 장중 공시'도 섞인다(보수적으로 '있음' 쪽)
    import event_lab as E
    D = E.disclosures()
    cal = sorted(A.date.unique()); prev = dict(zip(cal[1:], cal[:-1]))
    B["pdate"] = B.date.map(prev)
    D = D[D.rcept_dt >= "20041201"]
    kind = np.select([D.t.str.contains("유상증자|전환사채|신주인수권|교환사채|주식매수선택권"),
                      D.t.str.contains("영업\\(잠정\\)실적|매출액또는손익구조|연결재무제표기준영업|결산실적"),
                      D.t.str.contains("소유상황보고서|대량보유상황보고서|임원ㆍ주요주주|최대주주등소유주식변동")],
                     ["희석", "실적", "지분"], "기타")
    D["kind"] = kind
    Dk = D.groupby(["stock_code", "rcept_dt"]).kind.agg(lambda s: "희석" if "희석" in set(s) else ("실적" if "실적" in set(s) else ("기타" if "기타" in set(s) else "지분")))
    dk = Dk.to_dict()
    B["disc"] = [dk.get((t, d)) or dk.get((t, p)) or "없음" for t, d, p in zip(B.ticker, B.date, B.pdate)]
    head("기본과 갭 원인")
    row("기본 (중소형·갭 하위10%·거래량 하위30%)", B)
    for k in ("없음", "지분", "기타", "실적", "희석"):
        row("공시 %s" % k, B[B.disc == k])
    row("공시 없음 + 지분 공시만", B[B.disc.isin(["없음", "지분"])])
    head("시장 전체 갭 vs 혼자")
    row("시장 갭 ≤ -1% (다 같이 빠진 날)", B[B.mgap <= -1])
    row("시장 갭 -1 ~ -0.3%", B[(B.mgap > -1) & (B.mgap <= -0.3)])
    row("시장 갭 > -0.3% (혼자 빠진 날)", B[B.mgap > -0.3])
    row("시장 대비 -3%p 이상 더 빠짐", B[B.gap - B.mgap <= -3])
    row("시장 대비 -3%p 안", B[B.gap - B.mgap > -3])
    head("코스피 / 코스닥")
    if "mk" in B.columns:
        for m in ("KOSPI", "KOSDAQ"):
            row(m, B[B.mk == m])
    head("조건 하나 더 (기본 안에서)")
    for f, lab in (("r20", "20일 하락 하위30%"), ("d5", "5일선 아래 하위30%"), ("rng", "어제 고저폭 작음 하위30%"), ("r1", "어제 하락 하위30%"),
                   ("r5", "5일 하락 하위30%"), ("fh", "20일 고점서 먼 하위30%"), ("ir", "어제 개인 순매도 쪽 하위30%")):
        row(lab, B[B["q_" + f] <= 0.3])
    row("어제 상승 상위30%", B[B.q_r1 >= 0.7]); row("어제 외국인 순매수 상위30%", B[B.q_fr >= 0.7])
    head("갭 크기 · 요일")
    for lab, lo, hi in (("갭 -1~0%", -1, 0), ("갭 -2~-1%", -2, -1), ("갭 -3~-2%", -3, -2), ("갭 -5~-3%", -5, -3), ("갭 -10~-5%", -10, -5), ("갭 -10% 아래", -40, -10)):
        row(lab, B[(B.gap > lo) & (B.gap <= hi)])
    wd = pd.to_datetime(B.date).dt.dayofweek
    for i, n in enumerate("월화수목금"):
        row("%s요일" % n, B[wd == i])
    pd.to_pickle(B, ROOT / "cache" / "day2_T1.pkl")


def part2(A):
    P(""); P("## 2) 국장 오버나이트 — 종가 단일가 매수 → 다음날 시가 매도 (재료 = 오늘 값)")
    A = A[A.on.notna() & (A.on.abs() <= 30.5)].copy()
    A["onc"] = A.on.clip(-30, 30) - O.COST["KR"]
    A["liq"] = A.groupby("date").amt20.rank(pct=True)
    feats = {"r1t": "오늘 등락", "clvt": "오늘 종가 위치", "vmt": "오늘 거래량 배수", "rngt": "오늘 고저폭", "r5t": "5일 등락", "r20t": "20일 등락", "gap": "오늘 갭"}
    for f in feats: A["q_" + f] = A.groupby("date")[f].rank(pct=True)
    head("전체 · 거래대금 구간")
    row("유니버스 전체", A, "onc"); row("중소형(아래 2/3)", A[A.liq <= 2 / 3], "onc"); row("대형(위 1/3)", A[A.liq > 2 / 3], "onc")
    head("재료 10분위 끝 (유니버스)")
    for f, nm in feats.items():
        row(nm + " 하위10%", A[A["q_" + f] <= 0.1], "onc"); row(nm + " 상위10%", A[A["q_" + f] >= 0.9], "onc")
    head("조합 (중소형 안 · 둘 다 30% 끝)")
    S = A[A.liq <= 2 / 3]
    pairs = [("clvt", ">=", "vmt", ">="), ("clvt", ">=", "r1t", ">="), ("r1t", ">=", "vmt", ">="), ("clvt", ">=", "rngt", "<="),
             ("r1t", "<=", "clvt", "<="), ("r20t", "<=", "clvt", ">="), ("r5t", "<=", "clvt", ">="), ("gap", "<=", "clvt", ">=")]
    for a, oa, b, ob in pairs:
        ca = S["q_" + a] >= 0.7 if oa == ">=" else S["q_" + a] <= 0.3
        cb = S["q_" + b] >= 0.7 if ob == ">=" else S["q_" + b] <= 0.3
        row("%s %s & %s %s" % (feats[a], "높음" if oa == ">=" else "낮음", feats[b], "높음" if ob == ">=" else "낮음"), S[ca & cb], "onc")
    pd.to_pickle(A[["ticker", "date", "onc", "liq"] + ["q_" + f for f in feats]], ROOT / "cache" / "day2_on.pkl")


def part3():
    P(""); P("## 3) 미장 [갭 하락 조용주] — 국장 조합 그대로 (시가→종가, 비용 0.25%)")
    U, _ = O.build("US")
    U = U[(U.gap0.abs() <= 60)]
    for f in ("gap", "vm", "r20", "d5", "rng"): U["q_" + f] = U.groupby("date")[f].rank(pct=True)
    U["liq"] = U.groupby("date").amt20.rank(pct=True)
    B = U[(U.q_gap <= 0.10) & (U.q_vm <= 0.30)]
    head("미장")
    row("갭 하위10% & 거래량 하위30% (전체)", B)
    row("+ 중소형(아래 2/3)", B[B.liq <= 2 / 3]); row("+ 대형(위 1/3)", B[B.liq > 2 / 3])
    row("+ 중소형 & 20일 하락 하위30%", B[(B.liq <= 2 / 3) & (B.q_r20 <= 0.3)])
    row("+ 중소형 & 고저폭 작음", B[(B.liq <= 2 / 3) & (B.q_rng <= 0.3)])
    for lab, lo, hi in (("갭 -2~0%", -2, 0), ("갭 -5~-2%", -5, -2), ("갭 -5% 아래", -60, -5)):
        row("중소형 · " + lab, B[(B.liq <= 2 / 3) & (B.gap > lo) & (B.gap <= hi)])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    P("# 데이 2단계 · %s" % time.strftime("%Y-%m-%d"))
    A, feats = O.build("KR")
    part1(A.copy())
    A, feats = O.build("KR")                       # build 는 유니버스로 거른 뒤 on 을 이미 계산해 뒀다
    part2(A)
    part3()
    log_trials("day2_%s" % time.strftime("%Y%m%d"), N[0])
    P(""); P("(칸 %d · %.0f분)" % (N[0], (time.time() - t0) / 60))
    (ROOT / "reports" / ("day2_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
