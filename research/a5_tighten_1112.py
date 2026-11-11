# -*- coding: utf-8 -*-
"""[예상 하회](A5·T7) 조이기 — 종목 수를 줄이면서 수익금은 지키거나 늘릴 수 있나(2026-11-12 사용자 "실전 50만·100만, 매수 대기 금액이 너무 커지니 종목을 줄이면서 수익금 유지·증가").
자료 = 장전 호가 녹화(data/factory/auction, 10-12~) × 서버 1분봉(시가 = 09:01 봉 시가 · 종가 = 마지막 봉) × 데이 아침 snap 유니버스.
  a_err = (08:56 장전 균형가 − 시가) ÷ 어제 KRX 종가 %p · 시가 매수 → 종가 매도 · 비용 0.23 · 1천원↑ · 상하한가 근처 뺌
  ⚠ F1659 는 11-07 에 '최근 20거래일' 정답지로 뽑혀 10-12~11-06 은 고른 구간과 겹친다 — 11-07 뒤만 처음 보는 날.
  판마다: 하루 종목 수 · 건당 · 승률 · 날 바구니(시장 대비 초과) · 50만·100만 하루 손익(체결 손해 모형 t1_size_liq fit, p = 금액 ÷ 20일 평균 거래대금)
    python research/a5_tighten_1112.py
"""
import io, contextlib, glob, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory")); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import auction as AU
import t1_size_liq_1021 as SL

COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def m1(d):
    f = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % d)
    if not f.exists(): return None
    X = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); X = X[X.v > 0].sort_values(["t", "ts"]); g = X.groupby("t")
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "amt": (X.c * X.v).groupby(X.t).sum()})


def build():
    days = sorted(Path(p).name[3:11] for p in glob.glob(str(BASE / "data" / "factory" / "auction" / "KR_*_am.parquet")))
    allm = sorted(Path(p).stem for p in glob.glob(str(BASE / "data" / "m1" / "KR" / "day" / "*.parquet")))
    AM = {}                                                             # 날별 종목 거래대금(1분봉 합, NXT 포함) → 앞 날들 평균 = a20
    rows = []
    for d in days:
        sf = BASE / "data" / "day" / ("snap_%s.json" % d)
        pv = max([x for x in allm if x < d], default=None)
        K, Kp = m1(d), (m1(pv) if pv else None)
        if not sf.exists() or K is None or Kp is None: continue
        uni = list(json.loads(sf.read_text(encoding="utf-8")).get("all") or {})
        F = AU.features(d)
        if F is None or F.empty: continue
        F = F.set_index("ticker")
        prev = [x for x in allm if x < d][-20:]
        for x in prev:
            if x not in AM:
                k = m1(x); AM[x] = k.amt if k is not None else pd.Series(dtype=float)
        a20 = pd.concat([AM[x] for x in prev], axis=1).mean(axis=1) if len(prev) >= 3 else pd.Series(dtype=float)
        for t in uni:
            if t not in K.index or t not in Kp.index or t not in F.index: continue
            pc, o, c, e = Kp.c[t], K.o[t], K.c[t], F.eq59.get(t)
            if not (pc and o and c and e == e and e) or pc < 1000 or abs(o / pc - 1) >= 0.29: continue
            rows.append(dict(date=d, t=t, pc=pc, o=o, c=c, eq=e, aerr=(e - o) / pc * 100, gap=(o / pc - 1) * 100, aeq=(e / pc - 1) * 100,
                             imb=F.imb59.get(t), nxt=((F.nxt.get(t) / pc - 1) * 100) if F.nxt.get(t) == F.nxt.get(t) and F.nxt.get(t) else np.nan,
                             a20=a20.get(t, np.nan), ret=(c / o - 1) * 100 - COST))
    A = pd.DataFrame(rows)
    A["mkt"] = A.groupby("date").ret.transform("mean")
    A["q"] = A.groupby("date").aerr.rank(pct=True); A["rk"] = A.groupby("date").aerr.rank(ascending=False)
    return A


def main():
    A = build()
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    nd = A.date.nunique()
    P("자료 %d일(%s~%s) · 종목-일 %d · 하루 평균 %.0f종목 · 시장(유니버스) 시가→종가 평균 %+.2f%%\n" % (nd, A.date.min(), A.date.max(), len(A), len(A) / nd, A.groupby("date").ret.mean().mean()))
    top = A[A.q >= 0.9]
    V = {"지금: 상위 10%": top}
    for n in (5, 10, 20, 30, 50): V["상위 %d개" % n] = A[A.rk <= n]
    for x in (2, 3, 4, 5): V["a_err ≥ %d%%p" % x] = A[A.aerr >= x]
    V["상위 10% · 시가가 어제보다 낮게(갭<0)"] = top[top.gap < 0]
    V["상위 10% · 갭 ≤ -2%"] = top[top.gap <= -2]
    V["상위 10% · 갭 ≥ 0"] = top[top.gap >= 0]
    V["상위 10% · 예상 갭 > 0(올라 열릴 줄 알았는데)"] = top[top.aeq > 0]
    V["상위 10% · 매수 쏠림(imb>0)"] = top[top.imb > 0]
    V["상위 10% · 거래대금 큰 절반"] = top[top.a20 >= top.groupby("date").a20.transform("median")]
    V["상위 10% · 거래대금 작은 절반"] = top[top.a20 < top.groupby("date").a20.transform("median")]
    V["상위 10% · 거래대금 50억↑"] = top[top.a20 >= 50e8]
    V["상위 20개 · 거래대금 50억↑"] = A[A.a20 >= 50e8].sort_values(["date", "rk"]).groupby("date").head(20)
    V["상위 10개 · 거래대금 50억↑"] = A[A.a20 >= 50e8].sort_values(["date", "rk"]).groupby("date").head(10)
    V["상위 20개 · 거래대금 20억↑"] = A[A.a20 >= 20e8].sort_values(["date", "rk"]).groupby("date").head(20)
    V["상위 10% · a_err ≥ 3%p"] = top[top.aerr >= 3]
    P("| 판 | 하루 종목 | 건당 | 승률 | 날 바구니 − 시장 | 10-12~11-06 | 11-09~11(그림자) | 50만 하루 손익 · 총액 | 100만 하루 손익 · 총액 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for nm, Z in V.items():
        if not len(Z): continue
        bk = Z.groupby("date").apply(lambda g: g.ret.mean() - g.mkt.iloc[0])
        late = bk[bk.index >= "20261107"]; early = bk[bk.index < "20261107"]
        cells = []
        for amt in (50e4, 100e4):
            p = amt / Z.a20.fillna(Z.a20.median()) * 100
            pnl = (amt * fill(p) * (Z.ret - imp(p)) / 100).sum() / nd
            cells.append("%+.0f만 · %.0f만" % (pnl / 1e4, amt * len(Z) / nd / 1e4))
        P("| %s | %.1f | %+.2f%% | %.0f%% | %+.2f%%p (플러스 날 %d/%d) | %+.2f%%p (%d/%d) | %+.2f%%p | %s | %s |" % (
            nm, len(Z) / nd, Z.ret.mean(), (Z.ret > 0).mean() * 100, bk.mean(), (bk > 0).sum(), len(bk), early.mean(), (early > 0).sum(), len(early),
            late.mean() if len(late) else np.nan, cells[0], cells[1]))
    P("\n날짜별(지금 판 · 상위 20개 · 상위 10개): 시장 / 바구니")
    for d, g in A.groupby("date"):
        P("  %s 시장 %+.2f · 10%% %+.2f · 20개 %+.2f · 10개 %+.2f" % (d, g.ret.mean(), g[g.q >= 0.9].ret.mean(), g[g.rk <= 20].ret.mean(), g[g.rk <= 10].ret.mean()))
    A.to_pickle(BASE / "data" / "a5_tighten_1112.pkl")
    (ROOT / "a5_tighten_1112.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
