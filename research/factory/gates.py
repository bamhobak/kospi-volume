# -*- coding: utf-8 -*-
"""규칙 찾기 관문 4종 — 2026-11-14 사용자 "차례차례 진행해줘"(새 규칙 찾기 방식 9·11·5·4).
lab.judge 가 기존 G1·G2 를 다 통과한 명세에만 부른다(비싼 계산을 싸게 버린 뒤에). 하나라도 걸리면 G2 탈락 이유에 붙는다.

  ⑨ 분포 모양   검증 거래의 평균·중앙·상위 5% 뺀 평균·승률·좋은 날 10개 몫.
                상위 5% 빼면 0 이하 = 복권형(몇 건 대박이 평균을 만든 것) → 탈락. 좋은 날 10개가 손익의 SHAPE_TOP% 넘으면(날 100↑일 때) 탈락.
  ⑪ 자동 거울   뒤집기 짝(lab.invert — 조건마다 반대쪽)을 검증 구간에서 같이 잰다. 뒤집은 쪽도 비용 뒤 플러스면
                재료가 아니라 변동성·시장 흐름을 잡은 것 → 탈락(스윙은 같은 날 아무 종목 대비 초과로 본다).
                시가↔종가 거울(oc ↔ on, 미리 알 수 있을 때만)은 참고로만 적는다. 국장↔미장은 process 의 미장 판정 그대로.
  ⑤ 이웃 평탄도  조건 문턱을 하나씩 한 칸(백분위 ±0.05 · 0~100 재료 ±5 · 그 밖 값의 ±10%, 0 이면 ±0.5) 옮긴 판 + 전부 같이 옮긴 판 2개.
                학습+검증 건당이 원래와 같은 부호인 비율 < NEI_AGREE 이거나 이웃 평균 < 원래 × NEI_KEEP 이면 '봉우리' → 탈락.
  ④ 가짜 달력   검증 구간에서 '같은 날 같은 개수를 유니버스에서 아무렇게나 뽑은 판'을 CAL_N 번 → 실제 건당이 몇 등인지.
                날짜·하루 개수를 그대로 두니 장이 몰려 좋았던 날·나빴던 날 몫은 무작위 판도 똑같이 가진다(달 덩어리 섞기보다 엄격).
                상위 CAL_P 밖(= 무작위와 구별 안 됨) → 탈락. 손절·익절(exit) 명세는 무작위 판을 같은 청산으로 못 만들어 참고만.
"""
import math
import numpy as np, pandas as pd
import feats as FT

TRIM, SHAPE_TOP, SHAPE_DAYS = 0.05, 60.0, 100
NEI_AGREE, NEI_KEEP = 0.8, 0.5
CAL_N, CAL_P, CAL_SEED = 1000, 0.95, 7


def shape(T):
    if T is None or len(T) < 20: return None
    r = T.ret.to_numpy(float)
    hi = np.quantile(r, 1 - TRIM)
    dp = T.groupby("date").ret.sum(); tot = float(dp.sum())
    top = float(dp.sort_values(ascending=False).iloc[:10].sum() / tot * 100) if tot > 0 else None
    return dict(mean=float(r.mean()), med=float(np.median(r)), trim=float(r[r < hi].mean()) if (r < hi).any() else float(r.mean()),
                win=float((r > 0).mean() * 100), top10=top, days=int(len(dp)))


def _seg(T, a, b):
    return T[(T.date >= a) & (T.date <= b)]


def mirror(lab, U, spec, VA, mk):
    sw = spec["mode"].startswith("sw")
    inv = lab.invert(spec)
    T2 = _seg(lab.trades(U, inv, mk=mk), *VA)
    out = dict(inv_n=int(len(T2)), inv_mean=float(T2.ret.mean()) if len(T2) else None)
    if sw and len(T2):
        tg = FT.TARGET[spec["mode"]]
        out["inv_ex"] = float((T2.ret - T2.date.map(U.groupby("date")[tg].mean())).mean())
    if spec["mode"] == "oc" and mk == "KR":                                   # 시가↔종가 거울(참고)
        alt = dict(spec, mode="on")
        if lab.check(alt) is None:
            T3 = _seg(lab.trades(U, alt, mk=mk), *VA)
            out["on_mean"] = float(T3.ret.mean()) if len(T3) else None
    elif spec["mode"] == "on" and mk == "KR":
        alt = dict(spec, mode="oc")
        if lab.check(alt) is None:
            T3 = _seg(lab.trades(U, alt, mk=mk), *VA)
            out["oc_mean"] = float(T3.ret.mean()) if len(T3) else None
    return out


def _step(c):
    v = float(c["v"])
    if c.get("q"): return 0.05
    if FT.FEATS[c["f"]][2] == "h": return 5.0
    return abs(v) * 0.10 if v else 0.5


def neighbors(lab, spec):
    out = []
    cs = spec["conds"]
    for i, c in enumerate(cs):
        for sgn in (-1, 1):
            c2 = dict(c, v=round(float(c["v"]) + sgn * _step(c), 4))
            out.append(dict(spec, conds=cs[:i] + [c2] + cs[i + 1:]))
    if len(cs) > 1:
        for sgn in (-1, 1):
            out.append(dict(spec, conds=[dict(c, v=round(float(c["v"]) + sgn * _step(c), 4)) for c in cs]))
    return [s for s in out if lab.check(s) is None]


def plateau(lab, U, spec, a, b, base_mean, mk):
    ms = []
    for s in neighbors(lab, spec):
        T = _seg(lab.trades(U, s, mk=mk), a, b)
        if len(T) >= 30: ms.append(float(T.ret.mean()))
    if not ms: return dict(n=0)
    ms = np.array(ms)
    return dict(n=int(len(ms)), agree=float((np.sign(ms) == np.sign(base_mean)).mean()), nmean=float(ms.mean()), nmin=float(ms.min()),
                keep=float(ms.mean() / base_mean) if base_mean else None)


def calendar(U, spec, T, VA, mk, cost):
    tg = FT.TARGET[spec["mode"]]
    V = U.loc[(U.date >= VA[0]) & (U.date <= VA[1]), ["date", tg]].dropna()
    r = V[tg].astype(float).clip(-60, 60).to_numpy()
    if spec["mode"] in ("oc", "on"): r = r - cost
    elif spec["mode"].startswith("m"): r = r - cost - FT.INTRA_SLIP
    pools = {d: r[ix] for d, ix in V.groupby("date").indices.items()}
    k = T.groupby("date").size()
    rng = np.random.default_rng(CAL_SEED)
    tot = np.zeros(CAL_N); n = 0
    for d, kd in k.items():
        p = pools.get(d)
        if p is None or not len(p): continue
        tot += p[rng.integers(0, len(p), size=(CAL_N, kd))].sum(1); n += kd
    if not n: return None
    null = tot / n; real = float(T.ret.mean())
    return dict(real=real, null_mean=float(null.mean()), null_p95=float(np.quantile(null, 0.95)), pct=float((null < real).mean()))


def run_all(lab, U, spec, T, tr0, VA, mk="KR"):
    """T = 그 명세 전체 거래(lab.trades 결과, 스윙은 ex 열 있을 수 있음). 반환 dict(why=[...], shape, mirror, plateau, cal)."""
    why = []
    sw = spec["mode"].startswith("sw")
    cost = lab.US_COST if mk == "US" else FT.COST
    TV = _seg(T, *VA)
    G = dict(shape=shape(TV))
    s = G["shape"]
    if s:
        if s["trim"] <= 0: why.append("⑨ 복권형 — 상위 5%% 빼면 건당 %+.2f%%(평균 %+.2f · 중앙 %+.2f)" % (s["trim"], s["mean"], s["med"]))
        if s["top10"] is not None and s["days"] >= SHAPE_DAYS and s["top10"] >= SHAPE_TOP:
            why.append("⑨ 좋은 날 10개가 검증 손익의 %.0f%%" % s["top10"])
    G["mirror"] = m = mirror(lab, U, spec, VA, mk)
    if sw:
        if m.get("inv_ex") is not None and m["inv_ex"] > 0: why.append("⑪ 거울도 플러스 — 뒤집은 짝이 같은 날 아무 종목보다 %+.2f%%p" % m["inv_ex"])
    elif m.get("inv_mean") is not None and m["inv_n"] >= 40 and m["inv_mean"] > 0:
        why.append("⑪ 거울도 플러스 — 뒤집은 짝 검증 건당 %+.2f%%(비용 뒤)" % m["inv_mean"])
    TA = _seg(T, tr0, VA[1]); bm = float(TA.ret.mean())
    G["plateau"] = p = plateau(lab, U, spec, tr0, VA[1], bm, mk)
    if p.get("n"):
        if p["agree"] < NEI_AGREE or (p["keep"] is not None and p["keep"] < NEI_KEEP):
            why.append("⑤ 봉우리 — 문턱 한 칸 이웃 %d판 중 같은 부호 %.0f%% · 이웃 평균 %+.2f%%(원래 %+.2f)" % (p["n"], p["agree"] * 100, p["nmean"], bm))
    if spec.get("exit"):
        G["cal"] = None
    else:
        G["cal"] = c = calendar(U, spec, TV, VA, mk, cost)
        if c and c["pct"] < CAL_P:
            why.append("④ 가짜 달력 — 같은 날 무작위 %d판 중 상위 %.0f%%(무작위 평균 %+.2f · 실제 %+.2f)" % (CAL_N, (1 - c["pct"]) * 100, c["null_mean"], c["real"]))
    G["why"] = why
    return G


def fmt(G):
    """카드·보고서 한 줄."""
    if not G: return "-"
    ps = []
    s = G.get("shape")
    if s: ps.append("분포 중앙 %+.2f · 상위5%%뺀 %+.2f · 좋은 날10 %s" % (s["med"], s["trim"], "%.0f%%" % s["top10"] if s["top10"] is not None else "-"))
    m = G.get("mirror") or {}
    if m.get("inv_mean") is not None: ps.append("거울 %+.2f%s" % (m["inv_mean"], (" (초과 %+.2f)" % m["inv_ex"]) if m.get("inv_ex") is not None else ""))
    p = G.get("plateau") or {}
    if p.get("n"): ps.append("이웃 %d판 같은 부호 %.0f%% · 평균 %+.2f" % (p["n"], p["agree"] * 100, p["nmean"]))
    c = G.get("cal")
    if c: ps.append("가짜 달력 %.1f%% 자리" % (c["pct"] * 100))
    return " · ".join(ps)
