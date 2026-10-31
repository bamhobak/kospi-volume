# -*- coding: utf-8 -*-
"""[갭 하락 조용주] '하루 위 3개' 그림자 (2026-10-25 사용자 "H0362 이 그림자도 H0366처럼 실시간으로 볼 수 있게") — 돈 안 듦, 기록만.

H0362: 하루 예산을 고정해 그날 후보에 나눠 넣는다면, 후보 전부(지금 그물)보다 **시장 대비 가장 깊이 빠진 3개**에만 넣는 게
  연 +34.3%·낙폭 -4.8% vs 지금 +28.8%·-6.8%(2016~, 실제 시가로 고른 연구). 실전은 아침 예상 갭으로 고르니 덜 사질 수 있다 → 그걸 쟨다.
재료 = day_alert.py 가 매일 남기는 data/day/snap_<날>.json (아침 후보·지정가 → 09:01 실제 시가 → 16:25 종가·수익). 실전 코드는 안 건드린다.
  · 고르기: 아침 T1 후보(덤 T2·T3 빼고)를 rel(예상 갭 − 시장 중앙) 깊은 순으로 위 3개 · 비교로 위 5개
  · 체결: 지정가가 있으면 실제 시가 ≤ 지정가일 때만(10-12 전엔 시장가라 다 체결) — 안 사진 몫의 돈은 그날 논다
  · 하루 수익 = 무리 안 (사진 종목 수익 합 ÷ 무리 종목 수) — 하루 예산을 무리에 똑같이 나눴다고 본다 · 비용 0.23 뒤
  · 계좌 = 매일 계좌의 20% 를 그날 예산으로 썼다고 보고 복리(연구와 같은 가정)
  · 장중엔 토스 지금가로 시가 대비 수익을 다시 매긴다(5분마다)
결과 → Supabase '__t1top3__' (assets/factory.html 이 1분마다 읽는다).

    python day_top3.py           지금 상태로 계산해서 올리기(예약 작업이 평일 08:56~16:36 5분마다)
"""
import datetime as dt, json, sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
import collect_m1 as M
import autotrade as AT

KST = M.KST
DAY = BASE / "data" / "day"
COST = 0.23
BUDGET = 0.20                                    # 계좌 중 하루 예산 비율(H0362 연구 가정)
DOWN_Q = 0.30                                    # 장기하락 = 어제 종가의 120일선 대비(d120)가 그날 유니버스 하위 30% (H0368, lab q_d120 과 같은 식)
# (키, 이름, 위 몇 개, 거르기) — 거르기 무리는 그날 걸린 후보가 없으면 그날 돈이 논다(0%)
# 10-26 '장기하락만'(H0368) 무리는 같은 날 사용자 "하지 말자"로 뺌 — q120()·score(filt) 는 다른 거르기 무리를 붙일 때 쓰라고 남김
GROUPS = (("all", "지금 그물(후보 전부)", None, None), ("top3", "하루 위 3개", 3, None), ("top5", "하루 위 5개", 5, None))
KRD = BASE / "data" / "factory" / "live" / "kr_daily.parquet"


def log(*a):
    s = dt.datetime.now(KST).strftime("%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s)
    try:
        with open(DAY / "top3.log", "a", encoding="utf-8") as fh: fh.write(s + "\n")
    except Exception: pass


def live_prices(syms):
    out = {}
    for i in range(0, len(syms), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
            try: out[x["symbol"]] = float(x["lastPrice"])
            except (TypeError, ValueError, KeyError): pass
    return out


_K = None


def q120(snap):
    """{종목: d120 백분위} — 10-26 사용자(H0368 '장기하락만' 무리 추가). 공장 live/kr_daily.parquet(1분봉으로 만든 KRX 일봉 최근 200일)에서
    신호일 전날까지 종가로 d120 = 어제 종가 ÷ 120일 평균(96일↑) − 1 → 그날 유니버스(snap 'all' 종목)끼리 백분위. 자료가 없으면 {}."""
    global _K
    try:
        import pandas as pd
        if _K is None:
            _K = pd.read_parquet(KRD.resolve(), columns=["ticker", "date", "close"]).sort_values(["ticker", "date"])
        K = _K[_K.date < snap["date"]]
        if K.empty or K.date.max() < snap.get("prev", ""): return {}               # 전날 일봉이 아직 없음(자료 늦음)
        T = K.groupby("ticker").tail(120)
        g = T.groupby("ticker").close
        n, mean, last = g.size(), g.mean(), g.last()
        d = ((last / mean - 1) * 100)[n >= 96]
        d = d[d.index.isin(list((snap.get("all") or {}).keys()))]
        return d.rank(pct=True).to_dict() if len(d) >= 100 else {}
    except Exception as ex:
        log("120일선 계산 실패", repr(ex)[:120]); return {}


def day_rows(snap, px=None):
    """그날 T1 후보마다 {t, n, rel, lim, open, last, ret, filled, rank} — ret 는 종가(리뷰 뒤) 또는 지금가 기준"""
    C = sorted([x for x in snap.get("cand") or [] if x.get("t1", True)], key=lambda x: x.get("rel") if x.get("rel") is not None else 99)
    Q = q120(snap) if (C and any(g[3] == "down" for g in GROUPS)) else {}
    out = []
    for i, x in enumerate(C):
        o, lim = x.get("open"), x.get("lim")
        filled = None if not o else (lim is None or o <= lim)
        last = x.get("close")
        live = False
        if last is None and px and o:
            last = px.get(x["t"]); live = last is not None
        ret = round((last / o - 1) * 100 - COST, 3) if (o and last) else None
        out.append({"t": x["t"], "n": x.get("name", x["t"]), "rel": x.get("rel"), "gap": x.get("gap"), "lim": lim, "open": o, "last": last,
                    "ret": ret, "filled": filled, "rank": i + 1, "live": live,
                    "q120": (round(Q[x["t"]], 3) if x["t"] in Q else None), "qok": bool(Q)})
    return out


def score(rows, k, filt=None):
    if filt == "down":
        if rows and not rows[0]["qok"]: return None                        # 120일선 자료 없음 — 이 날은 안 셈
        rows = [x for x in rows if x["q120"] is not None and x["q120"] <= DOWN_Q]
        if not rows: return {"n": 0, "nf": 0, "day": 0.0, "trade": []}    # 걸린 후보 없음 = 그날 돈이 논다
    G = rows if k is None else rows[:k]
    if not G: return None
    F = [x for x in G if x["filled"] and x["ret"] is not None]
    if not F and any(x["filled"] is None or (x["filled"] and x["ret"] is None) for x in G): return None     # 시가 전 · 리뷰 전(0% 하루로 세지 않는다)
    return {"n": len(G), "nf": len(F), "day": round(sum(x["ret"] for x in F) / len(G), 3), "trade": [x["ret"] for x in F]}


def main():
    snaps = sorted(DAY.glob("snap_*.json"))
    if not snaps:
        log("데이 기록 없음"); return
    now = dt.datetime.now(KST)
    today = now.strftime("%Y%m%d")
    days, acct, tr = [], {g: 1.0 for g, _, _, _ in GROUPS}, {g: [] for g, _, _, _ in GROUPS}
    trows, tsnap = None, None
    for f in snaps:
        try: s = json.loads(f.read_text(encoding="utf-8"))
        except Exception: continue
        px = None
        is_today = s.get("date") == today and not s.get("review")
        if is_today and "0900" <= now.strftime("%H%M") <= "1545":
            syms = [x["t"] for x in s.get("cand") or [] if x.get("t1", True) and x.get("open")]
            try: px = live_prices(syms) if syms else None
            except Exception as ex: log("지금가 실패", repr(ex)[:120])
        rows = day_rows(s, px)
        if rows:
            trows, tsnap = rows, s                                         # 오늘(없으면 가장 최근 날) 후보표
        d = {"d": s["date"], "mg": s.get("mgap"), "n": len(rows), "live": is_today}
        done = True
        for g, _, k, ft in GROUPS:
            sc = score(rows, k, ft)
            d[g] = sc and {kk: sc[kk] for kk in ("n", "nf", "day")}
            if sc is None: done = False; continue
            if not is_today:
                acct[g] *= 1 + BUDGET * sc["day"] / 100
                tr[g] += sc["trade"]
        if rows: days.append(d)
    cum = []
    nd = sum(1 for d in days if not d["live"])
    for g, lab, k, ft in GROUPS:
        T = tr[g]
        D = [d[g]["day"] for d in days if not d["live"] and d.get(g)]
        cum.append({"g": g, "k": lab, "days": len(D), "trades": len(T), "avg": round(sum(T) / len(T), 3) if T else None,
                    "win": round(sum(1 for v in T if v > 0) / len(T) * 100) if T else None,
                    "day_avg": round(sum(D) / len(D), 3) if D else None, "day_win": round(sum(1 for v in D if v > 0) / len(D) * 100) if D else None,
                    "acct": round((acct[g] - 1) * 100, 2)})
    if tsnap and tsnap["date"] == today:
        stage = ("종가 채점 끝" if tsnap.get("review") else "장 전" if now.strftime("%H%M") < "0901" else
                 "장중(지금가)" if now.strftime("%H%M") <= "1530" else "장 마감 · 16:25 채점 전")
    else:
        stage = "오늘 후보 없음/휴장 — 최근 날 표시"
    data = {"updated": now.strftime("%Y-%m-%d %H:%M"), "stage": stage, "hid": "H0362", "days": nd,
            "rule": "아침 [갭 하락 조용주] 후보(덤 빼고)를 시장 대비 깊은 순으로 위 3개(비교 위 5개)만 산다고 보고, 후보 전부와 비교 · "
                    "지정가 체결(시가 ≤ 지정가)만 · "
                    "하루 예산을 무리에 똑같이 나눔(안 사진 몫은 놂) · 계좌 = 매일 계좌 %d%%를 그날 예산으로 · 비용 %.2f 뒤 · 돈은 안 든다(기록만)" % (BUDGET * 100, COST),
            "today": {"date": tsnap["date"], "mg": tsnap.get("mgap"), "rows": trows[:60], "n": len(trows)} if tsnap else None,
            "cum": cum, "recent": days[::-1][:40]}
    AT.rpc("kospi_state_set", {"p_pin": "__t1top3__", "p_data": data})
    log("올림 %s · 누적 %d일 · %s" % (stage, nd, " / ".join("%s %s%%" % (c["k"], c["acct"]) for c in cum)))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        log("실패", repr(ex)[:300])
