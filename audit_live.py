# -*- coding: utf-8 -*-
"""실전-연구 대조 감사관 — 2026-11-12 사용자 "② 해줘"(남는 토큰으로 더 시스템화).

매일 16:50: 데이 원장(data/day/ledger.json)의 끝난 왕복(매수 체결 + 매도 체결)마다 '연구가 가정한 값'과 실제를 대조한다.
  T1·T2·T3(·T4) 데이 [갭하락] 계열: 연구 매수 = KRX 시가(1분봉 첫 봉 시가) · 연구 매도 = KRX 종가(마지막 봉)
      + 연구 조건 맞음? = 실제 시가 갭의 시장 대비(그날 유니버스 실제 시가 갭 중앙 빼기) ≤ 그날 snap thr
      + 체결 어긋남 = 시가 ≤ 지정가인데 안 사짐 / 시가 > 지정가인데 사짐
  T5 [장전 되돌림] · T6 [장후 낙폭]: 연구 매수 = 주문 때 매도 1호가(ask) · 연구 매도 = 매도날 KRX 시가
기록: data/audit/live.csv(왕복 한 줄씩, 다시 돌려도 같은 줄은 덮어씀) · data/audit/days.csv(규칙×날 요약)
경보(텔레그램, 문제 있을 때만): 최근 5거래일 규칙별 (실전 − 연구) 평균 < -0.30%p · [갭하락] 조건 밖 체결 > 20% · 체결 어긋남 > 0
    python audit_live.py            오늘(또는 마지막 1분봉 날)
    python audit_live.py all        원장 전체 다시(처음 한 번)
    python audit_live.py report     지금까지 규칙별 표
"""
import csv, json, sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "audit"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "audit.log"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
import numpy as np, pandas as pd

COST = 0.23
LCSV, DCSV = OUT / "live.csv", OUT / "days.csv"
T1F = ("T1", "T2", "T3", "T4")
RNAME = {"T1": "갭하락", "T2": "갭하락+", "T3": "갭하락++", "T4": "미장 폭락", "T5": "장전 되돌림", "T6": "장후 낙폭"}
GAP_WARN, OUT_WARN, WIN = -0.30, 20.0, 5
M1 = BASE / "data" / "m1" / "KR" / "day"
_m1 = {}


def m1(d):
    """그날 KRX 정규장 종목별 시가(첫 봉)·종가(마지막 봉) — 거래량 0 봉 뺌."""
    if d in _m1: return _m1[d]
    f = M1 / ("%s.parquet" % d)
    if not f.exists(): _m1[d] = None; return None
    X = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); X = X[X.v > 0].sort_values(["t", "ts"]); g = X.groupby("t")
    _m1[d] = pd.DataFrame({"o": g.o.first(), "c": g.c.last()})
    return _m1[d]


def m1_days():
    return sorted(p.stem for p in M1.glob("*.parquet"))


def prev_day(d, days):
    p = [x for x in days if x < d]
    return p[-1] if p else None


def snap(d):
    f = BASE / "data" / "day" / ("snap_%s.json" % d)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def mkt_gap(d, days):
    """그날 데이 유니버스 실제 시가 갭(시가 ÷ 어제 KRX 종가) 중앙 %."""
    S, K, pv = snap(d), m1(d), prev_day(d, days)
    Kp = m1(pv) if pv else None
    if S is None or K is None or Kp is None: return None
    u = [t for t in (S.get("all") or {}) if t in K.index and t in Kp.index]
    g = (K.o[u] / Kp.c[u] - 1) * 100
    g = g[g.abs() < 29]
    return float(g.median()) if len(g) > 100 else None


def rounds(days, since=None):
    """끝난 왕복: (매수 주문, 매도 주문)."""
    X = json.loads((BASE / "data" / "day" / "ledger.json").read_text(encoding="utf-8"))["orders"]
    buys = {}
    for o in X:
        if o.get("side") == "BUY" and o.get("status") == "FILLED" and (o.get("fq") or 0) > 0 and (o.get("pos") or {}).get("id"):
            buys[o["pos"]["id"]] = o
    out = []
    for s in X:
        if s.get("side") != "SELL" or s.get("status") != "FILLED" or not s.get("posId") or not (s.get("ap") or 0): continue
        b = buys.get(s["posId"])
        if not b or not b.get("rid"): continue
        sd = (s.get("sold") or {}).get("sellDate") or s.get("date")
        if since and sd < since: continue
        out.append((b, s, sd))
    return out


def judge(b, s, sd, days, mg_cache):
    rid, t, bd = b["rid"], b["t"], b["date"]
    ap_b, ap_s = float(b["ap"]), float(s["ap"])
    Kb, Ks = m1(bd), m1(sd)
    r = dict(rid=rid, t=t, name=b.get("name", ""), buy_day=bd, sell_day=sd, buy=ap_b, sell=ap_s, lim=b.get("lim"))
    if rid in T1F:
        if Kb is None or t not in Kb.index: return None
        r["ref_buy"], r["ref_sell"] = float(Kb.o[t]), (float(Ks.c[t]) if Ks is not None and t in Ks.index else None)
        S = snap(bd) or {}
        thr = S.get("thr")
        pc = b.get("pc")
        if bd not in mg_cache: mg_cache[bd] = mkt_gap(bd, days)
        mg = mg_cache[bd]
        if pc and mg is not None and thr is not None:
            rel = (r["ref_buy"] / float(pc) - 1) * 100 - mg
            r["rel_actual"], r["thr"], r["in_cond"] = round(rel, 3), thr, int(rel <= float(thr))
        if b.get("lim"):
            r["fill_odd"] = int(r["ref_buy"] > float(b["lim"]) + 1e-9)          # 시가가 지정가 위인데 사짐
    else:                                                                     # T5·T6: 매도 1호가에 사서 매도날 KRX 시가에 판다고 쟀다
        r["ref_buy"] = float(b["ask"]) if b.get("ask") else None
        r["ref_sell"] = float(Ks.o[t]) if Ks is not None and t in Ks.index else None
    if not r.get("ref_buy") or not r.get("ref_sell"): return None
    r["live"] = round((ap_s / ap_b - 1) * 100 - COST, 3)
    r["research"] = round((r["ref_sell"] / r["ref_buy"] - 1) * 100 - COST, 3)
    r["gap"] = round(r["live"] - r["research"], 3)
    r["slip_buy"] = round((ap_b / r["ref_buy"] - 1) * 100, 3)                  # + = 연구보다 비싸게 삼
    r["slip_sell"] = round((r["ref_sell"] / ap_s - 1) * 100, 3)                # + = 연구보다 싸게 팜
    return r


def missed(d):
    """[갭하락] 계열 그날: 시가 ≤ 지정가인데 체결 안 된 실주문(돈 모자람 가상 말고 실제로 낸 주문)."""
    K = m1(d)
    if K is None: return []
    X = json.loads((BASE / "data" / "day" / "ledger.json").read_text(encoding="utf-8"))["orders"]
    out = []
    for o in X:
        if o.get("side") == "BUY" and o.get("date") == d and o.get("rid") in T1F and o.get("lim") and o["t"] in K.index:
            if (o.get("fq") or 0) == 0 and o.get("status") in ("CANCELED", "PENDING", None) and float(K.o[o["t"]]) < float(o["lim"]) - 1e-9:
                out.append(dict(t=o["t"], name=o.get("name", ""), lim=o["lim"], open=float(K.o[o["t"]]), status=o.get("status")))
    return out


def save(rows):
    cols = ["rid", "t", "name", "buy_day", "sell_day", "buy", "sell", "lim", "ref_buy", "ref_sell", "live", "research", "gap",
            "slip_buy", "slip_sell", "rel_actual", "thr", "in_cond", "fill_odd"]
    old = pd.read_csv(LCSV, dtype={"t": str, "buy_day": str, "sell_day": str}) if LCSV.exists() else pd.DataFrame(columns=cols)
    N = pd.DataFrame(rows, columns=cols)
    A = pd.concat([old, N]).drop_duplicates(["rid", "t", "buy_day", "sell_day"], keep="last").sort_values(["sell_day", "rid", "t"])
    A.to_csv(LCSV, index=False, encoding="utf-8-sig")
    return A


def summarize(A):
    g = A.groupby(["sell_day", "rid"])
    D = pd.DataFrame({"n": g.size(), "live": g.live.mean(), "research": g.research.mean(), "gap": g.gap.mean(),
                      "slip_buy": g.slip_buy.mean(), "slip_sell": g.slip_sell.mean(),
                      "out_cond": g.in_cond.apply(lambda z: float((z.dropna() == 0).mean() * 100) if z.notna().any() else np.nan)}).round(3).reset_index()
    D.to_csv(DCSV, index=False, encoding="utf-8-sig")
    return D


def alerts(A, today, miss):
    days = sorted(A.sell_day.unique())[-WIN:]
    R = A[A.sell_day.isin(days)]
    msg = []
    for rid, z in R.groupby("rid"):
        if len(z) >= 3 and z.gap.mean() < GAP_WARN:
            msg.append("[%s] 최근 %d일 %d건 실전 %+.2f%% · 연구 %+.2f%% · 차이 %+.2f%%p(살 때 %+.2f · 팔 때 %+.2f)" % (
                RNAME.get(rid, rid), len(days), len(z), z.live.mean(), z.research.mean(), z.gap.mean(), -z.slip_buy.mean(), -z.slip_sell.mean()))
    t1 = R[R.rid.isin(T1F) & R.in_cond.notna()]
    if len(t1) >= 3:
        oc = float((t1.in_cond == 0).mean() * 100)
        if oc > OUT_WARN: msg.append("[갭하락] 최근 %d일 연구 조건 밖 체결 %.0f%% (%d/%d)" % (len(days), oc, int((t1.in_cond == 0).sum()), len(t1)))
    odd = A[(A.sell_day == today) & (A.fill_odd == 1)]
    if len(odd): msg.append("[갭하락] 시가가 지정가 위인데 사짐 %d건: %s" % (len(odd), ", ".join(odd.name.astype(str)[:5])))
    if miss: msg.append("[갭하락] 시가가 지정가 아래인데 안 사짐 %d건: %s" % (len(miss), ", ".join(m["name"] for m in miss[:5])))
    return msg


def report(A):
    print("| 규칙 | 왕복 | 실전 건당 | 연구 건당 | 차이 | 살 때 더 냄 | 팔 때 덜 받음 | 조건 밖 |")
    print("|---|---|---|---|---|---|---|---|")
    for rid, z in A.groupby("rid"):
        ic = z.in_cond.dropna()
        print("| [%s] | %d | %+.2f%% | %+.2f%% | %+.2f%%p | %+.2f%% | %+.2f%% | %s |" % (
            RNAME.get(rid, rid), len(z), z.live.mean(), z.research.mean(), z.gap.mean(), z.slip_buy.mean(), z.slip_sell.mean(),
            ("%.0f%% (%d/%d)" % ((ic == 0).mean() * 100, int((ic == 0).sum()), len(ic))) if len(ic) else "-"))


def main(mode=""):
    days = m1_days()
    today = days[-1]
    since = None if mode in ("all", "report") else days[-WIN - 1]
    mg = {}
    rows = [r for r in (judge(b, s, sd, days, mg) for b, s, sd in rounds(days, since)) if r]
    A = save(rows) if mode != "report" else pd.read_csv(LCSV, dtype={"t": str, "buy_day": str, "sell_day": str})
    if mode in ("all", "report"):
        report(A); summarize(A); return
    summarize(A)
    miss = missed(today)
    msg = alerts(A, today, miss)
    print("%s 감사: 왕복 %d줄 갱신 · 경보 %d" % (today, len(rows), len(msg)), flush=True)
    if msg:
        import day_alert as D
        D.telegram("🔍 <b>실전-연구 대조</b> %s/%s\n%s" % (today[4:6], today[6:], "\n".join(msg)))


if __name__ == "__main__":
    main((sys.argv[1:] or [""])[0])
