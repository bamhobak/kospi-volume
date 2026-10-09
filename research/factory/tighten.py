# -*- coding: utf-8 -*-
"""검토 후보 조이기 (2026-10-10 사용자: "F0023 F0035 신호 더 적게 나와도 되니 많이 조여봐 — 승률이랑 수익률 올라가게").

  ① 재료 하나 더 붙이기(재료 사전 전부 × 백분위 문턱 하위 10·20·30% / 상위 70·80·90%) + 있는 문턱 더 세게
  ② **학습 구간에서만** 고른다: 학습 건수 300↑ · 학습 승률과 건당 수익이 둘 다 원안보다 높은 것 → 학습 점수(건당 × √건수 비슷한 t) 순
  ③ 위 12개끼리 두 개 붙이기(학습에서 또 고름)
  ④ 마지막에만 검증(2023~)·15:19 재검을 연다 — 검증 보고 고르면 운이 섞이므로, 검증은 '버티나' 확인용
  ⑤ 학습·검증 둘 다 원안보다 승률·수익이 나은 것 상위 2개를 명세(origin tighten)로 깔때기에 넣는다 → 검토 대기 카드
돌린 칸 수는 공장 시험 횟수에 더한다.
    python research/factory/tighten.py F0023 F0035
"""
import sys, time, json
import numpy as np, pandas as pd

import common as C
import feats as FT
import lab

QLO, QHI = (0.1, 0.2, 0.3), (0.7, 0.8, 0.9)


def _st(U, sp, a, b):
    return lab.stats(lab.seg(lab.trades(U, sp), a, b))


def score(s):
    return s["mean"] * np.sqrt(s["n"]) if s else -9


def run(xid, U=None, top=12):
    U = U if U is not None else lab.hist()
    L = lab.load(); x = next(y for y in L if y["id"] == xid)
    base = {k: x[k] for k in ("mode", "conds") if k in x}
    if x.get("top"): base["top"] = x["top"]
    RF, TR, VA = lab.periods(base)
    b_tr, b_va = _st(U, base, *TR), _st(U, base, *VA)
    ok_at = FT.MODES[base["mode"]][1]
    have = {c["f"] for c in base["conds"]}
    cands = []
    for f, (d, at, _k) in FT.FEATS.items():                         # ① 재료 하나 더
        if at not in ok_at or f in have or ("q_" + f) not in U.columns: continue
        for v in QLO: cands.append(("%s 하위 %d%%" % (d[:26], v * 100), dict(base, conds=base["conds"] + [{"f": f, "q": True, "op": "<=", "v": v}])))
        for v in QHI: cands.append(("%s 상위 %d%%" % (d[:26], round((1 - v) * 100)), dict(base, conds=base["conds"] + [{"f": f, "q": True, "op": ">=", "v": v}])))
    for i, c in enumerate(base["conds"]):                           # 있는 문턱 더 세게
        if not c.get("q"): continue
        for v in ((0.05, 0.03) if c["op"] == "<=" else (0.95, 0.97)):
            if (c["op"] == "<=" and v < c["v"]) or (c["op"] == ">=" and v > c["v"]):
                cs = [dict(cc) for cc in base["conds"]]; cs[i]["v"] = v
                cands.append(("%s 문턱 %g→%g" % (FT.FEATS[c["f"]][0][:20], c["v"], v), dict(base, conds=cs)))
    for c in base["conds"]:                                          # 하루 최대 n종목(그 재료가 가장 센 순) — 승률을 끌어올리는 다른 길
        if not c.get("q"): continue
        for n in (2, 3, 5):
            cands.append(("하루 %d종목만(%s %s 순)" % (n, FT.FEATS[c["f"]][0][:18], "낮은" if c["op"] == "<=" else "높은"),
                          dict(base, top={"n": n, "by": c["f"], "asc": c["op"] == "<="})))
    t0 = time.time(); res = []
    for lab_, sp in cands:
        s = _st(U, sp, *TR)
        if s and s["n"] >= 300 and s["mean"] > b_tr["mean"] and s["win"] > b_tr["win"]:
            res.append((score(s), lab_, sp, s))
    n1 = len(cands)
    res.sort(key=lambda z: -z[0]); best = res[:top]
    pairs = []                                                       # ③ 두 개 붙이기
    for i in range(len(best)):
        for j in range(i + 1, len(best)):
            ci = best[i][2]["conds"][-1]; cj = best[j][2]["conds"][-1]
            if ci["f"] == cj["f"]: continue
            sp = dict(base, conds=base["conds"] + [ci, cj])
            s = _st(U, sp, *TR)
            if s and s["n"] >= 300 and s["mean"] > b_tr["mean"] and s["win"] > b_tr["win"]:
                pairs.append((score(s), best[i][1] + " + " + best[j][1], sp, s))
    n2 = len(best) * (len(best) - 1) // 2
    allr = sorted(res[:top] + sorted(pairs, key=lambda z: -z[0])[:top], key=lambda z: -z[0])
    out = []
    for sc, lab_, sp, s in allr:                                     # ④ 검증·15:19
        v = _st(U, sp, *VA)
        h = lab.honest_1519(U, sp) if lab.needs_1519(sp) else None
        out.append(dict(label=lab_, spec=sp, tr=s, va=v, honest=h))
    from verdict import log_trials
    log_trials("factory", n1 + n2)
    C.log("조이기 %s: 변형 %d + 짝 %d · 학습 통과 %d · %.1f분" % (xid, n1, n2, len(res), (time.time() - t0) / 60))
    return x, base, b_tr, b_va, lab.honest_1519(U, base) if lab.needs_1519(base) else None, out


def f_(s):
    return "-" if not s else "%s건 %+.2f%% · 승률 %.0f%%" % (f"{s['n']:,}", s["mean"], s["win"])


def main(ids):
    U = lab.hist()
    rep = ["# 검토 후보 조이기 · %s" % time.strftime("%Y-%m-%d %H:%M"), "",
           "- 고르는 건 학습(2016~22)에서만 — 학습 승률·건당 둘 다 원안보다 높은 것. 검증(2023~)·15:19 는 마지막 확인용", ""]
    L = lab.load(); added = []
    for xid in ids:
        x, base, b_tr, b_va, b_h, out = run(xid, U)
        rep += ["## %s %s" % (xid, x.get("desc", "")), "", "| 변형 | 학습 2016~22 | 검증 2023~ | 15:19 재검 |", "|---|---|---|---|",
                "| **원안** | %s | %s | %s |" % (f_(b_tr), f_(b_va), f_(b_h))]
        good = []
        for o in out:
            rep.append("| %s | %s | %s | %s |" % (o["label"], f_(o["tr"]), f_(o["va"]), f_(o["honest"])))
            v, h = o["va"], o["honest"]
            if v and b_va and v["n"] >= 60 and v["mean"] > b_va["mean"] and v["win"] > b_va["win"] and (h is None or (h["mean"] > 0 and h["n"] >= 40)):
                good.append(o)
        rep.append("")
        for o in good[:2]:                                            # ⑤ 깔때기로
            sp = dict(o["spec"], name="%s 조임: %s" % (xid, o["label"][:40]), origin="tighten", source=xid)
            r = lab.add(sp, L, pair=False); added.append(r["id"])
    lab.save(L)
    done = lab.process(L); lab.save(L)
    rep += ["## 깔때기 결과(조인 것)", ""] + ["- %s %s · 학습 %s · 검증 %s · %s" % (d["id"], d["status"], lab.fmt_s((d.get("res") or {}).get("tr")),
                                                                         lab.fmt_s((d.get("res") or {}).get("va")), d.get("why") or "통과 → 검토 대기") for d in done]
    f = C.REP / ("tighten_%s.md" % time.strftime("%Y%m%d_%H%M")); f.write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("\n".join(rep)); print("보고서:", f)
    try:
        import board; board.publish()
    except Exception as ex: C.log("후보 페이지 실패:", repr(ex)[:200])
    return done


if __name__ == "__main__":
    main(sys.argv[1:] or ["F0023", "F0035"])
