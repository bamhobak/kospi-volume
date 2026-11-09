# -*- coding: utf-8 -*-
"""'이유 없는 하락' 거르개 — 공시 시각(KIND, 분 단위)으로 되돌림 규칙의 하락에 이유(공시)가 있었는지 가른다 (2026-11-09 사용자 "응 돌려줘").

가설(등록부 H0395~H0397, 시험 전 등록):
  H0395 [갭 하락 조용주] T1 — 갭을 만든 구간(전 거래일 15:30 뒤 ~ 당일 09:00 전) 공시가 있으면 되돌림이 약하다
  H0396 [NXT 장후 빠진 종목] T6 — 당일 15:30~19:50 공시가 있으면 다음 날 시가 되돌림이 약하다
  H0397 스윙 국장 규칙 — 신호 날의 하락에 공시(당일 장중 + 전날 장후·당일 장전)가 있으면 약하다 / 신호 뒤 매수 전(장후~다음 날 장전) 공시도 따로
수준 3개(미리 정함): 아무 공시 · 정보성(정기·지분·발행 실무 공시 뺌) · 악재형(자금조달·소송·감사·관리·경보·최대주주 변경 등)
구간: 학습 2016~22 · 검증 2023~ (T6 은 NXT 가 2025-03~ 이라 2025 / 2026)
기준선: 같은 규칙 안 '공시 없음' 거래 + 같은 날 짝 차이(있음과 없음이 같은 날 있는 날만) — 공시 내는 종목의 성질(크기 등)과 시장 날씨를 떼려고.

    python research/kind_filter_1109.py t1      # T1 거래 → C:/temp/kp/kind/t1.pkl
    python research/kind_filter_1109.py swing   # 스윙 거래 → swing.pkl
    python research/kind_filter_1109.py t6      # T6 거래(캐시만, 받기 없음) → t6.pkl
    python research/kind_filter_1109.py rep     # 표 → research/reports/kind_filter_1109.md
"""
import io, os, re, sys, pickle, sqlite3, warnings, contextlib
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
OUTD = Path("C:/temp/kp/kind"); OUTD.mkdir(parents=True, exist_ok=True)
cmd = sys.argv[1] if len(sys.argv) > 1 else "rep"
COST = 0.23

ROUTINE = re.compile(r"증권발행실적|투자설명서|일괄신고|대량보유|소유상황|특정증권등|주주총회|의결권|사외이사|지배구조|사업보고서|분기보고서|반기보고서"
                     r"|감사보고서제출|소집|참고서류|임원ㆍ주요주주|최대주주등소유주식|주식등의|기업설명회|\(IR\)|신탁계약|수시공시의무관련|자기주식처분결과|자기주식취득결과")
NEG = re.compile(r"유상증자|전환사채|신주인수권|교환사채|감자|소송|횡령|배임|불성실공시|관리종목|상장적격성|상장폐지|매매거래정지|거래정지|감사의견|의견거절"
                 r"|투자주의|투자경고|투자위험|조회공시|최대주주변경|최대주주 변경|영업정지|회생|부도|파산|자본잠식|손상차손|공급계약해지|계약해지|철회|단기과열")


def t1():
    import lab
    H = lab.hist()[["ticker", "date", "gap", "rgap", "q_vm", "liq", "oc"]]
    H = H[H.date >= "20160101"].dropna(subset=["gap", "rgap", "liq", "oc"]).copy()
    cal = sorted(H.date.unique())
    H["gq"] = H.groupby("date").gap.rank(pct=True)
    T = H[(H.q_vm.fillna(1) <= 0.30) & (H.liq <= 2 / 3) & (H.gq <= 0.40) & (H.rgap <= -1.5) & (H.gap > -27.5)].copy()
    T["r"] = T.oc - COST
    T = T[["ticker", "date", "gap", "rgap", "r"]].reset_index(drop=True)
    print("T1", len(T))
    pickle.dump(dict(T=T, cal=cal), open(OUTD / "t1.pkl", "wb"))


def swing():
    src = (BASE / "stats_2016.py").read_text(encoding="utf-8").split("OUT = {}")[0]
    ns = {"__file__": str(BASE / "stats_2016.py"), "__name__": "x"}
    real = sys.stdout
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    exec(compile(src, "stats_2016.py", "exec"), ns)
    sys.stdout = real; sys.stdout.reconfigure(encoding="utf-8")
    out = {}
    for rid in ns["ORDER"]:
        K = ns["RULES"][rid][0]
        Z, hold, stop = ns["take"](rid)
        # 매수가가 신호 날 종가인지 다음 날 시가인지 — 신호 뒤 공시를 거르개로 쓸 수 있는지가 여기 달렸다
        g = K.groupby("ticker", sort=False)
        o1 = g.open.shift(-1) if "open" in K.columns else pd.Series(np.nan, index=K.index)
        bz = K.loc[Z.index]
        m_close = float(np.isclose(bz.buy, bz.close, rtol=1e-6).mean())
        m_open1 = float(np.isclose(bz.buy, o1.loc[Z.index], rtol=1e-6).mean()) if "open" in K.columns else float("nan")
        out[rid] = dict(name=ns["NAME"][rid], disp=ns["DISP"][rid], hold=hold, buy_close=m_close, buy_open1=m_open1,
                        T=pd.DataFrame({"ticker": Z.ticker.values, "date": Z.date.values, "r": Z._r.values.astype(float)}))
        print(rid, ns["NAME"][rid], len(Z), "매수=종가 %.0f%% · 다음날 시가 %.0f%%" % (m_close * 100, m_open1 * 100), flush=True)
    pickle.dump(out, open(OUTD / "swing.pkl", "wb"))


def t6():
    C1D = ROOT / "cache" / "toss_kr_1d_wide.parquet"; CAH = ROOT / "cache" / "ah_m1.parquet"
    K = pd.read_pickle(BASE / "data/kr_scan.pkl")[["ticker", "date", "marcap", "pref"]]
    K = K[K.date >= "20250101"]
    K = K[(K.pref != 1) & K.marcap.notna()]
    first = K.groupby(K.date.str[:6]).date.min()
    U = {}
    for ym, d0 in first.items():
        z = K[K.date == d0]; U[ym] = set(z[z.marcap.rank(ascending=False, pct=True) <= 0.5].ticker)
    lastym = max(U)
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")[["t", "d", "o", "c"]]
    D = D[D.d >= "20250301"]; D["ym"] = D.d.str[:6]
    D = D[[t in U.get(ym, U[lastym]) for t, ym in zip(D.t, D.ym)]]
    T = pd.read_parquet(C1D)
    X = D.merge(T, on=["t", "d"]).sort_values(["t", "d"])
    X["o1"] = X.groupby("t").o.shift(-1)
    X = X.dropna(subset=["o1"]).copy()
    X["AHd"] = (X.tc / X.c - 1) * 100
    X["mkt"] = X.groupby("d").AHd.transform("mean")
    X["nxt"] = X.groupby("t").AHd.transform(lambda s: (s.abs() > 1e-9).mean() > 0.3)
    have = pd.read_parquet(CAH); have = have[have.hm.astype(float) >= 1541].copy(); have["hm"] = have.hm.astype(int)
    p50 = have[have.hm <= 1950].sort_values("hm").groupby(["t", "d"]).c.last().rename("p50")
    L = have[(have.hm >= 1951) & (have.hm <= 2000)]
    vw = ((L.c * L.v).groupby([L.t, L.d]).sum() / L.v.groupby([L.t, L.d]).sum().replace(0, np.nan)).rename("vw")
    a10 = (L.c * L.v).groupby([L.t, L.d]).sum().rename("a10")
    Z = X[X.nxt].merge(pd.concat([p50, vw, a10], axis=1).reset_index(), on=["t", "d"], how="inner")
    Z["AH50"] = (Z.p50 / Z.c - 1) * 100; Z["rel"] = Z.AH50 - Z.mkt
    Z["r"] = (Z.o1 / Z.vw - 1) * 100 - COST
    Z["r50"] = (Z.o1 / Z.p50 - 1) * 100 - COST
    sh = Z[(Z.rel <= -2.0) & (Z.mkt > -1.0) & (Z.a10 >= 1e7)].dropna(subset=["r"])
    T6 = sh.rename(columns={"t": "ticker", "d": "date"})[["ticker", "date", "AH50", "rel", "r", "r50"]].reset_index(drop=True)
    print("T6 그림자 조건", len(T6), "· 실주문 조건(장후 -2.5%↓)", int((T6.AH50 <= -2.5).sum()))
    pickle.dump(dict(T=T6, cal=sorted(D.d.unique())), open(OUTD / "t6.pkl", "wb"))


# ── 공시 붙이기 ──
def kind_events(cal):
    c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
    E = pd.read_sql("select day, hm, kcode, market, title from kind where market in ('유가증권','코스닥')", c)
    E["title"] = E.title.fillna("")
    E["fix"] = E.title.str.contains(r"\[기재정정\]|정정", regex=True)
    base_t = E.title.str.replace(r"\[[^\]]*\]", "", regex=True)
    E["info"] = ~base_t.str.contains(ROUTINE)
    E["neg"] = base_t.str.contains(NEG)
    cal = np.array(sorted(cal)); calset = set(cal)
    # 장전(<09:00, 거래일) → 그날 시가에 반영 · 장중(09:00~15:30, 거래일) → 그날 종가에 반영 · 장후·휴일 → 다음 거래일 시가
    hm = E.hm.astype(int)
    trd = E.day.isin(calset)
    nxt = cal[np.minimum(np.searchsorted(cal, E.day.values, side="right"), len(cal) - 1)]
    E["inday"] = np.where(trd & (hm >= 900) & (hm <= 1530), E.day, "")
    E["gapday"] = np.where(trd & (hm < 900), E.day, np.where(trd & (hm >= 900) & (hm <= 1530), "", nxt))
    E["hmi"] = hm
    return E


def flag(T, E, keys, lvl):
    """T(ticker,date) 마다 keys=[(E 열, T 날짜 열)] 창 안에 수준 lvl 공시가 있었나."""
    e = E if lvl == "any" else E[E[lvl]]
    hit = np.zeros(len(T), bool)
    k5 = T.ticker.str[:5].values
    for ecol, tcol in keys:
        s = set(zip(e.kcode.values, e[ecol].values))
        hit |= np.array([(a, b) in s for a, b in zip(k5, T[tcol].values)])
    return hit


def stats_block(T, hit, splits):
    rows = []
    for nm, a, b in splits:
        m = (T.date >= a) & (T.date <= b)
        z, h = T[m], hit[m.values]
        if not len(z): continue
        y, n = z.r[h], z.r[~h]
        # 같은 날 짝: 있음·없음이 같은 날 둘 다 있는 날만, 날마다 (없음 평균 - 있음 평균)
        zz = z.assign(h=h)
        dd = zz.groupby(["date", "h"]).r.mean().unstack()
        dd = dd.dropna() if (True in dd.columns and False in dd.columns) else pd.DataFrame(columns=[False, True])
        pdiff = (dd[False] - dd[True]) if len(dd) else pd.Series(dtype=float)
        rows.append(dict(per=nm, n=len(z), nh=int(h.sum()), sh=h.mean() * 100, all=z.r.mean(), yes=y.mean() if len(y) else np.nan,
                         no=n.mean() if len(n) else np.nan, med_yes=y.median() if len(y) else np.nan, med_no=n.median() if len(n) else np.nan,
                         win_yes=(y > 0).mean() * 100 if len(y) else np.nan, win_no=(n > 0).mean() * 100 if len(n) else np.nan,
                         pair=pdiff.mean() if len(pdiff) else np.nan, npair=len(pdiff),
                         tpair=(pdiff.mean() / pdiff.std() * np.sqrt(len(pdiff))) if len(pdiff) > 5 and pdiff.std() > 0 else np.nan))
    return rows


OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
LV = (("any", "아무 공시"), ("info", "정보성"), ("neg", "악재형"))


def table(title, T, E, keys, splits):
    P("### " + title); P("")
    P("| 수준 | 구간 | 거래 | 공시 있음 | 전체 평균 | **있음** | **없음** | 중앙 있음/없음 | 승률 있음/없음 | 같은 날 짝(없음-있음) |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    res = {}
    for lv, ln in LV:
        hit = flag(T, E, keys, lv)
        rr = stats_block(T, hit, splits); res[lv] = rr
        for r in rr:
            P("| %s | %s | %d | %d (%.1f%%) | %+.2f | **%+.2f** | **%+.2f** | %+.2f / %+.2f | %.0f / %.0f%% | %+.2f (%d날, t %.1f) |" % (
                ln, r["per"], r["n"], r["nh"], r["sh"], r["all"], r["yes"], r["no"], r["med_yes"], r["med_no"], r["win_yes"], r["win_no"],
                r["pair"], r["npair"], r["tpair"]))
    P(""); return res


def rep():
    from verdict import log_trials
    S1 = (("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))
    S6 = (("2025-03~12", "20250301", "20251231"), ("2026~", "20260101", "20991231"))
    d1 = pickle.load(open(OUTD / "t1.pkl", "rb")); d6 = pickle.load(open(OUTD / "t6.pkl", "rb")); sw = pickle.load(open(OUTD / "swing.pkl", "rb"))
    cal = sorted(set(d1["cal"]) | set(d6["cal"]))
    E = kind_events(cal)
    calA = np.array(cal)
    nxtday = dict(zip(calA[:-1], calA[1:]))
    P("# '이유 없는 하락' 거르개 — 공시 시각(KIND) 실측 · 2026-11-09"); P("")
    P("- 공시 %d건(유가·코스닥, 2016-01~2026-11) · 정보성 %.0f%% · 악재형 %.1f%%" % (len(E), E["info"].mean() * 100, E["neg"].mean() * 100))
    P("- 종목 짝: KIND 회사코드 5자리 = 종목코드 앞 5자리(우선주는 본주 공시를 같이 봄)")
    P("- 칸: 비용(0.23) 뒤 거래당 %. '같은 날 짝' 이 플러스면 공시 없는 쪽이 같은 날 더 좋았다는 뜻 → 공시 있는 거래를 빼는 거르개가 맞다"); P("")
    ncell = 0

    # T1
    T = d1["T"]
    P("## H0395 [갭 하락 조용주] — 갭 구간(전날 15:30 뒤 ~ 당일 09:00 전) 공시"); P("")
    P("- 거래 %d건(일봉 연구판: 실제 시가로 고름, 시가 매수 → 종가 매도)" % len(T)); P("")
    r1 = table("T1 · 갭 구간 공시", T, E, [("gapday", "date")], S1); ncell += 3
    P("**갭 깊이로 나눠 보기(아무 공시)**"); P("")
    hit = flag(T, E, [("gapday", "date")], "any")
    P("| 갭 | 학습 있음/없음 | 검증 있음/없음 |"); P("|---|---|---|")
    for a, b in ((-99, -6), (-6, -3), (-3, 99)):
        k = ((T.gap > a) & (T.gap <= b)).values
        cell = []
        for _, s, e in S1:
            m = k & ((T.date >= s) & (T.date <= e)).values
            cell.append("%+.2f (%d) / %+.2f (%d)" % (T.r[m & hit].mean(), (m & hit).sum(), T.r[m & ~hit].mean(), (m & ~hit).sum()))
        P("| %s~%s | %s | %s |" % (a, b, cell[0], cell[1]))
    P(""); ncell += 3

    # T6
    T = d6["T"].copy()
    T["d0"] = T.date
    P("## H0396 [NXT 장후 빠진 종목] — 당일 장후(15:30~19:50) 공시"); P("")
    P("- 그림자 조건(시장 대비 -2%%p↓·시장 장후 -1%% 위·마지막 10분 1천만↑) 거래 %d건 · 19:51~20:00 VWAP 매수 → 다음 날 KRX 시가" % len(T)); P("")
    e2 = E.copy()
    e2["ah"] = np.where((e2.hmi > 1530) & (e2.hmi <= 1950), e2.day, "")
    table("T6 · 당일 장후 공시(15:30~19:50)", T, e2, [("ah", "date")], S6); ncell += 3
    table("T6 · 당일 장중 + 장후 공시(09:00~19:50)", T, e2, [("ah", "date"), ("inday", "date")], S6); ncell += 3
    Tl = T[T.AH50 <= -2.5].reset_index(drop=True)
    table("T6 실주문 조건(장후 -2.5%%↓)만 · 장후 공시 — %d건" % len(Tl), Tl, e2, [("ah", "date")], S6); ncell += 3

    # 스윙
    P("## H0397 스윙 국장 규칙 — 신호 날 하락의 공시 / 신호 뒤 매수 전 공시"); P("")
    P("| 규칙 | 거래 | 매수가 = 신호 날 종가 / 다음 날 시가 |"); P("|---|---|---|")
    for rid, d in sw.items():
        P("| [%s] %s | %d | %.0f%% / %.0f%% |" % (d["name"], d["disp"], len(d["T"]), d["buy_close"] * 100, d["buy_open1"] * 100))
    P("")
    allT = []
    for rid, d in sw.items():
        z = d["T"].copy(); z["rid"] = rid; z["nx"] = z.date.map(nxtday).fillna(""); allT.append(z)
    A = pd.concat(allT, ignore_index=True)
    table("스윙 합침 · 신호 날 하락 공시(전날 장후·당일 장전·당일 장중)", A, E, [("gapday", "date"), ("inday", "date")], S1); ncell += 3
    table("스윙 합침 · 신호 뒤 매수 전 공시(신호 날 장후 ~ 다음 날 장전)", A, E, [("gapday", "nx")], S1); ncell += 3
    P("### 규칙별 · 신호 날 하락 공시(정보성)"); P("")
    P("| 규칙 | 구간 | 거래 | 있음 | 있음 평균 | 없음 평균 | 같은 날 짝 |"); P("|---|---|---|---|---|---|---|")
    for rid, d in sw.items():
        z = A[A.rid == rid].reset_index(drop=True)
        hit = flag(z, E, [("gapday", "date"), ("inday", "date")], "info")
        for r in stats_block(z, hit, S1):
            P("| [%s] | %s | %d | %d (%.0f%%) | %+.2f | %+.2f | %+.2f (%d날) |" % (d["name"], r["per"], r["n"], r["nh"], r["sh"], r["yes"], r["no"], r["pair"], r["npair"]))
        ncell += 1
    P("")
    P("(칸 %d)" % ncell)
    log_trials("kind_filter_1109", ncell)
    (ROOT / "reports" / "kind_filter_1109.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"t1": t1, "swing": swing, "t6": t6, "rep": rep}[cmd]()
