# -*- coding: utf-8 -*-
"""규칙 공장 깔때기 — 명세(JSON)를 같은 잣대로 판정하고, 뒤집기 짝을 붙이고, 등록부(data/factory/specs.jsonl)에 적는다.

명세 예:
  {"name": "갭 크게 빠진 조용한 작은 종목", "origin": "harvest|gp|answer|invert|manual", "source": "링크·설명",
   "mode": "oc", "conds": [{"f": "gap", "q": true, "op": "<=", "v": 0.1}, {"f": "vm", "op": "<=", "v": 0.7}],
   "top": {"n": 10, "by": "rgap", "asc": true}}     # top 은 선택 — 하루 최대 n 종목(by 순)
  q=true 면 그날 유니버스 안 백분위(0~1)로 비교, 아니면 원래 값(%·배)으로 비교.

깔때기(앞에서 떨어지면 멈춘다 — 나쁜 걸 싸게 버리는 게 목적):
  G0 형식   재료가 사전에 있고 그 매매 방식에서 미리 알 수 있는 재료인가 · 이미 본 명세인가
  G1 학습   2016~22(외국인 재료면 2018~22) — 건수 150↑·60일↑ · 건당 평균 > 0 · 하루 평균 t ≥ 2 · 해마다 플러스 60%↑
  G2 검증   2023~(잠가 둔 구간 — G1 통과한 것만 연다) — 건당 평균 > 0 · 하루 t ≥ 1 · 해마다 플러스 절반↑ ·
            다중검정(공장에서 지금까지 돌린 명세 수로 Deflated Sharpe ≥ 0.90) · T1(갭 하락 조용주)과 겹침 50% 미만
  G3 그림자  G2 통과 → 실제로 사지 않고 앞으로 오는 날 성적을 매일 기록(fshadow) — 20거래일·15건 뒤 판정 → 텔레그램 '1주 실전?'
판정은 자금 무제한·다 산다. 수익은 비용 뒤(oc·on 0.23% · sw 는 패널 비용).
"""
import hashlib, json, math, os, sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

import common as C
import feats as FT

SPECS = C.DATA / "specs.jsonl"
HIST = C.CACHE / "factory_kr.pkl"
VER = "f1"                      # 재료 정의 바꾸면 올린다 → 과거 자료 다시 만든다
TR = ("20160101", "20221231"); VA = ("20230101", "20991231"); REF = ("20100101", "20151231")
DSR_MIN = 0.90
_U = None


# ══════════════════════════════════════════════════════════════════════
# 과거 자료
# ══════════════════════════════════════════════════════════════════════
def load_flows(since="20170101"):
    c = sqlite3.connect("file:" + str(C.BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    return pd.read_sql("SELECT ticker, date, indiv, frgn FROM flow11 WHERE date >= ?", c, params=(since,))


def load_themes():
    S = pd.read_csv(C.BASE / "data" / "sector.csv", dtype=str)
    return S[S.kind == "theme"][["gname", "ticker"]].drop_duplicates()


def build_hist(force=False):
    src = C.BASE / "data" / "kr_scan.pkl"
    key = "%s_%d" % (VER, src.stat().st_mtime)
    meta = C.CACHE / "factory_kr.meta"
    if not force and HIST.exists() and meta.exists() and meta.read_text() == key:
        return
    t0 = time.time(); C.log("과거 자료 만들기 시작(kr_scan → 재료)")
    A = pd.read_pickle(src)
    A = A[A.date >= "20090101"][["ticker", "date", "open", "high", "low", "close", "volume", "pref", "n5", "n20"]].copy()
    X = FT.make(A, load_flows(), load_themes())
    del A
    U = X[X.uni & (X.date >= REF[0])].drop(columns=["uni"]).reset_index(drop=True)
    del X
    try:
        import transfer as TF
        TF.attach_hist(U)
    except Exception as ex:
        C.log("전이표 재료 못 붙임(미장 자료 없음?):", repr(ex)[:200])
    U = FT.shrink(FT.qcols(U, FT.HIST))
    U["t1"] = ((U.q_gap <= 0.10) & (U.q_vm <= 0.30) & (U.liq <= 1 / 3) & (U.rgap <= -2.0)).astype(bool)   # T1 근사(겹침 확인용)
    U.to_pickle(HIST); meta.write_text(key)
    C.log("과거 자료 끝 — %s줄 · %.1f분" % (f"{len(U):,}", (time.time() - t0) / 60))


def hist():
    global _U
    if _U is None:
        build_hist()
        _U = pd.read_pickle(HIST)
    return _U


# ══════════════════════════════════════════════════════════════════════
# 명세
# ══════════════════════════════════════════════════════════════════════
def canon(spec):
    cs = sorted((c["f"], bool(c.get("q")), c["op"], round(float(c["v"]), 4)) for c in spec["conds"])
    top = spec.get("top") or {}
    return json.dumps([spec["mode"], cs, top.get("n"), top.get("by"), top.get("asc")], ensure_ascii=False)


def key(spec):
    return hashlib.sha1(canon(spec).encode()).hexdigest()[:12]


def check(spec):
    """G0 — 문제가 있으면 이유 문자열, 없으면 None."""
    mode = spec.get("mode")
    if mode not in FT.MODES: return "매매 방식 모름: %s" % mode
    conds = spec.get("conds") or []
    if not 1 <= len(conds) <= 5: return "조건 수 %d (1~5개만)" % len(conds)
    ok_at = FT.MODES[mode][1] | {"live"}
    for c in conds:
        f = c.get("f")
        if f not in FT.FEATS: return "사전에 없는 재료: %s" % f
        if FT.FEATS[f][1] not in ok_at: return "%s 는 %s 방식에서 미리 알 수 없음(%s)" % (f, mode, FT.FEATS[f][1])
        if c.get("op") not in ("<=", ">="): return "부등호는 <= >= 만"
        try: float(c["v"])
        except Exception: return "값이 숫자가 아님: %s" % c.get("v")
        if c.get("q") and not 0 <= float(c["v"]) <= 1: return "백분위 값은 0~1"
    t = spec.get("top")
    if t and (t.get("by") not in FT.FEATS or not isinstance(t.get("n"), int)): return "top 형식 오류"
    return None


def uses_live(spec):
    return any(FT.FEATS[c["f"]][1] == "live" for c in spec["conds"])


def desc(spec):
    """사람이 읽는 한 줄."""
    ps = []
    for c in spec["conds"]:
        nm = FT.FEATS[c["f"]][0]
        if c.get("q"):
            v = float(c["v"])
            ps.append("%s %s %d%%" % (nm, "하위" if c["op"] == "<=" else "상위", round((v if c["op"] == "<=" else 1 - v) * 100)))
        else:
            ps.append("%s %s %g" % (nm, c["op"], float(c["v"])))
    t = spec.get("top")
    if t: ps.append("하루 %d종목(%s %s)" % (t["n"], FT.FEATS[t["by"]][0], "낮은 순" if t.get("asc", True) else "높은 순"))
    return "[%s] " % FT.MODES[spec["mode"]][0] + " · ".join(ps)


def invert(spec):
    """뒤집기 짝 — 조건마다 반대쪽으로. 국장은 개인 공매도가 사실상 안 돼서 '반대로 판다'가 아니라 '반대 성질 종목을 산다'."""
    cs = []
    for c in spec["conds"]:
        f = c["f"]; v = float(c["v"]); op = ">=" if c["op"] == "<=" else "<="
        if c.get("q") or FT.FEATS[f][2] == "u": v2 = 1 - v
        elif FT.FEATS[f][2] == "s": v2 = -v if v else 0.0
        elif FT.FEATS[f][2] == "r": v2 = (1 / v) if v > 0 else v
        else: v2 = v
        cs.append(dict(c, op=op, v=round(v2, 4)))
    t = spec.get("top")
    out = {"name": "뒤집기: " + spec.get("name", ""), "origin": "invert", "source": spec.get("id", ""), "mode": spec["mode"], "conds": cs}
    if t: out["top"] = dict(t, asc=not t.get("asc", True))
    return out


# ══════════════════════════════════════════════════════════════════════
# 판정
# ══════════════════════════════════════════════════════════════════════
def mask(U, spec):
    m = np.ones(len(U), bool)
    for c in spec["conds"]:
        col = ("q_" + c["f"]) if c.get("q") else c["f"]
        if col not in U.columns: return np.zeros(len(U), bool)
        x = U[col].to_numpy(); v = float(c["v"])
        with np.errstate(invalid="ignore"):
            m &= (x <= v) if c["op"] == "<=" else (x >= v)
    return m


def trades(U, spec):
    tgt = FT.TARGET[spec["mode"]]
    m = mask(U, spec) & U[tgt].notna().to_numpy()
    if spec["mode"] == "on":                                            # 상한가로 마감한 종목은 종가에 못 산다(줄만 서고 안 채워진다 — H0288 교훈)
        lim = np.where(U.date.to_numpy() < "20150615", 14.5, 29.5)
        m &= ~(U.r1t.to_numpy() >= lim)
    T = U.loc[m, ["date", "ticker", tgt] + (["t1"] if "t1" in U.columns else []) + ([spec["top"]["by"]] if spec.get("top") else [])]
    if spec.get("top"):
        t = spec["top"]
        T = T.sort_values(["date", t["by"]], ascending=[True, t.get("asc", True)]).groupby("date").head(int(t["n"]))
    r = T[tgt].astype(float).clip(-60, 60)
    T = T.assign(ret=(r - FT.COST) if spec["mode"] in ("oc", "on") else r)
    if spec["mode"].startswith("sw"):                                   # 보유 중 같은 종목 다시 안 산다
        h = int(spec["mode"][2:]); dates = sorted(U.date.unique()); di = {d: i for i, d in enumerate(dates)}
        T = T.sort_values("date"); keep, last = [], {}
        for tk_, d_, ix in zip(T.ticker.values, T.date.values, T.index):
            i = di[d_]
            if last.get(tk_, -10 ** 9) >= i: continue
            last[tk_] = i + h; keep.append(ix)
        T = T.loc[keep]
    return T


def stats(T):
    if len(T) == 0: return None
    d = T.groupby("date").ret.mean()
    yr = T.groupby(T.date.str[:4]).ret.mean()
    sd = d.std(ddof=1) if len(d) > 1 else np.nan
    return dict(n=int(len(T)), days=int(len(d)), mean=float(T.ret.mean()), med=float(T.ret.median()), win=float((T.ret > 0).mean() * 100),
                dmean=float(d.mean()), t=float(d.mean() / sd * math.sqrt(len(d))) if sd and sd > 0 else 0.0,
                ypos=int((yr > 0).sum()), ny=int(len(yr)), perday=float(len(T) / max(len(d), 1)),
                t1=float(T.t1.mean() * 100) if "t1" in T.columns and len(T) else 0.0)


def seg(T, a, b):
    return T[(T.date >= a) & (T.date <= b)]


def judge(spec, U=None, n_trials=None):
    """G1·G2. 반환 dict(stage=통과한 마지막 단계, why, ref, tr, va, dsr)."""
    from verdict import deflated_sharpe, trial_count
    U = hist() if U is None else U
    T = trades(U, spec)
    tr0 = "20180101" if any(c["f"] in FT.FLOW for c in spec["conds"]) else TR[0]
    R = dict(stage=0, why="", ref=stats(seg(T, *REF)), tr=stats(seg(T, tr0, TR[1])), va=None, dsr=None)
    s = R["tr"]
    why = []
    if not s or s["n"] < 150 or s["days"] < 60: why.append("학습 건수 부족(%s건)" % (s["n"] if s else 0))
    else:
        if s["mean"] <= 0: why.append("학습 건당 %+.2f%%" % s["mean"])
        if s["t"] < 2: why.append("학습 하루 t %.1f" % s["t"])
        if s["ypos"] < 0.6 * s["ny"]: why.append("학습 플러스 해 %d/%d" % (s["ypos"], s["ny"]))
    if why:
        R["why"] = " · ".join(why); return R
    R["stage"] = 1
    v = R["va"] = stats(seg(T, *VA))
    n_tr = n_trials or max(trial_count("factory"), 1)
    mon = seg(T, tr0, VA[1]).groupby("date").ret.mean()
    mon = mon.groupby(mon.index.str[:6]).mean()
    d = deflated_sharpe(mon, n_tr)
    R["dsr"] = d["dsr"] if d else None
    if not v or v["n"] < 40: why.append("검증 건수 부족(%s건)" % (v["n"] if v else 0))
    else:
        if v["mean"] <= 0: why.append("검증 건당 %+.2f%%" % v["mean"])
        if v["t"] < 1: why.append("검증 하루 t %.1f" % v["t"])
        if v["ypos"] * 2 < v["ny"]: why.append("검증 플러스 해 %d/%d" % (v["ypos"], v["ny"]))
    if R["dsr"] is None or R["dsr"] < DSR_MIN: why.append("다중검정 %.2f < %.2f(공장 누적 %d개 기준)" % (R["dsr"] or 0, DSR_MIN, n_tr))
    ov = stats(seg(T, tr0, VA[1]))["t1"]
    if ov >= 50: why.append("T1 과 겹침 %.0f%%" % ov)
    if not why and needs_1519(spec):
        H = R["honest"] = honest_1519(U, spec)
        if not H or H["n"] < 40: why.append("15:19 가격 재검 표본 부족(%s건)" % (H["n"] if H else 0))
        elif H["mean"] <= 0 or H["t"] < 1:
            why.append("종가 단일가 착시 — 15:19 가격으로 고르면 %s건 %+.2f%% · t %.1f" % (f"{H['n']:,}", H["mean"], H["t"]))
    if why:
        R["why"] = " · ".join(why); return R
    R["stage"] = 2
    return R


# ══════════════════════════════════════════════════════════════════════
# 종가 단일가 착시 확인 (2026-10-10) — 'on'(종가 매수) 방식이 '오늘 등락·오늘 시가→종가' 같은 종가 재료로 고르면
# 실제로는 15:20 종가 단일가 **전에** 골라야 하는데 최종 종가(단일가에서 움직인 몫 포함)로 고른 셈이 된다.
# 1분봉이 있는 2022-12~ 는 15:19 까지 봉으로 재료를 다시 만들어 같은 명세를 다시 잰다(가격은 1분봉끼리만 — H0295 함정).
# ══════════════════════════════════════════════════════════════════════
CLOSE_F = {"r1t", "clvt", "vmt", "rngt", "oct"}
_M1 = None


def needs_1519(spec):
    t = spec.get("top") or {}
    return spec["mode"] == "on" and (any(c["f"] in CLOSE_F for c in spec["conds"]) or t.get("by") in CLOSE_F)


def apply_1519(Z):
    """Z: 1분봉 기준 pc_m · o_m · p1519 · hi1519 · lo1519 · v1519 · vol_m 을 가진 줄 → 종가 재료를 15:19 값으로 바꾸고 q_ 다시."""
    Z = Z.copy()
    Z["r1t"] = (Z.p1519 / Z.pc_m - 1) * 100
    Z["oct"] = (Z.p1519 / Z.o_m - 1) * 100
    Z["clvt"] = (Z.p1519 - Z.lo1519) / (Z.hi1519 - Z.lo1519).replace(0, np.nan)
    Z["rngt"] = (Z.hi1519 - Z.lo1519) / Z.p1519 * 100
    Z["vmt"] = Z.vmt * (Z.v1519 / Z.vol_m.replace(0, np.nan))
    for f in CLOSE_F:
        Z["q_" + f] = Z.groupby("date")[f].rank(pct=True).astype("float32")
    return Z


def honest_1519(U, spec):
    global _M1
    if _M1 is None:
        _M1 = pd.read_pickle(C.CACHE / "m1_panel_KR.pkl")[["ticker", "date", "o", "pc", "p1519", "hi1519", "lo1519", "v1519", "vol"]].rename(
            columns={"o": "o_m", "pc": "pc_m", "vol": "vol_m"})
    Z = U[U.date >= VA[0]].merge(_M1, on=["ticker", "date"], how="inner")
    return stats(trades(apply_1519(Z), spec))


# ══════════════════════════════════════════════════════════════════════
# 등록부
# ══════════════════════════════════════════════════════════════════════
def load():
    if not SPECS.exists(): return []
    return [json.loads(l) for l in SPECS.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(L):
    tmp = SPECS.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in L), encoding="utf-8"); tmp.replace(SPECS)


def add(spec, L=None, pair=True):
    """명세를 줄에 세운다(상태 queued). 같은 명세가 이미 있으면 그걸 돌려준다. pair=True 면 뒤집기 짝도 같이 세운다."""
    own = L is None
    L = load() if own else L
    err = check(spec)
    k = key(spec) if not err else None
    for x in L:
        if k and x.get("key") == k: return x
    nid = "F%04d" % (max([int(x["id"][1:]) for x in L] or [0]) + 1)
    rec = dict(spec, id=nid, key=k, created=time.strftime("%Y-%m-%d %H:%M"), status="queued" if not err else "rejected",
               stage=None if not err else 0, why=err or "", desc=desc(spec) if not err else "")
    L.append(rec)
    if pair and not err and spec.get("origin") != "invert":
        inv = invert(rec); inv["source"] = nid
        add(inv, L, pair=False)
    if own: save(L)
    return rec


def process(L=None, limit=200):
    """줄 선 명세(queued)를 판정한다. 실시간 재료(live)를 쓰는 건 과거가 없으니 바로 그림자로."""
    from verdict import log_trials
    own = L is None
    L = load() if own else L
    todo = [x for x in L if x.get("status") == "queued"][:limit]
    if not todo: return []
    U = hist()
    log_trials("factory", len(todo))
    done = []
    for x in todo:
        if uses_live(x):
            x.update(status="shadow", stage=2, why="실시간 재료 — 과거 없음, 그림자로 바로", shadow_from=time.strftime("%Y%m%d"))
            done.append(x); continue
        try:
            R = judge(x, U)
        except Exception as ex:
            x.update(status="error", why=repr(ex)[:200]); done.append(x); continue
        x.update(stage=R["stage"], why=R["why"], res={k: R.get(k) for k in ("ref", "tr", "va", "dsr", "honest")}, judged=time.strftime("%Y-%m-%d %H:%M"))
        if R["stage"] >= 2:
            sib = sibling(x, L, U)
            if sib:
                x.update(status="sibling", why="그림자 %s 와 거래 %.0f%% 겹침 — 같은 규칙으로 보고 따로 안 봄" % sib)
            else:
                x.update(status="shadow", shadow_from=time.strftime("%Y%m%d"))
        else:
            x["status"] = "rejected"
        done.append(x)
    if own: save(L)
    return done


_TK = {}


def _tset(spec, U):
    k = spec.get("key") or key(spec)
    if k not in _TK:
        T = seg(trades(U, spec), *VA)
        _TK[k] = set(zip(T.date, T.ticker))
    return _TK[k]


def sibling(x, L, U, cut=0.6):
    """이미 그림자에 있는 명세와 검증 구간 거래가 cut 이상 겹치면 (그 id, 겹침%) — 같은 규칙을 여러 번 세지 않게(2026-10-10)."""
    A = _tset(x, U)
    if not A: return None
    best = None
    for y in L:
        if y is x or y.get("status") not in ("shadow", "propose") or uses_live(y): continue
        B = _tset(y, U)
        ov = len(A & B) / max(min(len(A), len(B)), 1)
        if ov >= cut and (best is None or ov > best[1] / 100):
            best = (y["id"], ov * 100)
    return best


STAGE = {None: "-", 0: "학습 탈락", 1: "검증 탈락", 2: "그림자로"}


def fmt_s(s):
    if not s: return "-"
    return "%s건 %+.2f%% · 승률 %.0f%% · t %.1f · %d/%d해" % (f"{s['n']:,}", s["mean"], s["win"], s["t"], s["ypos"], s["ny"])
