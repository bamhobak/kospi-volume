# -*- coding: utf-8 -*-
"""초단기 4단계 — 유일한 생존자를 현실 조건으로 두들긴다.

3단계에서 [코스닥 갭-5 + 하락장 + 이격] 만 네 구간·세 비중 전부 12/12 였다.
그러나 계좌 배수(135배)는 그대로 믿을 수 없다. 1일 보유는 자리가 매일 비어
연 200회 가까이 매매하고, 작은 엣지도 21년이면 터무니없이 불어난다.
채택 전에 **깨질 만한 곳을 전부 두들긴다.**

  ① 거래대금 하한 — 3억은 하루짜리 매매에 너무 낮다. 20·50·100·300억으로 올린다
  ② 체결 밀림 — 0.5% 는 낙관적일 수 있다. 1·2·3% 까지 밀어본다
  ③ 연도별 — 특정 해 몰림이 아닌가 (2020-03 함정)
  ④ 하루 신호 수 — 같은 날 몰려 나오면 실제로 다 못 산다. 상위 N 개만 산다면?
  ⑤ 매도 시점 — 종가 매도가 안 되면? 다음날 시가 매도로 바꾸면 남는가
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"

src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KQ, base, dn60 = ns["KQ"], ns["base"], ns["dn60"]

g = KQ.groupby("ticker", sort=False)
KQ["dev25x"] = (KQ.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
nxt_o, nxt_c = g.open.shift(-1), g.close.shift(-1)
nn_o = g.open.shift(-2)                       # 다다음날 시가 = '종가 매도 못 할 때' 대안
for slip, tag in ((0.0, ""), (0.005, "s5"), (0.010, "s10"), (0.020, "s20"), (0.030, "s30")):
    KQ[f"r1{tag}"] = (nxt_c / (nxt_o * (1 + slip)) - 1) * 100 - KQ.cost
KQ["r1open"] = (nn_o / (nxt_o * 1.005) - 1) * 100 - KQ.cost      # 다음날 시가 매도(밀림 0.5%)
UNI = KQ.dropna(subset=["r1"]).groupby("date").r1.mean()

CORE = base(KQ, 3) & (KQ.gap <= -5) & dn60(KQ) & (KQ.dev25x <= -12)


def ex(m, col="r1s5", lo=TR0, hi="20991231"):
    X = KQ[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[(X.date >= lo) & (X.date <= hi)]
    if len(X) < 30:
        return None
    e = X[col] - X.date.map(UNI)
    return dict(n=len(X), ex=e.mean(), med=e.median(),
                trim=e[e <= e.quantile(0.95)].mean(),
                ci=verdict.boot_ci(e.groupby(X.date.str[:6]).mean(), 0.10),
                win=(X[col] > 0).mean() * 100)


print("=" * 112)
print("① 거래대금 하한 — 하루짜리 매매에 3억은 너무 낮다 (밀림 0.5%)")
print("=" * 112)
print(f"  {'하한':<12}{'건수':>7}{'연평균':>7}{'초과':>9}{'중앙':>9}{'절삭':>9}{'승률':>6}"
      f"{'월CI':>9}{'학습':>9}{'검증':>9}")
NT = 0
for amt in (3, 20, 50, 100, 300):
    NT += 1
    m = CORE & (KQ.amt20 >= amt)
    r = ex(m)
    if r is None:
        print(f"  {amt}억↑  표본부족"); continue
    tr, va = ex(m, lo=TR0, hi=TR1), ex(m, lo=VA0)
    print(f"  {amt:>4}억↑{'':<6}{r['n']:>7,}{r['n']/11:>7.0f}{r['ex']:>+9.2f}{r['med']:>+9.2f}"
          f"{r['trim']:>+9.2f}{r['win']:>5.0f}%{r['ci']:>+9.2f}"
          f"{tr['ex'] if tr else float('nan'):>+9.2f}{va['ex'] if va else float('nan'):>+9.2f}")

print("\n" + "=" * 112)
print("② 체결 밀림 — 갭하락 시가에 코스닥을 담으면 0.5% 로 안 끝난다 (거래대금 50억↑)")
print("=" * 112)
M = CORE & (KQ.amt20 >= 50)
print(f"  {'밀림':<10}{'초과':>9}{'중앙':>9}{'절삭':>9}{'승률':>6}{'월CI':>9}")
for tag, lab in (("", "0%"), ("s5", "0.5%"), ("s10", "1%"), ("s20", "2%"), ("s30", "3%")):
    NT += 1
    r = ex(M, f"r1{tag}")
    print(f"  {lab:<10}{r['ex']:>+9.2f}{r['med']:>+9.2f}{r['trim']:>+9.2f}{r['win']:>5.0f}%{r['ci']:>+9.2f}")

print("\n" + "=" * 112)
print("③ 연도별 — 한 해 몰림이 아닌가 (거래대금 50억↑ · 밀림 0.5%)")
print("=" * 112)
X = KQ[M.fillna(False)].dropna(subset=["r1s5"]).copy()
X = X[X.date >= "20050101"]
X["e"] = X.r1s5 - X.date.map(UNI)
X["y"] = X.date.str[:4]
Y = X.groupby("y").e.agg(["size", "mean", "median"])
print("  " + "  ".join(f"{i}:{int(r['size'])}건 {r['mean']:+.1f}%" for i, r in Y.iterrows()))
tot = X[X.date >= TR0].e.sum()
top = X[X.date >= TR0].groupby(X.date.str[:6]).e.sum().sort_values(ascending=False)
print(f"  2016~ 수익 합 중 가장 큰 달 {top.index[0]} 가 {top.iloc[0]/tot*100:.0f}% · "
      f"상위 3개월 합 {top.iloc[:3].sum()/tot*100:.0f}% · 양수해 {(Y['mean']>0).sum()}/{len(Y)}")

print("\n" + "=" * 112)
print("④ 하루에 몇 개나 나오나 — 몰려 나오면 다 못 산다 (거래대금 50억↑)")
print("=" * 112)
D = X[X.date >= TR0].groupby("date").size()
print(f"  신호 난 날 {len(D)}일 · 하루 중앙 {D.median():.0f}개 · 평균 {D.mean():.1f}개 · "
      f"최대 {D.max()}개 · 5개 넘는 날 {(D > 5).sum()}일({(D>5).mean()*100:.0f}%)")
print("  하루에 상위 N 개만 산다면 (이격이 큰 순서로 골라):")
Z = X[X.date >= TR0].copy()
Z["rk"] = Z.groupby("date").dev25x.rank(method="first")
for n in (1, 2, 3, 5, 999):
    NT += 1
    z = Z[Z.rk <= n]
    print(f"    상위 {n if n < 999 else '전부':<4} {len(z):>5,}건 초과 {z.e.mean():>+6.2f}% "
          f"중앙 {z.e.median():>+6.2f} 절삭 {z[z.e <= z.e.quantile(0.95)].e.mean():>+6.2f} "
          f"CI {verdict.boot_ci(z.groupby(z.date.str[:6]).e.mean(), 0.10):>+6.2f}")

print("\n" + "=" * 112)
print("⑤ 매도 시점 — 종가에 못 팔면? 다음날 시가 매도로 바꾸면 (거래대금 50억↑)")
print("=" * 112)
NT += 1
r1 = ex(M, "r1s5")
Xo = KQ[M.fillna(False)].dropna(subset=["r1open"]).copy()
Xo = Xo[Xo.date >= TR0]
eo = Xo.r1open - Xo.date.map(UNI)
print(f"  당일 종가 매도  {r1['n']:>5,}건 초과 {r1['ex']:+.2f}% 중앙 {r1['med']:+.2f} 절삭 {r1['trim']:+.2f}")
print(f"  다음날 시가 매도 {len(Xo):>5,}건 초과 {eo.mean():+.2f}% 중앙 {eo.median():+.2f} "
      f"절삭 {eo[eo <= eo.quantile(0.95)].mean():+.2f}")

verdict.log_trials("초단기 스트레스", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
