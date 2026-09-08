# -*- coding: utf-8 -*-
"""초단기 규칙 탐색 (보유 1~3일) — 사용자 요청 2026-09-08.

지금 아홉 규칙의 보유일은 5~60일에 몰려 있다. 하락장 6규칙은 월 동조가 0.96 이라
사실상 한 덩어리다([[rule-relations]]). 시간축을 벌리면 그 덩어리를 깬다.

**1단계(이 스크립트) — 축 정찰.** 초단기에 엣지가 있을 만한 축을 넓게 훑는다.
후보를 '본' 순간부터 다중검정 대상이므로 셀 수를 전부 기록한다.
판정은 늘 쓰던 것: **유니버스 대비 초과** · 중앙값 · 상위 5% 제거 평균(복권형 걸러내기) ·
학습 2016~22 / 검증 2023~26 부호 일치 · 월블록 CI.

훑는 축 (우리가 이미 검증한 재료 위주 + 초단기에만 의미 있는 것)
  A 폭락 익일   — 당일 등락률 하위 구간 (해외 카더라에서 유일하게 근접했던 축)
  B 갭          — 시가 갭하락/갭상승 (gap 컬럼)
  C 거래량 폭발  — su1 (당일/20일평균)
  D 위치        — fromhi(52주 고점 대비) · dev25(25일선 이격)
  E 연속 하락   — ret3 · ret5
  F 수급        — fw5(외국인 5일) · ow20(기관 20일)
  G 공매도      — sr20 · srd(공매도 비중 감소)
  H 신용        — cr_chg20
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HS = [1, 2, 3]


def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["chg1"] = (K.close / g.close.shift(1) - 1) * 100        # 당일 등락률
    K["dev25"] = (K.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
    return K


KP = load("panel_kp.pkl", "KOSPI")
KQ = load("panel_kq.pkl", "KOSDAQ")

# 신용잔고는 패널에 없다 — portfolio.py 와 같은 방식으로 별도 DB 에서 붙인다.
import sqlite3
_cc = sqlite3.connect(f"file:{BASE}/data/kis/market.db?mode=ro", uri=True, timeout=600)
_CR = pd.read_sql("SELECT date,ticker,loan_rmnd FROM credit", _cc); _cc.close()
_CR = _CR.sort_values(["ticker", "date"])
_CR["cr_chg20"] = (_CR.loan_rmnd / _CR.groupby("ticker", sort=False).loan_rmnd.shift(20) - 1) * 100
for _K in (KP, KQ):
    _n = len(_K)
    _M = _K.merge(_CR[["date", "ticker", "cr_chg20"]], on=["ticker", "date"], how="left")
    assert len(_M) == _n
    _K["cr_chg20"] = _M.cr_chg20.values
del _CR, _M
import gc; gc.collect()


def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))


UNI = {}
for K in (KP, KQ):
    for h in HS:
        UNI[(id(K), h)] = K.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()


def stat(K, m, h, name):
    """유니버스 대비 초과로 잰다. 중복신호는 보유기간만큼 같은 종목을 막는다."""
    col = f"n{h}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 300:
        return None
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
    if len(X) < 300:
        return None
    X["ex"] = X[col] - X.date.map(UNI[(id(K), h)])
    tr = X[X.date <= TR1].ex
    va = X[X.date >= VA0].ex
    if len(tr) < 100 or len(va) < 50:
        return None
    # 복권형 걸러내기 — 상위 5% 를 빼고도 양수인가
    cut = X.ex.quantile(0.95)
    trim = X[X.ex <= cut].ex.mean()
    mo = X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean()
    ci = verdict.boot_ci(mo, 0.10)
    ly = X[X.date >= "20260101"].ex
    return dict(name=name, h=h, n=len(X), ex=X.ex.mean(), med=X.ex.median(), trim=trim,
                tr=tr.mean(), va=va.mean(), ci=ci,
                ly=ly.mean() if len(ly) >= 10 else np.nan,
                win=(X[col] > 0).mean() * 100)


def axes(K):
    """축별 구간을 만든다. 문턱은 이후 조이기 전 정찰용으로 성기게 잡는다."""
    b = base(K)
    A = {}
    for lo, hi, nm in ((-99, -20, "당일 -20%↓"), (-20, -15, "당일 -20~-15%"),
                       (-15, -10, "당일 -15~-10%"), (-10, -7, "당일 -10~-7%"),
                       (-7, -4, "당일 -7~-4%"), (4, 7, "당일 +4~7%"),
                       (7, 15, "당일 +7~15%"), (15, 99, "당일 +15%↑")):
        A[f"A {nm}"] = b & (K.chg1 > lo) & (K.chg1 <= hi)
    for lo, hi, nm in ((-99, -5, "갭 -5%↓"), (-5, -3, "갭 -5~-3%"), (-3, -1, "갭 -3~-1%"),
                       (1, 3, "갭 +1~3%"), (3, 5, "갭 +3~5%"), (5, 99, "갭 +5%↑")):
        A[f"B {nm}"] = b & (K.gap > lo) & (K.gap <= hi)
    for lo, hi, nm in ((3, 5, "거래량 3~5배"), (5, 10, "거래량 5~10배"), (10, 999, "거래량 10배↑")):
        A[f"C {nm}"] = b & (K.su1 > lo) & (K.su1 <= hi)
    for lo, hi, nm in ((-99, -40, "고점대비 -40%↓"), (-40, -25, "고점대비 -40~-25%"),
                       (-5, 0, "고점 근처")):
        A[f"D {nm}"] = b & (K.fromhi > lo) & (K.fromhi <= hi)
    for lo, hi, nm in ((-99, -20, "25일선 -20%↓"), (-20, -12, "25일선 -20~-12%"),
                       (-12, -7, "25일선 -12~-7%")):
        A[f"D {nm}"] = b & (K.dev25 > lo) & (K.dev25 <= hi)
    for lo, hi, nm in ((-99, -20, "3일 -20%↓"), (-20, -12, "3일 -20~-12%"), (-12, -7, "3일 -12~-7%")):
        A[f"E {nm}"] = b & (K.ret3 > lo) & (K.ret3 <= hi)
    for lo, hi, nm in ((-99, -25, "5일 -25%↓"), (-25, -15, "5일 -25~-15%")):
        A[f"E {nm}"] = b & (K.ret5 > lo) & (K.ret5 <= hi)
    A["F 외국인 5일 3%↑"] = b & (K.fw5 >= 3)
    A["F 기관 20일 0%↑"] = b & (K.ow20 >= 0)
    A["G 공매도 비중 감소"] = b & (K.srd == True)
    A["G 공매도 비중 0.5%↓"] = b & (K.sr20 <= 0.5)
    A["H 신용 20일 -15%↓"] = b & (K.cr_chg20 <= -15)
    A["H 신용 20일 +15%↑"] = b & (K.cr_chg20 >= 15)
    return A


NT = 0
ROWS = []
for K, mk in ((KP, "코스피"), (KQ, "코스닥")):
    A = axes(K)
    print("\n" + "=" * 118)
    print(f"[{mk}] 초단기 축 정찰 — 유니버스 대비 초과(2016~) · 중복신호 제거 · 상위5% 제거 평균 포함")
    print("=" * 118)
    print(f"  {'축':<22}{'보유':>3}{'건수':>8}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
          f"{'학습':>8}{'검증':>8}{'월CI':>8}{'26년':>8}")
    for nm, m in A.items():
        for h in HS:
            NT += 1
            r = stat(K, m, h, nm)
            if r is None:
                continue
            r["mk"] = mk
            ROWS.append(r)
            print(f"  {nm:<22}{h:>3}{r['n']:>8,}{r['ex']:>+8.2f}{r['med']:>+8.2f}{r['trim']:>+8.2f}"
                  f"{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}{r['ci']:>+8.2f}"
                  f"{r['ly']:>+8.2f}")

R = pd.DataFrame(ROWS)
print("\n" + "=" * 118)
print("생존 후보 — 초과>0 · 중앙>0 · 절삭평균>0 · 학습검증 둘 다>0 · 월CI하한>0")
print("=" * 118)
G = R[(R.ex > 0) & (R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0)]
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  [{r.mk}] {r['name']:<22} {r.h}일 · {r.n:>6,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} · 학{r.tr:+.2f} 검{r.va:+.2f} CI{r.ci:+.2f}")
else:
    print("  없음")
R.to_pickle(BASE / "data" / "short_scan.pkl")
verdict.log_trials("초단기 축 정찰", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개 · 결과 data/short_scan.pkl")
