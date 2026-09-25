# -*- coding: utf-8 -*-
"""**명세 실행기** — 가설을 코드가 아니라 JSON 명세로 적으면 0~5단계를 같은 잣대로 돌리고 등록부에 적는다 (2026-09-19).

왜: 아이디어 하나에 스크립트 하나를 새로 짜면 (1) 잣대가 스크립트마다 조금씩 달라지고 (2) 돌린 칸 수가
빠지고(실제로 180칸이 trials.json 에 안 들어갔다) (3) 통과할 때까지 조건을 만지게 된다. 여기서는
**명세를 돌리기 전에 고정**하고, 기계가 판정하고, 칸 수를 저절로 센다.

명세 (research/specs/H0080.json)
  {
    "id": "H0080",                       # 등록부 번호 — registry.add 로 먼저 등록(상태 시험중)
    "market": "KR" | "US",
    "derive": {"dn": "close < lag(close, 1)", "dn_n": "streak(dn)", "r5": "(close / lag(close, 5) - 1) * 100"},
    "cond": "(dn_n >= 5) & (r5 <= -5) & (r5 >= -15)",
    "holds": [5, 10, 20],                # 패널에 있는 n5 n10 n20 n40 n60 중에서
    "main_hold": 20,                     # 이웃·지연 검정에 쓸 보유기간
    "variants": [{"label": "낙폭 -3~-15", "cond": "..."}, ...],   # 이웃 칸 — 미리 적은 것만(2~8개)
    "differs_from": "H0068 과 다른 점: ...",  # 0단계에서 비슷한 기각 기록이 걸릴 때 필수
    "features": ["sv_rto5", "q_pens20"]        # 보유 재료 붙이기 — 목록은 research/features.py DESC
  }
  derive 에서 쓸 수 있는 함수(전부 종목별): lag(x,k≥1) · rmean/rmax/rmin/rsum/rstd(x,n) · ema/rma(x,n) · streak(불리언) · np
                                   · xrank(x) — 그날 종목 간 백분위(유일한 단면 함수)
  ⚠ 미래 열(n5·n10·n20·n40·n60·buy)은 derive·cond 어디에도 못 쓴다 — 0단계에서 바로 탈락.

단계 (앞 단계에서 떨어지면 거기서 멈춘다 — 나쁜 아이디어를 싸게 떨어뜨리는 게 목적)
  0 등록부 대조   원리가 같은 기각 기록이 있는데 differs_from 이 없으면 탈락 · 미래 열 사용 탈락
  1 지연 검정     조건을 하루 늦춰도 성적이 유지되나 — **경고만**(반전 신호는 원래 하루에 식는다)
  2 학습 판정     학습(2016~22) 중앙 > 0 · 절삭 > 0 · 학습 CI > 0 · 연도 양수 60%↑
  3 이웃 칸       미리 적은 변형 중 절반 이상이 2단계를 통과
  4 검증·다중검정 검증(2023~) 중앙 > 0 · 최근 두 해 중앙 ≥ 0 · 진짜일 확률 ≥ 0.90(DSR_MIN) ·
                  보유 40일↑ 칸은 같은 날 아무거나 산 중앙보다 높아야 함([[consec-5day]] 드리프트 착시)
  5 겹침          기존 규칙과 ±5일 겹침 50%↑ 이면 새 정보 아님
  통과 → 상태 '후보'. 채택·비중·자리는 **사람**이 정한다. 이 실행기는 사이트·portfolio.py·배포를 안 건드린다.

판정은 자금 무제한·다 산다([[rule-test-unconstrained]]), 유니버스 대비 초과는 안 본다.
보고서에는 함정 점검표(고유 종목 수 · 연도 쏠림 · 폐지 종목 채움률)를 반드시 붙인다.

    python research/run_spec.py research/specs/H0080.json
    python research/run_spec.py research/specs/H0080.json --dry   # 등록부·trials 에 안 적는다(실행기 점검용)
"""
import hashlib, io, json, pickle, re, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import registry
from verdict import deflated_sharpe, log_trials, boot_ci

CACHE = ROOT / "cache"; RUNS = ROOT / "runs"; REPORTS = ROOT / "reports"
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
# ⚠ gap 도 미래 열이다 — 두 패널 모두 (다음날 시가 ÷ 오늘 종가 - 1) 로 정의돼 있다(build_panel·us_panel).
#   2026-09-25 외국 기법 옮기다 발견(그 전 명세는 gap 을 안 썼다). 오늘 갭은 gap0 을 쓴다(load_market 에서 만든다).
FUTURE = re.compile(r"\b(n\d+|buy|gap)\b")
# 다중검정 문턱 — 0.95 에서 0.90 으로 풀었다(2026-09-19, 사용자 결정). 0.95 로는 현행 [깊은 이격] 조건도
# 0.933 으로 떨어졌다. 폭락 때만 몰려 사는 규칙은 월수익 꼬리가 두꺼워 깎이는 구조라, 우리 집안이 돈을 버는
# 형태(낙폭반전)가 새로 못 들어온다. 푼 만큼은 5단계 겹침과 그림자 기간(미래 날짜)이 받친다.
DSR_MIN = 0.90
OUT = []
_KEEP = []   # portfolio.py 가 만든 stdout 래퍼 — 버려지면 GC 가 버퍼를 닫아 이후 print 가 죽는다


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


# ══════════════════════════════════════════════════════════════════════
# 패널
# ══════════════════════════════════════════════════════════════════════
def load_market(mk):
    if mk == "KR":
        A = pd.read_pickle(BASE / "data/kr_scan.pkl")
        A = A[((A.close >= 1000) & (~A.pref.fillna(False))).fillna(False)]
        since = "20050101"
    else:
        A = pd.read_pickle(BASE / "data/us_scan.pkl")
        A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
        since = TR0
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    # 오늘의 시가·고가·저가·갭 — 미래 없이 (2026-09-25, 외국 셋업이 다 쓴다)
    g = A.groupby("ticker", sort=False)
    pc = g.close.shift(1)
    if "open" not in A.columns:                       # 미장 패널: 시가는 '어제의 다음날 시가' 로, 고저는 폭·종가위치로 되살린다
        A["open"] = pc * (1 + g.gap.shift(1) / 100)
        R = A.rng * A.close / 100
        A["low"] = A.close - (A.clv + 1) / 2 * R     # 미장 clv 는 -1~1
        A["high"] = A["low"] + R
    A["gap0"] = (A.open / pc - 1) * 100
    uni = (A.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
    return A, uni, since


def old_signals(mk):
    """기존 규칙 신호(겹침용). 국내는 portfolio.py 를 돌려야 해서 느리다 — 캐시한다."""
    CACHE.mkdir(exist_ok=True)
    if mk == "US":
        with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
            return pickle.load(f)["S"][["date", "ticker"]]
    src = BASE / "portfolio.py"
    key = "%d_%d" % (src.stat().st_mtime, (BASE / "data/kr_scan.pkl").stat().st_mtime)
    cp = CACHE / ("old_kr_%s.pkl" % key)
    if cp.exists():
        return pd.read_pickle(cp)
    log("기존 규칙 신호 계산(portfolio.py) — 처음 한 번만")
    SRC = src.read_text(encoding="utf-8")
    HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
    MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
    real_out, real_err = sys.stdout, sys.stderr
    ns = {"__file__": str(src)}
    try:
        exec(compile(HEAD, "portfolio.py", "exec"), ns)
        exec(compile(MID, "portfolio.py", "exec"), ns)
    finally:
        _KEEP.append((sys.stdout, sys.stderr))
        sys.stdout, sys.stderr = real_out, real_err
    S = ns["S"][["date", "ticker"]].copy()
    for old in CACHE.glob("old_kr_*.pkl"):
        old.unlink()
    S.to_pickle(cp)
    return S


# ══════════════════════════════════════════════════════════════════════
# 조건식
# ══════════════════════════════════════════════════════════════════════
class Cols(dict):
    def __init__(self, A):
        super().__init__(); self.A = A

    def __missing__(self, k):
        if k in self.A.columns:
            return self.A[k]
        raise KeyError(k)                    # KeyError 여야 eval 이 전역(함수)으로 넘어간다


def helpers(A):
    tk = A.ticker

    def lag(x, k=1):
        if k < 1:
            raise ValueError("lag 는 1 이상만 — 음수·0 은 미래를 본다")
        if x.dtype == bool:                          # 불리언은 밀어도 불리언 — 빈칸은 거짓(2026-09-25)
            return x.groupby(tk, sort=False).shift(k).fillna(False).astype(bool)
        return x.groupby(tk, sort=False).shift(k)

    def _roll(x, n, f):
        if x.dtype == bool:
            x = x.astype(float)
        return getattr(x.groupby(tk, sort=False).rolling(n, min_periods=n), f)().reset_index(level=0, drop=True)

    def streak(b):
        b = b.fillna(False).astype(bool)
        return b.astype(int).groupby([tk, (~b).groupby(tk).cumsum()]).cumsum()

    def _ewm(x, **kw):
        return x.groupby(tk, sort=False).transform(lambda s: s.ewm(adjust=False, **kw).mean())

    # 2026-09-25 추가 — 외국 기법(엘더·에일러스·볼린저·단면 순위)을 옮기려고. 전부 과거만 본다.
    #   ema(x,n): 지수이동평균(span=n) · rma(x,n): 와일더 평활(alpha=1/n, RSI·ATR 용) · rstd(x,n): 이동 표준편차
    #   xrank(x): 그날 전 종목 중 백분위(0~1) — 패널 전체(가격 필터 뒤) 기준이다
    return {"lag": lag, "streak": streak, "np": np,
            "rmean": lambda x, n: _roll(x, n, "mean"), "rmax": lambda x, n: _roll(x, n, "max"),
            "rmin": lambda x, n: _roll(x, n, "min"), "rsum": lambda x, n: _roll(x, n, "sum"),
            "rstd": lambda x, n: _roll(x, n, "std"),
            "ema": lambda x, n: _ewm(x, span=n), "rma": lambda x, n: _ewm(x, alpha=1.0 / n),
            "xrank": lambda x: x.groupby(A.date, sort=False).rank(pct=True)}


def evaluate(A, spec):
    env = Cols(A); g = {"__builtins__": {}, **helpers(A)}
    for name, expr in spec.get("derive", {}).items():
        if name in A.columns:
            raise ValueError("derive '%s' 가 패널 열을 덮어쓴다 — 다른 이름을 쓸 것" % name)
        A[name] = eval(expr, g, env)
    conds = {"원안": eval(spec["cond"], g, env)}
    for v in spec.get("variants", []):
        conds[v["label"]] = eval(v["cond"], g, env)
    return {k: pd.Series(v, index=A.index).fillna(False).astype(bool) for k, v in conds.items()}


# ══════════════════════════════════════════════════════════════════════
# 한 칸 판정 — vp_lib.Runner 와 같은 규율(익일 시가·비용·중복 제거)
# ══════════════════════════════════════════════════════════════════════
class Judge:
    def __init__(self, A, uni, since):
        self.A, self.uni, self.since = A, uni, since
        dates = sorted(A.date.unique())
        self.di = {d: i for i, d in enumerate(dates)}
        A["_di"] = A.date.map(self.di).astype(np.int32)
        self._ben = {}
        self.cells = 0
        last = A.groupby("ticker").date.max()
        self.dead = set(last[last < dates[-20]].index)          # 패널 끝 전에 사라진 종목

    def bench(self, h):
        if h not in self._ben:
            c = "n%d" % h
            self._ben[h] = self.A[self.uni].dropna(subset=[c]).groupby("date")[c].median()
        return self._ben[h]

    def run(self, cond, h):
        self.cells += 1
        c = "n%d" % h
        X = self.A[(self.uni & cond).fillna(False)].dropna(subset=[c])
        X = X[X.date >= self.since].sort_values("_di")
        keep, last = [], {}
        for t, i, ix in zip(X.ticker.values, X._di.values, X.index):
            if last.get(t, -10 ** 9) >= i:
                continue
            last[t] = i + h; keep.append(ix)
        Y = X.loc[keep, ["date", "ticker", c]].rename(columns={c: "r"})
        Y["yr"] = Y.date.str[:4]; Y["ym"] = Y.date.str[:6]
        return Y

    @staticmethod
    def stats(Y):
        if len(Y) < 30:
            return None
        v = Y.r
        yr = Y.groupby("yr").r.median()
        return dict(n=len(Y), med=v.median(), mean=v.mean(), trim=v[v <= v.quantile(0.95)].mean(),
                    win=(v > 0).mean() * 100, pos=int((yr > 0).sum()), ny=len(yr),
                    ci=boot_ci(Y.groupby("ym").r.mean()) if Y.ym.nunique() >= 12 else np.nan)

    def pass2(self, Y):
        tr = Y[(Y.date >= TR0) & (Y.date <= TR1)]
        s = self.stats(tr)
        ok = bool(s and s["med"] > 0 and s["trim"] > 0 and s["ci"] == s["ci"] and s["ci"] > 0
                  and s["pos"] / max(s["ny"], 1) >= 0.6)
        return ok, s


def fmt(s):
    if not s:
        return "| 표본 부족 | | | | | | |"
    return "| %s | %+.2f | %+.2f | %+.2f | %.0f%% | %d/%d | %s |" % (
        f"{s['n']:,}", s["med"], s["trim"], s["mean"], s["win"], s["pos"], s["ny"],
        ("%+.2f" % s["ci"]) if s["ci"] == s["ci"] else "-")


def overlap(Y, OLD, di):
    key = {}
    for t, d in zip(OLD.ticker.values, OLD.date.values):
        if d in di:
            key.setdefault(t, []).append(di[d])
    hit = sum(1 for t, d in zip(Y.ticker.values, Y.date.values)
              if di.get(d) is not None and any(abs(di[d] - x) <= 5 for x in key.get(t, [])))
    return hit / max(len(Y), 1) * 100


# ══════════════════════════════════════════════════════════════════════
def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    path = Path(argv[0]); dry = "--dry" in argv
    raw = path.read_bytes(); spec = json.loads(raw.decode("utf-8"))
    hid = spec["id"]; t0 = time.time()
    sha = hashlib.sha256(raw).hexdigest()[:16]

    # ── 명세 고정 ─────────────────────────────────────────────────────
    RUNS.mkdir(exist_ok=True); REPORTS.mkdir(exist_ok=True)
    lock = RUNS / ("%s.json" % hid)
    if lock.exists():
        prev = json.loads(lock.read_text(encoding="utf-8"))
        if prev["sha"] != sha and not dry:
            print("❌ %s 명세가 첫 실행(%s) 뒤 바뀌었다. 사후 수정은 새 가설로 등록할 것(registry add)." % (hid, prev["first"]))
            return 2
    reg = {x["id"]: x for x in registry.load()}
    if hid not in reg:
        print("❌ 등록부에 %s 가 없다 — registry.add 로 먼저 등록" % hid); return 2
    me = reg[hid]

    P("# %s · %s" % (hid, me["name"]))
    P("")
    P("- 시장 %s · 계열 %s · 출처 %s" % (spec["market"], "·".join(me["family"]), me.get("source") or "-"))
    P("- 원리: %s" % (me.get("mechanism") or "-"))
    P("- 명세 해시 `%s` · 실행 %s%s" % (sha, time.strftime("%Y-%m-%d %H:%M"), " · **dry**" if dry else ""))
    P("")
    P("```")
    P("derive: %s" % json.dumps(spec.get("derive", {}), ensure_ascii=False))
    P("cond:   %s" % spec["cond"])
    P("```")

    verdict = None; stage_fail = None; reason = ""

    def fail(st, why):
        nonlocal stage_fail, reason
        stage_fail, reason = st, why
        P(""); P("**❌ %d단계 탈락 — %s**" % (st, why))

    # ── 0 등록부 대조 · 미래 열 ─────────────────────────────────────────
    P(""); P("## 0 등록부 대조")
    texts = [spec["cond"]] + list(spec.get("derive", {}).values()) + [v["cond"] for v in spec.get("variants", [])]
    bad = sorted({m for t in texts for m in FUTURE.findall(t)})
    sim = [(s, x) for s, x in registry.find([me["name"], me.get("mechanism", "")], me["family"], top=6)
           if x["id"] != hid]
    for s, x in sim[:5]:
        P("- [%d] %s %s %s — %s" % (s, x["id"], x["status"], x["name"], x["result"]))
    close_rej = [x for s, x in sim if s >= 6 and x["status"] == "기각"]
    if bad:
        fail(0, "미래 열 사용: %s" % ", ".join(bad))
    elif close_rej and not spec.get("differs_from"):
        fail(0, "원리가 비슷한 기각 기록(%s)이 있는데 differs_from 이 없다" % ", ".join(x["id"] for x in close_rej[:3]))
    elif spec.get("differs_from"):
        P("- 다른 점: %s" % spec["differs_from"])

    J = None
    if stage_fail is None:
        log("%s 패널 읽는 중" % spec["market"])
        A, uni, since = load_market(spec["market"])
        if spec.get("features"):                     # 보유 재료 붙이기(research/features.py) — 국내만
            import features as FT
            FT.attach(A, spec["features"], cal=sorted(A.date.unique()))
            P(""); P("- 붙인 재료: %s" % ", ".join("%s(%s)" % (n, FT.DESC[n][1]) for n in spec["features"]))
        CD = evaluate(A, spec)
        J = Judge(A, uni, since)
        holds = [h for h in spec.get("holds", [20]) if "n%d" % h in A.columns]
        mh = spec.get("main_hold", 20 if 20 in holds else holds[0])
        base = CD["원안"]

        # ── 2 학습 (원안 전 보유기간) ────────────────────────────────
        P(""); P("## 원안 성적 (자금 무제한·다 산다 · 익일 시가 · 비용 차감)")
        P("| 보유 | 구간 | n | 중앙 | 절삭 | 평균 | 승률 | 양수해 | 월CI |")
        P("|---|---|---|---|---|---|---|---|---|")
        RES = {}
        for h in holds:
            Y = J.run(base, h); RES[h] = Y
            segs = [("학습 16~22", Y[(Y.date >= TR0) & (Y.date <= TR1)]), ("검증 23~", Y[Y.date >= VA0]),
                    ("전체 16~", Y[Y.date >= TR0])]
            if spec["market"] == "KR":
                segs.insert(0, ("홀드아웃 05~15", Y[Y.date < TR0]))
            for lbl, z in segs:
                P("| %d일 | %s %s" % (h, lbl, fmt(J.stats(z))))
        ok2, s2 = J.pass2(RES[mh])
        P(""); P("## 2 학습 판정 (%d일)" % mh)
        if not ok2:
            fail(2, "학습 구간 미달 (중앙·절삭·CI·연도 양수 60% 중 하나 이상)")
        else:
            P("- 통과")

        # ── 1 지연 검정 (경고만) ────────────────────────────────────
        P(""); P("## 1 지연 검정 (조건 하루 늦춤 · 경고만)")
        lagged = base.groupby(A.ticker, sort=False).shift(1).fillna(False).astype(bool)
        s0 = J.stats(RES[mh][RES[mh].date >= TR0]); s1 = J.stats(J.run(lagged, mh).pipe(lambda y: y[y.date >= TR0]))
        if s0 and s1:
            drop = s0["med"] - s1["med"]
            P("- 중앙 %+.2f → 하루 늦춤 %+.2f (차 %+.2f)" % (s0["med"], s1["med"], drop))
            if drop > max(1.5, abs(s0["med"]) * 0.5) and s0["med"] > 0:
                P("- ⚠ 하루 늦추면 크게 무너진다 — 미래참조 또는 하루짜리 반전. 사람이 재료 시차를 확인할 것")

        # ── 3 이웃 ─────────────────────────────────────────────────
        if stage_fail is None:
            P(""); P("## 3 이웃 칸 (%d일)" % mh)
            nb = [(k, c) for k, c in CD.items() if k != "원안"]
            if len(nb) < 2:
                fail(3, "이웃 변형이 2개 미만 — 명세에 variants 를 미리 적을 것")
            else:
                P("| 변형 | n | 중앙 | 절삭 | 평균 | 승률 | 양수해 | 학습CI | 2단계 |")
                P("|---|---|---|---|---|---|---|---|---|")
                okn = 0
                for k, c in nb:
                    Y = J.run(c, mh); ok, s = J.pass2(Y); okn += ok
                    P("| %s %s %s |" % (k, fmt(s), "✅" if ok else "❌"))
                if okn * 2 < len(nb):
                    fail(3, "이웃 %d개 중 %d개만 통과 — 한 칸만 좋은 것" % (len(nb), okn))

        # ── 4 검증·다중검정·드리프트 ────────────────────────────────
        if stage_fail is None:
            P(""); P("## 4 검증 · 다중검정 · 드리프트")
            Y = RES[mh]; va = Y[Y.date >= VA0]
            yrs = sorted(Y.yr.unique())[-2:]
            recent = {y: Y[Y.yr == y].r.median() for y in yrs if (Y.yr == y).sum() >= 10}
            d = deflated_sharpe(Y[Y.date >= TR0].groupby("ym").r.mean(), J.cells)
            dsr = d["dsr"] if d else float("nan")
            P("- 검증 중앙 %+.2f (n %d) · 최근 해 %s" % (va.r.median() if len(va) else float("nan"), len(va),
                                                   " · ".join("%s %+.2f" % kv for kv in recent.items())))
            P("- 진짜일 확률 %.3f (이 가설에서 돌린 칸 %d개 기준)" % (dsr, J.cells))
            why = []
            if not (len(va) >= 20 and va.r.median() > 0): why.append("검증 중앙 ≤ 0")
            if any(v < 0 for v in recent.values()): why.append("최근 해 음수")
            if not (dsr >= DSR_MIN): why.append("다중검정 미달(%.3f < %.2f)" % (dsr, DSR_MIN))
            for h in holds:
                if h >= 40:
                    z = RES[h][RES[h].date >= TR0]
                    bm = z.date.map(J.bench(h)).median()
                    P("- %d일: 신호 중앙 %+.2f vs 같은 날 아무거나 %+.2f" % (h, z.r.median(), bm))
                    if z.r.median() <= bm: why.append("%d일 드리프트 착시" % h)
            if why:
                fail(4, " · ".join(why))

        # ── 5 겹침 ─────────────────────────────────────────────────
        if stage_fail is None:
            P(""); P("## 5 기존 규칙과 겹침 (±5일)")
            ov = overlap(RES[mh][RES[mh].date >= TR0], old_signals(spec["market"]), J.di)
            P("- %.0f%%" % ov)
            if ov >= 50:
                fail(5, "겹침 %.0f%% — 새 정보 아님" % ov)

        # ── 함정 점검표 (항상) ───────────────────────────────────────
        Y = RES[mh][RES[mh].date >= TR0]
        if len(Y):
            P(""); P("## 함정 점검표 (%d일 · 2016~)" % mh)
            byy = Y.groupby("yr").r.agg(["size", "sum"])
            pos_sum = byy["sum"].clip(lower=0).sum()
            deadN = Y.ticker.isin(J.dead).mean() * 100
            uniD = A.loc[uni & (A.date >= TR0), "ticker"].isin(J.dead).mean() * 100
            P("| 항목 | 값 |"); P("|---|---|")
            P("| 고유 종목 | %s개 (신호 %s건) |" % (f"{Y.ticker.nunique():,}", f"{len(Y):,}"))
            P("| 건수 최다 해 | %s (%.0f%%) |" % (byy["size"].idxmax(), byy["size"].max() / len(Y) * 100))
            P("| 이익 최다 해 | %s (양수 이익의 %.0f%%) |" % (byy["sum"].idxmax(), byy["sum"].max() / max(pos_sum, 1e-9) * 100))
            P("| 폐지 종목 비중 | 신호 %.1f%% vs 유니버스 %.1f%% |" % (deadN, uniD))
            if spec["market"] == "US":
                P("| 생존편향 | 미장 패널은 현재 상장 종목 역추적 — 폐지 비중이 낮게 나오는 게 정상이고 성적은 부풀려져 있다 |")

    # ── 기록 ───────────────────────────────────────────────────────
    cells = J.cells if J else 0
    status = "후보" if stage_fail is None else "기각"
    summary = ("0~5단계 통과" if stage_fail is None else "%d단계 탈락" % stage_fail)
    P(""); P("---"); P("**판정: %s** · 돌린 칸 %d · %.0f초" % (summary, cells, time.time() - t0))
    rp = (CACHE / ("_dry_%s.md" % hid)) if dry else (REPORTS / ("%s.md" % hid))   # dry 는 저장소에 안 남긴다
    rp.parent.mkdir(exist_ok=True)
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    if not dry:
        if not lock.exists():
            lock.write_text(json.dumps({"sha": sha, "first": time.strftime("%Y-%m-%d %H:%M"),
                                        "spec": str(path.as_posix())}, ensure_ascii=False), encoding="utf-8")
            if cells:
                log_trials(hid, cells)
        registry.update(hid, status=status, result=summary + (" — " + reason if reason else ""),
                        reason=reason, date=time.strftime("%Y-%m-%d"),
                        scripts=["research/specs/%s" % path.name])
    print("\n".join(OUT))
    print("\n보고서: %s" % rp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
