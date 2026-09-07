# -*- coding: utf-8 -*-
"""새 재료 정찰 — 아직 어떤 규칙도 안 쓰는 데이터 세 축.

재고 조사(2026-09-07)에서 찾은 미개척 재료:
  A) 지수 편입·제외 (data/index_members.db · 2018~) — 코스피200 등에 새로 들어가거나 빠지는 이벤트.
     패시브 자금이 강제로 사고 팔아야 하므로 가격에 흔적이 남는다. 이벤트 드리븐 실측에서 아직 안 봤다.
  B) 공매도 잔고 비율 (krx_daily.short_balance.bal_rto · 2016~) — 우리는 공매도 '거래비중'(srd)만 쓴다.
     잔고는 '아직 안 갚은 빚' 이라 축이 다르다. 잔고가 쌓이다 줄기 시작하는 순간(숏커버링)이 관심사.
  C) 자기주식 보유 비율 (dart/shares.treasury/issued) — 자사주 '취득 공시'(bb)는 쓰지만 실제 보유량은 안 쓴다.
정찰 단계이므로 규칙화하지 않는다. 각 재료를 분위로 갈라 forward return 이 단조롭게 갈리는지만 본다.
갈리지 않으면 그 자리에서 접는다(조합 탐색으로 넘어가지 않는다 — 과적합 방지).
"""
import io, os, sys, sqlite3, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, base = ns["KP"], ns["KQ"], ns["base"]
HS = [5, 10, 20, 40, 60]
for K in (KP, KQ):
    g = K.groupby("ticker", sort=False)
    for h in HS:
        if f"n{h}" not in K.columns: K[f"n{h}"] = (g.close.shift(-h)/K.buy-1)*100 - K.cost
def uni(K, h): return K.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
def show(title, K, mask, hs=HS):
    """마스크가 잡은 종목-일의 forward return 을 유니버스 대비로 본다"""
    m = mask.fillna(False)
    if m.sum() < 30: print(f"  {title:<34} 표본 부족 ({int(m.sum())})"); return
    row = f"  {title:<34}{int(m.sum()):>7}건 "
    for h in hs:
        col = f"n{h}"; z = K[m].dropna(subset=[col])
        if len(z) < 20: row += f"{'—':>16}"; continue
        ex = (z[col] - z.date.map(uni(K, h))).mean()
        row += f"{z[col].mean():>+7.1f}%({ex:>+5.1f})"
    print(row)
print(f"  {'':<34}{'건수':>7} " + "".join(f"{'n'+str(h)+' 평균(초과)':>16}" for h in HS))

print("\n" + "="*120); print("C) 자기주식 보유 비율 (treasury/issued)"); print("="*120)
c = sqlite3.connect("file:data/dart/shares.db?mode=ro", uri=True)
SH = pd.read_sql("SELECT stock_code ticker, year, reprt, se, issued, treasury FROM shares", c); c.close()
SH = SH[(SH.issued > 0) & SH.treasury.notna()]
SH["trs"] = SH.treasury / SH.issued * 100
SH["year"] = SH.year.astype(str)          # 패널의 _y 는 문자열이라 맞춘다
SH = SH.groupby(["ticker","year"], as_index=False).trs.max()
print(f"  종목 {SH.ticker.nunique():,} · 연도 {SH.year.min()}~{SH.year.max()} · 자사주비율 중앙 {SH.trs.median():.2f}%")
for K, mkt in ((KP,"코스피"), (KQ,"코스닥")):
    K["_y"] = (K.date.str[:4].astype(int) - 1).astype(str)     # 전년도 사업보고서 기준(시차)
    n0 = len(K); K2 = K.merge(SH.rename(columns={"year":"_y"}), on=["ticker","_y"], how="left"); assert len(K2)==n0
    K["trs"] = K2.trs.values
    v = K[(K.date>="20160101") & K.trs.notna() & base(K, 3)]
    if len(v) < 1000: print(f"  [{mkt}] 자료 부족"); continue
    print(f"\n  [{mkt}] 자료 있는 종목-일 {len(v):,}")
    q = pd.qcut(v.trs, 5, labels=False, duplicates="drop")
    for i in range(int(q.max())+1):
        sel = v.index[q == i]
        mask = pd.Series(False, index=K.index); mask.loc[sel] = True
        lo, hi = v.trs[q==i].min(), v.trs[q==i].max()
        show(f"Q{i+1} 자사주 {lo:.1f}~{hi:.1f}%", K, mask)
