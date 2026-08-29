# -*- coding: utf-8 -*-
"""1·2번 필터 8.7년 재검증 (2019~2026)"""
import io, pickle, sys
import numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
S = pickle.load(open("data/sig_2018.pkl", "rb"))
S = [s for s in S if len(s["C"]) >= 2 and np.isfinite(s["surge"])]
YS = list(range(2019, 2027))

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev(s, h, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1); c = cost(s["amt"])
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - c
        if tp and H[i] >= tp: return tp - c
        if i == n: return C[i] - c
def stat(P, h, sl, tp):
    if len(P) < 5: return None
    r = np.array([ev(s, h, sl, tp) for s in P]); w, l = r[r > 0], r[r <= 0]
    ys = {y: [ev(s, h, sl, tp) for s in P if s["y"] == y] for y in YS}
    return dict(n=len(r), avg=r.mean(), med=np.median(r), win=len(w) / len(r) * 100,
                pf=(w.sum() / abs(l.sum())) if len(l) else 99,
                ys={y: (np.mean(v), len(v)) if v else (None, 0) for y, v in ys.items()})
def show(title, rows):
    print(f"\n## {title}\n")
    print("| 구성 | 건수 | 순수익 | 중앙값 | 승률 | PF | " + " | ".join(map(str, YS)) + " |")
    print("|---|---|---|---|---|---|" + "---|" * len(YS))
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 |" + " - |" * (4 + len(YS))); continue
        print(f"| {lab} | {a['n']} | **{a['avg']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['pf']:.2f} | "
              + " | ".join(f"{a['ys'][y][0]:+.1f}({a['ys'][y][1]})" if a['ys'][y][1] else "-" for y in YS) + " |")

F1 = lambda s: (s["quiet"] < 0.5 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 50
                and 0 <= s["ret10"] <= 20 and s["k20"] and not s["pref"])
F2 = lambda s: (s["quiet"] < 0.4 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 3
                and s["ret3"] <= 0 and not s["pref"])
A1 = [s for s in S if F1(s)]
A1r = [s for s in A1 if s["rs"] is not None and s["rs"] > 0]
A2 = [s for s in S if F2(s)]
show("1번 필터 (10일·손절15%·익절30%) — 상대강도 조건 효과",
     [("조건 없음 (구버전)", stat(A1, 10, 15, 30)),
      ("**+ 업종 상대강도>0 (현재)**", stat(A1r, 10, 15, 30)),
      ("+ 상대강도>+3%", stat([s for s in A1 if s["rs"] is not None and s["rs"] > 3], 10, 15, 30))])
show("2번 필터 (10일·손절10%)", [("현재 조건", stat(A2, 10, 10, None))])
print("\n## 기간 비교 — 예전 검증구간(2023~26) vs 새로 열린 구간(2019~22)\n")
print("| 필터 | 2019~2022 | 2023~2026 |\n|---|---|---|")
f = lambda x: "-" if not x else f"{x['avg']:+.2f}% / 승률 {x['win']:.0f}% / PF {x['pf']:.2f} ({x['n']}건)"
for lab, P, h, sl, tp in [("1번 (상대강도 없음)", A1, 10, 15, 30), ("1번 (상대강도>0)", A1r, 10, 15, 30),
                          ("2번", A2, 10, 10, None)]:
    old = [s for s in P if s["y"] <= 2022]; new = [s for s in P if s["y"] >= 2023]
    print(f"| {lab} | {f(stat(old,h,sl,tp))} | {f(stat(new,h,sl,tp))} |")
print("\n## 코로나 급락장(2020년 1~6월) 단독\n")
print("| 필터 | 건수 | 순수익 | 승률 | PF |\n|---|---|---|---|---|")
for lab, P, h, sl, tp in [("1번 (상대강도>0)", A1r, 10, 15, 30), ("2번", A2, 10, 10, None)]:
    c = [s for s in P if "20200101" <= s["d"] <= "20200630"]
    a = stat(c, h, sl, tp)
    print(f"| {lab} | {len(c)} | " + (f"{a['avg']:+.2f}% | {a['win']:.0f}% | {a['pf']:.2f} |" if a else "- | - | - |"))
