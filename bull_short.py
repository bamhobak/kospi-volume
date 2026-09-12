# -*- coding: utf-8 -*-
"""**상승장 · 짧은 보유(5~20일) 규칙 탐색** — 국내·미장 (2026-09-12).

왜 필요한가: 사용자가 "장기 보유는 나랑 안 맞는다, 5~20일이 좋다" 고 했다. 그런데 지금
국내 상승장 규칙은 [조용한 신고가](40일)·[외인 매집](60일) **둘뿐이고 둘 다 길다**.
5~20일 규칙 여섯은 **전부 하락장 전용**이다. 그래서 "짧게만 하겠다" = "하락장에만
매매하겠다" 가 되어 버린다(노출 맞춘 짝비교에서 낙폭 -10.8 → -13.7%).

→ **짧게 보유하는 상승장 규칙**을 찾는다. 예전 상승장 탐색(1만2천 칸)은 보유기간을 축으로
   잡지 않았다. 이번엔 5·10·20일로 못 박고 뒤진다.

1단계(이 파일): **단일 축 정찰.** 재료마다 그날 유니버스 안에서 5분위로 잘라, 상승 국면에서
   보유 5·10·20일 초과수익이 한쪽으로 기우는 축이 있는지 본다. 조합은 2단계에서.

    python bull_short.py [kr|us]
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
MK = (sys.argv[1] if len(sys.argv) > 1 else "kr").lower()
TR1, VA0 = "20221231", "20230101"
HOLDS = (5, 10, 20)
W = 128


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log(f"{'us_scan' if MK=='us' else 'kr_scan'}.pkl 읽는 중")
K = pd.read_pickle(BASE / (f"data/us_scan.pkl" if MK == "us" else "data/kr_scan.pkl"))
if MK == "us": K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
else:          K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
JW = (K.jw if "jw" in K.columns else pd.Series(False, index=K.index)).fillna(False)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)

# 국면 — 지수 60일선 위
import FinanceDataReader as fdr
IX = fdr.DataReader("US500" if MK == "us" else "KS11", "2004-06-01")
IX = IX[IX.Close > 0].copy(); IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)
log(f"  {len(K):,}행 · 유니버스 {int(UNI.sum()):,} · 상승국면 {int((UNI&UP).sum()):,}")

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
UTRIM = {}
for h in HOLDS:
    u = K[UNI & ~JW].dropna(subset=[f"n{h}"])[f"n{h}"]
    UTRIM[h] = u[u <= u.quantile(0.95)].mean()

AXES = [c for c in ("fromhi", "fromlo", "ret5", "ret10", "ret20", "ret60", "ret120", "ret250",
                    "dev25", "dma20", "dma60", "dma120", "above20", "dd", "mdd60",
                    "vol20", "vm1", "vm3", "su1", "r16", "rw1", "a40", "a240",
                    "rng", "clv", "gap", "PBR", "PER", "marcap", "sr20", "u") if c in K.columns]
log(f"축 {len(AXES)}개 · 5분위 · 보유 {HOLDS} → {len(AXES)*5*len(HOLDS)}칸")

BASE_M = (UNI & UP & ~JW).fillna(False)
A = K[BASE_M].copy()
log(f"정찰 대상 {len(A):,}행")
log("분위 계산 중")
for c in AXES:
    A[c + "_q"] = A.groupby("date")[c].rank(pct=True)

QS = [(0.0, 0.2, "최하 20%"), (0.2, 0.4, "20~40%"), (0.4, 0.6, "중간"),
      (0.6, 0.8, "60~80%"), (0.8, 1.0, "최상 20%")]


def cell(sub, h):
    X = sub.dropna(subset=[f"n{h}"]).sort_values("di")
    if len(X) < 200: return None
    keep, last = [], {}
    tk = X.ticker.values; di = X.di.values; ix = X.index.values
    for t, i, j in zip(tk, di, ix):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(j)
    Y = X.loc[keep]
    Y = Y[Y.date >= "20160101"]
    if len(Y) < 120: return None
    r = Y[f"n{h}"].astype(float); ex = r - Y.date.map(BEN[h])
    trim = r[r <= r.quantile(0.95)].mean() - UTRIM[h]
    ym = Y.date.str[:6]; yr = Y.date.str[:4]
    ci = boot_ci(ex.groupby(ym).mean())
    tr = Y.date <= TR1; va = Y.date >= VA0
    cit = boot_ci(ex[tr].groupby(ym[tr]).mean()) if tr.sum() >= 200 else np.nan
    ym2 = r.groupby(yr).median()
    return dict(n=len(Y), ex=ex.mean(), med=r.median(), trim=trim, win=(r > 0).mean() * 100,
                vam=r[va].median() if va.sum() > 50 else np.nan, ci=ci, cit=cit,
                pos=int((ym2 > 0).sum()), ny=len(ym2))


sec(f"1단계 정찰 — {'미장' if MK=='us' else '국내'} · 상승 국면 · 축별 5분위")
print("  초과 = 같은날 유니버스 대비 · 절삭Δ = 상위5% 자른 평균의 유니버스 대비 차")
print(f"\n  {'축':<10}{'분위':<10}{'보유':>5}{'n':>8}{'초과':>8}{'절삭Δ':>8}{'중앙':>8}{'승률':>6}"
      f"{'검증중앙':>9}{'학CI':>7}{'전CI':>7}{'양수해':>7}")
hits = []
t0 = time.time()
for c in AXES:
    best = None
    for lo, hi, qn in QS:
        m = (A[c + "_q"] > lo) & (A[c + "_q"] <= hi) if lo > 0 else (A[c + "_q"] <= hi)
        sub = A[m.fillna(False)]
        for h in HOLDS:
            d = cell(sub, h)
            if not d: continue
            ok = (d["ex"] > 0 and d["trim"] > 0 and d["med"] > 0 and d["ci"] == d["ci"] and d["ci"] > 0
                  and d["cit"] == d["cit"] and d["cit"] > 0 and d["vam"] > 0
                  and d["pos"] / max(d["ny"], 1) >= 0.6)
            if ok or d["ex"] >= 0.5:
                print(f"  {c:<10}{qn:<10}{h:>4}일{d['n']:>8,}{d['ex']:>8.2f}{d['trim']:>8.2f}"
                      f"{d['med']:>8.2f}{d['win']:>5.0f}%{d['vam']:>9.2f}{d['cit']:>7.2f}{d['ci']:>7.2f}"
                      f"{d['pos']:>3}/{d['ny']:<3}" + ("  ✅" if ok else ""))
            if ok: hits.append((c, qn, h, d))
    log(f"  {c} 완료 ({time.time()-t0:.0f}초 누적)") if c in (AXES[len(AXES)//2], AXES[-1]) else None

sec("통과한 칸")
if not hits:
    print("  없음 — 단일 축으로는 상승장 짧은 보유에서 아무것도 나오지 않는다.")
else:
    for c, qn, h, d in sorted(hits, key=lambda x: -x[3]["ex"]):
        print(f"  {c:<10}{qn:<10}{h:>4}일  n={d['n']:>6,}  초과 {d['ex']:+.2f}  절삭Δ {d['trim']:+.2f}"
              f"  검증중앙 {d['vam']:+.2f}  양수해 {d['pos']}/{d['ny']}")
log("끝")
