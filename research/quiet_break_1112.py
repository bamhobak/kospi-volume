# -*- coding: utf-8 -*-
"""잔잔하다 깨진 종목 — 2026-11-12 사용자 "등락률이 몇 달 동안 -1~+1% 안에서 대략 놀다가 최근 며칠 그 범위를 넘어서 거래되는 것들 실측".

자료: data/kospi.db(코스피 2005~ · 코스닥 2005~17) + kosdaq.db(코스닥 2018~) + delisted.db·delisted_kd.db(폐지 종목) — change 칸은 '원' 변동이라 등락률 = change ÷ (종가 − change).
유니버스: 신호일 종가 1천원↑ · 20일 평균 거래대금 3억↑(작은 쪽은 체결이 안 됨) · 상하한가(±29%) 날 제외.
잔잔: 신호 전 L일(L = 60·120, 깨진 며칠은 빼고 그 앞) 중 |등락| ≤ 1% 인 날 비율 ≥ q(0.8·0.9).
깨짐(신호일 t 기준):
  B1  오늘 처음 |등락| > 1% (어제까지 5일은 다 ±1% 안)
  B3  최근 3일 중 2일↑ |등락| > 1% (그 앞 5일은 ±1% 안 — 깨진 지 며칠 안 됨)
  크기: |오늘(또는 3일 합)| > 1%·2%·3% · 방향: 위(+)·아래(−)
매수: 신호 날 종가(종가 매수 — 코스닥 2018~ 자료에 시가가 없음) → h일째 종가(h = 1·5·20·60) · 비용 0.23 · 같은 종목은 60거래일 안 다시 안 셈.
비교: 같은 매수일·같은 보유 유니버스 평균(시장 대비) · 대조군 = 같은 날 '잔잔한데 안 깨진' 종목.
기간: 참고 2005~15 · 학습 2016~22 · 검증 2023~
    python research/quiet_break_1112.py
"""
import sqlite3, sys, math
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

COST = 0.23
HS = (1, 5, 20, 60)
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def load():
    q = lambda db, cols: pd.read_sql("select %s from daily where close > 0" % cols, sqlite3.connect("file:" + str(BASE / "data" / db) + "?mode=ro", uri=True))
    A = q("kospi.db", "ticker, date, open, close, change, amount")
    B = q("kosdaq.db", "ticker, date, open, close, change, volume"); B["amount"] = B.close * B.volume; B = B.drop(columns="volume")
    parts = [A, B]
    for db in ("delisted.db", "delisted_kd.db"):
        try:
            C = q(db, "ticker, date, open, close, change, volume"); C["amount"] = C.close * C.volume; parts.append(C.drop(columns="volume"))
        except Exception as ex:
            print("폐지 자료 못 읽음", db, ex)
    D = pd.concat(parts, ignore_index=True).drop_duplicates(["ticker", "date"], keep="first")
    D["date"] = D.date.astype(str)
    for c in ("open", "close", "change", "amount"): D[c] = pd.to_numeric(D[c], errors="coerce").astype("float32")
    D = D.dropna(subset=["close", "change"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    prev = (D.close - D.change)
    D["change"] = (D.change / prev.where(prev > 0) * 100).astype("float32")            # 원 → %
    D = D.dropna(subset=["change"]).reset_index(drop=True)
    return D


def build(D):
    g = D.groupby("ticker", sort=False)
    r = D.change
    D["in1"] = (r.abs() <= 1.0).astype("float32")
    D["out1"] = 1 - D.in1
    D["a20"] = g.amount.transform(lambda s: s.rolling(20, min_periods=15).mean().shift(1)).astype("float32")
    # 깨지기 전 구간: B1 은 어제까지, B3 는 3일 전까지 — 그 앞 L일의 ±1% 비율
    for L in (60, 120):
        D["q%d_1" % L] = g.in1.transform(lambda s: s.rolling(L, min_periods=int(L * .9)).mean().shift(1)).astype("float32")
        D["q%d_3" % L] = g.in1.transform(lambda s: s.rolling(L, min_periods=int(L * .9)).mean().shift(3)).astype("float32")
    D["calm5_1"] = g.in1.transform(lambda s: s.rolling(5).min().shift(1)).astype("float32")      # 어제까지 5일 다 ±1% 안
    D["calm5_3"] = g.in1.transform(lambda s: s.rolling(5).min().shift(3)).astype("float32")      # 3일 전까지 5일
    D["out3"] = g.out1.transform(lambda s: s.rolling(3).sum()).astype("float32")
    D["lr"] = np.log1p(D.change / 100).astype("float64")
    D["r3"] = ((np.exp(D.groupby("ticker", sort=False).lr.transform(lambda s: s.rolling(3).sum())) - 1) * 100).astype("float32")
    # 앞으로: 다음 날 시가 매수 → h일째 종가
    lc = np.log1p(D.change / 100).astype("float64")
    cs = lc.groupby(D.ticker).cumsum()
    for h in HS:
        cum = cs.groupby(D.ticker).shift(-h) - cs                              # 오늘 종가 → h일째 종가(등락률로, 분할 안전)
        D["f%d" % h] = ((np.exp(cum) - 1) * 100 - COST).astype("float32")
    return D


def stats(Z, h, mk):
    if len(Z) < 20: return None
    x = Z["f%d" % h].dropna()
    if len(x) < 20: return None
    ex = (Z["f%d" % h] - Z.date.map(mk)).dropna()
    by = Z.assign(e=Z["f%d" % h] - Z.date.map(mk)).groupby(Z.date.str[:4]).e.mean()
    seg = lambda a, b: (Z[(Z.date >= a) & (Z.date <= b)]["f%d" % h] - Z[(Z.date >= a) & (Z.date <= b)].date.map(mk)).dropna()
    s0, s1, s2 = seg("20050101", "20151231"), seg("20160101", "20221231"), seg("20230101", "20991231")
    t = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0
    return dict(n=len(x), mean=x.mean(), win=(x > 0).mean() * 100, ex=ex.mean(), t=t(ex),
                e0=(s0.mean(), len(s0)), e1=(s1.mean(), len(s1), t(s1)), e2=(s2.mean(), len(s2), t(s2)), ypos=int((by > 0).sum()), ny=len(by))


def dedup(Z, gap=60):
    """같은 종목은 60거래일 안 다시 안 셈 — 거래일 번호로."""
    Z = Z.sort_values(["ticker", "di"])
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if i - last.get(t, -10 ** 9) >= gap: keep.append(ix); last[t] = i
    return Z.loc[keep]


def main():
    D = build(load())
    days = sorted(D.date.unique()); dix = {d: i for i, d in enumerate(days)}; D["di"] = D.date.map(dix).astype("int32")
    U = D[(D.close >= 1000) & (D.a20 >= 3e8) & (D.change.abs() < 29)]
    run(D, U, days, tag="국장")
    (ROOT / "quiet_break_1112.out").write_text("\n".join(OUT), encoding="utf-8")


def run(D, U, days, tag):
    mk = {h: U.groupby("date")["f%d" % h].mean() for h in HS}
    P("%s 자료 %s~%s · 종목 %d · 유니버스 종목-일 %d\n" % (tag, days[0], days[-1], D.ticker.nunique(), len(U)))
    rows = []
    for L in (60, 120):
        for q in (0.8, 0.9):
            for B in ("B1", "B3"):
                base = U[(U["q%d_%s" % (L, B[1])] >= q) & (U["calm5_%s" % B[1]] >= 1)]
                if B == "B1":
                    br = base[base.change.abs() > 1.0]; mag = br.change
                else:
                    br = base[base.out3 >= 2]; mag = br.r3
                for side in ("위", "아래"):
                    for m in (1, 2, 3):
                        Z = br[(mag > m) if side == "위" else (mag < -m)]
                        Z = dedup(Z)
                        for h in HS:
                            s = stats(Z, h, mk[h])
                            if s: rows.append(dict(L=L, q=q, B=B, side=side, m=m, h=h, **s))
                # 대조: 잔잔한데 안 깨진(오늘도 ±1% 안) — 같은 조건 유니버스
                ctl = dedup(base[base.change.abs() <= 1.0].sample(frac=0.05, random_state=1) if len(base) > 200000 else base[base.change.abs() <= 1.0])
                for h in HS:
                    s = stats(ctl, h, mk[h])
                    if s: rows.append(dict(L=L, q=q, B=B, side="대조(안 깨짐)", m=0, h=h, **s))
    R = pd.DataFrame(rows)
    R.to_pickle(ROOT / "cache" / ("quiet_break_1112_%s.pkl" % ("kr" if tag == "국장" else "us")))
    fmt = lambda e: "%+.2f (%d)" % (e[0], e[1]) if e[1] else "-"
    for h in HS:
        P("\n## 보유 %d일 — 시장 대비 초과(건당, 비용 뒤) · 학습·검증 t\n" % h)
        P("| 잔잔 L·q | 깨짐 | 방향·크기 | 건수 | 건당 | 승률 | 시장 대비 | 2005~15 | 학습 16~22 (t) | 검증 23~ (t) | 해 플러스 |")
        P("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in R[R.h == h].itertuples():
            P("| %d일·%.0f%% | %s | %s %s | %d | %+.2f%% | %.0f%% | %+.2f%%p (t %.1f) | %s | %+.2f (%d, t %.1f) | %+.2f (%d, t %.1f) | %d/%d |" % (
                r.L, r.q * 100, "오늘 처음" if r.B == "B1" else "3일 중 2일", r.side, ("%d%%↑" % r.m) if r.m else "", r.n, r.mean, r.win, r.ex, r.t,
                fmt(r.e0), r.e1[0], r.e1[1], r.e1[2], r.e2[0], r.e2[1], r.e2[2], r.ypos, r.ny))
    return R


if __name__ == "__main__":
    main()
