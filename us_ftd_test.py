# -*- coding: utf-8 -*-
"""결제불이행(FTD) 축 실측 — 한국에 아예 없는 재료.

FTD 는 정해진 날짜에 주식이 인도되지 않은 수량이다. 무차입 공매도·유동성 압박의
대용 지표로 쓰이고 스퀴즈 직전에 치솟는 경향이 있다고 알려져 있다.
한국에는 종목별 공개 데이터가 없어 우리가 한 번도 못 재본 축이다.

우리 스타일과 맞는 이유: 우리는 떨어진 것을 산다. FTD 급증은 공매도 압력이 극에 달한
자리라 반등 재료일 수 있다. 반대로 '팔지 못한 물량이 쌓였다' 는 악재 해석도 가능하다.
어느 쪽인지는 재봐야 안다.

재는 것
  ① FTD 절대 수준 — 발행주식수 대비 비율(ftd_r)로 구간 나누기
  ② FTD 급증 — 20일 평균 대비 배수
  ③ 우리 재료와 조합 — 낙폭·업종붕괴와 함께
  ④ 반대편 — FTD 가 거의 없는 종목

⚠ FTD 는 결제일 기준이라 거래일보다 **2영업일 늦게** 보고된다. 공시 시점을 지켜
   미리보기가 생기지 않게 한다(SEC 는 격주로 묶어 그 다음 달에 낸다 → 넉넉히 15영업일 지연).
"""
import io, sys, glob, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HS = [5, 20, 60]

K = pd.read_pickle(BASE / "data" / "panel_us.pkl")
print(f"미국 패널 {len(K):,}행 · {K.ticker.nunique():,}종목")

F = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/ftd/*.pkl")))],
              ignore_index=True)
F = F.dropna(subset=["ticker", "date", "ftd"])
F["ftd"] = pd.to_numeric(F.ftd, errors="coerce")
F = F.dropna(subset=["ftd"]).groupby(["ticker", "date"], as_index=False).ftd.sum()
print(f"FTD {len(F):,}행 · {F.ticker.nunique():,}종목 · {F.date.min()}~{F.date.max()}")

# ⚠ 공시 지연 — 결제일 기준 데이터를 그날 알 수는 없다. 15영업일 뒤부터 쓴다.
dates = np.array(sorted(K.date.unique()))
pos = {d: i for i, d in enumerate(dates)}
F["i"] = F.date.map(pos)
F = F.dropna(subset=["i"])
F["i"] = F.i.astype(int) + 15
F = F[F.i < len(dates)]
F["date"] = dates[F.i.values]
F = F.groupby(["ticker", "date"], as_index=False).ftd.max()
print(f"  공시 지연 15영업일 반영 후 {len(F):,}행")

K = K.merge(F, on=["ticker", "date"], how="left")
g = K.groupby("ticker", sort=False)
K["ftd"] = g.ftd.ffill(limit=20)                       # 격주 공시라 사이를 메운다
K["ftd_r"] = K.ftd / K.shares * 100                    # 발행주식수 대비 %
K["ftd_a20"] = g.ftd.transform(lambda s: s.rolling(20, min_periods=5).mean())
K["ftd_sp"] = K.ftd / K.ftd_a20.replace(0, np.nan)     # 20일 평균 대비 배수
print(f"  ftd 유효 {K.ftd.notna().mean()*100:.0f}% · ftd_r 유효 {K.ftd_r.notna().mean()*100:.0f}%")


def base(amt=1.0):
    return (K.close >= 3) & (K.amt20.fillna(0) >= amt)


UNI = {h: K[base()].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HS}


def stat(m, h, nm):
    col = f"n{h}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 300:
        return None
    di = {d: i for i, d in enumerate(dates)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h; keep.append(ix)
    X = X.loc[keep]
    if len(X) < 200:
        return None
    X["ex"] = X[col] - X.date.map(UNI[h])
    tr, va = X[X.date <= TR1], X[X.date >= VA0]
    if len(tr) < 80 or len(va) < 40:
        return None
    yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
    return dict(n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                trim=X.ex[X.ex <= X.ex.quantile(0.95)].mean(),
                ret=X[col].mean(), win=(X[col] > 0).mean() * 100,
                tr=tr.ex.mean(), va=va.ex.mean(),
                ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean(), 0.10),
                pos=int((yr > 0).sum()), ny=len(yr))


NT, ROWS = 0, []
HDR = (f"  {'조건':<30}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'절대':>8}"
       f"{'승률':>6}{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")


def show(nm, m):
    global NT
    for h in HS:
        NT += 1
        r = stat(m, h, nm)
        if r is None:
            continue
        r["name"] = nm; r["h"] = h; ROWS.append(r)
        print(f"  {nm:<30}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}{r['trim']:>+8.2f}"
              f"{r['ret']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
              f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")


b = base()
print("\n" + "=" * 126)
print("① FTD 절대 수준 — 발행주식수 대비 비율 (2016~, 유니버스 대비 초과)")
print("=" * 126)
print(HDR)
for lo, hi, nm in ((0, 0.01, "FTD 0.01%↓"), (0.01, 0.05, "FTD 0.01~0.05%"),
                   (0.05, 0.2, "FTD 0.05~0.2%"), (0.2, 1.0, "FTD 0.2~1%"),
                   (1.0, 999, "FTD 1%↑(극단)")):
    show(f"① {nm}", b & (K.ftd_r > lo) & (K.ftd_r <= hi))

print("\n" + "=" * 126)
print("② FTD 급증 — 20일 평균 대비 몇 배")
print("=" * 126)
print(HDR)
for lo, hi, nm in ((3, 10, "급증 3~10배"), (10, 50, "급증 10~50배"), (50, 9999, "급증 50배↑")):
    show(f"② {nm}", b & (K.ftd_sp > lo) & (K.ftd_sp <= hi))

print("\n" + "=" * 126)
print("③ 우리 재료와 조합 — 떨어진 자리 + FTD")
print("=" * 126)
print(HDR)
fall = b & (K.ret20 <= -20)
show("③ 20일 -20%↓ (기준)", fall)
show("③ 낙폭 + FTD 0.2%↑", fall & (K.ftd_r >= 0.2))
show("③ 낙폭 + FTD 급증 10배↑", fall & (K.ftd_sp >= 10))
show("③ 낙폭 + 업종붕괴", fall & (K.u <= -10))
show("③ 낙폭 + 업종 + FTD 0.2%↑", fall & (K.u <= -10) & (K.ftd_r >= 0.2))

R = pd.DataFrame(ROWS)
print("\n" + "=" * 126)
print("생존 후보 — 중앙>0 · 절삭>0 · 학습·검증 둘 다>0 · 월CI>0")
print("=" * 126)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0)] if len(R) else R
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  {r['name']:<30} {r.h}일 · {r.n:>6,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} 절대 {r.ret:+.2f}% CI{r.ci:+.2f}")
else:
    print("  없음")
verdict.log_trials("미국 FTD 축", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
