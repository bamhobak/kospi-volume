# -*- coding: utf-8 -*-
"""우리 아홉 규칙이 식고 있나 — 시간에 따른 성적 변화를 본다.

경계 민감도(`split_sens.py`)에서 걸린 것: 코스피 업종+이격은 경계를 뒤로 밀수록
좋아지는데(+2.00 → +3.43) **코스닥은 계속 감쇠했다**(+0.91 → +0.68 → +0.40 → +0.09 → -0.21).
사용자는 지금 실제 돈으로 거래 중이므로 이게 미국 확장보다 급하다.

  ① 규칙별 연도 추이 — 건별 수익 중앙값이 해마다 어떻게 변했나
  ② 최근 3년 vs 그 이전 — 규칙별로 얼마나 식었나
  ③ 시장 탓인가 규칙 탓인가 — 같은 기간 유니버스도 같이 식었는지
  ④ 신호 빈도 변화 — 조건이 안 걸리게 된 것인지, 걸려도 성적이 나쁜 것인지

식는 게 확인되면 그 자체가 결론은 아니다. 표본이 적어 흔들리는 것일 수도 있다.
그래서 건수와 함께 본다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
_r = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = _r
KP, KQ, KB, RULES, TRAIL = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"], ns["TRAIL"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
MK = {"P1": "코스피", "P2": "코스피", "P3": "코스피", "P4": "코스피", "P5": "공통",
      "P6": "코스피", "P7": "코스피", "D1": "코스닥", "D2": "코스닥"}


def sigs(rid):
    K, hold, stop, pct, mx, cond = RULES[rid]
    g = K.groupby("ticker", sort=False)
    C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
    buy = K.buy.values
    t = TRAIL.get(rid)
    hit = np.zeros_like(C, dtype=bool); px = C.copy()
    if t:
        run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
        h = C <= run * (1 - t); hit |= h
        px = np.where(h & ~np.isnan(C), run * (1 - t), px)
    elif stop:
        h = C <= buy[:, None] * (1 - stop); hit |= h
        px = np.where(h, buy[:, None] * (1 - stop), px)
    ok = hit.any(axis=1)
    first = np.where(ok, hit.argmax(axis=1), hold - 1)
    ex = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
    m = cond.fillna(False).values
    X = K[cond.fillna(False)].copy()
    X["ret"] = (ex[m] / X.buy - 1) * 100 - X.cost
    X = X.dropna(subset=["ret"])
    X = X[X.buy > 0]
    # 중복신호 제거
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for tk, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(tk, -10 ** 9) >= i:
            continue
        last[tk] = i + hold; keep.append(ix)
    X = X.loc[keep]
    X["y"] = X.date.str[:4]
    return X, hold


# 유니버스 기준선(같은 기간 아무거나 담았을 때) — 시장 탓인지 가르려고
UNI = {}
for K, mk in ((KP, "코스피"), (KQ, "코스닥")):
    b = ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= 3))
    z = K[b]
    for h in (5, 10, 20, 40, 60):
        c = f"n{h}"
        if c in z.columns:
            UNI[(mk, h)] = z.dropna(subset=[c]).assign(y=lambda d: d.date.str[:4]).groupby("y")[c].median()

S = {rid: sigs(rid) for rid in RULES}

print("=" * 118)
print("① 규칙별 연도 추이 — 건별 수익 **중앙값** (괄호는 건수). 2016~")
print("=" * 118)
yrs = [str(y) for y in range(2016, 2027)]
print(f"  {'규칙':<15}{'시장':<6}" + "".join(f"{y[2:]:>10}" for y in yrs))
for rid in RULES:
    X, h = S[rid]
    z = X[X.date >= "20160101"]
    g = z.groupby("y").ret.agg(["median", "size"])
    row = ""
    for y in yrs:
        if y in g.index:
            row += f"{g.loc[y,'median']:>+7.1f}({int(g.loc[y,'size']):>2})"
        else:
            row += f"{'—':>10}"
    print(f"  {NAME[rid]:<15}{MK[rid]:<6}{row}")

print("\n" + "=" * 118)
print("② 최근 3년(2024~) vs 그 이전(2016~2023) — 얼마나 식었나")
print("=" * 118)
print(f"  {'규칙':<15}{'시장':<6}{'이전 건수':>9}{'이전 중앙':>10}{'최근 건수':>9}{'최근 중앙':>10}"
      f"{'변화':>10}{'유니버스 변화':>14}")
for rid in RULES:
    X, h = S[rid]
    a = X[(X.date >= "20160101") & (X.date < "20240101")]
    b = X[X.date >= "20240101"]
    if not len(a) or not len(b):
        continue
    mk = MK[rid] if MK[rid] != "공통" else "코스피"
    u = UNI.get((mk, h))
    ua = u[[y for y in u.index if "2016" <= y < "2024"]].median() if u is not None else np.nan
    ub = u[[y for y in u.index if y >= "2024"]].median() if u is not None else np.nan
    print(f"  {NAME[rid]:<15}{MK[rid]:<6}{len(a):>9,}{a.ret.median():>+10.2f}{len(b):>9,}"
          f"{b.ret.median():>+10.2f}{b.ret.median()-a.ret.median():>+10.2f}"
          f"{ub-ua:>+13.2f}p")

print("\n" + "=" * 118)
print("③ 3년 이동 중앙값 — 언제부터 꺾였나 (신호가 난 날 기준 최근 750거래일)")
print("=" * 118)
dates = sorted(set(KP.date) | set(KQ.date))
DI = {d: i for i, d in enumerate(dates)}
marks = ["20180101", "20200101", "20220101", "20240101", "20260101"]
print(f"  {'규칙':<15}" + "".join(f"{m[:4]+'까지':>12}" for m in marks) + f"{'지금':>12}")
for rid in RULES:
    X, h = S[rid]
    X = X.assign(i=X.date.map(DI))
    row = ""
    for m in marks + [dates[-1]]:
        # ⚠ 기준일이 거래일이 아니면 DI.get 이 기본값(마지막 인덱스)을 줘서
        #   모든 칸이 같은 값이 된다. 그 날짜 이하의 마지막 거래일을 찾는다.
        j = int(np.searchsorted(dates, m, side="right")) - 1
        j = max(0, min(j, len(dates) - 1))
        z = X[(X.i <= j) & (X.i > j - 750)]
        row += f"{z.ret.median():>+9.1f}({len(z):>2})" if len(z) >= 8 else f"{'—':>12}"
    print(f"  {NAME[rid]:<15}{row}")

print("\n" + "=" * 118)
print("④ 신호 빈도 — 조건이 안 걸리게 된 것인가 (연 신호 수)")
print("=" * 118)
print(f"  {'규칙':<15}" + "".join(f"{y[2:]:>6}" for y in yrs))
for rid in RULES:
    X, h = S[rid]
    g = X[X.date >= "20160101"].groupby("y").size()
    print(f"  {NAME[rid]:<15}" + "".join(f"{int(g.get(y,0)):>6}" for y in yrs))
