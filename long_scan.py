# -*- coding: utf-8 -*-
"""장기 규칙 탐색 (보유 120~250일) — 사용자 요청 2026-09-08.

지금 아홉 규칙은 5~60일에 몰려 있다. 긴 쪽을 채우면 시간축이 벌어져 국면 한 번에
아홉이 같이 흔들리는 구조를 깬다([[rule-relations]] 월동조 0.96).

장기에서만 의미가 생기는 재료를 위주로 훑는다. 며칠짜리 반등에는 안 듣지만
1년을 두면 값을 하는 것들 — **밸류에이션·재무·주식수·장기 소외**.
  V 밸류    PBR · PER · BPS 대비 주가
  F 재무    부채비율
  L 장기소외 52주 신고가 대비 · 1년 수익률 · 20일선 위 비율(above20) · 2M/1Y 거래량(r16)
  M 규모    시가총액
  S 수급    외국인 60일 · 기관 60일 · 공매도 비중
  X 장기낙폭 120일 수익률 · 250일 수익률

수익 컬럼은 long_prep.py 가 만든 data/long_ret_*.pkl (n120·n180·n250) 을 쓴다.
판정: 유니버스 대비 초과 · 중앙값 · 상위5% 절삭 · 학습 2016~22 / 검증 2023~26 ·
월블록 CI · 양수해 비율. 장기는 표본이 겹치므로 **중복신호 제거**가 특히 중요하다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HS = [120, 250]


def load(f, tag, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    L = pd.read_pickle(BASE / "data" / f"long_ret_{tag}.pkl")
    K = K.merge(L, on=["ticker", "date"], how="left")
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["ret250x"] = (K.close / g.close.shift(250) - 1) * 100
    ma20 = g.close.transform(lambda s: s.rolling(20).mean())
    K["above20x"] = (K.close > ma20).groupby(K.ticker).transform(
        lambda s: s.rolling(250, min_periods=80).mean()) * 100
    K["r16x"] = K.a40 / K.a240 * 100
    K["cap조"] = K.marcap / 1e12
    return K


KP = load("panel_kp.pkl", "kp", "KOSPI")
KQ = load("panel_kq.pkl", "kq", "KOSDAQ")


def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))


# ⚠ 기준선은 **우리가 실제로 고를 수 있는 종목**의 평균이어야 한다.
# 처음엔 전 종목으로 쟀는데(우선주·1000원 미만·유상증자·거래대금 미달 포함) 두 방향
# 모두 틀렸다. 전 종목 평균은 소수 급등주가 끌어올려 132셀 전부 중앙값 음수가 됐고,
# 전 종목 중앙값으로 바꾸니 '시총 1조 이상' 같은 단순 필터까지 통과해 잣대가 무의미해졌다.
# 우리 계좌는 base() 를 통과한 종목 중 몇 개를 동일가중으로 담는다. 그러니 정직한 잣대는
# **base() 유니버스의 평균**이다(무작위로 골라 같은 기간 담았을 때의 기대값).
UNI, UNIM = {}, {}
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    B = K[base(K)]
    for h in HS:
        z = B.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"]
        UNI[(mk, h)] = z.mean()          # 판정 기준
        UNIM[(mk, h)] = z.median()       # 참고용(치우침 확인)


def stat(K, mk, m, h, name):
    col = f"n{h}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 200:
        return None
    # 중복신호 제거 — 장기는 같은 종목이 몇 달 내내 조건을 만족하기 쉽다
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di)
    X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    X = X.loc[keep]
    if len(X) < 60:
        return None
    X["ex"] = X[col] - X.date.map(UNI[(mk, h)])          # 평균 기준
    X["exm"] = X[col] - X.date.map(UNIM[(mk, h)])        # 중앙 기준
    tr, va = X[X.date <= TR1], X[X.date >= VA0]
    if len(tr) < 30 or len(va) < 15:
        return None
    cut = X.ex.quantile(0.95)
    mo = X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean()
    yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
    return dict(name=name, h=h, n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                trim=X[X.ex <= cut].ex.mean(), tr=tr.ex.mean(), va=va.ex.mean(),
                exm=X.exm.mean(), medm=X.exm.median(),
                trimm=X[X.exm <= X.exm.quantile(0.95)].exm.mean(),
                ci=verdict.boot_ci(mo, 0.10), win=(X[col] > 0).mean() * 100,
                pos_years=int((yr > 0).sum()), n_years=len(yr))


def axes(K):
    b = base(K)
    A = {}
    for lo, hi, nm in ((0, 0.3, "PBR ≤0.3"), (0, 0.5, "PBR ≤0.5"), (0, 0.8, "PBR ≤0.8"),
                       (0, 1.2, "PBR ≤1.2"), (3, 99, "PBR ≥3")):
        A[f"V {nm}"] = b & (K.PBR > lo) & (K.PBR <= hi) if hi < 3 else b & (K.PBR >= lo)
    A["V PBR ≤0.5 + PER ≤10"] = b & (K.PBR > 0) & (K.PBR <= 0.5) & (K.PER > 0) & (K.PER <= 10)
    A["V PBR ≤0.8 + PER ≤15"] = b & (K.PBR > 0) & (K.PBR <= 0.8) & (K.PER > 0) & (K.PER <= 15)
    A["F 부채비율 ≤100%"] = b & (K["부채비율"] <= 100)
    A["F 부채비율 ≤50%"] = b & (K["부채비율"] <= 50)
    A["F 부채 ≤100 + PBR ≤0.8"] = b & (K["부채비율"] <= 100) & (K.PBR > 0) & (K.PBR <= 0.8)
    for lo, hi, nm in ((-99, -60, "고점대비 -60%↓"), (-60, -40, "고점대비 -60~-40%"),
                       (-40, -25, "고점대비 -40~-25%")):
        A[f"L {nm}"] = b & (K.fromhi > lo) & (K.fromhi <= hi)
    A["L 1년수익 -50%↓"] = b & (K.ret250x <= -50)
    A["L 1년수익 -50~-30%"] = b & (K.ret250x > -50) & (K.ret250x <= -30)
    A["L 20일선위 비율 ≤30%"] = b & (K.above20x <= 30)
    A["L 20일선위 비율 ≥70%"] = b & (K.above20x >= 70)
    A["L 2M/1Y 거래량 ≤60%"] = b & (K.r16x <= 60)
    A["L 소외 3종(고점·1년·거래량)"] = b & (K.fromhi <= -40) & (K.ret250x <= -30) & (K.r16x <= 80)
    A["M 시총 ≤1000억"] = b & (K["cap조"] <= 0.1)
    A["M 시총 1000억~1조"] = b & (K["cap조"] > 0.1) & (K["cap조"] <= 1)
    A["M 시총 ≥1조"] = b & (K["cap조"] >= 1)
    A["S 외국인 60일 ≥1%"] = b & (K.fw60 >= 1)
    A["S 기관 60일 ≥1%"] = b & (K.ow60 >= 1)
    A["S 공매도 비중 ≤0.3%"] = b & (K.sr20 <= 0.3)
    A["X 120일 -40%↓"] = b & (K.ret120 <= -40)
    A["X 250일 -50%↓"] = b & (K.ret250x <= -50)
    # 조합 — 밸류 × 소외 (장기에서 가장 그럴듯한 축)
    A["VL PBR≤0.8 + 고점 -40%↓"] = b & (K.PBR > 0) & (K.PBR <= 0.8) & (K.fromhi <= -40)
    A["VL PBR≤0.5 + 고점 -40%↓"] = b & (K.PBR > 0) & (K.PBR <= 0.5) & (K.fromhi <= -40)
    A["VL PBR≤0.8 + 1년 -30%↓"] = b & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret250x <= -30)
    A["VL PBR≤0.8 + 거래량침체"] = b & (K.PBR > 0) & (K.PBR <= 0.8) & (K.r16x <= 60)
    A["VLF PBR≤0.8 + 고점-40 + 부채≤100"] = (b & (K.PBR > 0) & (K.PBR <= 0.8)
                                          & (K.fromhi <= -40) & (K["부채비율"] <= 100))
    A["VLS PBR≤0.8 + 고점-40 + 외인60"] = (b & (K.PBR > 0) & (K.PBR <= 0.8)
                                        & (K.fromhi <= -40) & (K.fw60 >= 0))
    return A


NT = 0
ROWS = []
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    A = axes(K)
    print("\n" + "=" * 124)
    print(f"[{mk}] 장기 축 정찰 — 유니버스 대비 초과(2016~) · 중복신호 제거 · 상위5% 절삭 포함")
    print("=" * 124)
    print("  ※ 기준선 = base() 유니버스 **평균**(우리가 고를 수 있는 종목만). 중앙초과는 참고")
    print(f"  {'축':<30}{'보유':>5}{'건수':>8}{'초과':>9}{'중앙':>9}{'절삭':>9}{'중앙초과':>9}"
          f"{'승률':>6}{'학습':>9}{'검증':>9}{'월CI':>9}{'양수해':>7}")
    for nm, m in A.items():
        for h in HS:
            NT += 1
            r = stat(K, mk, m, h, nm)
            if r is None:
                continue
            r["mk"] = mk
            ROWS.append(r)
            print(f"  {nm:<30}{h:>5}{r['n']:>8,}{r['ex']:>+9.2f}{r['med']:>+9.2f}"
                  f"{r['trim']:>+9.2f}{r['exm']:>+9.2f}{r['win']:>5.0f}%{r['tr']:>+9.2f}"
                  f"{r['va']:>+9.2f}{r['ci']:>+9.2f}{r['pos_years']:>4}/{r['n_years']}")

R = pd.DataFrame(ROWS)
print("\n" + "=" * 124)
print("생존 후보 — base() 유니버스 평균 기준 · 중앙>0 · 절삭>0 · 학습·검증>0 · 월CI>0 · 양수해 70%↑")
print("=" * 124)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0) &
      (R.pos_years / R.n_years >= 0.7)]
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  [{r.mk}] {r['name']:<30} {r.h}일 · {r.n:>5,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} CI{r.ci:+.2f} "
              f"양수해 {r.pos_years}/{r.n_years}")
else:
    print("  없음")
R.to_pickle(BASE / "data" / "long_scan.pkl")
verdict.log_trials("장기 축 정찰", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개 · 결과 data/long_scan.pkl")
