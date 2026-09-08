# -*- coding: utf-8 -*-
"""생존편향이 실제로 몇 %짜리인가 — 우리 한국 패널로 직접 잰다.

미국 확장을 검토하며 확인한 것: yfinance 는 폐지 종목 주가를 거의 안 준다
(리먼·엔론·시어스·베드배스·SVB·트위터·액티비전 전부 0행, 8개 중 1개만 성공).
그러면 '지금 상장돼 있는 종목만' 으로 백테스트하게 되는데, 그 왜곡이 얼마인지
**추정하지 말고 재야** 한다. 우리 한국 패널은 폐지 512종목을 갖고 있으므로 잴 수 있다.

  ① 규칙별 — 폐지 종목을 빼면 성적이 얼마나 좋아 보이나
  ② 계좌 — 빼고 돌린 계좌와 넣고 돌린 계좌의 차이
  ③ 폐지 종목이 실제로 얼마나 나쁜가 — 폐지 직전 구간의 수익

여기서 나온 배율이 곧 '미국 데이터를 그대로 쓰면 얼마나 부풀려 보게 되는가' 의 하한이다
(미국은 폐지 비중이 한국과 다를 수 있으므로 정확히 같지는 않다).
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SEEDS = 12
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
_real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = _real
KP, KQ, KB, RULES, TRAIL = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"], ns["TRAIL"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}
# [자사주 낙폭] 이 쓰는 합본 패널(KB)에는 grp 이 없다(portfolio.py 가 필요한 열만 골라 담는다).
# 폐지 여부를 티커 단위로 옮겨 붙인다.
_g = {}
for _K in (KP, KQ):
    _g.update(dict(zip(_K.ticker, _K.grp)))
if "grp" not in KB.columns:
    KB["grp"] = KB.ticker.map(_g).fillna("생존")

print("=" * 104)
print("폐지 종목이 패널에서 차지하는 비중")
print("=" * 104)
for K, nm in ((KP, "코스피"), (KQ, "코스닥")):
    z = K[K.date >= "20160101"]
    d = z[z.grp == "폐지"]
    print(f"  {nm}  전체 {z.ticker.nunique():,}종목 중 폐지 {d.ticker.nunique():,}종목 "
          f"({d.ticker.nunique()/z.ticker.nunique()*100:.1f}%) · "
          f"행 비중 {len(d)/len(z)*100:.1f}%")


def signals(drop_dead):
    """drop_dead=True 면 폐지 종목을 아예 없는 셈 친다(= 미국 데이터 상황)."""
    out = []
    for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
        m = cond.fillna(False)
        if drop_dead:
            m = m & (K.grp != "폐지")
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
        X = K[m].copy()
        mm = m.values
        X["exit"] = ex[mm]; X["hold"] = (first + 1)[mm]
        X["rid"] = rid; X["pct"] = pct; X["mx"] = mx
        X["ret"] = (X.exit / X.buy - 1) * 100 - X.cost
        X = X.dropna(subset=["ret"])
        X = X[X.buy > 0]
        out.append(X[["date", "ticker", "hold", "rid", "pct", "mx", "ret", "grp"]])
    S = pd.concat(out, ignore_index=True)
    S["di"] = S.date.map(ADI)
    return S.dropna(subset=["di"]).sort_values("di").reset_index(drop=True)


SA = signals(False)      # 진짜(폐지 포함)
SB = signals(True)       # 폐지 종목이 없다고 치면

print("\n" + "=" * 104)
print("① 규칙별 — 폐지 종목을 빼면 성적이 얼마나 좋아 보이나 (2016~, 건별 수익)")
print("=" * 104)
print(f"  {'규칙':<16}{'진짜 건수':>9}{'진짜 평균':>10}{'진짜 중앙':>10}"
      f"{'빼면 건수':>10}{'빼면 평균':>10}{'빼면 중앙':>10}{'부풀림':>9}")
A16, B16 = SA[SA.date >= "20160101"], SB[SB.date >= "20160101"]
for rid in RULES:
    a, b = A16[A16.rid == rid], B16[B16.rid == rid]
    if not len(a):
        continue
    print(f"  {NAME[rid]:<16}{len(a):>9,}{a.ret.mean():>+9.2f}%{a.ret.median():>+9.2f}%"
          f"{len(b):>10,}{b.ret.mean():>+9.2f}%{b.ret.median():>+9.2f}%"
          f"{b.ret.mean()-a.ret.mean():>+8.2f}%p")
print(f"  {'전체':<16}{len(A16):>9,}{A16.ret.mean():>+9.2f}%{A16.ret.median():>+9.2f}%"
      f"{len(B16):>10,}{B16.ret.mean():>+9.2f}%{B16.ret.median():>+9.2f}%"
      f"{B16.ret.mean()-A16.ret.mean():>+8.2f}%p")

print("\n" + "=" * 104)
print("③ 폐지 종목이 실제로 얼마나 나쁜가 — 우리 규칙에 걸린 폐지 종목의 성적")
print("=" * 104)
d = A16[A16.grp == "폐지"]
s = A16[A16.grp == "생존"]
print(f"  폐지 종목 신호 {len(d):,}건 ({len(d)/len(A16)*100:.1f}%) · "
      f"평균 {d.ret.mean():+.2f}% · 중앙 {d.ret.median():+.2f}% · 승률 {(d.ret>0).mean()*100:.0f}% · "
      f"최악 {d.ret.min():.1f}%")
print(f"  생존 종목 신호 {len(s):,}건 · 평균 {s.ret.mean():+.2f}% · 중앙 {s.ret.median():+.2f}% · "
      f"승률 {(s.ret>0).mean()*100:.0f}% · 최악 {s.ret.min():.1f}%")


def sim(S, ds, seed):
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d_: g for d_, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd = 1.0, 0.0
    for d_ in ds:
        di = ADI[d_]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        g = byd.get(d_)
        if g is None:
            continue
        for r in g.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d_)
            if k in held:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    return nav, mdd * 100


print("\n" + "=" * 104)
print("② 계좌 — 폐지 종목이 없다고 치면 얼마나 좋아 보이나 (시드 12)")
print("=" * 104)
print(f"  {'구간':<16}{'진짜':>14}{'폐지 빼면':>14}{'부풀림':>12}{'낙폭(진짜→빼면)':>20}")
for pn, lo, hi in (("학습 2016~22", "20160101", "20221231"),
                   ("검증 2023~26", "20230101", "20991231"),
                   ("기준 2016~", "20160101", "20991231"),
                   ("전구간 2005~26", "20050101", "20991231")):
    ds = [d_ for d_ in adates if lo <= d_ <= hi]
    ra = [sim(SA, ds, k) for k in range(SEEDS)]
    rb = [sim(SB, ds, k) for k in range(SEEDS)]
    na, nb = np.median([x[0] for x in ra]), np.median([x[0] for x in rb])
    ma, mb = np.median([x[1] for x in ra]), np.median([x[1] for x in rb])
    print(f"  {pn:<16}{na:>13.2f}배{nb:>13.2f}배{(nb/na-1)*100:>+11.1f}%"
          f"{ma:>13.0f}% →{mb:>5.0f}%")
