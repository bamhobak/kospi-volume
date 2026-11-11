# -*- coding: utf-8 -*-
"""체결 손해 모형 매일 다시 맞추기 (2026-11-12 사용자 아이디어 ⑥).

지금 쓰는 모형(실현 실측, research/t1_size_liq_1021.py — [갭하락] 실주문 체결 기록으로 맞춤):
    손해 = 0.143 + 1.321 × √p (%, 사고 + 파는 합) · 체결률 = 1 / (1 + 3p) · p = 금액 ÷ 20일 평균 거래대금 × 100
여기서는 녹화된 호가창으로 '그 금액을 넣었다면 값이 얼마나 밀렸나'를 직접 잰다(호가 깊이만 본 하한 — 남이 따라 움직이는 몫은 없음):
  ① 단일가(시가·종가) — 녹화 호가는 '가상 체결 뒤 남은 주문'이라 매수·매도가 안 겹친다(11-11 확인: 400종목 다 안 겹침).
                        그래서 균형가 이동이 아니라 **최우선 호가부터 깊이 타기**: am 마지막 녹화(08:56) 매도 잔량을 q 원어치 탈 때
                        평균 ÷ 매도 1호가 − 1 + pm 마지막 녹화(15:27) 매수 잔량을 탈 때 1 − 평균 ÷ 매수 1호가 = 왕복 깊이 손해
                        (작은 금액은 1호가 안에서 끝나 0 — 단일가는 모두 같은 값에 체결돼 스프레드 몫이 없다는 가정. 시가 매수 → 종가 매도, 그림자 oc 와 같음)
  ② 접속매매 — tape am 09:01~09:05 호가(실매매 대상 종목)·NXT 장전 호가(nxtpre book·opentick nxtbook)에서
                매도 호가를 타고 q 원어치 살 때 평균 단가 ÷ 가운데값 − 1 (스프레드 반 + 깊이) × 2 = 왕복 근사
  금액 30만·50만·100만·300만·1000만 → 손해 = a + b√p 로 맞춤.
결과 data/factory/impact_fit.json (fshadow 등이 읽을 수 있게) · 날별 data/factory/impact_days.parquet · 요약 줄 data/factory/impact_log.csv
  python research/impact_refit.py          (예약 \\BamhobakFactory\\ImpactRefit 17:10 · 새 날만 계산, 실패 때만 텔레그램)
"""
import sys, json, glob, time, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT / "factory"))
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(BASE / "data" / "factory" / "impact_refit.log", "a", encoding="utf-8", buffering=1)
import numpy as np, pandas as pd

FAC = BASE / "data" / "factory"
AD = FAC / "auction"; TD = FAC / "tape"; ND = BASE / "data" / "nxtpre"
OUTJ, DAYS, LOGC = FAC / "impact_fit.json", FAC / "impact_days.parquet", FAC / "impact_log.csv"
AMTS = (30e4, 50e4, 100e4, 300e4, 1000e4)
REAL = dict(a=0.143, b=1.321, c=3.0, src="t1_size_liq_1021 — [갭하락] 실주문 체결 실측(10-21)")
VER = 2                                                   # 계산 방식이 바뀌면 올려서 날별 캐시를 다시 만든다


def log(*a):
    print("%s %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a)), flush=True)


def eq_mkt(P, V, S, mb=0.0, ms=0.0):
    """단일가 균형가격 — 시장가 매수 mb 주·매도 ms 주를 더해서. 후보 가격은 호가에 있는 값만(체결량 최대 → 매수·매도 차 작은 값)."""
    a, b = S == "A", S == "B"
    pa, va, pb, vb = P[a], V[a], P[b], V[b]
    best, bk = np.nan, (-1.0, 0.0)
    for p in np.unique(P):
        d = mb + vb[pb >= p].sum(); s = ms + va[pa <= p].sum()
        k = (min(d, s), -abs(d - s))
        if k > bk: best, bk = p, k
    if bk[0] <= 0:
        return np.nanmean([pa.min() if len(pa) else np.nan, pb.max() if len(pb) else np.nan])
    return best


def walk_side(P, V, S, amt, side):
    """남은 호가 한쪽을 1호가부터 타고 amt 원어치 — 매수(A 쪽 탐) (평균 ÷ 1호가 − 1)% · 매도(B 쪽) (1 − 평균 ÷ 1호가)%. 깊이 모자라면 nan."""
    m = S == side
    if not m.any(): return np.nan
    o = np.argsort(P[m]) if side == "A" else np.argsort(-P[m])
    pp, vv = P[m][o], V[m][o]
    need, cost, got = amt, 0.0, 0.0
    for p, v in zip(pp, vv):
        take = min(v, need / p)
        cost += take * p; got += take; need -= take * p
        if need <= 1e-6: break
    if need > 1e-6 or got <= 0: return np.nan
    avg = cost / got
    return (avg / pp[0] - 1) * 100 if side == "A" else (1 - avg / pp[0]) * 100


def walk(P, V, S, amt):
    """접속매매 — 매도 호가를 타고 amt 원어치 살 때 (평균 단가 ÷ 가운데값 − 1)%, 깊이 모자라면 nan."""
    a, b = S == "A", S == "B"
    if not a.any() or not b.any(): return np.nan
    o = np.argsort(P[a]); pa, va = P[a][o], V[a][o]
    mid = (pa[0] + P[b].max()) / 2
    if not mid > 0: return np.nan
    need, cost, got = amt, 0.0, 0.0
    for p, v in zip(pa, va):
        take = min(v, need / p)
        cost += take * p; got += take; need -= take * p
        if need <= 1e-6: break
    if need > 1e-6 or got <= 0: return np.nan
    return (cost / got / mid - 1) * 100


def a20_table():
    """종목·날 → 그날 전 20일 평균 거래대금(원). 공장 live 일봉(1분봉 합, NXT 포함 — fshadow 의 amt20 과 같은 기준)."""
    import live
    A = pd.read_parquet(live.DAILY, columns=["ticker", "date", "close", "volume"]).sort_values(["ticker", "date"])
    A["amt"] = A.close * A.volume
    A["a20"] = A.groupby("ticker").amt.transform(lambda z: z.rolling(20, min_periods=5).mean().shift(1))
    return A.set_index(["date", "ticker"]).a20


def last_tag(D):
    return D[D.tag == D.tag.max()] if len(D) else D


def one_day(d, A20):
    rows = []
    fa, fp = AD / ("KR_%s_am.parquet" % d), AD / ("KR_%s_pm.parquet" % d)
    if fa.exists() and fp.exists():
        Am, Pm = last_tag(pd.read_parquet(fa)), last_tag(pd.read_parquet(fp))
        gp = {t: g for t, g in Pm.groupby("ticker")}
        for t, g in Am.groupby("ticker"):
            a20 = A20.get((d, t))
            h = gp.get(t)
            if not (a20 and a20 > 0) or h is None: continue
            P, V, S = g.price.to_numpy(float), g.vol.to_numpy(float), g.side.to_numpy()
            P2, V2, S2 = h.price.to_numpy(float), h.vol.to_numpy(float), h.side.to_numpy()
            for amt in AMTS:
                wb, ws = walk_side(P, V, S, amt, "A"), walk_side(P2, V2, S2, amt, "B")
                rows.append(dict(date=d, t=t, kind="auction", amt=amt, a20=a20, p=amt / a20 * 100,
                                 loss=wb + ws if wb == wb and ws == ws else np.nan, short=bool(not (wb == wb and ws == ws))))
    conts = []
    ft = TD / ("KR_%s_am.parquet" % d)
    if ft.exists():
        X = pd.read_parquet(ft); X = X[(X.side != "P") & (X.tag >= "090130")]
        conts.append(X[X.tag == X.groupby("ticker").tag.transform("min")])         # 09:01:30 첫 접속매매 호가
    for f in (ND / ("book_%s.parquet" % d), AD / ("KR_%s_nxtbook.parquet" % d)):
        if f.exists():
            X = pd.read_parquet(f)
            conts.append(X[X.tag == X.groupby("ticker").tag.transform("max")])     # NXT 장전 마지막 녹화
    for X in conts:
        for t, g in X.groupby("ticker"):
            a20 = A20.get((d, t))
            if not (a20 and a20 > 0): continue
            P, V, S = g.price.to_numpy(float), g.vol.to_numpy(float), g.side.to_numpy()
            for amt in AMTS:
                w = walk(P, V, S, amt)
                rows.append(dict(date=d, t=t, kind="cont", amt=amt, a20=a20, p=amt / a20 * 100,
                                 loss=2 * w if w == w else np.nan, short=bool(w != w)))
    return rows


def fit(Z):
    """손해 = a + b√p (깊이 모자란 줄 빼고). 참여율 구간 표도 같이."""
    z = Z[~Z.short & Z.loss.notna() & (Z.p > 0)]
    if len(z) < 50: return None
    X = np.c_[np.ones(len(z)), np.sqrt(z.p)]
    a, b = np.linalg.lstsq(X, z.loss.to_numpy(float), rcond=None)[0]
    bins = [0, 0.01, 0.03, 0.1, 0.3, 1, 3, 100]
    tab = [dict(p=str(k), n=int(len(g)), loss=round(float(g.loss.mean()), 3), real=round(float(np.mean(np.maximum(0, REAL["a"] + REAL["b"] * np.sqrt(g.p)))), 3))
           for k, g in z.groupby(pd.cut(z.p, bins), observed=True)]
    by_amt = {"%d만" % (k / 1e4): dict(n=int(len(g)), loss=round(float(g.loss.mean()), 3), med=round(float(g.loss.median()), 3),
                                      real=round(float(np.mean(np.maximum(0, REAL["a"] + REAL["b"] * np.sqrt(g.p)))), 3),
                                      short=round(float(Z[(Z.amt == k)].short.mean() * 100), 1))
              for k, g in z.groupby("amt")}
    return dict(a=round(float(a), 4), b=round(float(b), 4), n=int(len(z)), days=int(z.date.nunique()), by_amt=by_amt, by_p=tab)


def main():
    t0 = time.time()
    days = sorted({Path(f).name[3:11] for f in glob.glob(str(AD / "KR_*_am.parquet"))} |
                  {Path(f).name[3:11] for f in glob.glob(str(TD / "KR_*_am.parquet"))} |
                  {Path(f).stem[5:13] for f in glob.glob(str(ND / "book_*.parquet"))})
    old = pd.read_parquet(DAYS) if DAYS.exists() else pd.DataFrame()
    if len(old) and (old.get("ver", pd.Series([0])).iloc[0] != VER): old = pd.DataFrame()
    have = set(old.date) if len(old) else set()
    todo = [d for d in days if d not in have]
    A20 = a20_table() if todo else None
    new = []
    for d in todo:
        try: new += one_day(d, A20)
        except Exception as ex: log("날 실패", d, repr(ex)[:200])
    Z = pd.concat([old, pd.DataFrame(new).assign(ver=VER)], ignore_index=True) if new else old
    if not len(Z):
        log("호가 녹화 없음 — 끝"); return
    Z.to_parquet(DAYS, index=False)
    out = dict(date=dt.date.today().strftime("%Y%m%d"), made=dt.datetime.now().isoformat(timespec="seconds"),
               model="손해 % = a + b×√p (사고+파는 합) · p = 금액 ÷ 20일 평균 거래대금 × 100 · 체결률 = 1/(1 + c×p)",
               realized=REAL, auction=fit(Z[Z.kind == "auction"]), cont=fit(Z[Z.kind == "cont"]))
    # 쓰는 값(use): 실현 실측이 기본. 호가로 잰 단일가 손해가 50만·100만에서 실현보다 크면(=실현 모형이 손해를 덜 잡음) 큰 쪽.
    au = out["auction"] or {}
    worse = [k for k in ("50만", "100만") if k in (au.get("by_amt") or {}) and au["by_amt"][k]["loss"] > au["by_amt"][k]["real"]]
    out["use"] = dict(a=au["a"], b=au["b"], c=REAL["c"], why="호가 단일가 손해가 실현 모형보다 큼(%s)" % "·".join(worse)) if worse and au \
        else dict(a=REAL["a"], b=REAL["b"], c=REAL["c"], why="실현 실측 유지(호가로 잰 손해는 그 아래 — 호가 깊이만 본 하한)")
    OUTJ.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    new_line = not LOGC.exists()
    with open(LOGC, "a", encoding="utf-8-sig") as fh:
        if new_line: fh.write("만든 날,날 수,단일가 a,단일가 b,단일가 50만,단일가 100만,접속 50만,접속 100만,실현 50만,실현 100만,쓰는 값\n")
        g = lambda f, k, c: (f or {}).get("by_amt", {}).get(k, {}).get(c, "")
        fh.write(",".join(str(x) for x in [out["date"], (au or {}).get("days", ""), au.get("a", ""), au.get("b", ""),
                                            g(au, "50만", "loss"), g(au, "100만", "loss"), g(out["cont"], "50만", "loss"), g(out["cont"], "100만", "loss"),
                                            g(au, "50만", "real"), g(au, "100만", "real"), out["use"]["why"][:20]]) + "\n")
    log("체결 손해 다시 맞춤 — 새 날 %d · 줄 %d · %.0f초 · 쓰는 값 %s" % (len(todo), len(Z), time.time() - t0, out["use"]["why"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        import traceback; log("실패:", traceback.format_exc()[-800:])
        try:
            import common as C; C.tg("⚠ 체결 손해 다시 맞추기 실패: %s" % str(ex)[:150])
        except Exception: pass
        raise
