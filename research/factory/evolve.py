# -*- coding: utf-8 -*-
"""규칙 진화기 (유전 프로그래밍, 2026-10-08 사용자 아이디어 ⑥).

유전자 = 매매 방식(oc 시가→종가 · on 종가→다음날 시가) + 조건 1~3개(재료 백분위 ≤/≥ 문턱).
매일 밤: 지난밤 개체군(data/factory/gp_pop.json)에서 변이·교배로 자식을 낳고 **학습 구간(2016~22)만** 보고 고른다.
  적합도 = 하루 평균 수익의 t 값(비용 뒤) - 조건 수 벌점 0.3/개 · 건수 150↑·60일↑ 이 안 되면 탈락
  검증 구간(2023~)은 여기서 절대 안 본다 → 상위(적합도 ≥ 3, 아직 안 본 명세) 최대 3개만 깔때기(lab)로 넘겨 G2 에서 한 번 연다.
  돌린 개체 수는 전부 공장 시험 횟수(verdict 'factory')에 더한다 → 많이 뒤질수록 다중검정 문턱이 올라간다(정직).
"""
import json, random, time
import numpy as np, pandas as pd

import common as C
import feats as FT
import lab

POP = C.DATA / "gp_pop.json"
THR_LO, THR_HI = [0.05, 0.1, 0.2, 0.3], [0.7, 0.8, 0.9, 0.95]
GP_MODES = ["oc", "on"]
_A = None


def feats_for(mode):
    ok = FT.MODES[mode][1]
    return [f for f in FT.HIST if FT.FEATS[f][1] in ok and f not in ("liq",)] + ["liq"]


def arrays():
    global _A
    if _A is not None: return _A
    U = lab.hist()
    Z = U[(U.date >= lab.TR[0]) & (U.date <= lab.TR[1])]
    fs = sorted(set(feats_for("oc")) | set(feats_for("on")))
    fs = [f for f in fs if ("q_" + f) in Z.columns]
    Q = np.column_stack([Z["q_" + f].to_numpy(np.float32) for f in fs])
    dates = Z.date.to_numpy(); ud, di = np.unique(dates, return_inverse=True)
    on = Z.on.to_numpy(np.float64) - FT.COST
    on[Z.r1t.to_numpy() >= np.where(dates < "20150615", 14.5, 29.5)] = np.nan       # 상한가 마감은 종가에 못 산다
    _A = dict(fs=fs, col={f: i for i, f in enumerate(fs)}, Q=Q, di=di, nd=len(ud),
              y={"oc": (Z.oc.to_numpy(np.float64) - FT.COST), "on": on})
    return _A


def fitness(ind):
    A = arrays()
    y = A["y"][ind["mode"]]
    m = np.isfinite(y)
    for f, op, v in ind["conds"]:
        if f not in A["col"]: return -9.0, 0
        x = A["Q"][:, A["col"][f]]
        with np.errstate(invalid="ignore"):
            m &= (x <= v) if op == "<=" else (x >= v)
    n = int(m.sum())
    if n < 150: return -9.0, n
    s = np.bincount(A["di"][m], weights=y[m], minlength=A["nd"]); c = np.bincount(A["di"][m], minlength=A["nd"])
    ok = c > 0
    if ok.sum() < 60: return -9.0, n
    d = s[ok] / c[ok]
    t = d.mean() / (d.std(ddof=1) + 1e-12) * np.sqrt(len(d))
    if y[m].mean() <= 0: t = min(t, 0)
    return float(t - 0.3 * (len(ind["conds"]) - 1)), n


def rcond(mode, avoid=()):
    f = random.choice([x for x in feats_for(mode) if x not in avoid])
    if random.random() < 0.5: return [f, "<=", random.choice(THR_LO)]
    return [f, ">=", random.choice(THR_HI)]


def rind():
    mode = random.choice(GP_MODES)
    cs = []
    for _ in range(random.choice([1, 2, 2, 3])):
        cs.append(rcond(mode, [c[0] for c in cs]))
    return {"mode": mode, "conds": cs}


def fix(ind):
    ok = set(feats_for(ind["mode"]))
    seen, cs = set(), []
    for c in ind["conds"]:
        if c[0] in ok and c[0] not in seen:
            seen.add(c[0]); cs.append(c)
    ind["conds"] = cs[:3] or [rcond(ind["mode"])]
    return ind


def mutate(ind):
    x = json.loads(json.dumps(ind))
    k = random.random()
    cs = x["conds"]
    if k < 0.35:                                                       # 문턱 옆으로
        c = random.choice(cs); L = THR_LO if c[1] == "<=" else THR_HI
        i = L.index(c[2]) if c[2] in L else 0
        c[2] = L[max(0, min(len(L) - 1, i + random.choice([-1, 1])))]
    elif k < 0.55:                                                     # 재료 바꾸기
        i = random.randrange(len(cs)); cs[i] = rcond(x["mode"], [c[0] for c in cs])
    elif k < 0.65:                                                     # 반대쪽
        c = random.choice(cs); c[1] = ">=" if c[1] == "<=" else "<="; c[2] = round(1 - c[2], 2)
    elif k < 0.82 and len(cs) < 3:                                     # 조건 더하기
        cs.append(rcond(x["mode"], [c[0] for c in cs]))
    elif k < 0.92 and len(cs) > 1:                                     # 조건 빼기
        cs.pop(random.randrange(len(cs)))
    else:                                                              # 매매 방식 바꾸기
        x["mode"] = "on" if x["mode"] == "oc" else "oc"
    return fix(x)


def cross(a, b):
    cs = a["conds"] + b["conds"]; random.shuffle(cs)
    return fix({"mode": a["mode"], "conds": json.loads(json.dumps(cs[:random.choice([1, 2, 3])]))})


def to_spec(ind, fit):
    return {"name": "진화기: " + " & ".join("%s%s%.2f" % tuple(c) for c in ind["conds"]), "origin": "gp",
            "source": "진화기 적합도 %.2f(학습 하루 t)" % fit, "mode": ind["mode"],
            "conds": [{"f": f, "q": True, "op": op, "v": v} for f, op, v in ind["conds"]]}


def ikey(ind):
    return lab.key(to_spec(ind, 0))


def run(gens=8, pop=40, kids=40, promote=3, seed=None):
    random.seed(seed or int(time.time()))
    t0 = time.time()
    P = C.jload(POP, []) or [rind() for _ in range(pop * 2)]
    scored, evals = {}, 0

    def ev(ind):
        nonlocal evals
        k = ikey(ind)
        if k not in scored:
            f, n = fitness(ind); evals += 1
            scored[k] = (f, n, ind)
        return scored[k]
    for ind in P: ev(ind)
    for gen in range(gens):
        par = sorted(scored.values(), key=lambda z: -z[0])[:pop]
        for _ in range(kids):
            if random.random() < 0.3 and len(par) > 1:
                a, b = random.sample(par, 2); ev(cross(a[2], b[2]))
            elif random.random() < 0.15:
                ev(rind())
            else:
                ev(mutate(random.choice(par[: max(5, pop // 2)])[2]))
    best = sorted(scored.values(), key=lambda z: -z[0])
    C.jsave(POP, [z[2] for z in best[:pop]])
    from verdict import log_trials
    log_trials("factory", evals)
    have = {x.get("key") for x in lab.load()}
    out = []
    for f, n, ind in best:
        if f < 3.0 or len(out) >= promote: break
        sp = to_spec(ind, f)
        if lab.key(sp) in have: continue
        out.append((sp, f, n))
    C.log("진화기: %d개 평가 · 최고 %.2f · 깔때기로 %d · %.1f분" % (evals, best[0][0] if best else 0, len(out), (time.time() - t0) / 60))
    return out, best[:10], evals
