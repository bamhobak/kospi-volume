# -*- coding: utf-8 -*-
"""물타기 실측 — 손실 중 추가매수가 정말 계좌를 죽이는가.

계기: TraderKim [97% 트레이더가 돈을 잃는 이유] (2026-09-11 사용자 링크).
영상 자체는 심리·습관 이야기라 실측할 기법이 없다. 다만 화자의 핵심 실패담이
**카드론으로 물타기하다 전액 손실**이고, 우리 체계에는 [외인 매집]의 **불타기**
(신호가 이어지고 이미 이익일 때 추가매수, 754건 평균 +17.34% 로 채택)만 있을 뿐
**물타기는 한 번도 재본 적이 없다.** 그것만 잰다.

방식 — 거래 단위로 원본과 물타기를 나란히 낸다.
  원본    신호일 다음날 시가에 1주 사서 보유기간 끝에 판다
  물타기  같은 자리에서 사고, 보유 중 **매수가 대비 -X% 아래로 종가가 닫히면**
          같은 금액을 한 번 더 산다. 두 몫 모두 원래 청산일에 판다.
  (참고) 불타기  같은 자리에서 사고, **+X% 위로 닫히면** 한 번 더 산다.

보는 값: 평균·중앙값·상위5% 절삭평균·**최악 5%**·**한 거래 최대손실**·승률.
물타기는 평균을 올리면서 꼬리를 키우는 경향이 있다 — 평균만 보면 속는다.
비중이 두 배가 되므로 **계좌에 주는 충격**을 보려면 최악 쪽을 봐야 한다.

    python mulddagi.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
src = open(BASE / "portfolio.py", encoding="utf-8").read().split("# @@ANALYSIS")[0]
exec(src.split('"""', 2)[2])          # 규칙·신호표(S)·패널을 그대로 빌려 쓴다

# 종목별 종가 경로 — 물타기 지점을 찾으려면 보유 중 일별 종가가 필요하다
PAN = {}
for f, mk in (("panel_kp.pkl", "KP"), ("panel_kq.pkl", "KQ")):
    d = pd.read_pickle(BASE / "data" / f)[["ticker", "date", "close", "low"]]
    PAN[mk] = d
ALL = pd.concat(PAN.values(), ignore_index=True).drop_duplicates(["ticker", "date"])
ALL = ALL.sort_values(["ticker", "date"]).reset_index(drop=True)
ALL["di"] = ALL.date.map(DI)
CL = {t: g[["di", "close"]].values for t, g in ALL.groupby("ticker", sort=False)}

def simulate_add(sig, mode=None, th=0.10):
    """mode: None(원본) · 'down'(물타기) · 'up'(불타기). th: 문턱(비율).
    반환: 거래별 수익률(%) — 물타기/불타기는 두 몫 평균(비중 2배를 뜻한다)."""
    out = []
    for t in sig.itertuples():
        arr = CL.get(t.ticker)
        if arr is None: continue
        path = arr[(arr[:, 0] > t.di) & (arr[:, 0] <= t.di + t.hold)]
        if not len(path): continue
        r0 = (t.exit / t.buy - 1) * 100 - t.cost
        if mode is None: out.append(r0); continue
        hit = None
        for di_, c in path:
            if mode == "down" and c <= t.buy * (1 - th): hit = c; break
            if mode == "up" and c >= t.buy * (1 + th): hit = c; break
        if hit is None: out.append(r0); continue
        r1 = (t.exit / hit - 1) * 100 - t.cost     # 추가매수분은 그 가격이 매수가다
        out.append((r0 + r1) / 2)                  # 같은 금액씩 두 번 → 두 몫 평균
    return np.array(out, float)

print(f"신호표 {len(S):,}건 · 규칙 {S.rid.nunique()}개")
HDR = (f"  {'구성':<22}{'거래':>7}{'승률':>7}{'평균':>8}{'중앙':>8}{'절삭':>8}"
       f"{'최악5%':>9}{'한거래최악':>10}{'표준편차':>9}")
def row(nm, r):
    if len(r) < 50: print(f"  {nm:<22}{len(r):>7}  (부족)"); return
    trim = r[r <= np.percentile(r, 95)].mean()
    print(f"  {nm:<22}{len(r):>7}{(r>0).mean()*100:>6.1f}%{r.mean():>8.2f}{np.median(r):>8.2f}"
          f"{trim:>8.2f}{np.percentile(r,5):>9.1f}{r.min():>10.1f}{r.std():>9.1f}")

print("\n" + "=" * 96)
print("① 전체 규칙 합계 — 원본 vs 물타기 vs 불타기")
print("=" * 96); print(HDR)
base = simulate_add(S)
row("원본 (추가매수 없음)", base)
print()
for th in (0.05, 0.10, 0.15):
    row(f"  물타기 -{th*100:.0f}%", simulate_add(S, "down", th))
print()
for th in (0.05, 0.10, 0.15):
    row(f"  불타기 +{th*100:.0f}%", simulate_add(S, "up", th))

print("\n" + "=" * 96)
print("② 규칙별 — 물타기 -10% 가 어디서 특히 나쁜가")
print("=" * 96)
print(f"  {'규칙':<6}{'거래':>7}{'원본평균':>10}{'물타기평균':>11}{'차이':>8}"
      f"{'원본최악':>10}{'물타기최악':>11}")
for rid in sorted(S.rid.unique()):
    sub = S[S.rid == rid]
    b = simulate_add(sub); m = simulate_add(sub, "down", 0.10)
    if len(b) < 30: continue
    print(f"  {rid:<6}{len(b):>7}{b.mean():>10.2f}{m.mean():>11.2f}{m.mean()-b.mean():>+8.2f}"
          f"{b.min():>10.1f}{m.min():>11.1f}")

print("\n" + "=" * 96)
print("③ 물타기가 실제로 몇 번이나 걸리나 (-10% 기준)")
print("=" * 96)
n_hit = 0
for t in S.itertuples():
    arr = CL.get(t.ticker)
    if arr is None: continue
    path = arr[(arr[:, 0] > t.di) & (arr[:, 0] <= t.di + t.hold)]
    if len(path) and (path[:, 1] <= t.buy * 0.9).any(): n_hit += 1
print(f"  전체 {len(S):,}건 중 보유 중 -10% 를 밟은 거래 {n_hit:,}건 ({n_hit/len(S)*100:.1f}%)")
print("  → 이만큼의 거래에서 비중이 두 배가 된다. 계좌가 감당할 수 있는 크기인지가 핵심이다.")
