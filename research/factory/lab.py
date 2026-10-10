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
VER = "f6"                      # 재료 정의 바꾸면 올린다 → 과거 자료 다시 만든다(f2 2026-10-10: 재료 17개·스윙 10/40/60일 추가)
TR = ("20160101", "20221231"); VA = ("20230101", "20991231"); REF = ("20100101", "20151231")
DSR_MIN = 0.90
#  2026-10-11 사용자 "F0161 정도는 많이 나오잖아, 규칙으로 쓸 수 없잖아" — 검증 건당 이 값 미만이거나 중앙값이 0 이하면 검토로 안 올린다
#  (종가 매수→다음날 시가 0.15~0.27%·중앙 마이너스 류가 검토 5건을 다 채웠음)
VA_MIN = 0.5
_U = None


# ══════════════════════════════════════════════════════════════════════
# 과거 자료
# ══════════════════════════════════════════════════════════════════════
def load_flows(since="20170101"):
    c = sqlite3.connect("file:" + str(C.BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    return pd.read_sql("SELECT ticker, date, indiv, frgn, (COALESCE(fin,0)+COALESCE(ins,0)+COALESCE(tru,0)+COALESCE(pef,0)+COALESCE(bank,0)+COALESCE(ofin,0)+COALESCE(pens,0)) AS inst "
                       "FROM flow11 WHERE date >= ?", c, params=(since,))


def load_kospi(back=6600):
    """코스피 일별 종가(네이버) — data/factory/kospi.json 에 두고 하루 한 번 새로(국면 재료 kdev 용)."""
    f = C.DATA / "kospi.json"
    if f.exists() and time.time() - f.stat().st_mtime < 20 * 3600:
        return C.jload(f, {})
    try:
        import index_cal as IC
        k = IC.naver_closes("KOSPI", back)
        if len(k) > 200: C.jsave(f, k)
        return k
    except Exception as ex:
        C.log("코스피 지수 못 받음:", repr(ex)[:150]); return C.jload(f, {})


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
    A = A[A.date >= "20090101"][["ticker", "date", "open", "high", "low", "close", "volume", "pref", "marcap", "n5", "n10", "n20", "n40", "n60"]].copy()
    A[["ticker", "date", "open", "high", "low", "close"]].to_pickle(PXF)      # 손절·익절 청산 계산용 가격 길(2026-10-10)
    X = FT.make(A, load_flows(), load_themes(), kospi=load_kospi())
    del A
    U = X[X.uni & (X.date >= REF[0])].drop(columns=["uni"]).reset_index(drop=True)
    del X
    try:
        import transfer as TF
        TF.attach_hist(U)
    except Exception as ex:
        C.log("전이표 재료 못 붙임(미장 자료 없음?):", repr(ex)[:200])
    try:                                                                # 장중 방식(m10c·m14c) — 1분봉 단면 2022-12~ 상위 1,000
        Mp = pd.read_pickle(C.CACHE / "m1_panel_KR.pkl")[["ticker", "date", "o", "c", "p1000", "vw1000", "v1000", "p1400", "vw1400", "hi1400", "lo1400", "v1400", "amt20"]]
        FT.intra(U, Mp.rename(columns={"o": "o_m", "c": "c_m", "amt20": "amt20_m"}))
    except Exception as ex:
        C.log("장중 재료 못 붙임:", repr(ex)[:200])
    U = FT.shrink(FT.qcols(U, FT.HIST))
    U["t1"] = ((U.q_gap <= 0.10) & (U.q_vm <= 0.30) & (U.liq <= 1 / 3) & (U.rgap <= -2.0)).astype(bool)   # T1 근사(겹침 확인용)
    U.to_pickle(HIST); meta.write_text(key)
    C.log("과거 자료 끝 — %s줄 · %.1f분" % (f"{len(U):,}", (time.time() - t0) / 60))


HIST_US = C.CACHE / "factory_us.pkl"
_UU = None
US_COST = 0.25                  # 미장 데이 왕복(수수료 0.1%×2 + SEC·미끄러짐) — oc_day 와 같게


def build_hist_us(force=False):
    """미장 과거 자료(2026-10-10 사용자: "국장 후보도 미장에, 미장 후보도 국장에") — 폐지 포함 us_scan_full 2011~.
    유니버스 = 그날 패널 거래대금(20일) 상위 20% · $3↑ (하루 약 1,100종목). 국장 전용 재료(수급·테마·전이표·코스피 국면·장중)는 빈칸.
    패널이 커서(2,500만 줄) 종목 묶음으로 재료를 만들고, 유니버스 줄만 남긴 뒤 날짜별 단면 재료를 계산한다."""
    import run_spec as RS
    src = C.BASE / "data" / "us_scan_full.pkl"
    key = "%s_us_%d" % (VER, src.stat().st_mtime)
    meta = C.CACHE / "factory_us.meta"
    if not force and HIST_US.exists() and meta.exists() and meta.read_text() == key:
        return
    t0 = time.time(); C.log("미장 과거 자료 만들기 시작")
    A, _, _ = RS.load_market("US")
    A = A[A.date >= "20110101"][["ticker", "date", "open", "high", "low", "close", "volume", "amt20", "pref", "marcap", "n5", "n10", "n20", "n40", "n60"]].copy()
    A["pre"] = A.groupby("date").amt20.rank(pct=True) >= 0.80               # 패널 거래대금으로 미리 고른 유니버스(줄 수 줄이기)
    A = A.rename(columns={"amt20": "amt20_p"})
    tks = A.ticker.unique(); parts = []
    feats = [f for f in FT.HIST if f not in FT.KR_ONLY and f not in FT.INTRA]
    for i in range(0, len(tks), 1500):
        D = A[A.ticker.isin(set(tks[i:i + 1500]))]
        X = FT.make(D.drop(columns=["pre", "amt20_p"]), mk="US", uni_pct=None, seam=False)
        keep = (X.uni & D.sort_values(["ticker", "date"]).pre.to_numpy() & (X.date >= REF[0])).to_numpy()
        parts.append(FT.shrink(X[keep].copy()))
        C.log("  미장 묶음 %d/%d · %.1f분" % (i // 1500 + 1, (len(tks) + 1499) // 1500, (time.time() - t0) / 60))
    del A
    U = pd.concat(parts, ignore_index=True); del parts
    U["uni"] = True
    FT.cross(U, U.date)
    U = U.drop(columns=["uni"])
    U = FT.shrink(FT.qcols(U, [f for f in feats if f in U.columns]))
    U.to_pickle(HIST_US); meta.write_text(key)
    C.log("미장 과거 자료 끝 — %s줄 · %.1f분" % (f"{len(U):,}", (time.time() - t0) / 60))


def hist_us():
    global _UU
    if _UU is None:
        build_hist_us()
        _UU = pd.read_pickle(HIST_US)
    return _UU


def us_ok(spec):
    """미장에서 판정할 수 있는 명세인가 — 국장 전용 재료·장중 방식이면 아니다."""
    fs = {c["f"] for c in spec["conds"]} | ({spec["top"]["by"]} if spec.get("top") else set())
    return not (fs & (FT.KR_ONLY | FT.INTRA)) and not spec["mode"].startswith("m") and not uses_live(spec) and not spec.get("exit")


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
    ex = spec.get("exit") or {}
    return json.dumps([spec["mode"], cs, top.get("n"), top.get("by"), top.get("asc")] + ([ex.get("stop"), ex.get("take")] + ([ex.get("trail"), ex.get("half")] if ex.get("trail") is not None or ex.get("half") is not None else []) if ex else []), ensure_ascii=False)


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
    ex = spec.get("exit")
    if ex:
        if not mode.startswith("sw"): return "손절·익절(exit)은 스윙(sw*) 방식에만"
        try:
            st, tk, tr, hf = ex.get("stop"), ex.get("take"), ex.get("trail"), ex.get("half")
            if st is not None and not -50 <= float(st) < 0: return "손절은 -50~0 사이 음수(%)"
            if tr is not None and not -50 <= float(tr) < 0: return "추적 손절은 -50~0 사이 음수(%)"
            if tk is not None and not 0 < float(tk) <= 200: return "익절은 0~200 사이 양수(%)"
            if hf is not None and not 0 < float(hf) <= 200: return "분할 익절은 0~200 사이 양수(%)"
            if st is None and tk is None and tr is None and hf is None: return "exit 에 stop·take·trail·half 중 하나는 있어야"
        except Exception: return "exit 형식 오류"
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
    ex = spec.get("exit") or {}
    if ex.get("stop") is not None: ps.append("손절 %g%%" % float(ex["stop"]))
    if ex.get("take") is not None: ps.append("익절 +%g%%" % float(ex["take"]))
    if ex.get("trail") is not None: ps.append("고점 대비 %g%% 추적 손절" % float(ex["trail"]))
    if ex.get("half") is not None: ps.append("+%g%%에 절반 익절" % float(ex["half"]))
    return "[%s] " % FT.MODES[spec["mode"]][0] + " · ".join(ps)


def invert(spec):
    """뒤집기 짝 — 조건마다 반대쪽으로. 국장은 개인 공매도가 사실상 안 돼서 '반대로 판다'가 아니라 '반대 성질 종목을 산다'."""
    cs = []
    for c in spec["conds"]:
        f = c["f"]; v = float(c["v"]); op = ">=" if c["op"] == "<=" else "<="
        if c.get("q") or FT.FEATS[f][2] == "u": v2 = 1 - v
        elif FT.FEATS[f][2] == "h": v2 = 100 - v                        # 0~100(RSI)
        elif FT.FEATS[f][2] == "s": v2 = -v if v else 0.0
        elif FT.FEATS[f][2] == "r": v2 = (1 / v) if v > 0 else v
        else: v2 = v
        cs.append(dict(c, op=op, v=round(v2, 4)))
    t = spec.get("top")
    out = {"name": "뒤집기: " + spec.get("name", ""), "origin": "invert", "source": spec.get("id", ""), "mode": spec["mode"], "conds": cs}
    if t: out["top"] = dict(t, asc=not t.get("asc", True))
    if spec.get("exit"): out["exit"] = dict(spec["exit"])
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


PXF = C.CACHE / "factory_px.pkl"
_PXD = {}
EXIT_COST = 0.6                    # 손절·익절 청산은 패널 비용 대신 0.6%(패널 하단 · 매일 자료 스윙과 같게)


def px_dict(P=None, key="hist"):
    """종목 → (날짜, 시, 고, 저, 종) 배열. P 없으면 과거 가격 길(factory_px.pkl)."""
    if key not in _PXD:
        P = pd.read_pickle(PXF) if P is None else P
        P = P.sort_values(["ticker", "date"])
        _PXD[key] = {t: (g.date.to_numpy(), g.open.to_numpy(float), g.high.to_numpy(float), g.low.to_numpy(float), g.close.to_numpy(float))
                     for t, g in P.groupby("ticker", sort=False)}
    return _PXD[key]


def _walk(ent, O, H, L, Cc, stop, take, trail):
    """한 묶음(보유분) 청산가 — 손절(stop%)·익절(take%)·추적 손절(trail%: 그 전날까지 고가 대비) 중 먼저 닿는 날.
    같은 날 손절류와 익절이 둘 다면 손절(보수적). 다음날 시가가 이미 넘어가 있으면 시가. 끝까지 안 닿으면 마지막 날 종가."""
    peak = ent
    for k in range(len(O)):
        lvl = -np.inf
        if stop is not None: lvl = ent * (1 + stop / 100)
        if trail is not None: lvl = max(lvl, peak * (1 + trail / 100))
        tp = ent * (1 + take / 100) if take is not None else np.inf
        if L[k] <= lvl: return lvl if k == 0 else min(O[k], lvl)
        if H[k] >= tp: return tp if k == 0 else max(O[k], tp)
        peak = max(peak, H[k])
    return Cc[-1]


def exit_returns(T, h, stop, take, PXD, trail=None, half=None):
    """시가 매수 → h 거래일 안 청산. half(%) 가 있으면 그 수익에 절반을 먼저 팔고(분할 익절) 나머지는 손절·추적·익절·보유일 끝으로.
    미래가 h 일 안 되면 NaN. (2026-10-10 분할 익절·추적 손절 추가 — 못 옮긴 조건 '손절·익절·분할 매매')"""
    out = np.full(len(T), np.nan)
    dts = T.date.to_numpy(); tks = T.ticker.to_numpy()
    for j in range(len(T)):
        z = PXD.get(tks[j])
        if z is None: continue
        d, o, hi, lo, c = z
        p = np.searchsorted(d, dts[j])
        if p >= len(d) or d[p] != dts[j] or p + h > len(d): continue
        ent = o[p]
        if not ent > 0: continue
        O, H, L, Cc = o[p:p + h], hi[p:p + h], lo[p:p + h], c[p:p + h]
        rest = _walk(ent, O, H, L, Cc, stop, take, trail)
        if half is not None:
            hp = ent * (1 + half / 100)
            first = _walk(ent, O, H, L, Cc, stop, half, trail)        # 절반: half% 익절이 먼저냐, 손절류가 먼저냐
            px = (first + rest) / 2 if first >= hp * 0.999 else rest    # 절반 익절 전에 손절류면 전부 같이 나간 것
        else:
            px = rest
        out[j] = (px / ent - 1) * 100 - EXIT_COST
    return out


def trades(U, spec, PXD=None, mk="KR"):
    tgt = FT.TARGET[spec["mode"]]
    ex = spec.get("exit")
    m = mask(U, spec) & (U[tgt].notna().to_numpy() if not ex else np.ones(len(U), bool))
    if spec["mode"] == "on":                                            # 상한가로 마감한 종목은 종가에 못 산다(줄만 서고 안 채워진다 — H0288 교훈)
        lim = np.where(U.date.to_numpy() < "20150615", 14.5, 29.5)
        m &= ~(U.r1t.to_numpy() >= lim)
    T = U.loc[m, ["date", "ticker", tgt] + (["t1"] if "t1" in U.columns else []) + ([spec["top"]["by"]] if spec.get("top") else [])]
    if spec.get("top"):
        t = spec["top"]
        T = T.sort_values(["date", t["by"]], ascending=[True, t.get("asc", True)]).groupby("date").head(int(t["n"]))
    r = T[tgt].astype(float).clip(-60, 60)
    cost = US_COST if mk == "US" else FT.COST
    T = T.assign(ret=(r - cost) if spec["mode"] in ("oc", "on") else (r - cost - FT.INTRA_SLIP) if spec["mode"].startswith("m") else r)
    if spec["mode"].startswith("sw"):                                   # 보유 중 같은 종목 다시 안 산다
        h = int(spec["mode"][2:]); dates = sorted(U.date.unique()); di = {d: i for i, d in enumerate(dates)}
        T = T.sort_values("date"); keep, last = [], {}
        for tk_, d_, ix in zip(T.ticker.values, T.date.values, T.index):
            i = di[d_]
            if last.get(tk_, -10 ** 9) >= i: continue
            last[tk_] = i + h; keep.append(ix)
        T = T.loc[keep]
        if ex:                                                          # 손절·익절 청산(2026-10-10 — 못 옮긴 조건 1위)
            fl = lambda k: None if ex.get(k) is None else float(ex[k])
            r2 = exit_returns(T, h, fl("stop"), fl("take"), PXD if PXD is not None else px_dict(), trail=fl("trail"), half=fl("half"))
            T = T.assign(ret=np.clip(r2, -60, 200))
            T = T[T.ret.notna()]
    return T


def stats(T):
    if len(T) == 0: return None
    d = T.groupby("date").ret.mean()
    yr = T.groupby(T.date.str[:4]).ret.mean()
    sd = d.std(ddof=1) if len(d) > 1 else np.nan
    return dict(n=int(len(T)), days=int(len(d)), mean=float(T.ret.mean()), med=float(T.ret.median()), win=float((T.ret > 0).mean() * 100),
                dmean=float(d.mean()), t=float(d.mean() / sd * math.sqrt(len(d))) if sd and sd > 0 else 0.0,
                ypos=int((yr > 0).sum()), ny=int(len(yr)), perday=float(len(T) / max(len(d), 1)),
                t1=float(T.t1.mean() * 100) if "t1" in T.columns and len(T) else 0.0,
                ex=float(T.ex.mean()) if "ex" in T.columns else None,
                pf=float(T.ret[T.ret > 0].sum() / max(-T.ret[T.ret < 0].sum(), 1e-9)) if (T.ret < 0).any() else None)


def periods(spec):
    """(참고, 학습, 검증) — 장중 방식(m*)은 1분봉이 2022-12~ 라 학습 2022-12~24 · 검증 2025~ · 참고 없음."""
    if spec["mode"].startswith("m"):
        return None, ("20221201", "20241231"), ("20250101", "20991231")
    return REF, TR, VA


def seg(T, a, b):
    return T[(T.date >= a) & (T.date <= b)]


def judge(spec, U=None, n_trials=None, mk="KR"):
    """G1·G2. 반환 dict(stage=통과한 마지막 단계, why, ref, tr, va, dsr)."""
    from verdict import deflated_sharpe, trial_count
    U = (hist() if mk == "KR" else hist_us()) if U is None else U
    T = trades(U, spec, mk=mk)
    sw = spec["mode"].startswith("sw")
    if sw:                                                              # 스윙: 같은 날 아무 종목을 같은 기간 들고 간 것보다 나은가(드리프트 착시 방지)
        tg = FT.TARGET[spec["mode"]]
        T = T.assign(ex=T.ret - T.date.map(U.groupby("date")[tg].mean()))
    REF_, TR_, VA_ = periods(spec)
    tr0 = max("20180101", TR_[0]) if any(c["f"] in FT.FLOW for c in spec["conds"]) else TR_[0]
    R = dict(stage=0, why="", ref=stats(seg(T, *REF_)) if REF_ else None, tr=stats(seg(T, tr0, TR_[1])), va=None, dsr=None)
    s = R["tr"]
    why = []
    if not s or s["n"] < 150 or s["days"] < 60: why.append("학습 건수 부족(%s건)" % (s["n"] if s else 0))
    else:
        if s["mean"] <= 0: why.append("학습 건당 %+.2f%%" % s["mean"])
        if s["t"] < 2: why.append("학습 하루 t %.1f" % s["t"])
        if s["ypos"] < 0.6 * s["ny"]: why.append("학습 플러스 해 %d/%d" % (s["ypos"], s["ny"]))
        if sw and not (s["ex"] or 0) > 0: why.append("학습: 같은 날 아무 종목보다 %+.2f%%p(못 이김)" % (s["ex"] or 0))
    if why:
        R["why"] = " · ".join(why); return R
    R["stage"] = 1
    v = R["va"] = stats(seg(T, *VA_))
    n_tr = n_trials or max(trial_count("factory"), 1)
    mon = seg(T, tr0, VA_[1]).groupby("date").ret.mean()
    mon = mon.groupby(mon.index.str[:6]).mean()
    d = deflated_sharpe(mon, n_tr)
    R["dsr"] = d["dsr"] if d else None
    if not v or v["n"] < 40: why.append("검증 건수 부족(%s건)" % (v["n"] if v else 0))
    else:
        if v["mean"] <= 0: why.append("검증 건당 %+.2f%%" % v["mean"])
        if v["t"] < 1: why.append("검증 하루 t %.1f" % v["t"])
        if v["ypos"] * 2 < v["ny"]: why.append("검증 플러스 해 %d/%d" % (v["ypos"], v["ny"]))
        if sw and not (v["ex"] or 0) > 0: why.append("검증: 같은 날 아무 종목보다 %+.2f%%p(못 이김)" % (v["ex"] or 0))
        if 0 < v["mean"] < VA_MIN: why.append("검증 건당 %+.2f%% — 얇음(%.1f%% 미만)" % (v["mean"], VA_MIN))
        if (v.get("med") or 0) <= 0: why.append("검증 중앙 %+.2f%% — 절반 넘게 손해" % (v.get("med") or 0))
    if R["dsr"] is None or R["dsr"] < DSR_MIN: why.append("다중검정 %.2f < %.2f(공장 누적 %d개 기준)" % (R["dsr"] or 0, DSR_MIN, n_tr))
    ov = stats(seg(T, tr0, VA_[1]))["t1"]
    if ov >= 50: why.append("T1 과 겹침 %.0f%%" % ov)
    if not why and needs_1519(spec) and mk == "US":
        why.append("미장 종가 매수는 장 막판 재검 자료가 없어 보류")
    if not why and needs_1519(spec) and mk == "KR":
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
CLOSE_F = {"r1t", "clvt", "vmt", "rngt", "oct", "uwt", "hi20t"}
_M1 = None


def needs_1519(spec):
    t = spec.get("top") or {}
    return spec["mode"] == "on" and (any(c["f"] in CLOSE_F for c in spec["conds"]) or t.get("by") in CLOSE_F)


def apply_1519(Z):
    """Z: 1분봉 기준 pc_m · o_m · p1519 · hi1519 · lo1519 · v1519 · vol_m 을 가진 줄 → 종가 재료를 15:19 값으로 바꾸고 q_ 다시."""
    Z = Z.copy()
    cfin = Z.pc_m * (1 + Z.r1t / 100)                                   # 최종 종가(바꾸기 전 r1t 로)
    if "hi20t" in Z.columns:                                            # 20일 고가는 그대로 두고 가격만 15:19 로
        Z["hi20t"] = ((1 + Z.hi20t / 100) * Z.p1519 / cfin - 1) * 100
    Z["r1t"] = (Z.p1519 / Z.pc_m - 1) * 100
    Z["oct"] = (Z.p1519 / Z.o_m - 1) * 100
    Z["clvt"] = (Z.p1519 - Z.lo1519) / (Z.hi1519 - Z.lo1519).replace(0, np.nan)
    Z["rngt"] = (Z.hi1519 - Z.lo1519) / Z.p1519 * 100
    Z["vmt"] = Z.vmt * (Z.v1519 / Z.vol_m.replace(0, np.nan))
    Z["uwt"] = (Z.hi1519 - np.maximum(Z.o_m, Z.p1519)) / (Z.hi1519 - Z.lo1519).replace(0, np.nan)
    for f in CLOSE_F:
        Z["q_" + f] = Z.groupby("date")[f].rank(pct=True).astype("float32")
    return Z


def _m1():
    global _M1
    if _M1 is None:
        _M1 = pd.read_pickle(C.CACHE / "m1_panel_KR.pkl")[["ticker", "date", "o", "pc", "p1519", "hi1519", "lo1519", "v1519", "vol"]].rename(
            columns={"o": "o_m", "pc": "pc_m", "vol": "vol_m"})
    return _M1


def honest_1519(U, spec):
    Z = U[U.date >= VA[0]].merge(_m1(), on=["ticker", "date"], how="inner")
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
        if us_ok(x):                                                    # 2026-10-10: 같은 명세를 미장에서도
            try:
                R2 = judge(x, hist_us(), mk="US")
                x.update(stage_us=R2["stage"], why_us=R2["why"], res_us={k: R2.get(k) for k in ("ref", "tr", "va", "dsr")})
            except Exception as ex:
                x.update(stage_us=None, why_us="미장 판정 오류 " + repr(ex)[:100])
        else:
            x.update(stage_us=None, why_us="미장 해당 없음(국장 전용 재료·방식)")
        x["pass_mk"] = [m for m, st in (("KR", R["stage"]), ("US", x.get("stage_us"))) if st is not None and st >= 2]
        if R["stage"] < 2 and "US" in x["pass_mk"]:
            x.update(status="review", shadow_from=time.strftime("%Y%m%d"))   # 미장에서만 통과 — 미장 후보로
            done.append(x); continue
        if R["stage"] >= 2:
            sib = sibling(x, L, U)
            if sib:
                x.update(status="sibling", why="검토 %s 와 거래 %.0f%% 겹침 — 같은 규칙으로 보고 따로 안 봄" % sib)
            else:                                                       # 2026-10-10 사용자: 그림자 말고 바로 알려서 조정·채택
                x.update(status="review", shadow_from=time.strftime("%Y%m%d"))
        else:
            x["status"] = "rejected"
        done.append(x)
    if own: save(L)
    return done


_TK = {}


def _tset(spec, U):
    k = spec.get("key") or key(spec)
    if k not in _TK:
        T = seg(trades(U, spec), *periods(spec)[2])
        _TK[k] = set(zip(T.date, T.ticker))
    return _TK[k]


def sibling(x, L, U, cut=0.6):
    """이미 그림자에 있는 명세와 검증 구간 거래가 cut 이상 겹치면 (그 id, 겹침%) — 같은 규칙을 여러 번 세지 않게(2026-10-10)."""
    A = _tset(x, U)
    if not A: return None
    best = None
    for y in L:
        if y is x or y.get("status") not in ("shadow", "propose", "review", "adopted") or uses_live(y): continue
        if x.get("origin") == "tighten" and y["id"] == x.get("source"): continue     # 조인 판은 원안의 부분집합이 당연 — 따로 본다
        B = _tset(y, U)
        ov = len(A & B) / max(min(len(A), len(B)), 1)
        if ov >= cut and (best is None or ov > best[1] / 100):
            best = (y["id"], ov * 100)
    return best


STAGE = {None: "-", 0: "학습 탈락", 1: "검증 탈락", 2: "그림자로"}


def fmt_s(s):
    if not s: return "-"
    return "%s건 %+.2f%% · 승률 %.0f%%%s · t %.1f · %d/%d해" % (f"{s['n']:,}", s["mean"], s["win"], (" · PF %.2f" % s["pf"]) if s.get("pf") else "", s["t"], s["ypos"], s["ny"])
