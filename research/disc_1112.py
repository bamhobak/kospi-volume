# -*- coding: utf-8 -*-
"""H0413 공시 본문 숫자화 1단계 (2026-11-12 사용자 "기억 rulefind-1112 7번 실측").

모델에게 판단을 안 시키는 길부터: ① 구조화 숫자(DART 주요사항 API — 유상증자 결정의 자금 용도별 금액·방식, 2016~) ② 목록만으로 공짜 예비 시험(KIND 분 단위 시각, 2016~).
 A. 최대주주 변경을 수반하는 주식 담보제공 계약 체결(=대주주가 주식을 담보로 돈을 빌림, 반대매매되면 최대주주가 바뀜) / 해제
    말한 판: 공시 뒤 첫 체결 가능 시가 매수 → 당일·5·20·60일 · 변형: 20일 -15%↓ 빠진 중(대주주 반대매매 압력) · 60일 안 두 번째 이상 · 해제
 B. 유상증자 결정 — 자금 용도 비중(시설·운영·채무상환·타법인 취득·영업양수·기타) × 방식(제3자배정·주주배정·일반공모) × 크기(조달액 ÷ 시총)
 대조 = 같은 날 거래 가능 전 종목 같은 보유 평균(시장 대비). 비용 0.23. 학습 2016~22 / 검증 2023~. 날 바구니 t.
    python research/disc_1112.py fetch   # DART piicDecsn 받기(회사당 1콜, 저속) → C:/temp/kp/disc/piic.pkl
    python research/disc_1112.py rep     → research/reports/disc_1112.md
"""
import os, sys, json, time, sqlite3, urllib.request, urllib.parse, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
CMD = sys.argv[1] if len(sys.argv) > 1 else "rep"
OUTD = Path("C:/temp/kp/disc"); OUTD.mkdir(parents=True, exist_ok=True)
COST = 0.23
HS = (1, 5, 20, 60)
PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))


def key():
    for line in open(BASE / ".env", encoding="utf-8"):
        if line.startswith("DART_API_KEY="): return line.split("=", 1)[1].strip().strip('"').strip("'")


def fetch():
    K = key()
    c = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
    cc = [r[0] for r in c.execute("select distinct corp_code from disclosure where report_nm like '%유상증자결정%' and rcept_dt >= '20151201'")]
    f = OUTD / "piic.pkl"
    have = pd.read_pickle(f) if f.exists() else pd.DataFrame()
    done = set(have.corp_code) if len(have) else set()
    rows = [] if not len(have) else have.to_dict("records")
    print("회사", len(cc), "이미", len(done), flush=True)
    for i, x in enumerate(cc):
        if x in done: continue
        for a, b in (("20151201", "20201231"), ("20210101", "20261231")):
            u = "https://opendart.fss.or.kr/api/piicDecsn.json?" + urllib.parse.urlencode(dict(crtfc_key=K, corp_code=x, bgn_de=a, end_de=b))
            for k in range(3):
                try:
                    with urllib.request.urlopen(u, timeout=20) as r: j = json.loads(r.read().decode("utf-8")); break
                except Exception as ex:
                    time.sleep(3); j = {"status": "err"}
            if j.get("status") == "020": print("한도 걸림 — 멈춤", flush=True); pd.DataFrame(rows).to_pickle(f); return
            for L in j.get("list") or []: rows.append(L)
            time.sleep(0.25)
        if i % 200 == 0: print(i, len(cc), len(rows), flush=True); pd.DataFrame(rows).to_pickle(f)
    pd.DataFrame(rows).to_pickle(f); print("끝", len(rows), flush=True)


def num(s):
    try: return float(str(s).replace(",", "")) if str(s).strip() not in ("-", "", "nan", "None") else 0.0
    except Exception: return 0.0


def rep():
    import common as C, lab
    from verdict import log_trials
    Px = pd.read_pickle(C.CACHE / "factory_px.pkl")
    Px = Px[Px.date >= "20151101"]
    cal = np.array(sorted(Px.date.unique())); tk = sorted(Px.ticker.unique())
    OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
    CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
    del Px
    ti = {t: i for i, t in enumerate(tk)}
    FR = {}
    for h in HS:
        x = (pd.DataFrame(CL).shift(-(h - 1)).values / OP - 1) * 100 - COST
        x[(np.abs(x) > 80) | ~np.isfinite(x)] = np.nan
        FR[h] = x
    MK = {h: np.nanmean(FR[h], axis=1) for h in HS}
    r20 = (CL / pd.DataFrame(CL).shift(20).values - 1) * 100
    H = lab.hist()[["ticker", "date", "mcap"]]
    mc = H.pivot(index="date", columns="ticker", values="mcap").reindex(index=cal, columns=tk).ffill().values

    def entry_idx(day, hm):
        """공시 날·시각 → 첫 체결 가능 시가의 날 인덱스: 08:50 전 = 그날 시가, 그 뒤 = 다음 거래일 시가."""
        j = np.searchsorted(cal, day)
        if j >= len(cal): return None
        if cal[j] != day: return j                       # 휴장일 공시 → 다음 거래일
        return j if (hm is not None and hm < 850) else j + 1

    def attach(E):
        out = []
        for r in E.itertuples():
            t = ti.get(r.ticker); e = entry_idx(r.day, r.hm)
            if t is None or e is None or e >= len(cal): continue
            d = dict(r._asdict()); d["e"] = e; d["date"] = cal[e]
            for h in HS:
                v = FR[h][e, t]; d["r%d" % h] = v; d["x%d" % h] = v - MK[h][e] if np.isfinite(v) else np.nan
            d["dd20"] = r20[e - 1, t] if e >= 1 else np.nan
            d["mcap"] = mc[e - 1, t] if e >= 1 else np.nan
            d["cl"] = CL[e - 1, t] if e >= 1 else np.nan
            out.append(d)
        return pd.DataFrame(out)

    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))

    def cell(z, col):
        z = z.dropna(subset=[col])
        if len(z) < 10: return "%d건" % len(z)
        dd = z.groupby("date")[col].mean()
        t = dd.mean() / dd.std() * np.sqrt(len(dd)) if len(dd) > 3 and dd.std() > 0 else float("nan")
        return "%d건 중앙 %+.2f · 날 %d **%+.2f** t%.1f" % (len(z), z[col].median(), len(dd), dd.mean(), t)

    per = lambda z, a, b: z[(z.date >= a) & (z.date <= b)]
    ncell = 0

    def table(title, groups):
        nonlocal ncell
        P("### " + title); P("")
        P("| 무리 | 보유 | 절대 학습 | 절대 검증 | 시장 대비 학습 | 시장 대비 검증 |"); P("|---|---|---|---|---|---|")
        for nm, z in groups:
            z = z[(z.cl >= 1000) | z.cl.isna()]
            for h in HS:
                P("| %s | %s | %s | %s | %s | %s |" % (nm, "당일" if h == 1 else "%d일" % h, cell(per(z, *PER[0][1:]), "r%d" % h), cell(per(z, *PER[1][1:]), "r%d" % h),
                                                    cell(per(z, *PER[0][1:]), "x%d" % h), cell(per(z, *PER[1][1:]), "x%d" % h))); ncell += 4
        P("")

    P("# 공시 본문 숫자화 1단계 — 주식 담보 계약 · 유상증자 자금 용도 (H0413) · 2026-11-12"); P("")
    P("- 매수 = 공시 뒤 첫 체결 가능 시가(08:50 전 공시면 그날 시가, 그 뒤면 다음 거래일 시가) · 비용 0.23 뒤 · 칸 = 건수 · 중앙 · 날 바구니 **평균** t · 주가 1,000원↑"); P("")
    # ── A. 담보 ──
    c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
    K = pd.read_sql("select day, hm, kcode, title from kind where market in ('유가증권','코스닥') and title like '%담보%'", c); c.close()
    K["hm"] = K.hm.astype(int); K["ticker"] = K.kcode.astype(str) + "0"
    K = K[~K.title.str.contains("정정")]
    pl = K[K.title.str.contains("최대주주") & K.title.str.contains("체결")].copy()
    rl = K[K.title.str.contains("최대주주") & K.title.str.contains("해제|취소")].copy()
    A = attach(pl.drop_duplicates(["ticker", "day"])); B = attach(rl.drop_duplicates(["ticker", "day"]))
    A = A.sort_values(["ticker", "date"])
    A["prev"] = A.groupby("ticker").e.shift(1); A["rep"] = (A.e - A.prev) <= 60
    P("## ① 최대주주 변경을 수반하는 주식 담보제공 계약 (KIND 목록, 2016~)"); P("")
    P("- 체결 %d건(종목 %d) · 해제·취소 %d건" % (len(A), A.ticker.nunique(), len(B))); P("")
    table("말한 판 — 담보 계약 체결 공시 뒤 시가 매수", [("체결 전체", A)])
    table("변형 — 대주주 반대매매 압력·반복·해제", [("체결 · 20일 -15%↓ 빠진 중", A[A.dd20 <= -15]), ("체결 · 20일 +0% 위", A[A.dd20 > 0]),
                                             ("체결 · 60일 안 두 번째↑", A[A.rep]), ("해제·취소", B)])
    # ── B. 유상증자 ──
    f = OUTD / "piic.pkl"
    if f.exists():
        Z = pd.read_pickle(f).drop_duplicates("rcept_no")
        for col in ("fdpp_fclt", "fdpp_bsninh", "fdpp_op", "fdpp_dtrp", "fdpp_ocsa", "fdpp_etc"): Z[col] = Z[col].map(num)
        Z["tot"] = Z[["fdpp_fclt", "fdpp_bsninh", "fdpp_op", "fdpp_dtrp", "fdpp_ocsa", "fdpp_etc"]].sum(1)
        Z = Z[Z.tot > 0].copy()
        db = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
        sc = dict(db.execute("select corp_code, stock_code from disclosure where stock_code is not null and stock_code != '' group by corp_code"))
        Z["ticker"] = Z.corp_code.map(sc); Z = Z.dropna(subset=["ticker"])
        Z["day"] = Z.rcept_no.str[:8]
        # KIND 시각(같은 날 같은 종목 '유상증자결정') — 없으면 장 마감 뒤로 보수 처리
        c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
        KT = pd.read_sql("select day, hm, kcode from kind where title like '%유상증자%결정%'", c); c.close()
        KT["ticker"] = KT.kcode.astype(str) + "0"; KT["hm"] = KT.hm.astype(int)
        hmmap = KT.groupby(["ticker", "day"]).hm.min().to_dict()
        Z["hm"] = [hmmap.get((t, d), 1600) for t, d in zip(Z.ticker, Z.day)]
        for k, col in (("시설", "fdpp_fclt"), ("운영", "fdpp_op"), ("채무", "fdpp_dtrp"), ("타법인", "fdpp_ocsa")): Z["s_" + k] = Z[col] / Z.tot
        Z["meth"] = Z.ic_mthn.fillna("")
        U = attach(Z[["ticker", "day", "hm", "tot", "meth", "s_시설", "s_운영", "s_채무", "s_타법인"]].drop_duplicates(["ticker", "day"]))
        U["size"] = U.tot / (U.mcap * 1e8)
        P("## ② 유상증자 결정 — 자금 용도(DART 구조화 숫자, 모델 안 씀)"); P("")
        P("- %d건(종목 %d) · 크기 = 조달액 ÷ 시총" % (len(U), U.ticker.nunique())); P("")
        table("말한 판 — 용도별(그 용도가 절반 이상)", [("전체", U), ("채무상환 ≥50%", U[U["s_채무"] >= 0.5]), ("운영자금 ≥50%", U[U["s_운영"] >= 0.5]),
                                               ("시설자금 ≥50%", U[U["s_시설"] >= 0.5]), ("타법인 취득 ≥50%", U[U["s_타법인"] >= 0.5])])
        table("변형 — 방식·크기", [("제3자배정", U[U.meth.str.contains("제3자")]), ("주주배정(실권 공모 포함)", U[U.meth.str.contains("주주배정")]),
                               ("일반공모", U[U.meth.str.contains("일반공모") & ~U.meth.str.contains("주주배정")]),
                               ("크기 ≥30% 시총", U[U["size"] >= 0.3]), ("크기 <5% 시총", U[U["size"] < 0.05]),
                               ("제3자배정 · 시설 ≥50%", U[U.meth.str.contains("제3자") & (U["s_시설"] >= 0.5)]),
                               ("주주배정 · 채무 ≥50%", U[U.meth.str.contains("주주배정") & (U["s_채무"] >= 0.5)])])
    P("(칸 %d)" % ncell)
    (ROOT / "reports" / "disc_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    log_trials("disc_1112", ncell)


if __name__ == "__main__":
    fetch() if CMD == "fetch" else rep()
