# -*- coding: utf-8 -*-
"""공시 시각 × 가격 반응 — '뉴스가 있는 움직임은 이어지고, 없는 움직임은 되돌린다'가 국장에서 비용을 넘는가 (2026-11-10 사용자 "새로운 규칙 찾기 한번 해보자").

공시 '내용'(8계열 25개 기각)이 아니라 **공시 시각과 그 직후 가격 반응**을 본다. 시험 전 등록 H0398~H0400.
  H0398 어제 급등락 × 그 움직임 구간 공시 유무 → 오늘 시가 매수(같은 날 종가 / 5일 / 20일)   — 일봉 2016~
  H0399 오늘 갭 상승 × 갭 구간 공시 유무·종류 → 시가 매수(같은 날 종가 / 5일)                — 일봉 2016~
  H0400 장중 공시(09:05~14:50) 직후 반응 크기 × 종류 → 1~2분 뒤 매수(15분 / 60분 / 종가)      — 1분봉 2022-12~
판정: 비용(0.23) 뒤 절대 수익 · 날 바구니(날마다 평균 → 날들의 평균·t) · 학습/검증 둘 다 · 최근 해.
  일봉 학습 2016~22 / 검증 2023~ · 장중 학습 2022-12~2024 / 검증 2025~(1분봉이 2022-12 부터).
장중 대조: 같은 종목·같은 시각의 **전 거래일**(공시 없는 날) 같은 매매 — '아무 때나 사면'의 바닥선.

    python research/kind_react_1110.py daily    # H0398·H0399 표
    python research/kind_react_1110.py intra    # H0400 사건 목록 → C:/temp/kp/kind/intra.pkl
    python research/kind_react_1110.py irep     # H0400 표
보고서 research/reports/kind_react_1110_{daily,intra}.md
"""
import os, re, sys, glob, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
OUTD = Path("C:/temp/kp/kind"); OUTD.mkdir(parents=True, exist_ok=True)
cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
COST = 0.23

ROUTINE = re.compile(r"증권발행실적|투자설명서|일괄신고|대량보유|소유상황|특정증권등|주주총회|의결권|사외이사|독립이사|지배구조|사업보고서|분기보고서|반기보고서"
                     r"|감사보고서|소집|참고서류|임원ㆍ주요주주|최대주주등소유주식|주식등의|기업설명회|\(IR\)|수시공시의무관련|자기주식처분결과|자기주식취득결과"
                     r"|주주명부폐쇄|기준일|ETF|상장지수|가격제한폭 확대요건|결산실적공시 예고|증권 발행결과|주식매수선택권|변경등록")
TYPES = (("실적", r"영업\(잠정\)실적|매출액\s*또는\s*손익구조|매출액또는손익구조"),
         ("공급계약", r"단일판매ㆍ공급계약체결"),
         ("자사주", r"자기주식\s*취득\s*결정|자기주식취득결정|자기주식취득 신탁계약 체결|주식소각"),
         ("무상증자", r"무상증자결정"),
         ("희석", r"유상증자결정|전환사채권발행결정|신주인수권부사채권발행결정|교환사채권발행결정"),
         ("주요경영", r"투자판단 관련 주요경영사항|기타 경영사항|기타 주요경영사항"),
         ("배당", r"현금ㆍ현물\s*배당\s*결정|현금ㆍ현물배당 결정"),
         ("투자·인수", r"타법인\s*주식\s*및\s*출자증권\s*취득결정|타법인주식및출자증권취득결정|신규시설투자|유형자산\s*취득결정|회사합병결정"),
         ("경보·조회", r"조회공시|투자주의|투자경고|투자위험|단기과열|불성실공시|매매거래정지|관리종목"))


def kind():
    c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
    E = pd.read_sql("select day, hm, kcode, title from kind where market in ('유가증권','코스닥')", c)
    E["title"] = E.title.fillna("")
    bt = E.title.str.replace(r"\[[^\]]*\]", "", regex=True)
    E["typ"] = "기타"
    E.loc[bt.str.contains(ROUTINE), "typ"] = "일상"
    for nm, rx in TYPES[::-1]:                    # 앞쪽 종류가 우선
        E.loc[bt.str.contains(rx, regex=True), "typ"] = nm
    E["hmi"] = E.hm.astype(int)
    return E


def day_flags(E, cal):
    """gapday = 그 공시가 처음 반영되는 시가의 날(장전 → 그날 · 장후·휴일 → 다음 거래일) · inday = 장중이면 그날."""
    cal = np.array(sorted(cal)); cs = set(cal)
    trd = E.day.isin(cs); hm = E.hmi
    nxt = cal[np.minimum(np.searchsorted(cal, E.day.values, side="right"), len(cal) - 1)]
    E = E.copy()
    E["inday"] = np.where(trd & (hm >= 900) & (hm <= 1530), E.day, "")
    E["gapday"] = np.where(trd & (hm < 900), E.day, np.where(trd & (hm <= 1530), "", nxt))
    return E


def has(E, col, T, tcol, typ=None):
    e = E if typ is None else (E[E.typ != "일상"] if typ == "정보성" else E[E.typ == typ])
    s = set(zip(e.kcode.values, e[col].values))
    return np.array([(a[:5], b) in s for a, b in zip(T.ticker.values, T[tcol].values)])


OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def basket(z, col):
    """거래 목록 → (건수, 건당 평균, 중앙, 승률, 날 수, 날 바구니 평균, t)."""
    z = z.dropna(subset=[col])
    if len(z) < 30: return None
    d = z.groupby("date")[col].mean()
    t = d.mean() / d.std() * np.sqrt(len(d)) if len(d) > 5 and d.std() > 0 else np.nan
    return len(z), z[col].mean(), z[col].median(), (z[col] > 0).mean() * 100, len(d), d.mean(), t


def cell(z, col):
    s = basket(z, col)
    return "—" if s is None else "%d건 **%+.2f** (중앙 %+.2f·승 %.0f%%) · 날 %+.2f t%.1f" % (s[0], s[1], s[2], s[3], s[5], s[6])


def daily():
    from verdict import log_trials
    import lab
    H = lab.hist()[["ticker", "date", "r1", "mk_r1", "gap", "rgap", "oc", "sw5", "sw20", "liq", "amt20", "px"]]
    H = H[H.date >= "20160101"].dropna(subset=["oc"]).reset_index(drop=True)
    H["oc"] = H.oc - COST
    H.loc[H.gap >= 25, ["oc", "sw5", "sw20"]] = np.nan          # 상한가 근처 시가 — 못 산다
    cal = sorted(H.date.unique()); prev = dict(zip(cal[1:], cal[:-1]))
    H["pd"] = H.date.map(prev).fillna("")
    E = day_flags(kind(), cal)
    # 어제 움직임의 이유 = 그제 장후~어제 장전(gapday=어제) + 어제 장중(inday=어제) · 매수 전 새 소식 = 어제 장후~오늘 장전(gapday=오늘)
    S = {k: has(E, "gapday", H, "pd", k) | has(E, "inday", H, "pd", k) for k in (None, "정보성")}
    G = {k: has(E, "gapday", H, "date", k) for k in (None, "정보성") + tuple(t[0] for t in TYPES)}
    PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"), ("최근 25~", "20250101", "20991231"))
    P("# 공시 시각 × 가격 반응(일봉) — H0398·H0399 · 2026-11-10"); P("")
    P("- 유니버스: 공장 패널(거래대금 상위 40%%) 2016-01~2026-08 · %d행 · 비용 0.23 뒤 · 날 = 날마다 평균의 평균과 t" % len(H))
    P("- 바닥선(아무 종목 시가 매수): " + " · ".join("%s 종가 %+.2f / 5일 %+.2f / 20일 %+.2f" % (
        nm, H.oc[(H.date >= a) & (H.date <= b)].mean(), H.sw5[(H.date >= a) & (H.date <= b)].mean(), H.sw20[(H.date >= a) & (H.date <= b)].mean()) for nm, a, b in PER[:2])); P("")
    n = 0
    P("## H0398 어제 급등락(시장 대비) × 어제 움직임 구간 공시 → 오늘 시가 매수"); P("")
    H["x"] = H.r1 - H.mk_r1
    bins = [(-99, -10), (-10, -7), (-7, -5), (-5, -3), (3, 5), (5, 7), (7, 10), (10, 99)]
    news = (("공시 없음(어제·오늘 장전 모두)", ~S[None] & ~G[None]), ("공시 있음", S[None]), ("정보성 공시", S["정보성"]))
    for mode, mn in (("oc", "같은 날 종가"), ("sw5", "5일 뒤 종가"), ("sw20", "20일 뒤 종가")):
        P("### 매도: %s" % mn); P("")
        P("| 어제 시장 대비 | 공시 | 학습 16~22 | 검증 23~ | 최근 25~ |"); P("|---|---|---|---|---|")
        for a, b in bins:
            k = (H.x > a) & (H.x <= b)
            for nn, m in news:
                P("| %s~%s | %s | %s |" % (a, b, nn, " | ".join(cell(H[k & m & (H.date >= s) & (H.date <= e)], mode) for _, s, e in PER))); n += 1
        P("")
    P("## H0399 오늘 갭 상승(시장 대비) × 갭 구간 공시 → 시가 매수"); P("")
    gb = [(2, 3), (3, 5), (5, 7), (7, 25)]
    gnews = (("공시 없음", ~G[None]), ("공시 있음", G[None]), ("정보성", G["정보성"])) + tuple((t[0], G[t[0]]) for t in TYPES)
    for mode, mn in (("oc", "같은 날 종가"), ("sw5", "5일 뒤 종가")):
        P("### 매도: %s" % mn); P("")
        P("| 갭(시장 대비) | 공시 | 학습 16~22 | 검증 23~ | 최근 25~ |"); P("|---|---|---|---|---|")
        for a, b in gb:
            k = (H.rgap >= a) & (H.rgap < b)
            for nn, m in gnews:
                P("| +%s~%s | %s | %s |" % (a, b, nn, " | ".join(cell(H[k & m & (H.date >= s) & (H.date <= e)], mode) for _, s, e in PER))); n += 1
        P("")
    # 덤: 갭 하락 쪽 종류별(이미 T1 에서 '있음' 은 약함을 봤다 — 종류로 갈리는지만)
    P("### 참고 — 갭 하락(시장 대비 -3%p↓) × 종류 · 같은 날 종가"); P("")
    P("| 공시 | 학습 16~22 | 검증 23~ | 최근 25~ |"); P("|---|---|---|---|")
    k = H.rgap <= -3
    for nn, m in gnews:
        P("| %s | %s |" % (nn, " | ".join(cell(H[k & m & (H.date >= s) & (H.date <= e)], "oc") for _, s, e in PER))); n += 1
    P(""); P("(칸 %d)" % n)
    log_trials("kind_react_1110_daily", n)
    (ROOT / "reports" / "kind_react_1110_daily.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


# ── 장중 ──
LAG = 3            # 공시 분(m) → 매수 봉 = 끝 시각 표기 m+3 이상인 첫 봉의 시가(= m+2분 00초 뒤 첫 체결 · 공시 뒤 1~2분)
EXITS = (15, 60)


def intra():
    E = kind()
    E = E[(E.day >= "20221201") & (E.hmi >= 905) & (E.hmi <= 1450)].copy()
    rank = {t[0]: i for i, t in enumerate(TYPES)}; rank.update({"기타": 50, "일상": 99})
    E["rk"] = E.typ.map(rank)
    E = E.sort_values(["kcode", "day", "hmi", "rk"])
    E["first"] = ~E.duplicated(["kcode", "day"])                       # 그날 그 회사 첫 장중 공시
    E = E.drop_duplicates(["kcode", "day", "hmi"])
    ev = {k: g for k, g in E.groupby("kcode")}
    rows = []
    files = sorted(glob.glob(str(BASE / "data" / "m1" / "KR" / "bf" / "*.parquet")))
    for i, f in enumerate(files):
        t = Path(f).stem
        if not t.endswith("0") or t[:5] not in ev: continue           # 보통주만
        g = ev[t[:5]]
        B = pd.read_parquet(f, columns=["ts", "o", "c", "v"])
        if not len(B): continue
        k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s")
        B["day"] = k.strftime("%Y%m%d"); B["hm"] = k.hour * 100 + k.minute
        B["mi"] = k.hour * 60 + k.minute
        days = {d: x for d, x in B.groupby("day", sort=True)}
        dl = sorted(days); pos = {d: j for j, d in enumerate(dl)}
        for day, hmi, typ, first, title in zip(g.day.values, g.hmi.values, g.typ.values, g["first"].values, g.title.values):
            if day not in pos or pos[day] == 0: continue
            m = (hmi // 100) * 60 + hmi % 100
            pday = dl[pos[day] - 1]
            pc = float(days[pday].c.values[-1])                        # 전 거래일 종가
            for tag, d in (("ev", day), ("pl", pday)):                 # 사건 / 대조(전 거래일 같은 시각)
                X = days[d]; mi = X.mi.values; o = X.o.values; c = X.c.values; v = X.v.values
                j0 = np.searchsorted(mi, m, side="right") - 1          # 끝 시각 ≤ m 인 마지막 봉 = 공시 분 직전 값
                je = np.searchsorted(mi, m + LAG, side="left")         # 매수 봉
                if j0 < 0 or je >= len(mi) or mi[je] > m + LAG + 5: continue
                p0, pe = float(c[j0]), float(o[je])
                if p0 <= 0 or pe <= 0: continue
                a30 = float((c[max(0, j0 - 29):j0 + 1] * v[max(0, j0 - 29):j0 + 1]).sum())
                ex = {}
                for kx in EXITS:
                    jx = np.searchsorted(mi, mi[je] + kx, side="right") - 1
                    ex["x%d" % kx] = float(c[jx]) if jx > je else np.nan
                ex["xc"] = float(c[-1]) if mi[-1] >= 15 * 60 + 20 else np.nan
                base = pc if tag == "ev" else (float(days[dl[pos[d] - 1]].c.values[-1]) if pos[d] > 0 else np.nan)
                rows.append((t, day, hmi, typ, bool(first), tag, (pe / p0 - 1) * 100, (p0 / base - 1) * 100 if base == base and base > 0 else np.nan,
                             (pe / base - 1) * 100 if base == base and base > 0 else np.nan, a30, pe,
                             (ex["x15"] / pe - 1) * 100, (ex["x60"] / pe - 1) * 100, (ex["xc"] / pe - 1) * 100, title[:40] if tag == "ev" else ""))
        if i % 300 == 0: print(i, len(files), len(rows), flush=True)
    Z = pd.DataFrame(rows, columns=["ticker", "date", "hm", "typ", "first", "tag", "r0", "pre", "rc", "a30", "pe", "r15", "r60", "rcl", "title"])
    Z.to_pickle(OUTD / "intra.pkl")
    print("사건", int((Z.tag == "ev").sum()), "대조", int((Z.tag == "pl").sum()))


def irep():
    from verdict import log_trials
    Z = pd.read_pickle(OUTD / "intra.pkl")
    Z = Z[(Z.rc < 28) & (Z.rc > -28) & (Z.a30 >= 3e7)].copy()          # 상·하한가 근처 빼고 · 직전 30분 거래대금 3천만↑(살 수 있는 종목)
    for c in ("r15", "r60", "rcl"): Z[c] = Z[c] - COST
    PER = (("학습 22.12~24", "20221201", "20241231"), ("검증 25~", "20250101", "20991231"))
    ev, pl = Z[Z.tag == "ev"], Z[Z.tag == "pl"]
    P("# 장중 공시 직후 반응(1분봉) — H0400 · 2026-11-10"); P("")
    P("- 사건 %d건(09:05~14:50 공시 · 보통주 · 직전 30분 거래대금 3천만↑ · 상·하한가 근처 뺌) · 매수 = 공시 분 +%d 봉 시가(공시 뒤 1~2분) · 비용 0.23 뒤" % (len(ev), LAG))
    P("- r0 = 공시 직전 값 → 매수가(공시 뒤 1~2분 반응) · 대조 = 같은 종목 전 거래일 같은 시각 같은 매매")
    P("- 바닥선(대조 전체): " + " · ".join("%s 15분 %+.2f / 60분 %+.2f / 종가 %+.2f" % (nm, pl.r15[(pl.date >= a) & (pl.date <= b)].mean(), pl.r60[(pl.date >= a) & (pl.date <= b)].mean(),
                                                                          pl.rcl[(pl.date >= a) & (pl.date <= b)].mean()) for nm, a, b in PER)); P("")
    n = 0
    rb = [(-99, -3), (-3, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 3), (3, 6), (6, 99)]
    types = ["전체(일상 뺌)"] + [t[0] for t in TYPES] + ["기타", "일상"]
    for mode, mn in (("r15", "15분 뒤"), ("r60", "60분 뒤"), ("rcl", "종가")):
        P("## 매도: %s" % mn); P("")
        P("| 종류 | 직후 반응 r0 | 학습 22.12~24 | 검증 25~ | 대조(전 거래일) 학습/검증 |"); P("|---|---|---|---|---|")
        for ty in types:
            e = ev[ev.typ != "일상"] if ty.startswith("전체") else ev[ev.typ == ty]
            q = pl[pl.typ != "일상"] if ty.startswith("전체") else pl[pl.typ == ty]
            for a, b in rb:
                k = (e.r0 > a) & (e.r0 <= b); kq = (q.r0 > a) & (q.r0 <= b)
                cs = [cell(e[k & (e.date >= s) & (e.date <= x)], mode) for _, s, x in PER]
                if cs[0] == "—" and cs[1] == "—": continue
                pm = ["%+.2f" % q[kq & (q.date >= s) & (q.date <= x)][mode].mean() if (kq & (q.date >= s) & (q.date <= x)).sum() >= 30 else "—" for _, s, x in PER]
                P("| %s | %s~%s | %s | %s | %s / %s |" % (ty, a, b, cs[0], cs[1], pm[0], pm[1])); n += 1
        P("")
    # 시간대
    P("## 참고 — 직후 반응 +1~6% 인 정보성 공시 · 시간대별 · 종가 매도"); P("")
    P("| 공시 시각 | 학습 | 검증 |"); P("|---|---|---|")
    e = ev[(ev.typ != "일상") & (ev.r0 > 1) & (ev.r0 <= 6)]
    for a, b in ((905, 1000), (1000, 1130), (1130, 1300), (1300, 1450)):
        k = (e.hm >= a) & (e.hm < b)
        P("| %04d~%04d | %s |" % (a, b, " | ".join(cell(e[k & (e.date >= s) & (e.date <= x)], "rcl") for _, s, x in PER))); n += 1
    P(""); P("(칸 %d)" % n)
    log_trials("kind_react_1110_intra", n)
    (ROOT / "reports" / "kind_react_1110_intra.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"daily": daily, "intra": intra, "irep": irep}[cmd]()
