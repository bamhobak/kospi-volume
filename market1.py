# -*- coding: utf-8 -*-
"""1번 필터 — 시장(코스피) 국면 조건 다각도 테스트"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
MKT = np.load("data/p1_MKT.npy")
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
GP = P.gp.values.astype(int); N = len(P)
SRD = P.sr5.notna() & P.sr20.notna() & (P.sr5 < P.sr20)

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
ki = fdr.DataReader("KS11", "2017-01-01"); ki = ki[ki.Close > 0]
ki.index = ki.index.strftime("%Y%m%d")
c = ki["Close"].reindex(dates).ffill()
M = pd.DataFrame(index=dates)
for w in (5, 10, 20, 30, 60, 120):
    M[f"ma{w}"] = (c > c.rolling(w).mean()).values
M["ma5_20"] = (c.rolling(5).mean() > c.rolling(20).mean()).values      # 정배열(단기)
M["ma20_60"] = (c.rolling(20).mean() > c.rolling(60).mean()).values
M["r5"] = (c / c.shift(5) - 1).values * 100
M["r20"] = (c / c.shift(20) - 1).values * 100
M["dev20"] = (c / c.rolling(20).mean() - 1).values * 100
MS = M.reindex([dates[i] for i in GP]).reset_index(drop=True)

def rets(h, sl=None, tp=None):
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    ks = np.where((Lm <= -sl).any(1), (Lm <= -sl).argmax(1), 999) if sl else np.full(N, 999)
    kt = np.where((Hm >= tp).any(1), (Hm >= tp).argmax(1), 999) if tp else np.full(N, 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(N), kk].astype(float)
    if sl is not None: r = np.where(ks <= np.minimum(kt, h), -float(sl), r)
    if tp is not None: r = np.where((kt < ks) & (kt <= h), float(tp), r)
    return r - COSTV, kk
def stat(m, h=10, sl=None, tp=20, mn=12):
    mv = np.asarray(m); mv = mv.values if hasattr(mv, "values") else mv
    if mv.sum() < mn: return None
    r, kk = rets(h, sl, tp); r = r[mv]; y = P.y.values[mv]
    mk = MKT[GP[mv], np.clip(kk[mv], 0, MKT.shape[1]-1)]
    dn = r[mk <= 0]
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); ok = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=float(np.median(r)), win=(r > 0).mean()*100,
                pf=(r[r > 0].sum()/abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}", is_=r[y <= 2022].mean(), os_=r[y >= 2023].mean(),
                dn=dn.mean() if len(dn) else np.nan, ndn=len(dn), tot=r.sum()/100*1_000_000, r=r, y=y)
def show(title, rows, h=10, sl=None, tp=20):
    print(f"\n## {title}\n")
    print("| 시장 조건 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습 | 검증 | +연도 | 100만원씩 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, m in rows:
        s = stat(m, h, sl, tp)
        if not s: print(f"| {lab} | 부족 |" + " - |" * 9); continue
        print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
              f"{s['dn']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} | **{s['tot']/10000:+,.0f}만** |")

# 1번 필터 시장조건 제외 골격
B0 = ((P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.rs.notna() & (P.rs > 0)
      & SRD & (P.fwp >= 3)).values
print(f"# 1번 필터 시장조건 테스트 (시장조건 제외 시 {B0.sum()}건)")
show("① 단일 이평선 위", [("조건 없음", B0)] + [(f"코스피 {w}일선 위", B0 & M[f"ma{w}"].reindex([dates[i] for i in GP]).values)
      for w in (5, 10, 20, 30, 60, 120)])
show("② 단일 이평선 아래", [(f"코스피 {w}일선 아래", B0 & ~M[f"ma{w}"].reindex([dates[i] for i in GP]).values)
      for w in (5, 10, 20, 30, 60, 120)])
g = lambda w: M[f"ma{w}"].reindex([dates[i] for i in GP]).values
show("③ 두 이평선 조합", [("5일선+20일선 위 (현행)", B0 & g(5) & g(20)),
      ("10일선+20일선 위", B0 & g(10) & g(20)), ("5일선+30일선 위", B0 & g(5) & g(30)),
      ("10일선+30일선 위", B0 & g(10) & g(30)), ("20일선+60일선 위", B0 & g(20) & g(60)),
      ("5일선 위 + 20일선 아래", B0 & g(5) & ~g(20)), ("5일선 아래 + 20일선 위", B0 & ~g(5) & g(20)),
      ("5·20·60 전부 위", B0 & g(5) & g(20) & g(60))])
ma520 = M["ma5_20"].reindex([dates[i] for i in GP]).values
ma2060 = M["ma20_60"].reindex([dates[i] for i in GP]).values
show("④ 이평선 배열", [("5일선>20일선 (정배열)", B0 & ma520), ("5일선<20일선", B0 & ~ma520),
      ("20일선>60일선", B0 & ma2060), ("5>20 & 20>60", B0 & ma520 & ma2060),
      ("5>20 & 종가>5일선", B0 & ma520 & g(5))])
r5 = M["r5"].reindex([dates[i] for i in GP]).values
r20 = M["r20"].reindex([dates[i] for i in GP]).values
dv = M["dev20"].reindex([dates[i] for i in GP]).values
show("⑤ 코스피 모멘텀·이격도", [("코스피 5일 +", B0 & (r5 > 0)), ("코스피 5일 -", B0 & (r5 <= 0)),
      ("코스피 20일 +", B0 & (r20 > 0)), ("코스피 20일 -", B0 & (r20 <= 0)),
      ("코스피 20일 +3%↑", B0 & (r20 >= 3)), ("20일선 이격 0~3%", B0 & (dv >= 0) & (dv <= 3)),
      ("20일선 이격 3%↑(과열)", B0 & (dv > 3)), ("20일선 이격 -3~0%", B0 & (dv >= -3) & (dv < 0))])
print("\n## 상위 후보 연도별\n")
CAND = [("현행 5+20일선 위", B0 & g(5) & g(20)), ("10일선+20일선 위", B0 & g(10) & g(20)),
        ("5일선 위만", B0 & g(5)), ("5>20 정배열", B0 & ma520)]
for lab, m in CAND:
    s = stat(m)
    if not s: continue
    cells = []
    for y in range(2019, 2027):
        gg = s["r"][s["y"] == y]
        cells.append(f"{gg.mean():+.1f}({len(gg)})" if len(gg) else "-")
    print(f"| {lab} | " + " | ".join(cells) + f" | 계 {s['tot']/10000:+,.0f}만 |")
