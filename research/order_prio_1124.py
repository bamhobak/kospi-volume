# -*- coding: utf-8 -*-
"""2026-11-24 데이 매수 주문 순서 — 돈이 모자랄 때 '옛 순서'와 '깊은 순'(804a93a) 비교. 사용자 "바꾼게 수익 볼 확률이 더 좋아?"
  옛 순서 = [갭하락] 깊은 순 → [미장 폭락] 전용 → 덤(T2·T3) · 새 순서 = 전부 시장 대비 갭(08:52 예상) 깊은 순(같은 종목 T1→T2→T3)
  자료 = 실전 후보 기록 data/day/snap_*.json(2026-10-06~, 34일) + 그날 1분봉 시가·종가. 주문 금액은 지금 실전식(기준 30만 × 깊이 배율 × 거래대금 배율 ÷ 지정가).
  주문은 낸 만큼 돈이 묶인다(안 사져도) → 예산 안에서 앞에서부터 채우고, 모자라면 살 수 있는 만큼, 1주도 안 되면 건너뜀. 체결 = 시가 ≤ 지정가 → 시가 매수·종가 매도 − 0.23%.
    python research/memguard.py research/order_prio_1124.py → research/reports/order_prio_1124.md"""
import glob, json, math, sys
from pathlib import Path
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import day_alert as D, audit_live as A
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK, UNIT = 0.23, 300000
BUDGETS = (1000, 2000, 3000)                                  # 만원 — 5천만 계좌에서 [장후 낙폭] 보유분을 뺀 아침 매수 가능


def old_list(L):
    return [(x, "T1" if x.get("t1", True) else "T4") for x in L] + [(x, r) for x in L if x.get("t1", True) for r in D.extras(x)]


def sized(x):
    px = float(int(x.get("lim") or D.limit_price(x["pc"], 0.0)))
    q = math.floor(UNIT * D.day_mult(x) * float(x.get("lm") or 1.0) / px)
    if q < 1 and px <= UNIT * 2: q = 1
    return px, q


def run(O, K, bp):
    """예산 bp(원) 안에서 순서대로. 돌려줌: [(x, rid, 주수, 원하던 주수, 체결?, 수익률%, 손익 원)]"""
    out = []
    for x, rid in O:
        px, want = sized(x)
        if want < 1 or x["t"] not in K.index: continue
        q = want
        if bp is not None and q * px > bp:
            q = math.floor(bp / px) if px <= bp else 0
        if bp is not None: bp -= q * px
        o, c = float(K.o[x["t"]]), float(K.c[x["t"]])
        fill = o <= px + 1e-9
        r = (c / o - 1) * 100 - CK
        out.append((x, rid, q, want, fill, r, q * o * r / 100 if fill else 0.0))
    return out


DAYS = []
for f in sorted(glob.glob(str(BASE / "data" / "day" / "snap_*.json"))):
    d = Path(f).stem[5:]; C = json.loads(Path(f).read_text(encoding="utf-8")).get("cand") or []
    K = A.m1(d)
    if K is None or not C: continue
    DAYS.append((d, C, K))
P("# 데이 매수 주문 순서 — 옛 순서 vs 깊은 순 (2026-11-24)\n")
P("- 실전 후보 기록 %d일(%s~%s) · 지금 실전 금액식으로 다시 돌림 · 값은 만원" % (len(DAYS), DAYS[0][0], DAYS[-1][0]))
full = {d: run(old_list(C), K, None) for d, C, K in DAYS}
want = {d: sum(q * sized(x)[0] for x, rid, q, w, fl, r, p in v) / 1e4 for d, v in full.items()}
ws = sorted(want.values())
P("- 돈 걱정 없이 전부 냈을 때 하루 주문 금액: 중앙 %.0f만 · 상위 25%% %.0f만 · 최대 %.0f만 · 1천만 넘는 날 %d · 2천만 넘는 날 %d · 3천만 넘는 날 %d" % (
    ws[len(ws) // 2], ws[int(len(ws) * 0.75)], ws[-1], sum(w > 1000 for w in ws), sum(w > 2000 for w in ws), sum(w > 3000 for w in ws)))
P("\n## 1) 같은 돈으로 순서만 바꾸면\n")
P("| 아침에 쓸 수 있는 돈 | 돈이 모자란 날 | 옛 순서 합 | 깊은 순 합 | 차이 | 깊은 순이 나은 날 / 못한 날 / 같은 날 | 옛 순서 플러스인 날 | 깊은 순 플러스인 날 | 체결 건 이긴 비율 옛→새 |")
P("|---|---|---|---|---|---|---|---|---|")
DET = {}
for b in BUDGETS:
    so = sn = 0.0; up = dn = eq = 0; po = pn = 0; short = 0; wo, wn = [], []; rows = []
    for d, C, K in DAYS:
        a = run(old_list(C), K, b * 1e4); n = run(D.order_list(C), K, b * 1e4)
        pa, pb = sum(z[6] for z in a) / 1e4, sum(z[6] for z in n) / 1e4
        so += pa; sn += pb; short += want[d] > b
        up += pb > pa + 0.01; dn += pb < pa - 0.01; eq += abs(pb - pa) <= 0.01; po += pa > 0; pn += pb > 0
        wo += [z[5] > 0 for z in a if z[4] and z[2] > 0]; wn += [z[5] > 0 for z in n if z[4] and z[2] > 0]
        rows.append((d, pa, pb, a, n))
    DET[b] = rows
    P("| %d만 | %d일 | %+.1f | %+.1f | %+.1f | %d / %d / %d | %d일 | %d일 | %.0f%% → %.0f%% |" % (b, short, so, sn, sn - so, up, dn, eq, po, pn, np.mean(wo) * 100, np.mean(wn) * 100))
P("\n## 2) 날마다 (쓸 수 있는 돈 2천만, 차이 난 날만)\n")
P("| 날 | 전부 냈다면 주문 금액 | 옛 순서 | 깊은 순 | 차이 | 깊은 순에서 새로 돈 받은 주문(체결분) | 대신 돈 못 받은 주문(체결분) |"); P("|---|---|---|---|---|---|---|")
RN = {"T1": "갭하락", "T2": "갭하락+", "T3": "갭하락++", "T4": "미장 폭락"}
for d, pa, pb, a, n in DET[2000]:
    if abs(pb - pa) <= 0.01: continue
    qa = {(z[0]["t"], z[1]): z for z in a}; qn = {(z[0]["t"], z[1]): z for z in n}
    gain = [(k, qn[k]) for k in qn if qn[k][4] and qn[k][2] > qa[k][2]]; lose = [(k, qa[k]) for k in qa if qa[k][4] and qa[k][2] > qn[k][2]]
    fmt = lambda L, o: ", ".join("%s[%s] %+.1f%%(%+.1f만)" % (z[0]["name"], RN[k[1]], z[5], (z[2] - o[k][2]) * float(K_o(d, k[0])) * z[5] / 1e6) for k, z in L[:4]) + (" 외 %d" % (len(L) - 4) if len(L) > 4 else "") if L else "-"
    K_o = lambda dd, t: next(K for x, C, K in DAYS if x == dd).o[t]
    P("| %s | %.0f | %+.1f | %+.1f | %+.1f | %s | %s |" % (d, want[d], pa, pb, pb - pa, fmt(gain, qa), fmt(lose, qn)))
P("\n## 3) 주문 종류별 성적 (돈 걱정 없이 전부 냈을 때, %d일)\n" % len(DAYS))
P("| 종류 | 주문 | 체결 | 체결 비율 | 체결 건당 | 이긴 비율 | 주문 금액 100만당 기대 손익 |"); P("|---|---|---|---|---|---|---|")
ALL = [(d, z) for d, v in full.items() for z in v]
def grp(lab, sel):
    Z = [z for d, z in ALL if sel(z)]
    if not Z: return
    F = [z for z in Z if z[4]]
    amt = sum(z[3] * sized(z[0])[0] for z in Z); pnl = sum(z[6] for z in Z)
    P("| %s | %d | %d | %.0f%% | %s | %s | %s |" % (lab, len(Z), len(F), len(F) / len(Z) * 100, "%+.2f%%" % np.mean([z[5] for z in F]) if F else "-", "%.0f%%" % (np.mean([z[5] > 0 for z in F]) * 100) if F else "-", "%+.2f만" % (pnl / amt * 100) if amt else "-"))
rel = lambda z: float(z[0].get("rel") or 0)
grp("[갭하락] 예상 시장 대비 -5%p↓", lambda z: z[1] == "T1" and rel(z) <= -5)
grp("[갭하락] -5 ~ -3", lambda z: z[1] == "T1" and -5 < rel(z) <= -3)
grp("[갭하락] -3 ~ -2", lambda z: z[1] == "T1" and -3 < rel(z) <= -2)
grp("[갭하락] -2 ~ -1.5", lambda z: z[1] == "T1" and -2 < rel(z) <= -1.5)
grp("[갭하락] -1.5보다 얕음", lambda z: z[1] == "T1" and rel(z) > -1.5)
grp("덤 [갭하락+]", lambda z: z[1] == "T2")
grp("덤 [갭하락++]", lambda z: z[1] == "T3")
grp("덤 — 깊은 종목(-3%p↓)", lambda z: z[1] in ("T2", "T3") and rel(z) <= -3)
grp("덤 — 얕은 종목(-3%p보다 얕음)", lambda z: z[1] in ("T2", "T3") and rel(z) > -3)
grp("[미장 폭락] 전용", lambda z: z[1] == "T4")
P("\n시험 칸 %d" % len(BUDGETS))
(ROOT / "reports" / "order_prio_1124.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
if "--nolog" not in sys.argv:
    try:
        from verdict import log_trials
        log_trials("order_prio_1124", len(BUDGETS))
    except Exception as ex: print("칸 수 기록 실패:", repr(ex)[:200])
