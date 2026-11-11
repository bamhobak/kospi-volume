# -*- coding: utf-8 -*-
"""같은 규칙 안에서 신호가 여러 개인 날, 무엇부터 살까 — 2026-11-12 사용자 "③ 고쳐놔줘"(지금은 처음 뜬 신호 → 종목 코드 순 = 사실상 무작위).
돈이 모자라 일부만 살 수 있는 날(= 신호가 몰린 날 = 보통 가장 좋은 날)에 앞쪽 절반이 뒤쪽 절반보다 나은 열쇠가 있나.

거래 목록: research/cache/kr_rules_recheck.pkl · us_rules_recheck.pkl(10-07 규칙 정의 — date = 신호일, ret = 비용 뒤, idx = 같은 보유기간 지수)
재료(신호일 종가까지만 — 사이트 표 행과 같은 정의):
  ret20 = 20거래일 등락 % · ret5 = 5일(미장은 ret10) · d1 = 그날 등락 %(국장 표 = ch ÷ (c − ch), 미장 표 = chpct) ·
  amt20 = 20일 평균 거래대금 · dev25 = 25일 이격 %(종가 ÷ 25일 평균 − 1) · fromhi = 52주 고점 대비 % · vol20 = 20일 일간 등락 표준편차
  국장: data/kospi.db daily(코스피·코스닥, 2005~) · 미장: data/us/raw/chunk_*.pkl(살아 있는 종목 수정주가) + data/us/tiingo_dead.db(폐지 종목)
비교: 그날 신호 2개↑ 인 날만. 그날 안에서 열쇠 순위로 앞 절반 vs 뒤 절반(가운데 하나는 뺌) — 날마다 (앞 − 뒤) 건당 차이의 평균·t.
  학습 2016~22 · 검증 2023~ (참고: 2005~15). 채택 = 학습 t ≥ 2 이고 검증도 같은 방향(t ≥ 1) — 아니면 기본값 '거래대금 큰 순'(체결 손해 작음).
결과: research/rule_order_1112.out · data/rule_order.json({규칙: {key, asc, why, ...}}) — autotrade 가 읽는다.
    python research/rule_order_1112.py
"""
import glob, json, math, sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
KR_RULES = {"P1": "조용 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴", "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
            "D1": "낙폭과대", "D2": "저PBR 낙폭"}
US_RULES = {"N1": "상승장 신고가", "N3": "저PBR 낙폭", "N5": "잔잔 급등", "N6": "실적 깜짝", "N8": "분사주", "N9": "S&P 편출"}
KEYS = ["ret20", "ret5", "d1", "amt20", "dev25", "fromhi", "vol20"]
# 사이트 표 행 필드 이름(국장 site/data/table.json · 미장 table_us.json) — autotrade 는 이 이름으로 읽는다
FIELD_KR = {"ret20": "ret20", "ret5": "ret5", "d1": "ch÷(c−ch)×100 (표에 % 칸 없음 — ch·c 로 계산)", "amt20": "amt20", "dev25": "dev25", "fromhi": "fromhi", "vol20": "vol20"}
FIELD_US = {"ret20": "ret20", "ret5": "ret10 (미장 표엔 ret5 없음 — 10일로 대신)", "d1": "chpct", "amt20": "amt20", "dev25": "dev25", "fromhi": "fromhi", "vol20": "vol20"}
NAME = {"ret20": "20일 등락", "ret5": "5일 등락", "d1": "그날 등락", "amt20": "20일 거래대금", "dev25": "25일 이격", "fromhi": "52주 고점 대비", "vol20": "20일 변동성"}


def feats(D, px="close", amt=None):
    """D: ticker·date·close(·high)·volume(·amount) 정렬된 일봉 → 재료."""
    D = D.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = D.groupby("ticker", sort=False)
    c = D[px]
    D["ret20"] = (c / g[px].shift(20) - 1) * 100
    D["ret5"] = (c / g[px].shift(5) - 1) * 100
    D["d1r"] = (c / g[px].shift(1) - 1) * 100
    D["d1"] = D.d1r
    a = D[amt] if amt else D.close * D.volume
    D["amt20"] = a.groupby(D.ticker).transform(lambda s: s.rolling(20, min_periods=10).mean())
    D["dev25"] = (c / g[px].transform(lambda s: s.rolling(25, min_periods=20).mean()) - 1) * 100
    D["fromhi"] = (c / g[px].transform(lambda s: s.rolling(250, min_periods=120).max()) - 1) * 100
    D["vol20"] = g.d1r.transform(lambda s: s.rolling(20, min_periods=15).std())
    return D[["ticker", "date"] + KEYS]


def kr_feats(need):
    """kospi.db(코스피 2005~ · 코스닥 2005~2017) + kosdaq.db(코스닥 2018~) 를 합친다 — 한쪽만 쓰면 2018 뒤 코스닥 신호가 빠진다."""
    c = sqlite3.connect("file:" + str(BASE / "data" / "kospi.db") + "?mode=ro", uri=True)
    c2 = sqlite3.connect("file:" + str(BASE / "data" / "kosdaq.db") + "?mode=ro", uri=True)
    tk = sorted({t for t, d in need})
    out = []
    for i in range(0, len(tk), 400):
        part = tk[i:i + 400]
        ph = ",".join("?" * len(part))
        D1 = pd.read_sql("select ticker, date, close, volume, amount from daily where ticker in (%s) and close > 0" % ph, c, params=part)
        D2 = pd.read_sql("select ticker, date, close, volume from daily where ticker in (%s) and close > 0" % ph, c2, params=part)
        D2["amount"] = np.nan
        D = pd.concat([D1, D2], ignore_index=True).drop_duplicates(["ticker", "date"], keep="first")
        D["amount"] = D.amount.where(D.amount > 0, D.close * D.volume)
        F = feats(D, amt="amount")
        out.append(F[F.set_index(["ticker", "date"]).index.isin(need)])
    return pd.concat(out, ignore_index=True)


def us_feats(need):
    tk = {t for t, d in need}
    parts = []
    for f in sorted(glob.glob(str(BASE / "data" / "us" / "raw" / "chunk_*.pkl"))):
        X = pd.read_pickle(f)
        X = X[X.ticker.isin(tk)]
        if len(X): parts.append(X[["ticker", "date", "adj", "close", "volume"]].copy())
    D = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["ticker", "date", "adj", "close", "volume"])
    have = set(D.ticker.unique())
    miss = sorted(tk - have)
    if miss:
        c = sqlite3.connect("file:" + str(BASE / "data" / "us" / "tiingo_dead.db") + "?mode=ro", uri=True)
        for i in range(0, len(miss), 400):
            part = miss[i:i + 400]
            q = "select ticker, date, adjClose as adj, close, volume from px where ticker in (%s)" % ",".join("?" * len(part))
            E = pd.read_sql(q, c, params=part)
            E["date"] = E.date.astype(str).str[:10].str.replace("-", "")
            parts.append(E)
        D = pd.concat(parts, ignore_index=True)
    D["date"] = D.date.astype(str)
    D = D.drop_duplicates(["ticker", "date"])
    F = feats(D, px="adj")
    return F[F.set_index(["ticker", "date"]).index.isin(need)], len(miss)


def day_diff(Z, key, asc):
    """그날 안 앞 절반(먼저 살 쪽) − 뒤 절반 건당 수익·지수 대비 → 날별 차이."""
    rk = Z.groupby("date")[key].rank(method="first", ascending=asc)
    n = Z.groupby("date")[key].transform("count")
    front = rk <= np.floor(n / 2); back = rk > np.ceil(n / 2)
    A = Z.assign(front=front, back=back)
    f = A[A.front].groupby("date")[["ret", "ex"]].mean(); b = A[A.back].groupby("date")[["ret", "ex"]].mean()
    return (f - b).dropna()


def tstat(s):
    s = s.dropna()
    if len(s) < 3 or s.std(ddof=1) == 0: return 0.0
    return s.mean() / s.std(ddof=1) * math.sqrt(len(s))


def study(rid, name, T, F, field):
    Z = T.merge(F, on=["ticker", "date"], how="left")
    cover = Z[KEYS].notna().all(axis=1).mean() * 100
    n = Z.groupby("date").size()
    multi = Z[Z.date.map(n) >= 2]
    P("\n### %s [%s] — 거래 %d · 신호 2개↑ 날 %d일·%d건 · 재료 붙은 몫 %.0f%%" % (rid, name, len(Z), multi.date.nunique(), len(multi), cover))
    if multi.date.nunique() < 15:
        P("신호 2개↑ 날이 %d일뿐 — 판단 못 함 → 기본값(거래대금 큰 순)" % multi.date.nunique())
        return dict(key="amt20", asc=False, why="신호 2개↑ 날 %d일뿐 — 기본값(거래대금 큰 순: 체결 손해 작음)" % multi.date.nunique(), field=field["amt20"], adopted=False)
    P("| 열쇠(먼저 살 쪽) | 학습 2016~22 앞−뒤 건당 (t · 날) | 검증 2023~ (t · 날) | 2005~15 참고 | 지수 대비 학습/검증 |")
    P("|---|---|---|---|---|")
    best = None
    for key in KEYS:
        if multi[key].notna().sum() < 20: continue
        for asc in (True, False):
            Dd = day_diff(multi.dropna(subset=[key]), key, asc)
            if not len(Dd): continue
            L, V, O = Dd[(Dd.index >= "20160101") & (Dd.index < "20230101")], Dd[Dd.index >= "20230101"], Dd[Dd.index < "20160101"]
            tl, tv = tstat(L.ret), tstat(V.ret)
            P("| %s %s | %+.2f%% (t %.1f · %d) | %+.2f%% (t %.1f · %d) | %s | %+.2f / %+.2f |" % (
                NAME[key], "낮은 순" if asc else "높은 순", L.ret.mean() if len(L) else float("nan"), tl, len(L), V.ret.mean() if len(V) else float("nan"), tv, len(V),
                ("%+.2f%% (t %.1f · %d)" % (O.ret.mean(), tstat(O.ret), len(O))) if len(O) >= 3 else "-",
                L.ex.mean() if len(L) else float("nan"), V.ex.mean() if len(V) else float("nan")))
            ok = len(L) >= 10 and len(V) >= 5 and tl >= 2 and tv >= 1 and L.ret.mean() > 0 and V.ret.mean() > 0 and L.ex.mean() > 0 and V.ex.mean() > 0
            if ok and (best is None or tl + tv > best[0]):
                best = (tl + tv, key, asc, L.ret.mean(), tl, len(L), V.ret.mean(), tv, len(V))
    if best:
        _, key, asc, lm, tl, nl, vm, tv, nv = best
        why = "%s %s — 앞 절반이 뒤 절반보다 학습 %+.2f%%(t %.1f·%d일) · 검증 %+.2f%%(t %.1f·%d일)" % (NAME[key], "낮은 순" if asc else "높은 순", lm, tl, nl, vm, tv, nv)
        P("→ **채택: %s**" % why)
        return dict(key=key, asc=bool(asc), why=why, field=field[key], adopted=True, learn=round(float(lm), 2), learn_t=round(float(tl), 1), val=round(float(vm), 2), val_t=round(float(tv), 1))
    P("→ 두 구간 다 맞는 열쇠 없음 → 기본값(거래대금 큰 순)")
    Dd = day_diff(multi.dropna(subset=["amt20"]), "amt20", False)
    L, V = Dd[(Dd.index >= "20160101") & (Dd.index < "20230101")], Dd[Dd.index >= "20230101"]
    return dict(key="amt20", asc=False, field=field["amt20"], adopted=False,
                why="두 구간 다 맞는 열쇠 없음 — 기본값 거래대금 큰 순(체결 손해 작음 · 그 순서 학습 %+.2f%% · 검증 %+.2f%%)" % (
                    L.ret.mean() if len(L) else float("nan"), V.ret.mean() if len(V) else float("nan")))


def main():
    t0 = time.time()
    res = {}
    A = pd.read_pickle(ROOT / "cache" / "kr_rules_recheck.pkl")
    TK = {k: (v[0] if isinstance(v, tuple) else v).assign(date=lambda z: z.date.astype(str)) for k, v in A.items() if k in KR_RULES}
    need = {(t, d) for X in TK.values() for t, d in zip(X.ticker, X.date)}
    FK = kr_feats(need)
    P("## 국장 (재료 %d/%d 신호, %.0f초)" % (len(FK), len(need), time.time() - t0))
    for rid in KR_RULES:
        if rid not in TK: P("\n### %s [%s] — 자료 없음(10-07 거래 목록에 없음)" % (rid, KR_RULES[rid])); continue
        X = TK[rid].copy(); X["ex"] = X.ret - X.idx
        res[rid] = study(rid, KR_RULES[rid], X, FK, FIELD_KR)
    B = pd.read_pickle(ROOT / "cache" / "us_rules_recheck.pkl")
    TU = {k: v.assign(date=lambda z: z.date.astype(str)) for k, v in B.items() if k in US_RULES}
    need = {(t, d) for X in TU.values() for t, d in zip(X.ticker, X.date)}
    FU, nmiss = us_feats(need)
    P("\n## 미장 (재료 %d/%d 신호 · 폐지 종목 %d개는 tiingo_dead, %.0f초)" % (len(FU), len(need), nmiss, time.time() - t0))
    for rid in US_RULES:
        if rid not in TU: P("\n### %s [%s] — 자료 없음" % (rid, US_RULES[rid])); continue
        X = TU[rid].copy(); X["ex"] = X.ret - X.idx
        res[rid] = study(rid, US_RULES[rid], X, FU, FIELD_US)
    for rid, nm in (("P8", "신탁 급락"),):
        res[rid] = dict(key="amt20", asc=False, field=FIELD_KR["amt20"], adopted=False, why="10-07 거래 목록에 없음(자료 없음) — 기본값 거래대금 큰 순")
    P("\n## 정리 — 규칙별 '같은 날 신호 여럿이면 이 순서로'\n")
    P("| 규칙 | 열쇠 | 사이트 표 필드 | 채택? | 근거 |"); P("|---|---|---|---|---|")
    for rid, r in res.items():
        P("| %s | %s %s | %s | %s | %s |" % (rid, NAME[r["key"]], "낮은 순" if r["asc"] else "높은 순", r["field"], "채택" if r["adopted"] else "기본값", r["why"]))
    meta = {"_설명": "같은 규칙 안 매수 순서(2026-11-12 research/rule_order_1112.py) — key 는 사이트 표 행 필드(국장 d1 = ch÷(c−ch)×100, 미장 ret5 → ret10). asc=true 면 값이 낮은 것부터 산다. adopted=false 는 기본값(거래대금 큰 순)."}
    (ROOT / "rule_order_1112.out").write_text("\n".join(OUT), encoding="utf-8")
    (BASE / "data" / "rule_order.json").write_text(json.dumps(dict(meta, **res), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    P("\n(%.0f초)" % (time.time() - t0))


if __name__ == "__main__":
    main()
