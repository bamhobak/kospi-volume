# -*- coding: utf-8 -*-
"""한국 아홉 규칙을 미국에 그대로 대입해 본다.

사용자 요청(2026-09-09): "국내 주식 규칙 만들 때 쓴 데이터들 대입해서 미국 주식으로도
데이터 만들 수 있는 거 만들어놔줘."

원칙 — **조건을 마음대로 고치지 않는다.**
  · 미국에 있는 재료는 한국과 **같은 문턱**으로 그대로 쓴다(업종 -20%, 이격 -10% 등).
  · 미국에 없는 재료(외국인·기관 순매수, 신용잔고, 증자공시, 자사주, 내부자)는
    **뺀다**. 빼면 조건이 느슨해지므로 '몇 개를 뺐는지' 를 규칙마다 표시한다.
  · 단위가 다른 것만 환산한다 — 주가 하한(1,000원 → $3)과 거래대금(억원 → 백만달러).
  · 국면 게이트는 코스피 60일선 → **S&P500 60일선**.

판정도 한국과 같은 잣대를 쓴다 — 유니버스 대비 초과 · 중앙값 · 상위5% 절삭 ·
학습 2016~22 / 검증 2023~26 · 월블록 CI · 양수해 비율. 그래야 두 시장을 나란히 놓을 수 있다.

  python us_rules.py            # 규칙별 성적
  python us_rules.py --acct     # 계좌 시뮬까지
"""
import io, sys, time, argparse, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


K = pd.read_pickle(BASE / "data" / "panel_us.pkl")
log(f"미국 패널 {len(K):,}행 · {K.ticker.nunique():,}종목 · {K.date.min()}~{K.date.max()}")

# ── 국면 게이트 — S&P500 60일선 ──────────────────────────────────────
import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2004-06-01")
IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
UP60 = dict(zip(IX.date, IX.Close > IX.ma60))
K["up60"] = K.date.map(UP60)
dn60 = K.up60 == False
up60 = K.up60 == True
log(f"  S&P500 60일선 게이트 · 하락 구간 비중 {dn60.mean()*100:.0f}%")


def base(amt):
    """한국 base() 대응. 1,000원 → $3, 억원 → 백만달러(대략 1억원 ≈ $0.073M 이지만
    시장 규모가 달라 절대 환산은 무의미하다. **유니버스 통과 비율**을 한국과 맞춘다:
    한국 base(K,3) 은 전체의 약 60% 를 남긴다)."""
    return (~K.pref) & (K.close >= 3) & (K.amt20.fillna(0) >= amt)


# 한국 amt 문턱(억원) → 미국(백만달러). 통과 비율을 맞추려고 잡은 값이다.
AMT = {3: 1.0, 5: 2.0, 10: 5.0, 200: 100.0}
for kr, us in AMT.items():
    log(f"  거래대금 {kr}억원 → ${us}M · 통과 비율 {base(us).mean()*100:.0f}%")

# ══════════════════════════════════════════════════════════════════════
# 아홉 규칙 — 옮길 수 있는 조건만. 뺀 조건은 dropped 에 적는다.
# ══════════════════════════════════════════════════════════════════════
RULES = {
 "P1": dict(name="조용한 신고가", hold=40, trail=0.08, pct=12, mx=7,
            cond=lambda: base(100.0) & (K.fromhi >= -10) & (K.vol20 <= 2)
                         & (K.above20 <= 70) & (K.r16 <= 120),
            drop=["외국인 5일 ≥3%", "공매도 비중 ≤0.5%", "1년수익 120% 조건"]),
 "P2": dict(name="조정매집", hold=10, trail=None, pct=15, mx=2,
            cond=lambda: base(1.0) & (K.ret3 <= -5) & (K.ret10 < 0)
                         & (K.rw1 >= 200) & (K.r16 <= 30),
            drop=["외인/거래량 ≥2%"]),
 "P3": dict(name="폭락반등", hold=20, trail=None, pct=5, mx=3,
            cond=lambda: base(1.0) & dn60 & (K.ret20 <= -25),
            drop=["신용잔고 -15%↓", "기타 수급"]),
 "P4": dict(name="업종붕괴 이탈", hold=5, trail=0.08, pct=3, mx=4,
            cond=lambda: base(5.0) & dn60 & (K.u <= -20) & (K.dma20 <= -10)
                         & (K.mdd60 <= -40),
            drop=["공매도 비중 감소(2019 이전 결측)"]),
 "P5": dict(name="자사주 낙폭", hold=10, trail=None, pct=5, mx=3,
            cond=lambda: None, drop=["자사주 취득공시 — EDGAR 파싱 필요. 대입 불가"]),
 "P6": dict(name="깊은 이격", hold=5, trail=0.08, pct=4, mx=4,
            cond=lambda: base(5.0) & dn60 & (K.dev25 <= -25) & (K.u <= -20),
            drop=[]),
 "P7": dict(name="외인 매집", hold=60, trail=None, pct=4, mx=5,
            cond=lambda: None, drop=["외국인 순매수 — 미국에 없음. 대입 불가"]),
 "D1": dict(name="낙폭과대", hold=20, trail=None, pct=5, mx=3,
            cond=lambda: base(2.0) & dn60 & (K.ret20 <= -30) & (K.su1 >= 2)
                         & (K.u <= -10) & (K["부채비율"].isna() | (K["부채비율"] <= 200)),
            drop=["외국인 60일 ≥1%", "기관 20일 ≥0%"]),
 "D2": dict(name="저PBR 낙폭", hold=40, trail=None, pct=5, mx=3,
            cond=lambda: base(2.0) & dn60 & (K.PBR > 0) & (K.PBR <= 0.8)
                         & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10),
            drop=["기관 20일 ≥0%", "공매도 비중 감소"]),
}

UNI = {h: K[base(1.0)].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
       for h in (5, 10, 20, 40, 60)}


def measure(rid, r):
    cond = r["cond"]()
    if cond is None:
        return None
    h = r["hold"]
    m = cond.fillna(False)
    g = K.groupby("ticker", sort=False)
    C = np.column_stack([g.px.shift(-i).values for i in range(1, h + 1)])
    buy = K.buy.values
    hit = np.zeros_like(C, dtype=bool); px = C.copy()
    if r["trail"]:
        run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
        hh = C <= run * (1 - r["trail"]); hit |= hh
        px = np.where(hh & ~np.isnan(C), run * (1 - r["trail"]), px)
    ok = hit.any(axis=1)
    first = np.where(ok, hit.argmax(axis=1), h - 1)
    ex = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
    mv = m.values
    X = K[m].copy()
    X["ret"] = (ex[mv] / X.buy - 1) * 100 - X.cost
    X["hold"] = (first + 1)[mv]
    X = X.dropna(subset=["ret"])
    X = X[(X.buy > 0) & (X.date >= TR0)]
    if len(X) < 30:
        return dict(n=len(X), few=True)
    # 중복신호 제거
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h; keep.append(ix)
    X = X.loc[keep]
    if len(X) < 30:
        return dict(n=len(X), few=True)
    u = UNI.get(h, UNI[20])
    X["ex"] = X.ret - X.date.map(u)
    tr, va = X[X.date <= TR1], X[X.date >= VA0]
    yr = X.assign(y=X.date.str[:4]).groupby("y").ret.median()
    return dict(n=len(X), few=False, ret=X.ret.mean(), med=X.ret.median(),
                trim=X.ret[X.ret <= X.ret.quantile(0.95)].mean(),
                win=(X.ret > 0).mean() * 100, ex=X.ex.mean(), exmed=X.ex.median(),
                trm=tr.ret.median() if len(tr) else np.nan,
                vam=va.ret.median() if len(va) else np.nan,
                ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm").ret.mean(), 0.10),
                pos=int((yr > 0).sum()), ny=len(yr), X=X)


print("\n" + "=" * 126)
print("한국 아홉 규칙을 미국에 대입 — 조건은 그대로, 없는 재료만 뺀다 (2016~, 비용차감)")
print("=" * 126)
print(f"  {'규칙':<16}{'건수':>7}{'절대평균':>9}{'중앙':>8}{'절삭':>8}{'승률':>6}"
      f"{'초과':>8}{'학습중앙':>9}{'검증중앙':>9}{'월CI':>8}{'양수해':>7}  뺀 조건")
RES = {}
for rid, r in RULES.items():
    z = measure(rid, r)
    if z is None:
        print(f"  {r['name']:<16}{'—':>7}{'':<66}대입 불가: {r['drop'][0]}")
        continue
    if z.get("few"):
        print(f"  {r['name']:<16}{z['n']:>7,}  표본부족")
        continue
    RES[rid] = z
    print(f"  {r['name']:<16}{z['n']:>7,}{z['ret']:>+9.2f}{z['med']:>+8.2f}{z['trim']:>+8.2f}"
          f"{z['win']:>5.0f}%{z['ex']:>+8.2f}{z['trm']:>+9.2f}{z['vam']:>+9.2f}"
          f"{z['ci']:>+8.2f}{z['pos']:>4}/{z['ny']}  {len(r['drop'])}개")

print("\n" + "=" * 126)
print("한국 원본과 나란히 (한국 건별 평균은 2016~ 기준)")
print("=" * 126)
KR = {"P1": 7.02, "P2": 11.81, "P3": 33.02, "P4": 10.68, "P5": 10.20,
      "P6": 10.76, "P7": 15.36, "D1": 42.54, "D2": 40.87}
print(f"  {'규칙':<16}{'한국 평균':>10}{'미국 평균':>10}{'차이':>9}   판정")
for rid, r in RULES.items():
    if rid not in RES:
        continue
    z = RES[rid]
    ok = (z["med"] > 0 and z["trim"] > 0 and z["trm"] > 0 and z["vam"] > 0
          and z["ci"] > 0 and z["pos"] / z["ny"] >= 0.7)
    print(f"  {r['name']:<16}{KR[rid]:>+9.2f}%{z['ret']:>+9.2f}%{z['ret']-KR[rid]:>+8.2f}p"
          f"   {'✅ 통과' if ok else '❌ 기각'}")

print("\n  ── 대입 불가 ──")
for rid, r in RULES.items():
    if rid not in RES:
        print(f"    {r['name']} — {r['drop'][0]}")
print("\n  ── 뺀 조건(있으면 더 엄격해졌을 것) ──")
for rid, r in RULES.items():
    if rid in RES and r["drop"]:
        print(f"    {r['name']}: " + " · ".join(r["drop"]))
