# -*- coding: utf-8 -*-
"""2026-11-13 사용자 "현재 규칙 기준으로 거래된것만 체크해봐" — 데이 실전 왕복(data/audit/live.csv) 중 지금 설정이었어도 샀을 것만 남겨 성적.
[갭하락]·덤(T1·T2·T3): 그날 snap 값으로 지금 후보 그물(예상 갭 유니버스 하위 40% · 예상 시장 대비 ≤ -1.0) · 지금 지정가(-2.0, 실제 KRX 시가 ≤ 지정가여야 체결)
   · 갭 구간 공시(KIND, 11-10~ 빼기) · 예상 갭 -27.5↓ 안 삼. 덤은 1/3 작은 쪽 안(snap tiny).
[장전 되돌림](T5): 그날 순위 4 안(11-11~) · 신호(-3%p·얇음) 10개↑ 날 쉼(11-12~).
[장후 낙폭](T6): 실주문 조건(11-05 D)이 실전 첫날(11-09) 전부터 그대로 → 전부 남김.
"""
import json, sys, math, sqlite3
from pathlib import Path
import pandas as pd, numpy as np
B = Path(r"C:\vscode\kospi-volume"); sys.path.insert(0, str(B))
sys.stdout.reconfigure(encoding="utf-8")
from day_alert import kr_tick
LIMIT_THR, CAND_Q, CAND_REL, NOBUY = -2.0, 0.40, -1.0, -27.5
RANK_MAX, CROWD_MAX, REL, CUM_MAX = 4, 10, -3.0, 1_019_060_000
A = pd.read_csv(B / "data/audit/live.csv", encoding="utf-8-sig", dtype={"t": str})
A["buy_day"] = A.buy_day.astype(str)
kc = sqlite3.connect(B / "data/dart/kind_time.db", timeout=30)

def lim_now(pc, mg):
    p = pc * (1 + (mg + LIMIT_THR) / 100); t = kr_tick(p); return int(math.floor(p / t) * t)

def kind_has(t, prev, today):
    r = kc.execute("SELECT title FROM kind WHERE market IN ('유가증권','코스닥') AND kcode=? AND ((day=? AND hm>'1530') OR (day>? AND day<?) OR (day=? AND hm<'0850')) LIMIT 1",
                   (t[:5], prev, prev, today, today)).fetchone()
    return r[0] if r else None

SN, NP = {}, {}
def snap(d):
    if d not in SN:
        p = B / ("data/day/snap_%s.json" % d); SN[d] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return SN[d]
def nsnap(d):
    if d not in NP:
        p = B / ("data/nxtpre/snap_%s.json" % d); NP[d] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return NP[d]

rows = []
for r in A.itertuples():
    why = []
    if r.rid in ("T1", "T2", "T3"):
        s = snap(r.buy_day)
        if s is None: why.append("장전 기록 없음")
        else:
            c = {x["t"]: x for x in s.get("cand") or []}.get(r.t)
            al = s.get("all") or {}
            if c is None: why.append("그날 후보 목록에 없음")
            else:
                mg = float(s["mgap"]); gaps = sorted(v["gap"] for v in al.values() if v.get("gap") is not None)
                g = c["gap"]; q = (np.searchsorted(gaps, g, side="right")) / len(gaps) if gaps else 0
                if q > CAND_Q + 1e-9: why.append("예상 갭 하위 %.0f%%(40%% 밖)" % (q * 100))
                if c["rel"] > CAND_REL: why.append("예상 시장 대비 %+.2f(-1.0 위)" % c["rel"])
                if g <= NOBUY: why.append("예상 갭 -27.5↓")
                if r.rid in ("T2", "T3") and al.get(r.t, {}).get("tiny") is False: why.append("덤인데 1/3 밖")
                ln = lim_now(float(c["pc"]), mg); op = float(r.ref_buy)
                if op > ln: why.append("시가 %s > 지금 지정가 %s" % (int(op), ln))
                k = kind_has(r.t, str(s["prev"]), r.buy_day)
                if k: why.append("갭 구간 공시(%s)" % k[:18])
    elif r.rid == "T5":
        s = nsnap(r.buy_day)
        if s is None: why.append("장전 기록 없음")
        else:
            C = s["cand"]
            order = sorted(C, key=lambda x: x["pre"]); rk = {x["t"]: i + 1 for i, x in enumerate(order)}
            p0 = [x for x in C if x["rel"] <= REL and x.get("cum") is not None and x["cum"] <= CUM_MAX]
            if len(p0) >= CROWD_MAX: why.append("붐비는 날(신호 %d개)" % len(p0))
            if rk.get(r.t, 999) > RANK_MAX: why.append("순위 %s(4 밖)" % rk.get(r.t, "?"))
    rows.append(dict(rid=r.rid, t=r.t, name=r.name, buy_day=r.buy_day, live=r.live, research=r.research, ok=not why, why=" · ".join(why)))
R = pd.DataFrame(rows)
R.to_csv(B / "research/reports/recheck_day_1113.csv", index=False, encoding="utf-8-sig")
E = {"T1": (1.35, 65), "T2": (2.62, 75), "T3": (2.05, 71), "T5": (1.01, 56), "T6": (1.83, 66)}
print("| 규칙 | 전체 | 지금 규칙으로 남는 것(일수) | 남은 것 실전 건당 | 승률 | 날 바구니 | 빠진 것 건당 | 기대 |")
for rid, g in R.groupby("rid"):
    k = g[g.ok]; x = g[~g.ok]
    nd = k.buy_day.nunique()
    print("| %s | %d | %d (%d일) | %s | %s | %s | %s | %+.2f%% · %d%% |" % (rid, len(g), len(k), nd,
          ("%+.2f%%" % k.live.mean()) if len(k) else "-", ("%.0f%%" % ((k.live > 0).mean() * 100)) if len(k) else "-",
          ("%+.2f%%" % k.groupby("buy_day").live.mean().mean()) if len(k) else "-", ("%+.2f%% (%d)" % (x.live.mean(), len(x))) if len(x) else "-", *E[rid]))
print()
for rid in ("T1", "T2", "T3", "T5"):
    g = R[(R.rid == rid) & ~R.ok]
    if len(g):
        c = g.why.str.split(" · ").explode().str.replace(r"\(.*", "", regex=True).str.replace(r"시가 \d+ > 지금 지정가 \d+", "시가 > 지금 지정가", regex=True).str.replace(r"순위 \d+", "순위", regex=True).value_counts()
        print(rid, "빠진 이유", c.to_dict())
k = R[(R.rid == "T1") & R.ok]
if len(k):
    print("T1 남은 것 주별", k.assign(w=pd.to_datetime(k.buy_day).dt.to_period("W").astype(str)).groupby("w").live.agg(["size", "mean"]).round(2).to_dict("index"))
    print("T1 남은 것 중앙 %.2f · 연구 가정가 %.2f" % (k.live.median(), k.research.mean()))
for rid in ("T2", "T3", "T5"):
    k = R[(R.rid == rid) & R.ok]
    if len(k): print(rid, "남은 것", k[["buy_day", "name", "live"]].to_string(index=False))
