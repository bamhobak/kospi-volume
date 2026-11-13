# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "지금 규칙대로면 안 샀을 것들 사이트에서 삭제해줘" — 사이트 데이 기록(positions_scalp, 실제·가상) 중 지금 규칙이면 안 샀을 것 삭제.
[갭하락]·덤(T1·T2·T3) — research/recheck_day_1113.py 와 같은 판정: 예상 갭 하위 40% · 예상 시장 대비 ≤ -1.0 · 예상 갭 -27.5↓ 안 삼 · 덤은 1/3 작은 쪽
   · 실제 KRX 시가 ≤ 지금 지정가(-2.0) — 시가 > 지정가인데 장중 체결된 것도 지금(11-13 open_guard 고침)은 취소 · 갭 구간 KIND 공시 빼기
[장전 되돌림](T5) — 순위 4 안 · 장후(어제 통합 종가 ÷ 어제 KRX 종가) +1.5% 넘으면 뺌(11-14) · 그 뒤 신호 10개↑ 날 쉼
[장후 낙폭](T6)·[반대매매](P9)·그 밖 — 산 뒤 조건 안 바뀜 → 그대로. 그날 기록이 없어 판단 못 하면 남긴다.
원장(data/day/ledger.json)은 그대로 — 사이트 표시만. 실제 주문 건 id 는 data/autotrade/site_hidden.json 에도 넣는다(되살림 막기).
    python research/del_day_1114.py        (세기만)
    python research/del_day_1114.py --do   (지움 · 백업 data/day/positions_scalp_backup_날짜_시각.json)"""
import json, sys, time, math, sqlite3, glob
from pathlib import Path
import numpy as np
B = Path(r"C:\vscode\kospi-volume"); sys.path.insert(0, str(B)); sys.stdout.reconfigure(encoding="utf-8")
import autotrade as AT
import day_alert as D
from day_alert import kr_tick
DO = "--do" in sys.argv
LIMIT_THR, CAND_Q, CAND_REL, NOBUY = -2.0, 0.40, -1.0, -27.5
RANK_MAX, CROWD_MAX, REL, CUM_MAX, AH_MAX = 4, 10, -3.0, 1_019_060_000, 1.5
kc = sqlite3.connect(B / "data/dart/kind_time.db", timeout=30)
KDAYS = sorted(Path(f).stem for f in glob.glob(str(B / "data/m1/KR/day/*.parquet")))


def lim_now(pc, mg):
    p = pc * (1 + (mg + LIMIT_THR) / 100); t = kr_tick(p); return int(math.floor(p / t) * t)


def kind_has(t, prev, today):
    r = kc.execute("SELECT title FROM kind WHERE market IN ('유가증권','코스닥') AND kcode=? AND ((day=? AND hm>'1530') OR (day>? AND day<?) OR (day=? AND hm<'0850')) LIMIT 1",
                   (t[:5], prev, prev, today, today)).fetchone()
    return r[0] if r else None


SN, NP, KC = {}, {}, {}
def jl(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
def snap(d):
    if d not in SN: SN[d] = jl(B / ("data/day/snap_%s.json" % d))
    return SN[d]
def nsnap(d):
    if d not in NP: NP[d] = jl(B / ("data/nxtpre/snap_%s.json" % d))
    return NP[d]
def kclose(d):
    if d not in KC:
        pv = [x for x in KDAYS if x < d]
        KC[d] = D.krx_closes(pv[-1]) if pv else {}
    return KC[d]


def judge(p):
    rid = (p.get("filters") or ["?"])[0]; d = str(p.get("date")); t = p.get("code")
    why = []
    if rid in ("T1", "T2", "T3"):
        s = snap(d)
        if s is None: return None, "장전 기록 없음"
        c = {x["t"]: x for x in s.get("cand") or []}.get(t); al = s.get("all") or {}
        if c is None: return None, "그날 후보 목록에 없음"
        mg = float(s["mgap"]); gaps = sorted(v["gap"] for v in al.values() if v.get("gap") is not None)
        g = c["gap"]; q = np.searchsorted(gaps, g, side="right") / len(gaps) if gaps else 0
        if q > CAND_Q + 1e-9: why.append("예상 갭 하위 %.0f%%" % (q * 100))
        if c["rel"] > CAND_REL: why.append("예상 시장 대비 %+.2f" % c["rel"])
        if g <= NOBUY: why.append("예상 갭 -27.5↓")
        if rid in ("T2", "T3") and al.get(t, {}).get("tiny") is False: why.append("덤인데 1/3 밖")
        op = c.get("open") or (float(p["price"]) if p.get("paper") else None)
        if op is None: return None, "시가 모름"
        ln = lim_now(float(c["pc"]), mg)
        if float(op) > ln: why.append("시가 %s > 지금 지정가 %s" % (int(op), ln))
        k = kind_has(t, str(s.get("prev") or ""), d) if s.get("prev") else None
        if k: why.append("갭 구간 공시(%s)" % k[:16])
    elif rid == "T5":
        s = nsnap(d)
        if s is None: return None, "장전 기록 없음"
        C = s["cand"]; K = kclose(d)
        for x in C: x["_ah"] = (x["yc"] / K[x["t"]] - 1) * 100 if K.get(x["t"]) and x.get("yc") else None
        order = sorted(C, key=lambda x: x["pre"]); rk0 = {x["t"]: i + 1 for i, x in enumerate(order)}
        rk = {x["t"]: x.get("rank") or rk0[x["t"]] for x in C}
        p0 = [x for x in C if x["rel"] <= REL and x.get("cum") is not None and x["cum"] <= CUM_MAX and not (x["_ah"] is not None and x["_ah"] > AH_MAX)]
        me = {x["t"]: x for x in C}.get(t)
        if len(p0) >= CROWD_MAX: why.append("붐비는 날(신호 %d개)" % len(p0))
        if rk.get(t, 999) > RANK_MAX: why.append("순위 %s" % rk.get(t, "?"))
        if me and me["_ah"] is not None and me["_ah"] > AH_MAX: why.append("장후 %+.1f%%" % me["_ah"])
    else:
        return True, ""
    return (not why), " · ".join(why)


S = AT.site_state()
P = [p for p in S.get("positions_scalp") or [] if (p.get("filters") or ["?"])[0] in ("T1", "T2", "T3", "T5")]
drop, keep, unk = [], [], []
for p in P:
    ok, why = judge(p); p["_why"] = why
    (unk if ok is None else keep if ok else drop).append(p)
ret = lambda p: (float(p["sell"]) / float(p["price"]) - 1) * 100 - 0.23 if p.get("sell") else None
def line(L):
    r = [ret(p) for p in L if ret(p) is not None]
    return "%d건(실제 %d·가상 %d) 건당 %s 승 %s" % (len(L), sum(1 for p in L if not p.get("paper")), sum(1 for p in L if p.get("paper")),
            ("%+.2f%%" % np.mean(r)) if r else "-", ("%.0f%%" % (np.mean([x > 0 for x in r]) * 100)) if r else "-")
print("사이트 데이 기록(T1·T2·T3·T5) %d건 · 전체 positions_scalp %d건" % (len(P), len(S.get("positions_scalp") or [])))
print("남김:", line(keep)); print("지움:", line(drop)); print("판단 못 함(남김):", line(unk), [(p["date"], p.get("name"), p["_why"]) for p in unk][:8])
from collections import Counter
for rid in ("T1", "T2", "T3", "T5"):
    k = [p for p in keep if p["filters"][0] == rid]; x = [p for p in drop if p["filters"][0] == rid]
    c = Counter(w.split("(")[0].split(" ")[0] if not w.startswith("시가") else "시가 > 지정가" for p in x for w in p["_why"].split(" · "))
    print("  %s 남김 %s · 지움 %s · 이유 %s" % (rid, line(k), line(x), dict(c)))
print("지울 날짜별:", dict(Counter(str(p["date"]) for p in drop)))
if not DO: sys.exit(0)
bk = B / "data" / "day" / ("positions_scalp_backup_%s.json" % time.strftime("%Y%m%d_%H%M"))
bk.write_text(json.dumps(S.get("positions_scalp"), ensure_ascii=False), encoding="utf-8")
ids = {p["id"] for p in drop}; n = {"k": 0}
def mut(X):
    before = len(X); X[:] = [x for x in X if x.get("id") not in ids]; n["k"] = before - len(X); return n["k"] > 0
AT.state_update("positions_scalp", mut, "지금 규칙이면 안 샀을 데이 %d건 삭제(사용자 11-14)" % len(ids))
real = [p for p in drop if not p.get("paper")]
H = AT.HIDDEN; cur = json.loads(H.read_text(encoding="utf-8")) if H.exists() else {}
hid = set(cur.get("ids") or []) | {p["id"] for p in real}
cur["ids"] = sorted(hid); cur["why"] = str(cur.get("why") or "") + " · 2026-11-14 사용자 지시: 지금 규칙(갭하락 판정·장전 되돌림 순위4·장후1.5·붐빔)이면 안 샀을 데이 실제 %d건 — 사이트에서 지움, 원장은 그대로" % len(real)
H.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
print("지움 %d · 백업 %s · 되살림 막기 +%d (전체 %d)" % (n["k"], bk.name, len(real), len(hid)))
