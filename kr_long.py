# -*- coding: utf-8 -*-
"""한국 유튜브 둘 — 장기투자 주장 실측 (2026-09-12).

  ⓐ 상승효과TV '주식으로 10배 수익? (장기투자 5가지 꿀팁)'
     핵심 주장: **"기업가치가 성장하는 기업은 보유 기간이 늘어날수록 수익률이 높아진다"**
     근거로 삼성전자 20년 17배 · 애플 10년 10배를 든다.
     → 이건 **살아남아 크게 오른 두 종목을 뒤에서 고른 것**이다. 같은 잣대를 전체에 대면
       어떻게 되는지 잰다. 나머지 팁(확신·계좌분리·복리·도태기업 손절·기간설정)은 마음가짐이라
       기계화할 게 없다.

  ⓑ 시동위키(박시동) '이렇게 투자해야 안 망한다'
     세 주장 중 둘이 기계화된다.
     ① "목돈 전까지 분산투자 하지 마라 — 수익에 배팅하라" → 종목 수(집중도) 비교
     ③ "장기투자는 묻어두기가 아니다. 아는 종목이면 목표가에 팔고 싸지면 다시 사라"
        (7만원에 사서 8만원 되면 팔고, 6.6만원 되면 다시 산다) → **밴드 매매 vs 매수후보유**
     ②(자금 성격·기간·목표·로스컷 체크리스트)는 옳은 말이지만 잴 대상이 아니다.

⚠ 오늘 배운 둘을 그대로 적용한다:
  · 보유기간이 패널 끝을 넘는 것은 **끝난 거래로 세지 않는다**(미완료 보유 함정).
  · 보유 중 폐지되면 **마지막 종가로 청산해 손실을 먹는다**(생존편향).

    python kr_long.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 128


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DI).astype(np.int32)
LASTPOS = len(ud) - 1
G = K.groupby("ticker", sort=False)
AR = K.groupby("date").amt20.rank(pct=True)
UNIS = [("거래대금 상위40%", (AR >= 0.60).fillna(False)),
        ("거래대금 상위10%(대형)", (AR >= 0.90).fillna(False)),
        ("거래대금 상위3%(초대형)", (AR >= 0.97).fillna(False))]
# 종목별 마지막 행 위치와 마지막 종가 — 폐지 손실을 먹기 위해
pos = np.arange(len(K))
endpos = G.di.transform("max")
lastclose = G.close.transform("last")
log(f"준비 {len(K):,}행 · {K.ticker.nunique():,}종목")

HS = (20, 60, 120, 250, 500, 1000)
log("보유기간별 수익 계산 중")
for h in HS:
    sell = G.close.shift(-h)
    dead = (K.di + h) > endpos                      # 그 전에 상장폐지된 종목
    sell = sell.where(~dead, lastclose)             # 폐지분은 마지막 종가로 청산 — 손실을 먹는다
    trunc = (K.di + h + 1) > LASTPOS                # 패널이 끝나 아직 안 끝난 거래 — 제외
    K[f"L{h}"] = ((sell / K.buy - 1) * 100 - K.cost).where(~trunc)
    K[f"D{h}"] = dead & ~trunc

sec("ⓐ 상승효과TV — '보유 기간이 늘어날수록 수익률이 높아진다' 가 맞나")
print("  아무 날 아무 종목을 사서 그냥 들고 있었을 때. 연환산은 (1+r)^(252/h)-1 로 환산했다.")
print(f"\n  {'유니버스':<20}{'보유':>7}{'n':>10}{'평균':>9}{'중앙':>9}{'승률':>7}"
      f"{'연환산중앙':>11}{'하위10%':>9}{'폐지비중':>9}")
for unm, uni in UNIS:
    for h in HS:
        z = K[uni & K[f"L{h}"].notna()]
        if len(z) < 500: continue
        r = z[f"L{h}"]
        med = r.median(); ann = ((1 + med / 100) ** (252 / h) - 1) * 100
        print(f"  {unm if h == HS[0] else '':<20}{h:>6}일{len(z):>10,}{r.mean():>9.2f}{med:>9.2f}"
              f"{(r > 0).mean() * 100:>6.0f}%{ann:>10.2f}%{r.quantile(0.10):>9.1f}"
              f"{z[f'D{h}'].mean() * 100:>8.1f}%")
    print()

sec("ⓐ-2 폐지 손실을 빼면(= 살아남은 것만 보면) 얼마나 달라 보이나")
print("  영상이 든 삼성전자·애플은 '살아남아 크게 오른' 사례다. 그 편향의 크기를 잰다.")
print(f"\n  {'유니버스':<20}{'보유':>7}{'전체 중앙':>11}{'생존만 중앙':>13}{'부풀림':>9}")
for unm, uni in UNIS[:2]:
    for h in (250, 500, 1000):
        z = K[uni & K[f"L{h}"].notna()]
        if len(z) < 500: continue
        a = z[f"L{h}"].median(); b = z[~z[f"D{h}"]][f"L{h}"].median()
        print(f"  {unm if h == 250 else '':<20}{h:>6}일{a:>11.2f}{b:>13.2f}{b - a:>+9.2f}")
    print()
