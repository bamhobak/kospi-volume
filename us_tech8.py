# -*- coding: utf-8 -*-
"""[잔잔한 급등주] 확장 조사 ① — 국내 대입 · 정의 흔들기.

계기: 미장에서 유일하게 살아남았는데 DSR 하나에 걸려 기각됐다([[us-web-techniques]]).
'아깝다' 는 판단이라 가능성을 열고 더 파본다.

**먼저 자백.** 내가 쓴 '잔잔함' 은 Frog-in-the-Pan 원논문 정의가 아니다.
원논문(Da·Gurun·Warachka 2014)의 정보 이산성은
    ID = sgn(1년수익) × (음봉비율 − 양봉비율)
이고 나는 편의상 **평균 |일간수익|** 로 대신했다. 둘은 다른 것을 잰다 —
전자는 '자주 조금씩 올랐나(연속적)', 후자는 '하루하루가 조용한가(저변동)'.
여기서 둘 다 넣고 어느 쪽이 진짜인지 가린다.

재는 것
  ① 국내(코스피·코스닥) 대입 — 미장 조건 그대로, 그리고 국내에 맞게 문턱 조정
  ② 잔잔함의 정의 5가지 — |일간수익| · 원논문 ID · 변동성 · 고저폭 · 양봉비율
  ③ 상승폭의 정의 3가지 — 1년(250일) · 6개월(120일) · 3개월(60일)
  ④ 문턱 격자 — 상승폭 6단계 × 잔잔함 5단계
  ⑤ 여집합·대조군 — 부호가 갈리는지

판정: 익일 시가 매수(n{h} 에 이미 반영) · 비용차감 · 중복제거 · 같은날 유니버스 대비 초과
     · 절삭평균은 **유니버스 절삭평균과** 견준다(절삭Δ) · 학습/검증/스트레스 · 월블록 CI

    python us_tech8.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


class Board:
    """한 시장(미국·코스피·코스닥)을 얹어 두고 조건을 재는 판."""

    def __init__(self, name, path, mk=None, price_min=3, amt_q=0.6):
        log(f"{name} 읽는 중")
        K = pd.read_pickle(BASE / path)
        if mk: K = K[K.mk == mk]
        px = K.rawclose if "rawclose" in K.columns else K.close
        K = K[((~K.pref.fillna(False)) & (px >= price_min)).fillna(False)]
        K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
        ud = sorted(K.date.unique())
        K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
        self.uni = (K.groupby("date").amt20.rank(pct=True) >= amt_q).fillna(False)
        TK = K.ticker
        g = lambda c: K.groupby(TK, sort=False)[c]
        K["r1"] = g("close").pct_change() * 100
        # ── 잔잔함 다섯 가지 ────────────────────────────────────────
        K["q_abs"] = g("r1").transform(lambda s: s.abs().rolling(60).mean())      # 평균 |일간수익|
        K["_pos"] = (K.r1 > 0).astype(float); K["_neg"] = (K.r1 < 0).astype(float)
        pos = g("_pos").transform(lambda s: s.rolling(250, min_periods=200).mean())
        neg = g("_neg").transform(lambda s: s.rolling(250, min_periods=200).mean())
        K["posr"] = pos * 100
        # 원논문 ID — 1년 수익이 양수일 때 (음봉비율 − 양봉비율). 작을수록 '연속적'.
        K["q_id"] = np.sign(K.ret250.fillna(0)) * (neg - pos)
        K["q_vol"] = K.vol20                                                      # 20일 변동성
        K["q_rng"] = g("rng").transform(lambda s: s.rolling(60).mean())           # 평균 고저폭
        K["q_pos"] = -K.posr                                                      # 양봉비율(부호 뒤집어 '작을수록 좋음' 통일)
        K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
        self.K = K; self.ud = ud; self.name = name
        self.ben = {h: K[self.uni].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
                    for h in (20, 40, 60)}
        self.nday = len([d for d in ud if d >= "20160101"])
        self.bt = {h: self.trim(K[self.uni & (K.date >= "20160101")][f"n{h}"].dropna().astype(float))
                   for h in (20, 40, 60)}
        log(f"  {name} {len(K):,}행 · 유니버스 {int(self.uni.sum()):,} · "
            f"기준선 절삭 " + " ".join(f"{h}일 {self.bt[h]:.2f}" for h in self.bt))

    @staticmethod
    def trim(r):
        r = pd.Series(r).dropna()
        return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan

    def dd(self, cond, h, lo="20160101", hi="20991231"):
        K = self.K
        X = K[(cond & self.uni).fillna(False)].dropna(subset=[f"n{h}"])
        X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
            if last.get(t, -10**9) >= i: continue
            last[t] = i + h; keep.append(ix)
        d = X.loc[keep].copy()
        d["r"] = d[f"n{h}"].astype(float)
        d["ex"] = d.r - d.date.map(self.ben[h]); d["ym"] = d.date.str[:6]
        return d[d.r.notna()]

    def show(self, tag, cond, h=40, sink=None):
        d = self.dd(cond, h)
        if len(d) < 60:
            print(f"  {tag:<30} {len(d):>7}  (표본 부족)"); return
        st = self.dd(cond, h, lo="20050101", hi="20151231")
        tr = d[d.date <= TR1]; va = d[d.date >= VA0]
        ci = boot_ci(d.groupby("ym").ex.mean()); yr = d.groupby(d.date.str[:4]).ex.mean()
        dtm = self.trim(d.r) - self.bt[h]; per = len(d) / self.nday
        stx = st.ex.mean() if len(st) >= 60 else np.nan
        print(f"  {tag:<30} {len(d):>7,} {per:>5.2f} {per*h:>5.0f} {(d.r>0).mean()*100:>5.1f}% "
              f"{d.r.mean():>7.2f} {d.r.median():>7.2f} {dtm:>7.2f} {d.ex.mean():>7.2f} "
              f"{tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} {stx:>7.2f} {ci:>7.2f} "
              f"{int((yr>0).sum()):>4}/{len(yr)}")
        ok = (dtm > 0 and d.ex.mean() > 0 and va.ex.mean() > 0 and ci > 0
              and (yr > 0).sum() >= len(yr) * 0.72)
        if ok and sink is not None:
            sink.append((self.name, tag, h, len(d), per * h, d.ex.mean(), va.ex.mean(), ci,
                         int((yr > 0).sum()), len(yr)))
        return ok


HDR = (f"  {'조건':<30} {'n':>7} {'일':>5} {'동시':>5} {'승률':>6} {'평균':>7} {'중앙':>7} "
       f"{'절삭Δ':>7} {'초과':>7} {'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>7}")
W = 152
OK = []

US = Board("미국", "data/us_scan.pkl")
print("\n" + "=" * W)
print("① 잔잔함의 정의를 바꿔본다 — 원논문 ID 가 내 프록시보다 나은가 (미국 · 1년 120%↑ · 40일)")
print("=" * W); print(HDR)
K = US.K
BIG = K.multi & (K.ret250 >= 120)
Z = K[US.uni]
def pct_rank(col):
    """그날 유니버스 안에서의 백분위 — 시장·시대가 달라도 뜻이 같다."""
    r = pd.Series(np.nan, index=K.index)
    r.loc[Z.index] = Z.groupby("date")[col].rank(pct=True).values
    return r
US.show("  (기준) |일간수익| ≤1.5%", BIG & (K.q_abs <= 1.5), sink=OK)
for col, nm in (("q_abs", "|일간수익|"), ("q_id", "원논문 ID"), ("q_vol", "20일 변동성"),
                ("q_rng", "평균 고저폭"), ("q_pos", "양봉비율(뒤집음)")):
    rk = pct_rank(col)
    US.show(f"  {nm} 하위 30%", BIG & (rk <= 0.30), sink=OK)
print()
for col, nm in (("q_abs", "|일간수익|"), ("q_id", "원논문 ID"), ("q_vol", "20일 변동성"),
                ("q_rng", "평균 고저폭"), ("q_pos", "양봉비율(뒤집음)")):
    rk = pct_rank(col)
    US.show(f"  {nm} 상위 30%(대조군)", BIG & (rk >= 0.70), sink=None)

print("\n" + "=" * W)
print("② 상승폭의 정의 — 1년이 맞나 (미국 · |일간수익| ≤1.5% · 40일)")
print("=" * W); print(HDR)
for col, nm, ths in (("ret250", "1년", (80, 120, 150)), ("ret120", "6개월", (50, 80, 100)),
                     ("ret60", "3개월", (30, 50, 80))):
    for th in ths:
        US.show(f"  {nm} {th}%↑", K.multi & (K[col] >= th) & (K.q_abs <= 1.5), sink=OK)
    print()

print("\n" + "=" * W)
print("③ 문턱 격자 — 상승폭 × 잔잔함 (미국 · 40일)")
print("=" * W)
print(f"  {'':>10}" + "".join(f"{'≤'+str(a)+'%':>11}" for a in (1.0, 1.2, 1.5, 2.0, 2.5)))
for rt in (60, 80, 100, 120, 150, 200):
    row = f"  1년 {rt:>3}%↑"
    for ab in (1.0, 1.2, 1.5, 2.0, 2.5):
        d = US.dd(K.multi & (K.ret250 >= rt) & (K.q_abs <= ab), 40)
        row += f"{(f'{d.ex.mean():+.2f}({len(d)})' if len(d) >= 60 else '-'):>11}"
    print(row)
print("  (칸 = 초과 %p · 괄호는 건수) 이웃이 함께 좋아야 진짜다.")

del US, K, Z, BIG
import gc; gc.collect()

print("\n" + "=" * W)
print("④ 국내 대입 — 미장 조건 그대로, 그리고 국내에 맞게 (코스피 · 코스닥)")
print("=" * W)
for mk, nm in (("KOSPI", "코스피"), ("KOSDAQ", "코스닥")):
    B = Board(nm, "data/kr_scan.pkl", mk=mk, price_min=1000)
    K = B.K
    print(f"\n  ── {nm} ──"); print(HDR)
    for rt in (50, 80, 120, 150):
        for ab in (1.5, 2.0, 3.0):
            B.show(f"  1년 {rt}%↑ · 잔잔 ≤{ab}%", K.multi & (K.ret250 >= rt) & (K.q_abs <= ab),
                   h=40, sink=OK)
        print()
    print("  ── 보유기간 (1년 80%↑ · 잔잔 ≤2.0%) ──")
    C = K.multi & (K.ret250 >= 80) & (K.q_abs <= 2.0)
    for h in (20, 40, 60): B.show(f"  {h}일 보유", C, h=h, sink=OK)
    print("  ── 대조군: 같은 상승폭인데 요란한 쪽 ──")
    B.show("  1년 80%↑ · 요란 ≥4%", K.multi & (K.ret250 >= 80) & (K.q_abs >= 4), h=40)
    B.show("  1년 80%↑ · 등락 무관", K.multi & (K.ret250 >= 80), h=40)
    B.show("  잔잔 ≤2% 만 (모멘텀 없이)", K.q_abs <= 2.0, h=40)
    del B, K; gc.collect()

print("\n" + "=" * W)
print("⑤ 집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for mkt, tag, h, n, sim, ex, va, ci, y, ny in OK:
        print(f"  ✅ [{mkt}] {tag.strip():<30} {h:>2}일 · {n:>6,}건 · 동시 {sim:>4.0f}종목 · "
              f"초과 {ex:+.2f} · 검증 {va:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
