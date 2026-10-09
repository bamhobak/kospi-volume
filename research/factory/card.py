# -*- coding: utf-8 -*-
"""검토 카드 (2026-10-10 사용자: "검증까지 통과한 거 그림자로 돌리지 말고 바로 알려줘서 조정해서 좋으면 바로 규칙으로").

깔때기 G2 를 통과한 명세마다 카드 한 장 — data(x) 가 숫자를 모으고, make(x) 가 md(research/reports/factory/review/<id>.md)로,
board.py 가 같은 숫자를 사이트 '규칙 후보' 페이지(factory.html ← Supabase __factory__)로 보낸다.
  ① 기본 성적(참고 2010~15 · 학습 · 검증 · 15:19 재검) + 해마다
  ② 조건 하나씩 빼면 · ③ 문턱 옮기면 · (스윙) 손절·익절 붙이면 · 보유 기간 바꾸면 — 조정 후보
  ④ 종목 크기별 · 시장 국면별(유니버스 5일 등락 ±) · 비용 +0.1%p 더 들면
  ⑤ T1·다른 후보와 겹침 · 최근 신호 10개 ⑥ 실전이면 어떻게 사고파나
⚠ 조정 칸을 고르는 것도 시험이다(여러 칸을 보고 고르면 그만큼 운이 섞인다) — 검증 칸만 좋은 것보다 참고·학습 칸도 같이 좋은 걸로.
"""
import time
import numpy as np, pandas as pd

import common as C
import feats as FT
import lab

RV = C.REP / "review"; RV.mkdir(parents=True, exist_ok=True)
HOW = {"oc": "08:5x 장전에 골라 시가 단일가(OPG) 매수 → 같은 날 15:20~30 종가 단일가 매도 — [갭 하락 조용주] 와 같은 방식(day_alert 에 붙인다)",
       "m": "%s:00 에 그때까지 모습으로 골라 장중 시장가 매수 → 같은 날 종가 단일가 매도 — 데이 탭 장중 규칙으로 새로 붙인다(토스 실시간 소켓 200종목 한계 안)",
       "on": "15:19 가격으로 골라 종가 단일가(15:20~30) 매수 → 다음날 시가 단일가 매도 — 데이 탭에 '종가 매수' 규칙으로 새로 붙인다",
       "sw": "장전에 골라 시가 매수 → %d거래일 뒤 종가 매도%s — 스윙 탭 규칙(사이트 FILTERS + 엣지 함수 보유일 + autotrade)"}


def _T(U, spec):
    T = lab.trades(U, spec)
    if spec["mode"].startswith("sw"):
        T = T.assign(ex=T.ret - T.date.map(U.groupby("date")[FT.TARGET[spec["mode"]]].mean()))
    return T


def _s(T, a, b):
    s = lab.stats(lab.seg(T, a, b)) if T is not None and len(T) else None
    if not s: return None
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items() if k in ("n", "mean", "med", "win", "t", "ypos", "ny", "ex", "perday")}


def _three(U, spec):
    T = _T(U, spec)
    rf, tr, va = lab.periods(spec)
    return {"ref": _s(T, *rf) if rf else None, "tr": _s(T, *tr), "va": _s(T, *va)}


def variants(spec):
    out = []
    cs = spec["conds"]
    if len(cs) > 1:
        for i, c in enumerate(cs):
            out.append(("빼기: " + lab.desc({"mode": spec["mode"], "conds": [c]}).split("] ", 1)[1], dict(spec, conds=cs[:i] + cs[i + 1:])))
    for i, c in enumerate(cs):
        v = float(c["v"])
        alts = ([round(v + d, 2) for d in (-0.1, -0.05, 0.05, 0.1) if 0 < v + d < 1] if c.get("q")
                else [round(v * k, 4) for k in (0.5, 0.75, 1.25, 1.5)] if v else [-1.0, 1.0])
        for a in alts:
            out.append(("%s %s %g → %g" % (FT.FEATS[c["f"]][0][:22], c["op"], v, a), dict(spec, conds=cs[:i] + [dict(c, v=a)] + cs[i + 1:])))
    if spec["mode"].startswith("sw"):
        base = {k: v for k, v in spec.items() if k != "exit"}
        for st, tk in ((-5, 10), (-7, 15), (-10, 20), (-7, None), (None, 15)):
            ex = {k: v for k, v in (("stop", st), ("take", tk)) if v is not None}
            if ex != (spec.get("exit") or {}):
                out.append(("청산: " + ("손절 %d%% " % st if st else "") + ("익절 +%d%%" % tk if tk else ""), dict(base, exit=ex)))
        if spec.get("exit"): out.append(("청산 없이(보유일 끝 종가)", base))
        for hh in FT.SWH:
            if "sw%d" % hh != spec["mode"]: out.append(("보유 %d일" % hh, dict(spec, mode="sw%d" % hh)))
    return out


def data(x, L=None):
    U = lab.hist()
    T = _T(U, x)
    RF, TRp, VAp = lab.periods(x)
    names = C.jload(C.DATA / "names.json", {})
    L = L or lab.load()
    r = x.get("res") or {}
    yr = T.groupby(T.date.str[:4]).ret.agg(["size", "mean"])
    Tm = T.merge(U[["date", "ticker", "liq", "mk_r5"]], on=["date", "ticker"], how="left")
    parts = []
    for nm, m in (("작은 종목(거래대금 아래 1/3)", Tm.liq <= 1 / 3), ("중간", (Tm.liq > 1 / 3) & (Tm.liq <= 2 / 3)), ("큰 종목(위 1/3)", Tm.liq > 2 / 3),
                  ("시장 5일 오름", Tm.mk_r5 > 0), ("시장 5일 내림", Tm.mk_r5 <= 0)):
        z = Tm[m.fillna(False)]
        parts.append({"label": nm, "tr": _s(z, *TRp), "va": _s(z, *VAp)})
    z = T.assign(ret=T.ret - 0.1)
    parts.append({"label": "비용 +0.1%p 더 들면", "tr": _s(z, *TRp), "va": _s(z, *VAp)})
    var = []
    for lab_, sp in variants(x):
        try: var.append(dict(label=lab_, **_three(U, sp)))
        except Exception as ex: var.append({"label": lab_, "err": str(ex)[:60]})
    ov = []
    if "t1" in T.columns: ov.append({"with": "[갭 하락 조용주] T1", "pct": round(float(T.t1.mean() * 100), 1)})
    A = set(zip(lab.seg(T, *VAp).date, lab.seg(T, *VAp).ticker))
    for y in L:
        if y["id"] != x["id"] and y.get("status") in ("review", "adopted"):
            B = lab._tset(y, U)
            if A and B: ov.append({"with": y["id"], "pct": round(len(A & B) / max(min(len(A), len(B)), 1) * 100, 1)})
    sib = [y["id"] for y in L if y.get("status") == "sibling" and x["id"] in (y.get("why") or "")]
    last = T.sort_values("date").tail(10)
    va = lab.seg(T, *VAp)
    m = x["mode"]; ex = x.get("exit") or {}
    how = (HOW["m"] % m[1:3]) if m.startswith("m") else HOW["sw"] % (int(m[2:]), (" (보유 중 %s%s)" % (("손절 %g%% " % ex["stop"]) if ex.get("stop") else "", ("익절 +%g%%" % ex["take"]) if ex.get("take") else "")) if ex else "") if m.startswith("sw") else HOW[m]
    return {"id": x["id"], "status": x.get("status"), "name": x.get("name", ""), "desc": x.get("desc") or lab.desc(x), "mode": m,
            "kind": "스윙" if m.startswith("sw") else "데이", "origin": x.get("origin"), "source": x.get("source", ""),
            "approx": x.get("approx", ""), "untestable": x.get("untestable", ""), "since": x.get("shadow_from"),
            "res": {k: r.get(k) for k in ("ref", "tr", "va", "honest", "dsr")},
            "yearly": [[y_, int(n), round(float(mn), 3)] for y_, (n, mn) in yr.iterrows()],
            "variants": var, "parts": parts, "overlap": ov, "siblings": sib,
            "recent": [[d, names.get(t, t), round(float(rr), 2)] for d, t, rr in zip(last.date, last.ticker, last.ret)],
            "perday": round(float(lab.stats(va)["perday"]), 2) if len(va) else 0,
            "dayshare": round(va.date.nunique() / max(U[U.date >= VAp[0]].date.nunique(), 1) * 100, 1),
            "how": how, "fwd": x.get("fwd") or {}}


def _fs(s):
    if not s: return "-"
    return "%s건 %+.2f%% · 승률 %.0f%%%s" % (f"{s['n']:,}", s["mean"], s["win"], (" · 초과 %+.2f" % s["ex"]) if s.get("ex") is not None else "")


def make(x, d=None):
    d = d or data(x)
    r = d["res"]
    L = ["# 검토 카드 %s — %s" % (d["id"], d["name"]), "", "- 명세: %s" % d["desc"], "- 출처: %s · %s" % (d["origin"], d["source"]), ""]
    if d["approx"] or d["untestable"]: L += ["- 근사한 부분: %s" % (d["approx"] or "-"), "- 못 옮긴 부분: %s" % (d["untestable"] or "-"), ""]
    L += ["## ① 기본 성적 (비용 뒤 · 건당)", "", "| 구간 | 성적 |", "|---|---|",
          "| 참고 2010~15 | %s |" % lab.fmt_s(r.get("ref")), "| 학습 2016~22 | %s |" % lab.fmt_s(r.get("tr")), "| 검증 2023~ | %s |" % lab.fmt_s(r.get("va"))]
    if r.get("honest"): L.append("| 15:19 가격으로 고르면(2023~) | %s |" % lab.fmt_s(r["honest"]))
    if r.get("dsr") is not None: L.append("| 다중검정(진짜일 확률) | %.2f |" % r["dsr"])
    L += ["", "해마다: " + " · ".join("%s %+.2f%%(%d)" % (y, mn, n) for y, n, mn in d["yearly"]), ""]
    L += ["## ② 조정 후보", "", "| 바꾼 것 | 참고 2010~15 | 학습 2016~22 | 검증 2023~ |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % (v["label"], _fs(v.get("ref")), _fs(v.get("tr")), _fs(v.get("va"))) for v in d["variants"]]
    L += ["", "## ④ 어디서 먹히나", "", "| 나눔 | 학습 | 검증 |", "|---|---|---|"] + ["| %s | %s | %s |" % (p["label"], _fs(p["tr"]), _fs(p["va"])) for p in d["parts"]]
    L += ["", "## ⑤ 겹침 · 최근 신호", ""] + ["- %s 와 겹침 %.0f%%" % (o["with"], o["pct"]) for o in d["overlap"]]
    if d["siblings"]: L.append("- 형제(같은 규칙으로 묶음): " + ", ".join(d["siblings"]))
    L += ["", "| 날짜 | 종목 | 수익(비용 뒤) |", "|---|---|---|"] + ["| %s | %s | %+.2f%% |" % tuple(t) for t in d["recent"]]
    L += ["", "- 하루 평균 %.1f종목(신호 있는 날) · 신호 있는 날 비율 %.0f%%" % (d["perday"], d["dayshare"]),
          "", "## ⑥ 실전이면", "", "- " + d["how"], "- 채택·조정은 클로드 창에서 \"%s 채택\" 또는 \"%s 문턱 ○○로\" 처럼 말하면 된다" % (d["id"], d["id"]), ""]
    f = RV / ("%s.md" % d["id"]); f.write_text("\n".join(L) + "\n", encoding="utf-8")
    return f


def notify(xs):
    """검토 대기 알림 — 사용자가 정할 것이라 텔레그램으로(중요한 것만 기준)."""
    for x in xs:
        r = x.get("res") or {}
        C.tg("🔔 <b>규칙 후보 검토 대기 %s</b>\n%s\n학습 %s\n검증 %s%s\n사이트 '규칙 후보' 페이지(factory.html)에서 자세히\n→ 클로드 창에서 '%s 채택 / 조정' 말하면 됨" % (
            x["id"], x.get("desc", ""), lab.fmt_s(r.get("tr")), lab.fmt_s(r.get("va")),
            ("\n15:19 재검 %s" % lab.fmt_s(r["honest"])) if r.get("honest") else "", x["id"]))
