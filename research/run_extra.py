# -*- coding: utf-8 -*-
"""run_spec 에 **미리 계산한 열**을 붙여 돌린다 — 조건식 문법(종목별 lag·rolling)으로 못 만드는 재료용 (2026-09-29).

판정·등록·명세 고정·칸 수 기록은 run_spec 그대로다. 패널을 읽는 함수만 가로채 열을 더한다(run_batch 와 같은 방식).

국내(KR)
  secmed20  그날 같은 업종(up) 종목들의 20일 수익 중앙값(업종 5종목↑)
  secrank   secmed20 의 그날 업종 간 백분위(0~1)
  lead3     그 업종 거래대금 상위 3종목의 20일 수익 평균(시총은 2018~22 결측이라 거래대금으로 대장주를 잡는다)
  islead    이 종목이 그 업종 거래대금 상위 3위 안인가
  ytd       올해 첫 거래일 종가 대비 수익(%)
  yend      12월 마지막 거래일인가
미장(US)
  dn60      S&P500 종가가 60일선 아래인가(us_verify 와 같은 국면 정의)

    python research/run_extra.py research/specs/H0240.json ...
"""
import gc, json, sys, time, traceback
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT.parent))
import run_spec as R

_orig = R.load_market
_CACHE = {}


def add_cols(A, mk):
    if mk == "KR":
        g = A.groupby(["date", "up"])
        n = g.ret20.transform("size")
        A["secmed20"] = g.ret20.transform("median").where(n >= 5)
        sm = A.dropna(subset=["secmed20"]).drop_duplicates(["date", "up"])[["date", "up", "secmed20"]]
        sm["secrank"] = sm.groupby("date").secmed20.rank(pct=True)
        A["secrank"] = pd.MultiIndex.from_arrays([A.date, A.up]).map(dict(zip(zip(sm.date, sm.up), sm.secrank)))
        rk = g.amt20.rank(ascending=False, method="first")
        A["islead"] = (rk <= 3) & A.up.notna()
        l3 = A[A.islead].groupby(["date", "up"]).ret20.mean()
        A["lead3"] = pd.MultiIndex.from_arrays([A.date, A.up]).map(l3)
        yr = A.date.str[:4]
        first = A.groupby([A.ticker, yr]).close.transform("first")
        A["ytd"] = (A.close / first - 1) * 100
        dec = A.date[A.date.str[4:6] == "12"]
        lastdec = set(dec.groupby(dec.str[:4]).max().values)
        A["yend"] = A.date.isin(lastdec)
        # 미장 업종 20일(짝 업종) — 미장 d 값은 다음 국내 거래일에 쓴다 (us_sector20.py 가 만든다)
        cp = ROOT / "cache" / "us_sec20.pkl"
        if cp.exists():
            M = pd.read_pickle(cp)
            kd = np.array(sorted(A.date.unique()))
            M["kdate"] = [kd[i] if i < len(kd) else None for i in np.searchsorted(kd, M.date.values, "right")]
            M = M.dropna(subset=["kdate"]).drop_duplicates(["kdate", "up"], keep="last")
            key = pd.MultiIndex.from_arrays([A.date, A.up])
            A["us20"] = key.map(dict(zip(zip(M.kdate, M.up), M.us20)))
            A["us20l5"] = key.map(dict(zip(zip(M.kdate, M.up), M.us20_l5)))
    else:
        import FinanceDataReader as fdr
        ix = fdr.DataReader("US500", "2004-06-01"); ix = ix[ix.Close > 0]
        dn = (ix.Close < ix.Close.rolling(60).mean())
        A["dn60"] = A.date.map(dict(zip(ix.index.strftime("%Y%m%d"), dn.values))).fillna(False).astype(bool)
    return A


def cached_load(mk):
    if mk not in _CACHE:
        A, uni, since = _orig(mk)
        A = add_cols(A, mk)
        _CACHE[mk] = (A, uni, since, list(A.columns))
    A, uni, since, cols = _CACHE[mk]
    extra = [c for c in A.columns if c not in cols]
    if extra:
        A.drop(columns=extra, inplace=True)
    return A, uni, since


R.load_market = cached_load


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    paths = [Path(a) for a in argv if a.endswith(".json")]
    for p in paths:
        R.OUT.clear()
        print("\n" + "=" * 90 + "\n" + p.name + "\n" + "=" * 90, flush=True)
        try:
            R.main([str(p)])
        except Exception:
            traceback.print_exc()
        gc.collect()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
