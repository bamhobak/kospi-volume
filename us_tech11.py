# -*- coding: utf-8 -*-
"""[잔잔한 급등주] 최종 사양 굳히기 — 60일 보유로 다시 전부 잰다.

us_tech9.py 에서 **60일 보유가 40일보다 확실히 낫다**는 게 나왔다
(초과 +2.22→+3.05 · CI +0.20→+0.92 · 승률 54.2→56.5% · 중앙 +1.12→+1.97).
그런데 지금까지의 해부(us_tech4)·계좌(us_tech5·6)·다중검정(us_tech7)은 대부분
**40일 기준**이었다. 사양이 바뀌었으니 판정을 다시 해야 한다.

특히 다중검정: 40일·2016~ 로는 월 64개뿐이라 구조적으로 못 넘었는데,
60일·2005~ 는 월 145개다. us_tech7 에서 그 사양의 본페로니 t 가 3.20(필요 3.23)이었다.
그게 우연이 아니라 **60일이 이 규칙의 제 보유기간**이었기 때문인지 확인한다.

  ① 60일 기준 함정 재검사 — 연도별·쏠림·생존편향·프록시·갭
  ② 60일 기준 다중검정 — 문턱 120/150 × 2005~/2016~
  ③ 60일 기준 계좌 — 노출 맞춤 · 시드 60 짝비교
  ④ 최종 사양 제안

    python us_tech11.py
"""
import sys, math, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as st
from vp_lib import boot_ci
import verdict

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
TK = K.ticker
K["r1"] = K.groupby(TK, sort=False).close.pct_change() * 100
K["q"] = K.groupby(TK, sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
K["lastdi"] = K.groupby(TK, sort=False).di.transform("max")
LAST = len(ud) - 1
H = 60
BEN = K[UNI].dropna(subset=["n60"]).groupby("date").n60.mean()
NDAY = len([d for d in ud if d >= "20160101"])
def trim(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan
BT = trim(K[UNI & (K.date >= "20160101")].n60.dropna().astype(float))
log(f"준비 완료 · {len(K):,}행 · 60일 기준선 절삭 {BT:.2f}")

def dd(cond, lo="20050101", hi="20991231"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=["n60"])
    X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + H; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d.n60.astype(float); d["ex"] = d.r - d.date.map(BEN); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

def C(rt, ab=1.5): return K.multi & (K.ret250 >= rt) & (K.q <= ab)
CELLS = [(100, "1년 100%↑"), (120, "1년 120%↑"), (150, "1년 150%↑")]
W = 120

print("\n" + "=" * W)
print("① 60일 기준 연도별 — 최근 해가 살아 있는가")
print("=" * W)
YT = {rt: (lambda d: d.groupby(d.date.str[:4]).agg(n=("r", "size"), x=("ex", "mean")))(dd(C(rt)))
      for rt, _ in CELLS}
print(f"  {'해':<6}" + "".join(f"{nm:>22}" for _, nm in CELLS))
for y in sorted(set().union(*[set(v.index) for v in YT.values()])):
    row = f"  {y:<6}"
    for rt, _ in CELLS:
        t = YT[rt]
        row += f"{(str(int(t.loc[y,'n']))+'건 '+format(t.loc[y,'x'],'+.2f')):>22}" if y in t.index else f"{'-':>22}"
    print(row)
print()
for rt, nm in CELLS:
    t = YT[rt]
    print(f"  {nm}: 양수해 {int((t.x>0).sum())}/{len(t)} · 최근 3해 "
          + " ".join(f"{y} {t.loc[y,'x']:+.2f}" for y in ("2024", "2025", "2026") if y in t.index))

print("\n" + "=" * W)
print("② 60일 기준 함정 재검사 (2016~)")
print("=" * W)
print(f"  {'조건':<14}{'건수':>7}{'최다해':>8}{'비중':>7}{'전체초과':>9}{'그해빼면':>9}{'CI(뺀뒤)':>10}"
      f"{'끊긴종목':>9}{'갭':>8}")
for rt, nm in CELLS:
    d = dd(C(rt), lo="20160101")
    cnt = d.date.str[:4].value_counts(); top = cnt.index[0]
    e = d[d.date.str[:4] != top]
    X = K[(C(rt) & UNI).fillna(False)]
    X = X[(X.date >= "20160101") & (X.di <= LAST - H)]
    dead = int((X.lastdi < X.di + H).sum())
    gap = (d.buy / d.close - 1) * 100
    print(f"  {nm:<14}{len(d):>7,}{top:>8}{cnt.iloc[0]/len(d)*100:>6.0f}%{d.ex.mean():>+9.2f}"
          f"{e.ex.mean():>+9.2f}{boot_ci(e.groupby('ym').ex.mean()):>+10.2f}"
          f"{dead:>6}건{gap.mean():>+8.2f}%")
print()
print("  ── 크기·유동성·주가 4분위 안에서도 유지되나 (1년 120%↑) ──")
d = dd(C(120), lo="20160101")
for lab, col in (("시총", "marcap"), ("거래대금", "amt20"), ("주가", "rawclose")):
    v = pd.qcut(K.loc[d.index, col].rank(method="first"), 4, labels=False)
    m = d.groupby(v).agg(n=("r", "size"), x=("ex", "mean"))
    print(f"  {lab:<8} " + " ".join(f"Q{int(i)+1} {r.x:+.2f}({int(r.n)})" for i, r in m.iterrows()))

print("\n" + "=" * W)
print("③ 60일 기준 다중검정 — 구간과 문턱을 나란히")
print("=" * W)
print(f"  {'경우':<24}{'월수':>6}{'월평균':>8}{'실제t':>7}{'필요t':>7}{'샤프':>7}{'우연최대':>9}{'DSR':>8}{'보정CI':>8}")
NT = 161; need_t = st.norm.ppf(1 - 0.10 / NT)
BEST = None
for lo, ln in (("20160101", "2016~"), ("20050101", "2005~")):
    for rt, nm in CELLS:
        r = dd(C(rt), lo=lo).groupby("ym").ex.mean().dropna()
        if len(r) < 12: continue
        T = len(r); se = r.std(ddof=1) / math.sqrt(T); t = r.mean() / se
        ds = verdict.deflated_sharpe(r, NT); ci = boot_ci(r, 0.10 / NT)
        print(f"  {nm+' · '+ln:<24}{T:>6}{r.mean():>8.2f}{t:>7.2f}{need_t:>7.2f}"
              f"{ds['sr']:>7.3f}{ds['sr0']:>9.3f}{ds['dsr']*100:>7.1f}%{ci:>+8.2f}")
        if ln == "2005~" and (BEST is None or ds["dsr"] > BEST[1]["dsr"]):
            BEST = ((rt, nm), ds, r, ci)
print()
print("  ── N 을 흔들면 (2005~ · 문턱별) ──")
print(f"  {'N':>7}" + "".join(f"{nm:>24}" for _, nm in CELLS))
SER = {rt: dd(C(rt), lo="20050101").groupby("ym").ex.mean().dropna() for rt, _ in CELLS}
for n in (1, 5, 10, 20, 50, 161, 1000, 16159):
    row = f"  {n:>7}"
    for rt, _ in CELLS:
        r = SER[rt]; ds = verdict.deflated_sharpe(r, max(n, 2)); ci = boot_ci(r, min(0.10/n, 0.10))
        row += f"{f'DSR {ds[chr(100)+chr(115)+chr(114)]*100:.0f}% / CI {ci:+.2f}':>24}"
    print(row)

print("\n" + "=" * W)
print("④ 정식 판정 (60일 · 2005~)")
print("=" * W)
for rt, nm in CELLS:
    d = dd(C(rt), lo="20050101")
    yr = d.groupby(d.date.str[:4]).ex.mean()
    verdict.judge(f"{nm} · 잔잔 ≤1.5% · 60일 (2005~)", d.groupby("ym").ex.mean(),
                  topic="us_tech_web", median=d.r.median(), last_year=yr.get("2026"))
