# -*- coding: utf-8 -*-
"""**주봉 연속 하락 뒤 2주 반등** — 국내·미장 (2026-09-16 요청).

물음: "주봉 기준으로 5주나 7주 10주 이상 하락하다가 2주 연속 상승한 종목.
       하락할 때의 하락률에 대한 비교값도 같이."

지금까지 반전 계열은 전부 **일봉**으로만 봤다(20일 -30%, 60일 이격 등). 주봉은 처음이다.
주봉이 다른 점은 **잡음이 깎인다**는 것이다 — 일봉 5일 연속 하락은 흔하지만
주봉 5주 연속 하락은 한 달 넘게 쉬지 않고 밀렸다는 뜻이다.

  ① 재료 만들기 — 연속 하락 주수 분포
  ② 하락 주수별 (3~12주) · 보유 20일
  ③ 보유기간별 (10·20·40·60일)
  ④ **하락률 축** — 같은 주수라도 얼마나 빠졌나로 갈리나
  ⑤ 교차표 — 주수 × 하락률
  ⑥ 반등 주수 1주 / 2주 / 3주
  ⑦ 미장에서 같은 표

판정 규율은 집안 정본이다.
  · 매수는 **신호 주의 마지막 거래일 다음날 시가**(패널 buy), 비용 차감
  · 같은 종목 중복 제거(보유기간 안에는 한 번만)
  · 판정은 **같은 날 유니버스 대비 초과** — 지수와 견주지 않는다
  · 중앙값 + **상위 5% 절삭평균**(복권형 거르기) + 연도별 양수 개수
  · 학습 2016~22 / 검증 2023~26 분리, 월블록 부트스트랩 신뢰구간

⚠ 주봉은 **미래참조가 나기 쉽다**. "그 주의 종가"를 쓰려면 그 주가 **끝나야** 한다.
   그래서 신호일은 언제나 그 주의 **마지막 거래일**이고 매수는 그 다음 거래일이다.
   주 중간에는 신호를 낼 수 없다.

    python week_reversal.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from vp_lib import Runner, hdr, boot_ci

BASE = Path(__file__).parent
W = 150
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


def weekly(K):
    """일봉에서 주봉 재료를 만들어 **신호일(주 마지막 거래일)** 에 붙여 돌려준다.

    돌려주는 것: down_n(직전 연속 하락 주수) · drop(그 구간 누적 하락률%) · up_n(연속 상승 주수)
    """
    dt = pd.to_datetime(K.date, format="%Y%m%d")
    K = K.assign(_wk=(dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.strftime("%Y%m%d"))
    # 주봉 = 그 주 마지막 거래일의 종가. 그 거래일이 곧 신호일이 된다.
    Wk = (K.groupby(["ticker", "_wk"], sort=True)
            .agg(date=("date", "last"), close=("close", "last")).reset_index())
    Wk = Wk.sort_values(["ticker", "_wk"]).reset_index(drop=True)
    g = Wk.groupby("ticker", sort=False)
    # 주 사이가 끊기면(상장 전·거래 정지) 연속으로 세면 안 된다 — 7일 간격만 인정한다
    wdt = pd.to_datetime(Wk._wk, format="%Y%m%d")
    cont = (wdt - wdt.groupby(Wk.ticker).shift(1)).dt.days.eq(7).fillna(False)
    prev = g.close.shift(1)
    wret = (Wk.close / prev - 1) * 100
    dn = ((wret < 0) & cont).fillna(False)
    up = ((wret > 0) & cont).fillna(False)
    # 연속 하락 주수 — 하락이 끊긴 지점마다 묶음 번호를 새로 매겨 누적한다
    blk = (~dn).groupby(Wk.ticker).cumsum()
    Wk["dn_n"] = dn.astype(int).groupby([Wk.ticker, blk]).cumsum()
    blk2 = (~up).groupby(Wk.ticker).cumsum()
    Wk["up_n"] = up.astype(int).groupby([Wk.ticker, blk2]).cumsum()
    # 하락 구간의 시작 종가 = 하락이 아니었던 마지막 주의 종가(ffill 로 끌어온다)
    base = Wk.close.where(~dn).groupby(Wk.ticker).ffill()
    Wk["fall"] = (Wk.close / base - 1) * 100          # 하락 구간 누적 등락(음수)
    return Wk


def build(Wk, K):
    """주봉 재료를 **일봉 신호일 행**에 붙인다 — 매수·수익률은 일봉 쪽 것을 쓴다."""
    g = Wk.groupby("ticker", sort=False)
    # 신호 주 t 에서 보는 것: up_n(t) · dn_n(t-up_n) · drop(t-up_n)
    out = {}
    for u in (1, 2, 3):
        dn_prev = g.dn_n.shift(u)
        dp_prev = g.fall.shift(u)
        ok = (Wk.up_n >= u) & (dn_prev >= 1)
        out[u] = pd.DataFrame({"ticker": Wk.ticker, "date": Wk.date,
                               "dn_n": dn_prev, "fall": dp_prev, "up_n": Wk.up_n})[ok.fillna(False)]
    return out


def market(name, K, uni, since="20160101"):
    sec("【%s】" % name)
    log("주봉 만드는 중")
    Wk = weekly(K)
    SIG = build(Wk, K)
    log("  주봉 %s행 · 신호후보(2주 반등) %s건" % (f"{len(Wk):,}", f"{len(SIG[2]):,}"))

    R = Runner(K, uni, name, since=since)
    KEY = (K.ticker + K.date)

    def mask(S, dnlo, dnhi=99, lo=-1e9, hi=1e9):
        z = S[(S.dn_n >= dnlo) & (S.dn_n <= dnhi) & (S.fall > lo) & (S.fall <= hi)]
        return KEY.isin(set(z.ticker + z.date))

    print("\n① 연속 하락 주수 분포 (2주 연속 상승한 것만)")
    d = SIG[2].dn_n.value_counts().sort_index()
    print("  " + "  ".join("%d주:%s" % (i, f"{int(v):,}") for i, v in d.items() if i <= 14))
    print("  15주 이상 %s건 · 전체 %s건" % (f"{int(d[d.index >= 15].sum()):,}", f"{len(SIG[2]):,}"))

    hdr("② 연속 하락 주수별 — 2주 반등 · 보유 20일")
    RES = {}
    for lo, hi, lbl in [(3, 3, "3주"), (4, 4, "4주"), (5, 5, "5주"), (6, 6, "6주"),
                        (7, 7, "7주"), (8, 9, "8~9주"), (10, 12, "10~12주"), (13, 99, "13주↑"),
                        (5, 99, "5주 이상(합)"), (7, 99, "7주 이상(합)"), (10, 99, "10주 이상(합)")]:
        RES[lbl] = R.run("연속하락 %s → 2주 반등" % lbl, mask(SIG[2], lo, hi), hold=20, minn=30)

    hdr("③ 보유기간별 — 주수 묶음마다")
    for lo, hi, lbl in [(5, 6, "5~6주"), (7, 9, "7~9주"), (10, 99, "10주↑")]:
        for h in (10, 20, 40, 60):
            R.run("연속하락 %s → 2주 반등 · %d일" % (lbl, h), mask(SIG[2], lo, hi), hold=h, minn=30)
        print()

    hdr("④ 하락률 축 — 5주 이상 하락한 것만, 누적 하락률로 가름")
    for lo, hi, lbl in [(-1e9, -50, "-50% 아래"), (-50, -40, "-40~-50%"), (-40, -30, "-30~-40%"),
                        (-30, -20, "-20~-30%"), (-20, -15, "-15~-20%"), (-15, -10, "-10~-15%"),
                        (-10, -5, "-5~-10%"), (-5, 0, "-5% 이내")]:
        R.run("5주↑ 하락 · 낙폭 %s" % lbl, mask(SIG[2], 5, 99, lo, hi), hold=20, minn=30)

    hdr("⑤ 교차 — 주수 × 하락률 (보유 20일)")
    for wlo, whi, wl in [(3, 4, "3~4주"), (5, 6, "5~6주"), (7, 9, "7~9주"), (10, 99, "10주↑")]:
        for dlo, dhi, dl in [(-1e9, -30, "-30%↓"), (-30, -20, "-20~-30%"),
                             (-20, -10, "-10~-20%"), (-10, 0, "-10% 이내")]:
            R.run("%s · %s" % (wl, dl), mask(SIG[2], wlo, whi, dlo, dhi), hold=20, minn=30)
        print()

    hdr("⑥ 반등 주수 — 1주 / 2주 / 3주 (5주 이상 하락)")
    for u in (1, 2, 3):
        R.run("5주↑ 하락 → %d주 반등" % u, mask(SIG[u], 5, 99), hold=20, minn=30)
    print()
    for u in (1, 2, 3):
        R.run("7주↑ 하락 → %d주 반등" % u, mask(SIG[u], 7, 99), hold=20, minn=30)
    return RES


log("국내 패널 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
AR = K.groupby("date").amt20.rank(pct=True)
UNI_K = (AR >= 0.60).fillna(False)      # 그날 거래대금 상위 40% — 집안 기준
log("  %s행 · %s종목" % (f"{len(K):,}", f"{K.ticker.nunique():,}"))
market("국내 (코스피+코스닥 · 거래대금 상위40%)", K, UNI_K)
del K, AR, UNI_K

log("미장 패널 읽는 중")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)]
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
AU = U.groupby("date").amt20.rank(pct=True)
UNI_U = (AU >= 0.60).fillna(False)
log("  %s행 · %s종목" % (f"{len(U):,}", f"{U.ticker.nunique():,}"))
market("미장 (거래대금 상위40%)", U, UNI_U)

print("\n총 %.0f초" % (time.time() - t0))
