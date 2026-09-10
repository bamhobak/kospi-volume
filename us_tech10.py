# -*- coding: utf-8 -*-
"""[잔잔한 급등주] 확장 조사 ③ — 절대 문턱을 백분위로 바꾼다 · 국내 재도전.

us_tech8.py 에서 국내가 전멸했는데, 기각하기 전에 **문턱이 절대값이라서** 진 건 아닌지
확인해야 한다. '일간 등락 1.5% 이하' 는 미국 종목에서 나온 숫자다. 국내 종목은 변동성
수준 자체가 달라 같은 1.5% 가 전혀 다른 뜻이 된다.
[[us-rules-never-fired]] 의 유동성 교훈과 같은 문제다 — 미장 거래대금 중앙값이 10년 새
두 배가 돼서 절대 $10M 문턱이 해마다 다른 뜻이 됐고, 백분위로 바꿔서 해결했다.

여기서 재는 것
  ① 미장 — 절대 문턱이 시대에 따라 헐거워지는가 (연도별 통과 비율)
  ② 미장 — 백분위판이 절대판보다 나은가 (특히 2021 쏠림이 줄어드는가)
  ③ 국내 — 백분위판으로 재도전 (코스피 · 코스닥)
  ④ 국내 — '요란한 급등주' 는 강한 회피 신호였다. 우리 규칙과 겹치기는 하는가

    python us_tech10.py
"""
import sys, time, gc, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


class Board:
    def __init__(self, name, path, mk=None, price_min=3):
        log(f"{name} 읽는 중")
        K = pd.read_pickle(BASE / path)
        if mk: K = K[K.mk == mk]
        px = K.rawclose if "rawclose" in K.columns else K.close
        K = K[((~K.pref.fillna(False)) & (px >= price_min)).fillna(False)]
        K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
        ud = sorted(K.date.unique())
        K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
        self.uni = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
        TK = K.ticker
        K["r1"] = K.groupby(TK, sort=False).close.pct_change() * 100
        K["q"] = K.groupby(TK, sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
        K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
        # 그날 유니버스 안에서의 백분위 — 시대·시장이 달라도 뜻이 같다
        Z = K[self.uni]
        for c, nm in (("q", "q_pc"), ("ret250", "up_pc")):
            r = pd.Series(np.nan, index=K.index)
            r.loc[Z.index] = Z.groupby("date")[c].rank(pct=True).values
            K[nm] = r
        self.K = K; self.ud = ud; self.name = name
        self.ben = {h: K[self.uni].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
                    for h in (20, 40, 60)}
        self.nday = len([d for d in ud if d >= "20160101"])
        self.bt = {h: self.trim(K[self.uni & (K.date >= "20160101")][f"n{h}"].dropna().astype(float))
                   for h in (20, 40, 60)}
        log(f"  {name} {len(K):,}행")

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
            print(f"  {tag:<32} {len(d):>6}  (표본 부족)"); return
        st = self.dd(cond, h, lo="20050101", hi="20151231")
        tr = d[d.date <= TR1]; va = d[d.date >= VA0]
        ci = boot_ci(d.groupby("ym").ex.mean()); yr = d.groupby(d.date.str[:4]).ex.mean()
        dtm = self.trim(d.r) - self.bt[h]; per = len(d) / self.nday
        cnt = d.date.str[:4].value_counts(); top = cnt.iloc[0] / len(d) * 100
        stx = st.ex.mean() if len(st) >= 60 else np.nan
        print(f"  {tag:<32} {len(d):>6,} {per*h:>5.0f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
              f"{d.r.median():>7.2f} {dtm:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} "
              f"{va.ex.mean():>7.2f} {stx:>7.2f} {ci:>7.2f} {int((yr>0).sum()):>3}/{len(yr)} {top:>5.0f}%")
        if (sink is not None and dtm > 0 and d.ex.mean() > 0 and va.ex.mean() > 0 and ci > 0
                and (yr > 0).sum() >= len(yr) * 0.72):
            sink.append((self.name, tag, h, len(d), per * h, d.ex.mean(), va.ex.mean(), ci,
                         int((yr > 0).sum()), len(yr)))


HDR = (f"  {'조건':<32} {'n':>6} {'동시':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭Δ':>7} "
       f"{'초과':>7} {'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>6} {'최다해':>6}")
W = 152
OK = []

US = Board("미국", "data/us_scan.pkl")
K = US.K
print("\n" + "=" * W)
print("① 절대 문턱은 시대에 따라 뜻이 달라지는가 — 유니버스 중 '잔잔 ≤1.5%' 통과 비율")
print("=" * W)
Z = K[US.uni & (K.date >= "20050101")]
yq = Z.groupby(Z.date.str[:4]).agg(잔잔비율=("q", lambda s: (s <= 1.5).mean() * 100),
                                   q중앙=("q", "median"))
print("  해   " + "  ".join(f"{y[2:]}" for y in yq.index))
print("  통과% " + " ".join(f"{v:>4.0f}" for v in yq.잔잔비율))
print("  중앙  " + " ".join(f"{v:>4.1f}" for v in yq.q중앙))
print("  → 통과 비율이 해마다 크게 다르면 절대 문턱은 '같은 조건' 이 아니다.")
print("    백분위는 정의상 해마다 같은 비율을 통과시킨다.")

print("\n" + "=" * W)
print("② 미장 — 절대판 vs 백분위판 (40일 보유 · 맨 오른쪽은 신호가 한 해에 몰린 비율)")
print("=" * W); print(HDR)
print("  ── 절대 문턱 ──")
US.show("  1년 120%↑ · 잔잔 ≤1.5%", K.multi & (K.ret250 >= 120) & (K.q <= 1.5), sink=OK)
US.show("  1년 150%↑ · 잔잔 ≤1.5%", K.multi & (K.ret250 >= 150) & (K.q <= 1.5), sink=OK)
print("  ── 백분위 문턱 (그날 유니버스 대비) ──")
for up in (0.90, 0.95, 0.97):
    for qq in (0.20, 0.30, 0.40):
        US.show(f"  상승 상위{(1-up)*100:.0f}% · 잔잔 하위{qq*100:.0f}%",
                K.multi & (K.up_pc >= up) & (K.q_pc <= qq), sink=OK)
    print()
print("  ── 섞기: 상승은 절대 · 잔잔은 백분위 ──")
for qq in (0.20, 0.30, 0.40):
    US.show(f"  1년 120%↑ · 잔잔 하위{qq*100:.0f}%", K.multi & (K.ret250 >= 120) & (K.q_pc <= qq), sink=OK)

del US, K, Z; gc.collect()

print("\n" + "=" * W)
print("③ 국내 재도전 — 백분위판 (코스피 · 코스닥)")
print("=" * W)
for mk, nm in (("KOSPI", "코스피"), ("KOSDAQ", "코스닥")):
    B = Board(nm, "data/kr_scan.pkl", mk=mk, price_min=1000)
    K = B.K
    print(f"\n  ── {nm} ──"); print(HDR)
    for up in (0.90, 0.95, 0.97):
        for qq in (0.20, 0.30, 0.40):
            B.show(f"  상승 상위{(1-up)*100:.0f}% · 잔잔 하위{qq*100:.0f}%",
                   K.multi & (K.up_pc >= up) & (K.q_pc <= qq), sink=OK)
        print()
    print("  ── 보유기간 (상승 상위5% · 잔잔 하위30%) ──")
    C = K.multi & (K.up_pc >= 0.95) & (K.q_pc <= 0.30)
    for h in (20, 40, 60): B.show(f"  {h}일 보유", C, h=h, sink=OK)
    print("  ── 대조군 ──")
    B.show("  상승 상위5% · 잔잔 상위30%(요란)", K.multi & (K.up_pc >= 0.95) & (K.q_pc >= 0.70))
    B.show("  상승 상위5% · 등락 무관", K.multi & (K.up_pc >= 0.95))
    del B, K; gc.collect()

print("\n" + "=" * W)
print("④ 집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for mkt, tag, h, n, sim, ex, va, ci, y, ny in OK:
        print(f"  ✅ [{mkt}] {tag.strip():<32} {h:>2}일 · {n:>6,}건 · 동시 {sim:>4.0f}종목 · "
              f"초과 {ex:+.2f} · 검증 {va:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
