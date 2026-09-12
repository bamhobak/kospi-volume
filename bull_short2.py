# -*- coding: utf-8 -*-
"""**미장 상승장 · 짧은 보유(10·20일) 규칙 2단계 — 축 조합** (2026-09-13).

1단계(`bull_short.py`)에서 미장은 465칸 중 33칸이 통과했다. 그런데 통과한 축이 전부 한
덩어리다 — `a240`(장기 거래대금) · `fromhi`(고점 근처) · `above20` · `mdd60`(안 빠짐) ·
`vol20`·`rng`(조용) · `ret120`·`ret250`(중기 상승). 단일로는 초과가 +0.05~+0.74 로 얇다.

여기서 둘씩·셋씩 묶어 **상승장 20일 자리**(지금 비어 있다 — N2 만 20일인데 하락장 전용)를
채울 수 있는지 본다. ⚠ 그냥 묶으면 **N1 [상승장 신고가]를 다시 만들 뿐**이므로,
통과한 칸은 반드시 **N1·N5 와 겹치는 정도**를 같이 잰다.

    python bull_short2.py
"""
import sys, time, warnings, itertools
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
TR1, VA0 = "20221231", "20230101"
HOLDS = (10, 20)
W = 136


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
UTRIM = {}
for h in HOLDS:
    u = K[UNI].dropna(subset=[f"n{h}"])[f"n{h}"]
    UTRIM[h] = u[u <= u.quantile(0.95)].mean()

BM = (UNI & UP).fillna(False)
A = K[BM].copy()
log(f"상승 국면 유니버스 {len(A):,}행")
for c in ("a240", "fromhi", "vol20", "mdd60", "above20", "ret120", "rng"):
    A[c + "_q"] = A.groupby("date")[c].rank(pct=True)

# 1단계에서 살아남은 방향 그대로
AX = [("A 거래대금(1년) 상위20%", A.a240_q >= 0.8),
      ("B 고점 근처 상위40%", A.fromhi_q >= 0.6),
      ("C 조용함(변동성 하위40%)", A.vol20_q <= 0.4),
      ("D 안 빠짐(낙폭 상위40%)", A.mdd60_q >= 0.6),
      ("E 20일선 위 오래 상위40%", A.above20_q >= 0.6),
      ("F 중기상승(120일 상위40%)", A.ret120_q >= 0.6),
      ("G 일간폭 작음(하위20%)", A.rng_q <= 0.2)]
NM = {n[0]: n for n, _ in AX}

# N1·N5 대리 조건 — 겹침 측정용
N1p = (A.fromhi >= -5) & (A.ret250 > 0) & (A.vol20 <= 3)
N5p = (A.ret250 >= 120) & (A.ret60 > 0) & (A.ret120 > 0) & (A.vol20 <= 1.5)

NT = 0
HDR = (f"  {'조합':<34}{'보유':>5}{'n':>8}{'초과':>7}{'중앙':>7}{'절삭Δ':>7}{'승률':>6}"
       f"{'검증중앙':>9}{'학CI':>7}{'전CI':>7}{'양수해':>7}{'N1겹':>6}{'N5겹':>6}")


def judge(tag, mask, h, minn=150, show=True):
    global NT
    NT += 1
    X = A[mask.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    Y = X.loc[keep]; Y = Y[Y.date >= "20160101"]
    if len(Y) < minn:
        if show: print(f"  {tag:<34}{h:>4}일{len(Y):>8} (부족)")
        return None
    Y = Y.copy()
    Y["r"] = Y[f"n{h}"].astype(float); Y["ex"] = Y.r - Y.date.map(BEN[h])
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean() - UTRIM[h]
    ym = Y.date.str[:6]; yr = Y.date.str[:4]
    tr = Y.date <= TR1; va = Y.date >= VA0
    ci = boot_ci(Y.ex.groupby(ym).mean())
    cit = boot_ci(Y.ex[tr].groupby(ym[tr]).mean()) if tr.sum() >= 60 else np.nan
    ymed = Y.groupby(yr).r.median(); pos, ny = int((ymed > 0).sum()), len(ymed)
    vam = Y.r[va].median() if va.sum() >= 30 else np.nan
    o1 = N1p.reindex(Y.index).fillna(False).mean() * 100
    o5 = N5p.reindex(Y.index).fillna(False).mean() * 100
    ok = (Y.r.median() > 0 and trim > 0 and Y.ex.mean() > 0 and ci == ci and ci > 0
          and cit == cit and cit > 0 and vam == vam and vam > 0 and pos / max(ny, 1) >= 0.6)
    if show:
        print(f"  {tag:<34}{h:>4}일{len(Y):>8,}{Y.ex.mean():>7.2f}{Y.r.median():>7.2f}{trim:>7.2f}"
              f"{(Y.r > 0).mean() * 100:>5.0f}%{vam:>9.2f}{cit:>7.2f}{ci:>7.2f}{pos:>3}/{ny:<3}"
              f"{o1:>5.0f}%{o5:>5.0f}%" + ("  ✅" if ok else ""))
    return dict(tag=tag, h=h, n=len(Y), ex=Y.ex.mean(), med=Y.r.median(), trim=trim,
                ci=ci, cit=cit, vam=vam, pos=pos, ny=ny, o1=o1, o5=o5, ok=ok)


sec("① 두 축 조합 (21쌍 × 보유 2종)")
print("  N1겹·N5겹 = 신호 중 N1·N5 대리조건도 만족하는 비중. 높으면 '그 규칙을 다시 만든 것' 이다.")
print(HDR)
hits = []
for (n1, c1), (n2, c2) in itertools.combinations(AX, 2):
    tag = f"{n1[0]}+{n2[0]} {n1[2:14]}·{n2[2:12]}"
    for h in HOLDS:
        d = judge(tag, c1 & c2, h)
        if d and d["ok"]: hits.append((d, c1 & c2))

sec("② 통과한 짝에 세 번째 축 얹기")
print(HDR)
top = sorted({h[0]["tag"][:3] for h in hits})
if not hits:
    print("  통과한 짝이 없다 — 삼중 조합은 건너뛴다.")
else:
    seen = set()
    for d, m in hits:
        key = d["tag"][:3]
        if key in seen: continue
        seen.add(key)
        used = set(key.replace("+", ""))
        for n3, c3 in AX:
            if n3[0] in used: continue
            for h in HOLDS:
                r = judge(f"{key}+{n3[0]} {n3[2:16]}", m & c3, h)
                if r and r["ok"]: hits.append((r, m & c3))

sec("③ 판정")
best = sorted([d for d, _ in hits], key=lambda x: -x["ex"])[:12]
if not best:
    print("  통과 없음.")
else:
    print(f"  {'조합':<34}{'보유':>5}{'n':>8}{'초과':>7}{'절삭Δ':>7}{'N1겹':>7}{'N5겹':>7}")
    for d in best:
        print(f"  {d['tag']:<34}{d['h']:>4}일{d['n']:>8,}{d['ex']:>7.2f}{d['trim']:>7.2f}"
              f"{d['o1']:>6.0f}%{d['o5']:>6.0f}%")
print(f"\n  시험한 칸 {NT}개")
try:
    from verdict import log_trials
    log_trials("us_bull_short", 465 * 2 + NT)
    print("  trials.json 기록 — 1단계 930칸 + 여기 칸수")
except Exception as e:
    print(f"  trials 기록 실패: {e!r}")
log("끝")
