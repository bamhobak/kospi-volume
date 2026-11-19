# -*- coding: utf-8 -*-
"""수능일(2026-11-19, 10:00 개장) [갭하락]을 돌렸다면 — 되짚기 (사용자 11-19 "하면 안 돼?" → 장 끝나고 계산해 주기로).
day_alert.morning() 의 고르기(T1 + 덤 T2·T3, 11-19 설정)를 그대로 옮겨, 평소 08:52 에 보는 값을 한 시간 뒤(09:52)로 놓고 다시 만든다.
 예상 시가 = 09:01~09:51 봉(NXT 장전, 수능일은 한 시간 밀림)의 마지막 체결가 · 없으면 평소엔 장전 단일가 호가 중간값인데 녹화가 없어 **실제 10:00 시가로 대신**(그만큼 후하다).
 체결 = 실제 KRX 시가(10:01 봉 시가) ≤ 지정가 · 매수가 = 시가 · 매도 = 종가 단일가(16:31 봉 종가) · 비용 0.23.
 금액 = 기준 30만 × 깊이 배율(1~3) × 거래대금 배율(0.3~3) ÷ 지정가(내림).  갭 구간 공시 거르개 = 전 거래일 15:30 뒤 ~ 오늘 09:50.
 안 넣은 것: T4 [미장 폭락](나스닥 조건 따로 적음) · 악재 공시(-10%p 넘는 것만 해당) · 돈 모자람.
    python research/suneung_whatif_1119.py
"""
import datetime as dt, math, pickle, sqlite3, sys, time
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE)); sys.stdout.reconfigure(encoding="utf-8")
import day_alert as D
M, AT = D.M, D.AT
TODAY, PREV = "20261119", "20261118"
CACHE = Path("C:/temp/kp/suneung_1119.pkl")
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))


def day_bars(sym):
    """오늘 1분봉(봉 끝 시각) 09:01~16:31 → (장전 마지막 체결가, 장전 거래 봉 수, 시가, 종가)."""
    before = "%s-%s-%sT16:40:00.000+09:00" % (TODAY[:4], TODAY[4:6], TODAY[6:]); rows = {}
    for _ in range(4):
        c = (M.get("/api/v1/candles", symbol=sym, interval="1m", count=200, before=before) or {}).get("candles") or []
        if not c: break
        for x in c:
            ts = x["timestamp"]
            if ts[:10].replace("-", "") == TODAY: rows[ts[11:16]] = (float(x["openPrice"]), float(x["closePrice"]), float(x.get("volume") or 0))
        old = min(x["timestamp"] for x in c)
        if old[:10].replace("-", "") < TODAY or old[11:16] <= "09:01": break
        before = old
    pre = [(k, v) for k, v in sorted(rows.items()) if "09:01" <= k <= "09:51" and v[2] > 0]
    reg = [(k, v) for k, v in sorted(rows.items()) if "10:01" <= k <= "16:31" and v[2] > 0]
    return (pre[-1][1][1] if pre else None, len(pre), reg[0][1][0] if reg else None, reg[-1][1][1] if reg else None, reg[-1][0] if reg else None)


if CACHE.exists():
    R, B, lh, up = pickle.load(open(CACHE, "rb"))
else:
    R = D.prep(TODAY, PREV)
    R = {k: v for k, v in R.items() if v["pc"] >= 1000 and v["pdate"] == PREV}
    liq = D.pct_rank({k: v["amt20"] for k, v in R.items()}); uni = [k for k in R if liq[k] >= 0.60]
    B = {}
    for n, s in enumerate(uni):
        try: B[s] = day_bars(s)
        except Exception as ex: print("봉 실패", s, repr(ex)[:80])
        if n % 200 == 0: print("봉", n, len(uni), flush=True)
    uliq = D.pct_rank({k: R[k]["amt20"] for k in uni}); vmq = D.pct_rank({k: R[k]["vm"] for k in uni})
    pre0 = [k for k in uni if uliq[k] <= 2 / 3 and vmq[k] <= 0.30]; tiny0 = {k for k in uni if uliq[k] <= 1 / 3}
    lh = D.yday_lasth([k for k in pre0 if k in tiny0], PREV); up = D.us_pred(TODAY)
    pickle.dump((R, B, lh, up), open(CACHE, "wb"))

liq = D.pct_rank({k: v["amt20"] for k, v in R.items()}); uni = [k for k in R if liq[k] >= 0.60 and k in B and B[k][2]]
uliq = D.pct_rank({k: R[k]["amt20"] for k in uni}); vmq = D.pct_rank({k: R[k]["vm"] for k in uni})
small = [k for k in uni if uliq[k] <= 2 / 3]; pre = [k for k in small if vmq[k] <= 0.30]
tiny = {k for k in uni if uliq[k] <= 1 / 3}; t1u = {k for k in uni if uliq[k] <= D.T1_LIQ}


def run(label, exp, src):
    gap = {s: (exp[s] / R[s]["pc"] - 1) * 100 for s in uni if exp.get(s)}
    gq = D.pct_rank(gap); mg = sorted(gap.values())[len(gap) // 2]
    cand = sorted([s for s in pre if s in t1u and s in gq and gq[s] <= D.CAND_Q and gap[s] - mg <= D.CAND_REL], key=lambda s: gap[s] - mg)
    cand = [s for s in cand if gap[s] > D.NOBUY_GAP]
    c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
    kk = {r[0] for r in c.execute("SELECT kcode FROM kind WHERE market IN ('유가증권','코스닥') AND ((day = ? AND hm > '1530') OR (day = ? AND hm < '0950'))", (PREV, TODAY))}; c.close()
    kdrop = [s for s in cand if s[:5] in kk]; cand = [s for s in cand if s[:5] not in kk]
    nm = {k: v[0] for k, v in AT.names(cand).items()} if cand else {}
    L = [dict(t=s, name=nm.get(s, s), gap=gap[s], rel=gap[s] - mg, pc=R[s]["pc"], lim=D.limit_price(R[s]["pc"], mg), a20=R[s]["amt20"] / 1e8, src=src[s],
              t2=(s in tiny and s in lh and lh[s] <= D.T2_CUT), t3=(s in tiny and s in up and up[s] <= D.T3_CUT), o=B[s][2], c=B[s][3]) for s in cand]
    md = sorted(x["a20"] for x in L)[len(L) // 2] if L else 1.0
    rows = []
    for x in L:
        x["lm"] = min(D.LIQ_HI, max(D.LIQ_LO, x["a20"] / md)); mult = D.day_mult(x)
        q = math.floor(D.DAY_BASE * mult * x["lm"] / x["lim"])
        if q < 1 and x["lim"] <= D.DAY_BASE * 2: q = 1
        for rid in ["T1"] + D.extras(x):
            fill = x["o"] <= x["lim"]
            r = (x["c"] / x["o"] - 1) * 100 - D.COST if fill and x["c"] else None
            rows.append(dict(x, rid=rid, q=q, mult=mult, order=q * x["lim"], fill=fill, r=r, pnl=(q * x["o"] * r / 100) if r is not None else 0.0))
    F = [z for z in rows if z["fill"]]
    P_("\n## %s\n" % label)
    P_("시장 갭(유니버스 중앙) %+.2f%% · 유니버스 %d · 예상가 NXT 장전 %d · 대신 쓴 값 %d · 후보 %d종목(공시로 뺌 %d) · 주문 %d건 %s원 · **체결 %d건 %s원**" % (
        mg, len(uni), sum(1 for s in uni if src[s] == "NXT"), sum(1 for s in uni if src[s] != "NXT"), len(L), len(kdrop), len(rows), f"{sum(z['order'] for z in rows):,.0f}",
        len(F), f"{sum(z['q'] * z['o'] for z in F):,.0f}"))
    if F:
        rs = [z["r"] for z in F]; tot = sum(z["pnl"] for z in F)
        P_("체결분 건당 %+.2f%%(중앙 %+.2f) · 오른 것 %d/%d · **손익 %+s원**(비용 뒤) · 가장 나쁜 건 %+.2f%% · 가장 좋은 건 %+.2f%%\n" % (
            sum(rs) / len(rs), sorted(rs)[len(rs) // 2], sum(1 for r in rs if r > 0), len(rs), f"{tot:,.0f}", min(rs), max(rs)))
        P_("| 종목 | 규칙 | 예상 갭(시장 대비) | 예상가 출처 | 지정가 | 실제 시가 | 종가 | 주수 | 수익률 | 손익 |\n|---|---|---|---|---|---|---|---|---|---|")
        for z in sorted(F, key=lambda z: z["pnl"]):
            P_("| %s | %s | %+.1f%% (%+.1f) | %s | %s | %s | %s | %d | %+.2f%% | %+s |" % (z["name"], D.RNAME[z["rid"]], z["gap"], z["rel"], z["src"], f"{z['lim']:,}", f"{z['o']:,.0f}", f"{z['c']:,.0f}", z["q"], z["r"], f"{z['pnl']:,.0f}"))
    U = [z for z in rows if not z["fill"]]
    if U: P_("\n안 사진 것 %d건(시가가 지정가보다 높음): " % len(U) + " · ".join(sorted({z["name"] for z in U})[:25]))
    return rows


P_("# 수능일(2026-11-19) [갭하락]을 돌렸다면 — 되짚기\n")
n_pre = sum(1 for s in uni if B[s][0]); last = sorted({B[s][4] for s in uni if B[s][4]})[-1]
P_("유니버스 %d종목 중 09:01~09:51 NXT 장전 체결 있는 종목 %d · 마지막 정규장 봉 %s · 조용한 작은 종목(장전 확정) %d" % (len(uni), n_pre, last, len(pre)))
try:
    nas, nsrc = D.nasdaq_last(TODAY); P_("T4 [미장 폭락]: 나스닥 %+.2f%%(%s) — 문턱 %.1f%% %s" % (nas, nsrc, D.U_NAS, "→ 발동(여기선 안 계산)" if nas <= D.U_NAS else "→ 해당 없음"))
except Exception as ex: P_("나스닥 못 받음 %r" % ex)
expA = {s: (B[s][0] or B[s][2]) for s in uni}; srcA = {s: ("NXT" if B[s][0] else "실제 시가(대신)") for s in uni}
A = run("A. 09:52 에 봤을 값으로(장전 체결가 · 없으면 실제 시가로 대신) — 실전에 가장 가까움", expA, srcA)
expB = {s: B[s][2] for s in uni}; srcB = {s: "실제 시가" for s in uni}
Bq = run("B. 실제 10:00 시가를 미리 알았다면(연구 정의 — 위쪽 한계)", expB, srcB)
# 예상가가 얼마나 맞았나: 장전 마지막 체결가 vs 실제 시가
import numpy as np
e = np.array([(B[s][0] / B[s][2] - 1) * 100 for s in uni if B[s][0]])
if len(e):
    P_("\n## 예상 시가가 얼마나 맞았나(장전 마지막 체결가 ÷ 실제 시가 − 1, %d종목)\n\n평균 %+.2f%% · 중앙 %+.2f%% · 절대값 중앙 %.2f%% · ±1%% 안 %.0f%%" % (
        len(e), e.mean(), np.median(e), np.median(np.abs(e)), (np.abs(e) <= 1).mean() * 100))
else:
    P_("\n## 예상 시가 출처\n\n**수능일엔 개장 전 NXT 장전 체결이 한 건도 없었다**(09:01~09:51 봉 거래량 0 · 08:00~09:03 녹화도 전부 어제 시각). "
       "평소 유니버스의 약 3분의 2(616/966)가 NXT 장전 체결가로 예상 시가를 잡는데 그게 통째로 없음 → 남는 건 KRX 장전 단일가 호가 중간값뿐(오늘 09:50 녹화 없음). "
       "그래서 A 와 B 가 같은 값(둘 다 실제 시가) = **미리 시가를 알았을 때의 위쪽 한계**이지 실전 추정이 아니다.")
(BASE / "research" / "reports" / "suneung_whatif_1119.md").write_text("\n".join(OUT), encoding="utf-8")
