# -*- coding: utf-8 -*-
"""후보 해부 — '1년 크게 올랐는데 일간은 잔잔한 종목' (Frog-in-the-Pan 강화판).

3차(us_tech3.py)에서 이웃 셋이 함께 통과했다. 40일 보유 기준
  1년 80%↑  초과 +1.40 · 검증 +1.28 · CI +0.02 · 8/11
  1년 120%↑ 초과 +2.22 · 검증 +3.11 · CI +0.20 · 9/11
  1년 150%↑ 초과 +3.57 · 검증 +4.69 · CI +1.78 · 9/11
여집합(같은 상승폭인데 일간이 요란한 쪽)은 초과 -2.03 · 승률 42.3% 로 정확히 갈렸다.

그러나 통과는 시작이다. 우리 집 함정 여섯을 하나씩 짚는다([[backtest-pitfalls]]).
  ① 중복신호 — dd() 에서 이미 제거했다(보유기간 내 재진입 금지)
  ② 생존편향 — 신호 뒤 데이터가 끊긴 종목이 빠졌는가
  ③ 연도쏠림 — 2021 한 해에 신호 39% 가 몰렸다. 그 해를 빼면?
  ④ 기준선  — 같은날 유니버스 대비 초과로 이미 잰다. 여기서는 **크기·유동성 프록시**인지 본다
  ⑤ 보유기간 — 20/40/60 을 나란히
  ⑥ 체결가능성 — 미국은 상한가가 없다. 대신 **다음날 시가 갭**이 얼마나 큰지 본다
그리고 마지막에 **다중검정 보정**과 **계좌**로 판정한다.
규칙 단위 통과가 계좌에서 뒤집힌 전례가 많다([[short-program-combo]] · [[stock-feargreed]]).

    python us_tech4.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci
import verdict

BASE = Path(__file__).parent
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
K["absr"] = K.groupby(TK, sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
K["lastdi"] = K.groupby(TK, sort=False).di.transform("max")   # 그 종목의 마지막 거래일
LASTDI = len(ud) - 1
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])
def trimmed(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan
BT = {h: trimmed(K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)) for h in (20, 40, 60)}
log(f"준비 완료 · {len(K):,}행")

def dd(cond, h, lo="20050101", hi="20991231"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

def C(rt, ab=1.5):
    return K.multi & (K.ret250 >= rt) & (K.absr <= ab)

CELLS = [(80, "1년 80%↑"), (120, "1년 120%↑"), (150, "1년 150%↑")]
W = 120

print("\n" + "=" * W)
print("① 연도별 — 최근 해가 살아 있는가 (40일 보유 · 잔잔 ≤1.5%)")
print("=" * W)
print(f"  {'해':<6}" + "".join(f"{nm:>22}" for _, nm in CELLS))
YT = {}
for rt, nm in CELLS:
    d = dd(C(rt), 40)
    YT[rt] = d.groupby(d.date.str[:4]).agg(n=("r", "size"), x=("ex", "mean"))
years = sorted(set().union(*[set(v.index) for v in YT.values()]))
for y in years:
    row = f"  {y:<6}"
    for rt, _ in CELLS:
        t = YT[rt]
        row += f"{(str(int(t.loc[y,'n']))+'건 ' + format(t.loc[y,'x'],'+.2f')):>22}" if y in t.index else f"{'-':>22}"
    print(row)
print()
for rt, nm in CELLS:
    t = YT[rt]; pos = (t.x > 0).sum()
    print(f"  {nm}: 양수해 {pos}/{len(t)} · 최근 3해(2024~26) "
          + " ".join(f"{y} {t.loc[y,'x']:+.2f}" for y in ("2024", "2025", "2026") if y in t.index))

print("\n" + "=" * W)
print("② 쏠림 — 한 해에 몰려 있는가, 그 해를 빼면 남는가 (40일 · 2016~)")
print("=" * W)
print(f"  {'조건':<14}{'건수':>7}{'최다해':>8}{'그해비중':>9}{'전체초과':>9}{'그해빼면':>9}{'CI(뺀 뒤)':>11}{'양수해':>8}")
for rt, nm in CELLS:
    d = dd(C(rt), 40, lo="20160101")
    cnt = d.date.str[:4].value_counts(); top = cnt.index[0]; sh = cnt.iloc[0] / len(d) * 100
    e = d[d.date.str[:4] != top]
    yr = e.groupby(e.date.str[:4]).ex.mean()
    print(f"  {nm:<14}{len(d):>7,}{top:>8}{sh:>8.0f}%{d.ex.mean():>+9.2f}{e.ex.mean():>+9.2f}"
          f"{boot_ci(e.groupby('ym').ex.mean()):>+11.2f}{int((yr>0).sum()):>5}/{len(yr)}")

print("\n" + "=" * W)
print("② -2 월 단위 쏠림 — 한 달에 몰리면 '한 사건' 이다")
print("=" * W)
for rt, nm in CELLS:
    d = dd(C(rt), 40, lo="20160101")
    cnt = d.ym.value_counts()
    print(f"  {nm:<14} 서로 다른 달 {d.ym.nunique():>3}개 · 최다 달 {cnt.index[0]} "
          f"{cnt.iloc[0]}건({cnt.iloc[0]/len(d)*100:.0f}%) · 상위3달 합 {cnt.head(3).sum()/len(d)*100:.0f}%")

print("\n" + "=" * W)
print("③ 생존편향 — 신호 뒤 40일을 못 채운 종목이 통계에서 빠졌는가")
print("=" * W)
for rt, nm in CELLS:
    X = K[(C(rt) & UNI).fillna(False)]
    X = X[(X.date >= "20160101") & (X.di <= LASTDI - 40)]      # 아직 안 끝난 최근분 제외
    dead = (X.lastdi < X.di + 40).sum()
    print(f"  {nm:<14} 신호 {len(X):>6,}건 중 40일 내 데이터가 끊긴 종목 {dead:>4}건 ({dead/max(len(X),1)*100:.2f}%)")
print("  → 이 값이 크면 '살아남은 것만 재고 있다' 는 뜻이다. 미장 패널은 상장폐지분도 담고 있다.")

print("\n" + "=" * W)
print("④ 크기·유동성 프록시인가 — 분위 안에서도 유지되어야 진짜 축이다 (1년 120%↑ · 40일)")
print("=" * W)
d = dd(C(120), 40, lo="20160101")
for lab, col in (("시총", "marcap"), ("거래대금", "amt20"), ("주가", "rawclose")):
    v = pd.qcut(K.loc[d.index, col].rank(method="first"), 4, labels=False)
    m = d.groupby(v).agg(n=("r", "size"), x=("ex", "mean"))
    print(f"  {lab:<8} " + " ".join(f"Q{int(i)+1} {r.x:+.2f}({int(r.n)}건)" for i, r in m.iterrows()))
print("  → 네 분위 전부 양수면 크기·유동성 프록시가 아니다.")

print("\n" + "=" * W)
print("⑤ 보유기간 (1년 120%↑ · 잔잔 ≤1.5%)")
print("=" * W)
print(f"  {'보유':<8}{'건수':>7}{'동시':>6}{'승률':>7}{'평균':>8}{'중앙':>8}{'절삭Δ':>8}{'초과':>8}{'CI':>8}{'양수해':>8}")
for h in (20, 40, 60):
    d = dd(C(120), h, lo="20160101")
    yr = d.groupby(d.date.str[:4]).ex.mean()
    print(f"  {h}일{'':<5}{len(d):>7,}{len(d)/NDAY*h:>6.0f}{(d.r>0).mean()*100:>6.1f}%{d.r.mean():>8.2f}"
          f"{d.r.median():>8.2f}{trimmed(d.r)-BT[h]:>8.2f}{d.ex.mean():>8.2f}"
          f"{boot_ci(d.groupby('ym').ex.mean()):>8.2f}{int((yr>0).sum()):>5}/{len(yr)}")

print("\n" + "=" * W)
print("⑥ 체결 가능성 — 다음날 시가 갭이 얼마나 벌어지나 (신호일 종가 → 매수가)")
print("=" * W)
for rt, nm in CELLS:
    d = dd(C(rt), 40, lo="20160101")
    g = (d.buy / d.close - 1) * 100
    print(f"  {nm:<14} 갭 평균 {g.mean():+.2f}% · 중앙 {g.median():+.2f}% · "
          f"상위10% {g.quantile(0.9):+.2f}% · 5%↑ 갭 {(g>=5).mean()*100:.1f}%")
print("  → 미국은 상한가가 없어 [영웅전 2편] 의 체결불가 함정은 없다. 갭이 크면 그만큼 비싸게 산다는 뜻.")

print("\n" + "=" * W)
print("⑦ 다중검정 보정 — 지금까지 훑은 시행 전부를 반영한다")
print("=" * W)
for rt, nm in CELLS:
    d = dd(C(rt), 40, lo="20160101")
    yr = d.groupby(d.date.str[:4]).ex.mean()
    verdict.judge(f"{nm} · 일간등락 ≤1.5% · 40일",
                  d.groupby("ym").ex.mean(), topic="us_tech_web",
                  median=d.r.median(), last_year=yr.get("2026", np.nan))
