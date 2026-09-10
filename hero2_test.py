# -*- coding: utf-8 -*-
"""[2025 영웅전 수상자 인터뷰] 방타니 트레이더 — '종가 배팅' 만 떼어 실측한다.

영상(51분)의 기법은 대부분 **우리가 검증할 수 없는 종류**다:
  · 재료(텔레그램 뉴스) 기반 진입 — "99%가 뉴스 반응"      → 실시간 뉴스 없음
  · 호가 물량 잡아먹기 — 15,000원 만주를 순식간에 먹는 순간  → 호가·틱 없음
  · 1분씩 3분할 매수 · 물타기 금지 · 불타기                 → 분봉 없음
  · 파란불 뜨면 즉시 손절                                  → [[heroleague-kr]] 에서 기각됨
  · 테마 대장주 급등 추격(20%·25%·상한가 근처)             → [[invert-test]] 13개 전량 기각
회전율 131,181% 가 말해주듯 하루에 계좌를 몇 번씩 도는 스캘핑이고, 우리 체계
(일봉·익일 시가 매수·5~60일 보유)와 시간축이 근본적으로 다르다.

**일봉으로 검증 가능한 한 조각**이 있다 — 종가 배팅:
  "종가에 **어느 섹터로 돈이 쏠리는지** 보고 그 섹터의 **대장**을 산다.
   3시 19분 59초까지 확인한다. 종가에 들어온 섹터가 시간외에 갑자기 죽을 리 없다."
이걸 일봉으로 옮기면: **그날 업종 전체가 크게 오른 업종에서 그 업종의 대장주를
종가에 사서 다음날(또는 며칠) 판다.**

⚠ 한계를 미리 적는다.
 · 영상의 '섹터' 는 테마(로봇·유리기판)인데 우리 테마 자료는 2026-08-28 **한 장뿐**이라
   과거 소속을 복원할 수 없다. KSIC **업종**으로 대신한다 — 테마보다 넓어 신호가 약해질 수 있다.
 · 매수를 **종가**로 잡는다(집안 규율은 익일 시가지만 영상 주장이 종가 매수다).
   대신 매도는 익일 시가·익일 종가·3일·5일을 모두 낸다.
 · 시간외 거래는 우리 자료에 아예 없다. '종가에 사서 다음날' 까지만 잰다.

    python hero2_test.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
from vp_lib import boot_ci

BASE = Path(__file__).parent
TR1, VA0 = "20221231", "20230101"
P = []
for f, mk in (("panel_kp.pkl", "KOSPI"), ("panel_kq.pkl", "KOSDAQ")):
    d = pd.read_pickle(BASE / "data" / f); d["mk"] = mk; P.append(d)
K = pd.concat(P, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
K["pref"] = ~K.ticker.str.endswith("0")
K = K[(~K.pref) & (K.close >= 1000)].copy()
g = K.groupby("ticker", sort=False)
K["r1"] = g.close.pct_change() * 100                     # 당일 수익률
K["nc"] = g.close.shift(-1)                              # 다음날 종가
K["nc3"] = g.close.shift(-3)
K["nc5"] = g.close.shift(-5)
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)

# ── '그날 돈이 쏠린 업종' — 회원 5종목 이상 업종의 당일 수익률 중앙값 ──────────
U = K.dropna(subset=["up", "r1"])
gsz = U.groupby(["date", "up"]).r1.agg(["median", "size"]).reset_index()
gsz = gsz[gsz["size"] >= 5].rename(columns={"median": "ur1"})
gsz["urank"] = gsz.groupby("date").ur1.rank(pct=True)     # 그날 업종 중 몇 등인가
K = K.merge(gsz[["date", "up", "ur1", "urank"]], on=["date", "up"], how="left")

# ── '그 업종의 대장주' — 그날 업종 안에서 상승률 / 거래대금 순위 ────────────
K["lead_r"] = K.groupby(["date", "up"]).r1.rank(ascending=False, method="first")
K["lead_a"] = K.groupby(["date", "up"]).amt.rank(ascending=False, method="first")

# ── 종가 매수 기준 수익 ─────────────────────────────────────────────
K["c2o"] = (K.buy / K.close - 1) * 100 - K.cost           # 종가 매수 → 익일 시가
K["c2c"] = (K.nc / K.close - 1) * 100 - K.cost            # 종가 매수 → 익일 종가
K["c2c3"] = (K.nc3 / K.close - 1) * 100 - K.cost
K["c2c5"] = (K.nc5 / K.close - 1) * 100 - K.cost
LIQ = (K.amt20.fillna(0) >= 3).fillna(False)              # 20일 평균 거래대금 3억 이상
BEN = {c: K[LIQ].dropna(subset=[c]).groupby("date")[c].mean() for c in ("c2o", "c2c", "c2c3", "c2c5")}
NDAY = len([d for d in ud if d >= "20160101"])

HDR = (f"  {'조건':<34} {'n':>6} {'일':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'초과':>7} "
       f"{'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>6}")
def show(tag, cond, col="c2c", lo="20160101", hi="20991231"):
    X = K[(cond & LIQ).fillna(False)].dropna(subset=[col]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + 3; keep.append(ix)               # 3일 안 재진입 금지
    d = X.loc[keep].copy()
    st = d[(d.date >= "20050101") & (d.date <= "20151231")]
    d = d[(d.date >= lo) & (d.date <= hi)]
    if len(d) < 60: print(f"  {tag:<34} {len(d):>6}  (표본 부족)"); return
    d["r"] = d[col].astype(float); d["ex"] = d.r - d.date.map(BEN[col]); d["ym"] = d.date.str[:6]
    stx = (st[col] - st.date.map(BEN[col])).mean() if len(st) >= 60 else np.nan
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<34} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {trim:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{stx:>7.2f} {boot_ci(d.groupby('ym').ex.mean()):>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")

print(f"패널 {len(K):,}행 · 업종 붙은 비율 {K.up.notna().mean()*100:.0f}% · "
      f"업종-일 조합 {len(gsz):,} · 기준구간 {NDAY}일")
print("\n" + "=" * 150)
print("① 업종이 얼마나 올랐을 때 · 대장주를 종가에 사면 (익일 종가 매도)")
print("=" * 150); print(HDR)
for th, nm in ((0.95, "업종 상위 5%"), (0.90, "업종 상위 10%"), (0.80, "업종 상위 20%")):
    for L in (1, 3):
        show(f"  {nm} · 상승률 {L}위 이내", (K.urank >= th) & (K.lead_r <= L))
    print()
for v in (3, 5, 7):
    show(f"  업종 당일 +{v}% 이상 · 대장주", (K.ur1 >= v) & (K.lead_r <= 1))
print()
print("  ── 대장주를 거래대금 1위로 보면 ──")
for th, nm in ((0.95, "업종 상위 5%"), (0.90, "업종 상위 10%")):
    show(f"  {nm} · 거래대금 1위", (K.urank >= th) & (K.lead_a <= 1))

print("\n" + "=" * 150); print("② 언제 파는가 (업종 상위 5% · 상승률 1위)"); print("=" * 150); print(HDR)
C = (K.urank >= 0.95) & (K.lead_r <= 1)
for col, nm in (("c2o", "익일 시가"), ("c2c", "익일 종가"), ("c2c3", "3일 후 종가"), ("c2c5", "5일 후 종가")):
    show(f"  {nm} 매도", C, col=col)

print("\n" + "=" * 150); print("③ 대조군 — 정말 '대장' 이라서인가"); print("=" * 150); print(HDR)
show("  업종 상위5% · 상승률 1위", (K.urank >= 0.95) & (K.lead_r <= 1))
show("  업종 상위5% · 상승률 2~5위", (K.urank >= 0.95) & (K.lead_r >= 2) & (K.lead_r <= 5))
show("  업종 상위5% · 나머지 전부", (K.urank >= 0.95) & (K.lead_r > 5))
show("  업종 상관없이 그날 상승률 1위", K.groupby("date").r1.rank(ascending=False, method="first") <= 1)
show("  업종 하위5% · 상승률 1위", (K.urank <= 0.05) & (K.lead_r <= 1))
try:
    import verdict; verdict.log_trials("hero2_종가배팅", 30)
except Exception as e: print(e)
