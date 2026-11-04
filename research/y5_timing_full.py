# -*- coding: utf-8 -*-
"""1억 1년에서 잘 나온 시장 타이밍(y4_timing: 'vol20 ≥ 찾기 중앙 & 시장 외인 20일 순매수 ≥ 찾기 30%')을 전체 과거로(2026-11-05 사용자
"1년 테스트 좋게 나온 건 과거 데이터로 전체 실측해봐").
y4 의 외인 신호는 flow11(2018~) 종목 합이라 그 전이 없다 → KRX 시장 합계(pykrx 투자자별 거래대금, 코스피+코스닥, 2005~)로
  ff20' = 외국인합계 순매수 20일 합 ÷ 시장 거래대금 20일 합 × 100 을 만들고, 문턱은 y4 와 같은 방식(2018~2022 의 30% 분위)으로 정한다.
  2005~2017 은 외인 조건이 한 번도 안 본 구간 · vol20 문턱(0.912)은 y4 그대로.
판: 둘 다 · 변동성만 · 외인만 · 그냥 들고 있기 — 해마다·전체 연 수익·샤프·낙폭·들고 있는 날. 코스피(KS11, 배당 뺌), 바꿀 때 0.1%.
    python research/y5_timing_full.py
"""
import os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import y4_timing as T

CACHE = BASE / "data" / "y5_ff.pkl"
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def ff_hist():
    if CACHE.exists(): return pd.read_pickle(CACHE)
    for l in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    from pykrx import stock
    F, V = [], []
    for y in range(2004, 2027):
        a, b = "%d0101" % y, "%d1231" % y
        for mk, ix in (("KOSPI", "1001"), ("KOSDAQ", "2001")):
            d = stock.get_market_trading_value_by_date(a, b, mk)[["외국인합계"]].rename(columns={"외국인합계": mk}); time.sleep(2); F.append(d)
            o = stock.get_index_ohlcv(a, b, ix)[["거래대금"]].rename(columns={"거래대금": mk}); time.sleep(2); V.append(o)
        print("받음", y, flush=True)
    f = pd.concat(F).groupby(level=0).sum(min_count=1); v = pd.concat(V).groupby(level=0).sum(min_count=1)
    D = pd.DataFrame({"fnet": f.sum(axis=1), "turn": v.sum(axis=1)}); D.index = D.index.strftime("%Y%m%d")
    D.to_pickle(CACHE); return D


def main():
    S = T.signals(); ret = S.ret.shift(-1)
    D = ff_hist()
    S["ffx"] = (D.fnet.rolling(20).sum() / D.turn.rolling(20).sum() * 100).reindex(S.index)
    L = S[(S.index >= "20050101") & (S.index <= "20221231")]; L18 = S[(S.index >= "20180101") & (S.index <= "20221231")]
    tv = L.vol20.quantile(0.5); tf = L18.ff20.quantile(0.3); tx = L18.ffx.quantile(0.3)
    m = S.ff20.notna() & S.ffx.notna()
    P("시장 외인 신호 비교(2018~): 종목 합 ff20 ↔ 시장 합계 ff20' 상관 %.2f · 조건(30%% 위) 일치 %.0f%%" % (
        S.ff20[m].corr(S.ffx[m]), ((S.ff20[m] >= tf) == (S.ffx[m] >= tx)).mean() * 100))
    P("문턱: vol20 ≥ %.3f · ff20' ≥ %.3f (2018~2022 30%%)" % (tv, tx))
    pos = {"둘 다(규칙)": ((S.vol20 >= tv) & (S.ffx >= tx)).astype(float), "변동성만": (S.vol20 >= tv).astype(float),
           "외인만": (S.ffx >= tx).astype(float), "그냥 들고 있기": pd.Series(1.0, index=S.index)}
    P("\n## 구간별\n"); P("| 구간 | " + " | ".join(pos) + " |"); P("|---" * (len(pos) + 1) + "|")
    for nm, lo, hi in (("2005~2017(외인 조건 처음 보는 구간)", "20050101", "20171231"), ("2018~2022(찾기)", "20180101", "20221231"),
                       ("2023~2025-10(확인)", "20230101", "20251031"), ("2025-11~2026-11(굴리기)", "20251104", "20261103"), ("전체 2005~2026", "20050101", "20261103")):
        P("| %s | %s |" % (nm, " | ".join("연 %+.1f%% · 샤프 %.2f · 낙폭 %.0f%% · %.0f%%" % tuple(T.perf(p, ret, lo, hi)[k] for k in ("cagr", "sh", "dd", "expo")) for p in pos.values())))
    P("\n## 해마다 수익(%)\n"); P("| 해 | " + " | ".join(pos) + " | 규칙 − 들고 있기 |"); P("|---" * (len(pos) + 2) + "|")
    win = 0; ys = range(2005, 2027)
    for y in ys:
        lo, hi = "%d0101" % y, "%d1231" % y
        if y == 2026: hi = "20261103"
        v = [T.perf(p, ret, lo, hi)["cagr"] if y < 2026 else (np.prod(1 + (p * ret.fillna(0) / 100)[(S.index >= lo) & (S.index <= hi)]) - 1) * 100 for p in pos.values()]
        win += v[0] > v[3]
        P("| %d | %s | %+.1f |" % (y, " | ".join("%+.1f" % x for x in v), v[0] - v[3]))
    P("\n규칙이 그냥 들고 있기를 이긴 해 %d/%d" % (win, len(ys)))
    (ROOT / "y5_timing_full.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
