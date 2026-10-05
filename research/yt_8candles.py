# -*- coding: utf-8 -*-
"""유튜브 — 박재훈 '100조 운용역이 신입 펀드매니저에게 가르쳤던 차트 패턴 8가지' (2026-10-06 사용자 링크 0JHEax_R7DE).
전제: 상승 전환 패턴은 첫째 날 전에 **3일 이동평균이 5일 연속 하락**, 하락 전환은 5일 연속 상승.
  적삼병/흑삼병 · 상승/하락 잉태 확인형 · 상승장/하락장 확인형 · 샛별형/석별형 (조건은 영상 그대로 — 아래 코드 주석)
'작은 몸통'·'장대' 는 영상이 숫자를 안 줘서 그 종목 20일 평균 몸통 대비 0.5배 이하 · 1.5배 이상으로 정했다.
판정: 셋째 날 다음날 시가 매수 → 5·10·20일 · 같은 날 유니버스(거래대금 상위 40%) 아무 종목 대비 초과(중앙) ·
      국장(이음새 제외) · 미장(폐지 포함 us_scan_full) · 학습 2016~22 / 검증 2023~ / 참고 2005~15.
하락 전환 4종은 '피할 신호' 인지 — 초과가 마이너스면 맞는 것. 추세 조건을 뺀 판도 같이 재서 조건 효과를 본다.
    python research/yt_8candles.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import gh_engine as G
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def patterns(A):
    g = A.groupby("ticker", sort=False)
    S = lambda c, n: g[c].shift(n)
    O, C = A.open, A.close
    o1, c1, o2, c2, o3, c3 = S("open", 2), S("close", 2), S("open", 1), S("close", 1), O, C
    body = (C - O).abs() / O
    avgb = body.groupby(A.ticker).transform(lambda s: s.shift(3).rolling(20, min_periods=15).mean())
    b1, b2, b3 = S_(body, A, 2), S_(body, A, 1), body
    small = lambda b: b <= 0.5 * avgb
    long_ = lambda b: b >= 1.5 * avgb
    ma3 = g.close.transform(lambda s: s.rolling(3).mean())
    d = ma3.groupby(A.ticker).diff()
    # 첫째 날(t-2) 전: t-3 까지 3일선이 5일 연속 하락/상승
    dn5 = (d < 0).astype(float).groupby(A.ticker).transform(lambda s: s.shift(3).rolling(5).sum()) == 5
    up5 = (d > 0).astype(float).groupby(A.ticker).transform(lambda s: s.shift(3).rolling(5).sum()) == 5
    bull = lambda o, c: c > o
    bear = lambda o, c: c < o
    lo = lambda a, b: np.minimum(a, b); hi = lambda a, b: np.maximum(a, b)
    P_ = {}
    # 적삼병: 양봉 셋 · 둘째·셋째 시가가 전날 몸통 안 · 종가 계속 높게(셋째가 가장 높음)
    P_["적삼병"] = (bull(o1, c1) & bull(o2, c2) & bull(o3, c3) & o2.between(o1, c1) & (o3 >= o2) & (o3 <= c2) & (c2 > c1) & (c3 > c2), dn5)
    P_["흑삼병"] = (bear(o1, c1) & bear(o2, c2) & bear(o3, c3) & (o2 <= o1) & (o2 >= c1) & (o3 <= o2) & (o3 >= c2) & (c2 < c1) & (c3 < c2), up5)
    # 상승 잉태 확인형: 첫날 음봉 · 둘째 몸통이 첫날 몸통 안(양끝이 다 같지는 않게) · 셋째 장대 양봉 · 셋째 종가 > 첫날 시가
    inside2 = (hi(o2, c2) <= hi(o1, c1)) & (lo(o2, c2) >= lo(o1, c1)) & ~((hi(o2, c2) == hi(o1, c1)) & (lo(o2, c2) == lo(o1, c1)))
    P_["상승 잉태 확인형"] = (bear(o1, c1) & inside2 & bull(o3, c3) & long_(b3) & (c3 > o1), dn5)
    P_["하락 잉태 확인형"] = (bull(o1, c1) & inside2 & bear(o3, c3) & long_(b3) & (c3 < o1), up5)
    # 상승장 확인형: 작은 음봉 → 시가가 전날 종가보다 낮은 장대 양봉 → 양봉, 종가가 둘째보다 높게
    P_["상승장 확인형"] = (bear(o1, c1) & small(b1) & bull(o2, c2) & long_(b2) & (o2 < c1) & bull(o3, c3) & (c3 > c2), dn5)
    P_["하락장 확인형"] = (bull(o1, c1) & small(b1) & bear(o2, c2) & long_(b2) & (o2 > c1) & (c2 < o1) & bear(o3, c3) & (c3 < c2), up5)
    # 샛별형: 장대 음봉 → 몸통이 갭 하락한 봉(십자 아님) → 몸통이 갭 상승한 양봉, 종가가 첫날 몸통 절반 위
    P_["샛별형"] = (bear(o1, c1) & long_(b1) & (hi(o2, c2) < c1) & (o2 != c2) & (o3 > hi(o2, c2)) & bull(o3, c3) & (c3 > (o1 + c1) / 2), dn5)
    P_["석별형"] = (bull(o1, c1) & long_(b1) & (lo(o2, c2) > c1) & (o2 != c2) & (o3 < lo(o2, c2)) & bear(o3, c3) & (c3 < (o1 + c1) / 2), up5)
    return P_


def S_(s, A, n):
    return s.groupby(A.ticker).shift(n)


def run(mk):
    t0 = time.time()
    A = G.load(mk, full=(mk == "US"))
    P_ = patterns(A)
    P("## %s — %s행 · 준비 %.0f초" % ("국장" if mk == "KR" else "미장(폐지 포함)", f"{len(A):,}", time.time() - t0)); P("")
    P("| 패턴 | 추세 조건 | 보유 | 학습 16~22 | 검증 23~ | 참고 05~15 |"); P("|---|---|---|---|---|---|")
    bm = {h: G.bench(A, h) for h in (5, 10, 20)}
    n = 0
    for name, (pat, trend) in P_.items():
        for tl, sig in (("있음(영상대로)", pat & trend), ("없음", pat)):
            for h in (5, 10, 20):
                Y = G.simulate(A, sig.fillna(False), mk, exit="hold", H=h)
                r = G.report(Y, name, bm[h]); n += 1
                cells = []
                for s in r["rows"]:
                    cells.append("-" if not s else "%d건 · 평균 %+.2f · 중앙 %+.2f · 승률 %.0f%% · 초과 %+.2f · %d/%d해" % (s["n"], s["m"], s["med"], s["win"], s["ex"], s["yp"], s["ny"]))
                P("| %s | %s | %d일 | %s | %s | %s |" % (name, tl, h, *cells))
    P("")
    return n


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    P("# 유튜브 차트 패턴 8가지(박재훈) 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("매수 = 셋째 날 다음날 시가 · 비용 = 우리 스윙 비용(국장 0.35~1.15% · 미장 0.10~0.60%) · 초과 = 같은 날 유니버스 아무 종목 같은 보유 대비(중앙)"); P("")
    n = run("KR") + run("US")
    log_trials("yt_8candles_%s" % time.strftime("%Y%m%d"), n)
    P("(칸 %d · %.0f분)" % (n, (time.time() - t0) / 60))
    (ROOT / "reports" / ("yt_8candles_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
