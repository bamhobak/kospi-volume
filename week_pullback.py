# -*- coding: utf-8 -*-
"""**주봉 연속 상승 뒤 2주 눌림** — 국내·미장 (2026-09-16 요청).

물음: "반대로 5주 7주 10주 상승하다가 2주 연속 하락한 건 어때?"

앞의 `week_reversal.py`(하락 뒤 반등)는 양쪽 시장에서 전부 음수였다. 이건 그 거울인데
**성격이 정반대**다. 하락 뒤 반등은 '남이 먼저 산 자리' 를 늦게 따라가는 것이고,
이건 오르던 추세가 **잠깐 쉬는 자리**를 사는 것이다 — 우리 집안 규칙 중
[조용한 신고가]·[잔잔한 급등주]가 추세 유지형이라 **결이 맞는다**.

미장은 추세유지형, 국내는 낙폭반전형이라는 게 이 집안의 결론이므로([[us-market-character-n1]])
**미장 쪽에서 살아날 가능성이 더 크다**고 보고 들어간다.

  ① 재료 — 연속 상승 주수 분포
  ② 상승 주수별 (3~12주) · 2주 눌림 · 보유 20일
  ③ 보유기간별 (10·20·40·60일)
  ④ **상승률 축** — 얼마나 올랐던 종목이 눌렸나
  ⑤ 교차 — 주수 × 상승률
  ⑥ 눌림 주수 1주 / 2주 / 3주
  ⑦ **되돌림 깊이 축** — 눌림이 얕아야 좋나 깊어야 좋나

판정 규율은 집안 정본이다(week_reversal.py 와 같다).
  · 매수는 신호 주의 **마지막 거래일 다음날 시가**, 비용 차감 · 같은 종목 중복 제거
  · 같은 날 **유니버스 대비 초과** · 중앙값 + 상위5% 절삭평균 · 연도별 양수 개수
  · 학습 2016~22 / 검증 2023~26 · 월블록 부트스트랩 신뢰구간

    python week_pullback.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from vp_lib import Runner, hdr

BASE = Path(__file__).parent
W = 150
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


def weekly(K):
    """주봉 재료. 앞 스크립트의 거울이라 **상승** 쪽을 센다.

    up_n   : 그 주까지의 연속 상승 주수
    rise   : 그 상승 구간의 누적 상승률(%)
    dn_n   : 그 주까지의 연속 하락 주수
    back   : 그 하락 구간의 누적 하락률(%) — 되돌림 깊이
    """
    dt = pd.to_datetime(K.date, format="%Y%m%d")
    K = K.assign(_wk=(dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.strftime("%Y%m%d"))
    Wk = (K.groupby(["ticker", "_wk"], sort=True)
            .agg(date=("date", "last"), close=("close", "last")).reset_index())
    Wk = Wk.sort_values(["ticker", "_wk"]).reset_index(drop=True)
    g = Wk.groupby("ticker", sort=False)
    wdt = pd.to_datetime(Wk._wk, format="%Y%m%d")
    cont = (wdt - wdt.groupby(Wk.ticker).shift(1)).dt.days.eq(7).fillna(False)
    wret = (Wk.close / g.close.shift(1) - 1) * 100
    up = ((wret > 0) & cont).fillna(False)
    dn = ((wret < 0) & cont).fillna(False)
    Wk["up_n"] = up.astype(int).groupby([Wk.ticker, (~up).groupby(Wk.ticker).cumsum()]).cumsum()
    Wk["dn_n"] = dn.astype(int).groupby([Wk.ticker, (~dn).groupby(Wk.ticker).cumsum()]).cumsum()
    Wk["rise"] = (Wk.close / Wk.close.where(~up).groupby(Wk.ticker).ffill() - 1) * 100
    Wk["back"] = (Wk.close / Wk.close.where(~dn).groupby(Wk.ticker).ffill() - 1) * 100
    return Wk


def build(Wk):
    """눌림 주수 d 마다 신호표를 만든다 — 신호 주 t 는 눌림의 마지막 주다."""
    g = Wk.groupby("ticker", sort=False)
    out = {}
    for d in (1, 2, 3):
        up_prev = g.up_n.shift(d)       # 눌림 직전의 연속 상승 주수
        ri_prev = g.rise.shift(d)       # 그때까지의 누적 상승률
        ok = (Wk.dn_n >= d) & (up_prev >= 1)
        out[d] = pd.DataFrame({"ticker": Wk.ticker, "date": Wk.date, "up_n": up_prev,
                               "rise": ri_prev, "back": Wk.back})[ok.fillna(False)]
    return out


def market(name, K, uni, since="20160101"):
    sec("【%s】" % name)
    log("주봉 만드는 중")
    Wk = weekly(K)
    SIG = build(Wk)
    log("  주봉 %s행 · 신호후보(2주 눌림) %s건" % (f"{len(Wk):,}", f"{len(SIG[2]):,}"))

    R = Runner(K, uni, name, since=since)
    KEY = (K.ticker + K.date)

    def mask(S, ulo, uhi=99, rlo=-1e9, rhi=1e9, blo=-1e9, bhi=1e9):
        z = S[(S.up_n >= ulo) & (S.up_n <= uhi)
              & (S.rise > rlo) & (S.rise <= rhi)
              & (S.back > blo) & (S.back <= bhi)]
        return KEY.isin(set(z.ticker + z.date))

    print("\n① 연속 상승 주수 분포 (2주 연속 하락한 것만)")
    d = SIG[2].up_n.value_counts().sort_index()
    print("  " + "  ".join("%d주:%s" % (i, f"{int(v):,}") for i, v in d.items() if i <= 14))
    print("  15주 이상 %s건 · 전체 %s건" % (f"{int(d[d.index >= 15].sum()):,}", f"{len(SIG[2]):,}"))

    hdr("② 연속 상승 주수별 — 2주 눌림 · 보유 20일")
    for lo, hi, lbl in [(3, 3, "3주"), (4, 4, "4주"), (5, 5, "5주"), (6, 6, "6주"),
                        (7, 7, "7주"), (8, 9, "8~9주"), (10, 12, "10~12주"), (13, 99, "13주↑"),
                        (5, 99, "5주 이상(합)"), (7, 99, "7주 이상(합)"), (10, 99, "10주 이상(합)")]:
        R.run("연속상승 %s → 2주 눌림" % lbl, mask(SIG[2], lo, hi), hold=20, minn=30)

    hdr("③ 보유기간별")
    for lo, hi, lbl in [(3, 4, "3~4주"), (5, 6, "5~6주"), (7, 9, "7~9주"), (10, 99, "10주↑")]:
        for h in (10, 20, 40, 60):
            R.run("연속상승 %s → 2주 눌림 · %d일" % (lbl, h), mask(SIG[2], lo, hi), hold=h, minn=30)
        print()

    hdr("④ 상승률 축 — 5주 이상 오른 것만, 누적 상승률로 가름")
    for lo, hi, lbl in [(0, 10, "+10% 이내"), (10, 20, "+10~20%"), (20, 30, "+20~30%"),
                        (30, 50, "+30~50%"), (50, 100, "+50~100%"), (100, 1e9, "+100% 이상")]:
        R.run("5주↑ 상승 · 상승폭 %s" % lbl, mask(SIG[2], 5, 99, lo, hi), hold=20, minn=30)

    hdr("⑤ 교차 — 주수 × 상승률 (보유 20일)")
    for ulo, uhi, ul in [(3, 4, "3~4주"), (5, 6, "5~6주"), (7, 9, "7~9주"), (10, 99, "10주↑")]:
        for rlo, rhi, rl in [(0, 15, "+15% 이내"), (15, 30, "+15~30%"),
                             (30, 60, "+30~60%"), (60, 1e9, "+60% 이상")]:
            R.run("%s · %s" % (ul, rl), mask(SIG[2], ulo, uhi, rlo, rhi), hold=20, minn=30)
        print()

    hdr("⑥ 눌림 주수 — 1주 / 2주 / 3주")
    for lbl, lo in (("5주↑ 상승", 5), ("7주↑ 상승", 7)):
        for d_ in (1, 2, 3):
            R.run("%s → %d주 눌림" % (lbl, d_), mask(SIG[d_], lo, 99), hold=20, minn=30)
        print()

    hdr("⑦ 되돌림 깊이 — 5주 이상 상승 뒤 2주 눌림이 얼마나 깊었나")
    for blo, bhi, bl in [(-1e9, -25, "-25% 아래"), (-25, -15, "-15~-25%"), (-15, -10, "-10~-15%"),
                         (-10, -6, "-6~-10%"), (-6, -3, "-3~-6%"), (-3, 0, "-3% 이내")]:
        R.run("5주↑ 상승 · 눌림 %s" % bl, mask(SIG[2], 5, 99, blo=blo, bhi=bhi), hold=20, minn=30)
    print()
    for blo, bhi, bl in [(-1e9, -15, "-15% 아래"), (-15, -8, "-8~-15%"), (-8, 0, "-8% 이내")]:
        for h in (40, 60):
            R.run("5주↑ 상승 · 눌림 %s · %d일" % (bl, h), mask(SIG[2], 5, 99, blo=blo, bhi=bhi),
                  hold=h, minn=30)


log("국내 패널 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
UNI_K = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
log("  %s행 · %s종목" % (f"{len(K):,}", f"{K.ticker.nunique():,}"))
market("국내 (코스피+코스닥 · 거래대금 상위40%)", K, UNI_K)
del K, UNI_K

log("미장 패널 읽는 중")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)]
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
UNI_U = (U.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
log("  %s행 · %s종목" % (f"{len(U):,}", f"{U.ticker.nunique():,}"))
market("미장 (거래대금 상위40%)", U, UNI_U)

print("\n총 %.0f초" % (time.time() - t0))
