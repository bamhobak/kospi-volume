# -*- coding: utf-8 -*-
"""연구 패널 새 판 만들기 + 건강 진단 (2026-10-31).

(1) 국장: kr_scan.pkl 이 2026-08-28 에 멈춰 있다 → 서버에 있는 재료로 2026-10-30 까지 잇는다.
    새 파일: data/panel_kp_new.pkl · data/panel_kq_new.pkl · data/kr_scan_new.pkl (기존 파일은 안 건드린다)
(2) 미장: us_scan_full 에서 토스에서 못 사는 증권을 뺀 판 → data/us_scan_full_notoss.pkl
    + H0306 정의(us_rules_recheck.py)로 포함/제외 성적 비교.
(3) 건강 진단: 규칙을 고르거나 고치지 않는다. 숫자만 낸다.

재료 고르는 법(대조 근거는 research/reports/panel_refresh_1031.md):
  ⚠ 2026-09-14 부터 monthly CSV·kospi.db·kosdaq.db 의 close 는 KRX 종가가 아니다(종목 80% 가 다름 — NXT 까지 섞인 값).
    연구 패널의 close 는 KRX 공식 종가여야 한다 → 공매도 잔고 표의 mktcap÷shrs(T+2 · 10-28 까지)를 쓰고,
    끝 이틀은 1분봉 마지막 봉·KIS 종가(둘 다 공식과 99.9~100% 일치)로 채운다.
  네트워크 호출 없음. FinanceDataReader 도 안 부른다. 지수는 data/factory/kospi.json, S&P 는 패널 안 SPY.

    python research/panel_refresh_1031.py raw        # 새 행 재료 모으기
    python research/panel_refresh_1031.py kr         # 패널 잇기
    python research/panel_refresh_1031.py patch_kr   # 시장 이전 12종목 새 행 빼기 · 재개 종목 공백 결측
    python research/panel_refresh_1031.py verify2    # 앞부분 전수 대조(저메모리)
    python research/panel_refresh_1031.py audit_kr2  # audit_contam 14항목
    python research/panel_refresh_1031.py kr_health  # 국장 규칙·[지수 덮개]·사이트 대조
    python research/panel_refresh_1031.py us         # 미지원 판별 · us_scan_full_notoss.pkl(빼기+수리)
    python research/panel_refresh_1031.py audit_us2
    python research/panel_refresh_1031.py smoke      # run_spec.load_market 이 새 판을 읽는지
    python research/panel_refresh_1031.py us_rules   # 포함/제외 성적(앞선 실행의 V0·V1·V3 를 재사용, V2·V4 계산)
"""
import gc, glob, json, os, re, sqlite3, sys, time, types, warnings
warnings.filterwarnings("ignore")
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent; DATA = BASE / "data"
WORK = ROOT / "cache" / "panel_refresh_1031"; WORK.mkdir(parents=True, exist_ok=True)
OLD_END = "20260828"
HZ = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 40, 50, 60]
BASECOLS = ["date", "ticker", "name", "open", "high", "low", "close", "volume", "frgn", "organ", "marcap", "shares", "short_ratio", "grp"]
pd.set_option("display.width", 230); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 300)
T0 = time.time()


def base(fn):
    """잇기의 바탕(2026-08-28 까지인 옛 판). 11-10~ 새 판을 본이름(kr_scan.pkl 등)으로 바꿔 끼우므로 옛 판은 *_0828.pkl 로 남긴다 — 있으면 그걸 읽는다."""
    p = DATA / fn.replace(".pkl", "_0828.pkl")
    return p if p.exists() else DATA / fn


def log(m): print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)
def ro(p): return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=120)
def save(name, obj): json.dump(obj, open(WORK / name, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)


# ═══════════════════════════════════════════════════════════════════════
# 1. 새 행 재료
# ═══════════════════════════════════════════════════════════════════════
def agg_m1(M):
    """1분봉(t ts o h l c v) → 정규장 일봉. live.agg 와 같되 분봉이 5개 미만인 얇은 종목도 남긴다."""
    k = M.ts.to_numpy().astype("int64") + 9 * 3600
    dn, sec = k // 86400, k % 86400
    ud = np.unique(dn); dstr = dict(zip(ud, pd.to_datetime(ud, unit="D").strftime("%Y%m%d")))
    hm = (sec // 3600) * 100 + (sec % 3600) // 60
    M = M.assign(date=pd.Series(dn, index=M.index).map(dstr).values, hm=hm)
    M = M[(M.hm >= 901) & (M.hm <= 1531)].sort_values(["t", "ts"])
    if M.empty: return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close"])
    g = M.groupby(["t", "date"], sort=False)
    R = pd.DataFrame({"open": g.o.first(), "high": g.h.max(), "low": g.l.min(), "close": g.c.last(), "first": g.hm.first()}).reset_index().rename(columns={"t": "ticker"})
    R.loc[R["first"] != 901, "open"] = np.nan
    return R.drop(columns=["first"])


def stage_raw():
    log("재료 읽기")
    months = sorted(f for f in glob.glob(str(DATA / "20??-??.csv")) if Path(f).stem >= OLD_END[:4] + "-" + OLD_END[4:6])      # 11-10: 08~10 고정 → 옛 판 끝 달부터 있는 달 전부
    log("  월별 CSV %s" % [Path(f).stem for f in months])
    def rd(f):                                                         # 11-10: 서버 작업본 CSV 는 누가 git pull 해야 새로워진다 → panel_daily 가 origin/main 에서 받아 둔 사본(WORK/csv_*.csv)이 더 새로우면 그걸 쓴다
        a = pd.read_csv(f, dtype={"ticker": str, "date": str}); g = WORK / ("csv_" + Path(f).name)
        if g.exists():
            try:
                b = pd.read_csv(g, dtype={"ticker": str, "date": str})
                if len(b) and b.date.max() > a.date.max(): log("  %s — 받아 둔 사본이 더 새로움(%s > %s)" % (Path(f).name, b.date.max(), a.date.max())); return b
            except Exception as ex: log("  사본 못 읽음 %s %r" % (g.name, ex))
        return a
    csv = pd.concat([rd(f) for f in months], ignore_index=True)
    csv = csv[csv.date > OLD_END].drop(columns=["market"], errors="ignore")
    for c in ("open", "high", "low"): csv[c] = pd.to_numeric(csv[c], errors="coerce").where(lambda s: s > 0)
    c = ro(DATA / "kosdaq.db"); qdb = pd.read_sql("SELECT date,ticker,name,open,high,low,close,volume,frgn,organ FROM daily WHERE date>?", c, params=(OLD_END,)); c.close()
    for x in ("open", "high", "low"): qdb[x] = pd.to_numeric(qdb[x], errors="coerce").where(lambda s: s > 0)
    c = ro(DATA / "kis" / "market.db"); kis = pd.read_sql("SELECT date,ticker,close kis_close,volume kis_vol FROM short_sale WHERE date>?", c, params=(OLD_END,)); c.close()
    c = ro(DATA / "krx_daily.db"); sb = pd.read_sql("SELECT date,ticker,shrs,mktcap FROM short_balance WHERE date>?", c, params=(OLD_END,)); c.close()
    sb["shrs"] = pd.to_numeric(sb.shrs, errors="coerce"); sb["mktcap"] = pd.to_numeric(sb.mktcap, errors="coerce")
    sb["kc"] = np.round(sb.mktcap / sb.shrs.replace(0, np.nan))
    c = ro(DATA / "toss.db"); ti = pd.read_sql("SELECT date,ticker,frg_net,org_net FROM investor WHERE date>?", c, params=(OLD_END,)); c.close()
    # 1분봉 일봉: kr_daily + (거기 없는 종목은) bf·day 파일에서 직접
    kd = pd.read_parquet(DATA / "factory" / "live" / "kr_daily.parquet"); kd = kd[kd.date > OLD_END][["ticker", "date", "open", "high", "low", "close"]]
    t0 = int(pd.Timestamp("2026-08-29").timestamp())
    have = set(zip(kd.ticker, kd.date)); extra = []
    all_t = (set(kis.ticker) | set(sb.ticker)) - set(kd[kd.date == "20260917"].ticker)
    n = 0
    for t in sorted(all_t):
        f = DATA / "m1" / "KR" / "bf" / f"{t}.parquet"
        if not f.exists(): continue
        try: x = pd.read_parquet(f, filters=[("ts", ">=", t0)])
        except Exception: continue
        if len(x): extra.append(agg_m1(x)); n += 1
    log(f"  bf 에서 {n}종목 추가")
    for f in sorted(glob.glob(str(DATA / "m1" / "KR" / "day" / "*.parquet"))):
        extra.append(agg_m1(pd.read_parquet(f)))
    E = pd.concat(extra, ignore_index=True)
    E = E[[(a, b) not in have for a, b in zip(E.ticker, E.date)]]
    m1 = pd.concat([kd, E], ignore_index=True).drop_duplicates(["ticker", "date"]).rename(columns={"open": "m_o", "high": "m_h", "low": "m_l", "close": "m_c"})
    log(f"  1분봉 일봉 {len(m1):,}행 · 직접 합친 {len(E):,}행")
    last = min(kis.date.max(), csv.date.max())                         # 11-10: KIS 공매도 표(거래량·날 목록)나 월별 CSV 중 덜 온 쪽까지만 — 나머지 날은 다음 실행에
    csv = csv[csv.date <= last]; kis = kis[kis.date <= last]; sb = sb[sb.date <= last]
    days = sorted(set(kis.date))
    assert set(csv.date) == set(days), (sorted(set(csv.date) ^ set(days)))
    log(f"  새 거래일 {len(days)}일 {days[0]}~{days[-1]}")
    K = csv[["date", "ticker", "name", "open", "high", "low", "volume", "frgn", "organ", "close"]].rename(columns={"close": "csv_close", "volume": "csv_vol"}).assign(mk="KOSPI")
    kospi_keys = set(zip(K.ticker, K.date))
    Q0 = pd.concat([kis[["date", "ticker"]], sb[["date", "ticker"]]]).drop_duplicates()
    Q0 = Q0[[(a, b) not in kospi_keys for a, b in zip(Q0.ticker, Q0.date)]].assign(mk="KOSDAQ")
    Q = Q0.merge(qdb.rename(columns={"close": "csv_close", "volume": "csv_vol"}), on=["date", "ticker"], how="left")
    N = pd.concat([K, Q], ignore_index=True)
    N = N.merge(kis, on=["date", "ticker"], how="left").merge(sb[["date", "ticker", "shrs", "mktcap", "kc"]], on=["date", "ticker"], how="left").merge(m1, on=["date", "ticker"], how="left").merge(ti, on=["date", "ticker"], how="left")
    # 종가: 공식(kc) 우선. kc 가 KIS·1분봉 둘과 어긋나고 그 둘이 서로 맞으면(주식수 바뀐 날) 그 둘을 믿는다.
    agree = (np.abs(N.kis_close / N.m_c - 1) < 0.001)
    bad_kc = N.kc.notna() & agree & (np.abs(N.kc / N.kis_close - 1) > 0.002)
    N["close"] = N.kc.where(~bad_kc, N.kis_close)
    N["close_src"] = np.where(N.kc.notna() & ~bad_kc, "KRX", "")
    miss = N.close.isna()
    N.loc[miss, "close"] = N.m_c[miss]; N.loc[miss & N.m_c.notna(), "close_src"] = "M1"
    miss = N.close.isna()
    N.loc[miss, "close"] = N.kis_close[miss]; N.loc[miss & N.kis_close.notna(), "close_src"] = "KIS"
    N.loc[bad_kc, "close_src"] = "KIS"
    miss = N.close.isna()
    N.loc[miss, "close"] = N.csv_close[miss]; N.loc[miss & N.csv_close.notna(), "close_src"] = "CSV"
    # 거래량: KIS(=KRX, CSV·DB 와 99.6% 일치), 없으면 CSV
    N["volume"] = N.kis_vol.where(N.kis_vol.notna(), N.csv_vol)
    # 시가·고저: CSV/DB 가 먼저(옛 패널의 출처), 없으면 1분봉
    for a, b in (("open", "m_o"), ("high", "m_h"), ("low", "m_l")):
        N[a + "_src"] = np.where(N[a].notna(), "CSV", np.where(N[b].notna(), "M1", ""))
        N[a] = N[a].where(N[a].notna(), N[b])
    N["frgn_src"] = np.where(N.frgn.notna(), "NAVER", np.where(N.frg_net.notna(), "TOSS", ""))
    N["frgn"] = pd.to_numeric(N.frgn, errors="coerce"); N["organ"] = pd.to_numeric(N.organ, errors="coerce")
    N["frgn"] = N.frgn.where(N.frgn.notna(), N.frg_net); N["organ"] = N.organ.where(N.organ.notna(), N.org_net)
    N = N.sort_values(["ticker", "date"]).reset_index(drop=True)
    N["shares"] = N.groupby("ticker").shrs.ffill()
    N["marcap"] = N.mktcap.where(N.mktcap.notna(), N.close * N.shares)      # 원 단위
    keep = (N.close > 0) & (N.volume.fillna(0) > 0)
    log(f"  거래량 0·종가 없음 {int((~keep).sum()):,}행 제외(정지 — 옛 패널의 open>0 과 같은 뜻)")
    N = N[keep].copy()
    h = N[["high", "open", "close"]].max(axis=1); l = N[["low", "open", "close"]].min(axis=1)
    N["high"] = h.where(N.high.notna()); N["low"] = l.where(N.low.notna())
    # 이름
    nm = {}
    try: nm = json.load(open(DATA / "factory" / "names.json", encoding="utf-8"))
    except Exception: pass
    N["name"] = N.name.where(N.name.notna(), N.ticker.map(nm))
    N["short_ratio"] = None; N["grp"] = "생존"
    cols = BASECOLS + ["mk", "close_src", "open_src", "frgn_src", "kis_close", "csv_close", "kc"]
    N[cols].to_pickle(WORK / "new_base.pkl")
    # 채움표
    tab = N.groupby(["mk", "date"]).agg(rows=("close", "size"), open=("open", lambda s: s.notna().sum()), csvO=("open_src", lambda s: (s == "CSV").sum()), m1O=("open_src", lambda s: (s == "M1").sum()),
                                        krx=("close_src", lambda s: (s == "KRX").sum()), m1c=("close_src", lambda s: (s == "M1").sum()), kisc=("close_src", lambda s: (s == "KIS").sum()),
                                        fnaver=("frgn_src", lambda s: (s == "NAVER").sum()), ftoss=("frgn_src", lambda s: (s == "TOSS").sum()))
    print(tab.to_string())
    tab.reset_index().to_pickle(WORK / "fill_table.pkl")
    x = N.dropna(subset=["kc", "csv_close"]); print("CSV 종가 ≠ 공식(>0.05%) 날짜별 비율", (np.abs(x.csv_close / x.kc - 1) > 5e-4).groupby(x.date).mean().round(3).to_dict())
    log(f"새 행 {len(N):,} · 시가 빈 행 {int(N.open.isna().sum()):,} · kc 교정 {int(bad_kc.sum()):,}")


# ═══════════════════════════════════════════════════════════════════════
# 2. 패널 잇기 — 파생값은 build_panel.py · fix_panels.py 와 같은 식
# ═══════════════════════════════════════════════════════════════════════
class Static:
    """build_panel 의 보조 자료(업종·공시). 시장마다 다시 읽지 않게 한 번만."""
    def __init__(self):
        import csv as _c
        IND = {}
        for r in _c.DictReader(open(DATA / "industry.csv", encoding="utf-8-sig")):
            if r.get("ticker") and r.get("industry"): IND[r["ticker"]] = r["industry"]
        KS = {}
        for r in _c.DictReader(open(DATA / "ksic.csv", encoding="utf-8-sig")):
            k = r.get("ksic") or ""
            if r.get("ticker") and k: KS[r["ticker"]] = "KSIC" + k[:3]
        self.SECT = dict(KS); self.SECT.update(IND)
        c = ro(DATA / "kospi.db"); SH = pd.read_sql("SELECT snap,ticker,gname FROM sector WHERE kind='upjong'", c); c.close()
        self.SNAPS = np.array(sorted(SH.snap.unique()))
        self.SHMAP = {(s, t): g for s, t, g in zip(SH.snap, SH.ticker, SH.gname)}
        self.NSNAP = SH.groupby("snap").size().reindex(self.SNAPS).values
        log(f"업종 스냅샷 끝 {self.SNAPS[-4:].tolist()} · 스냅샷당 종목 {SH.groupby('snap').size().tail(4).to_dict()}")
        d = ro(DATA / "dart" / "disclosures.db")
        dz = pd.read_sql("SELECT stock_code t, rcept_dt FROM disclosure WHERE replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%' OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'", d)
        self.DIL = defaultdict(list)
        for r in dz.itertuples(): self.DIL[r.t].append(r.rcept_dt)
        bz = pd.read_sql("SELECT stock_code t, rcept_dt, report_nm FROM disclosure WHERE length(stock_code)=6 AND replace(report_nm,' ','') LIKE '%자기주식취득결정%'", d)
        nm = bz.report_nm.str.replace(" ", "", regex=False)
        bz = bz[~nm.str.contains("신탁") & ~nm.str.contains("정정")]
        self.BBSET = set(zip(bz.t, bz.rcept_dt))
        iz = pd.read_sql("SELECT stock_code t, rcept_dt FROM disclosure WHERE length(stock_code)=6 AND replace(report_nm,' ','') LIKE '%임원ㆍ주요주주특정증권등소유상황보고서%'", d)
        d.close()
        self.INS = defaultdict(list)
        for r in iz.itertuples(): self.INS[r.t].append(r.rcept_dt)
        c = ro(DATA / "dart" / "financials.db")
        F = pd.read_sql("SELECT stock_code ticker, year, reprt, fs_div, account, amount FROM fin WHERE account IN ('부채총계','자본총계')", c); c.close()
        F = F.pivot_table(index=["ticker", "year", "reprt", "fs_div"], columns="account", values="amount", aggfunc="first").reset_index()
        F = F[F["자본총계"] > 0]; F["dbt"] = F["부채총계"] / F["자본총계"] * 100
        F["_pri"] = (F.fs_div == "CFS").astype(int)
        F = F.sort_values("_pri", ascending=False).drop_duplicates(["ticker", "year", "reprt"])
        AV = {"11013": "0515", "11012": "0815", "11014": "1115", "11011": "0401"}
        F["availn"] = [int(f"{y+1}{AV[r]}" if r == "11011" else f"{y}{AV[r]}") for y, r in zip(F.year, F.reprt)]
        self.FIN = F[["ticker", "availn", "dbt"]].dropna().sort_values("availn")
        log(f"재무 끝 공시 가능일 {self.FIN.availn.max()}")
        c = ro(DATA / "krx_daily.db")
        self.VAL = pd.read_sql("SELECT date, ticker, pbr AS PBR, per AS PER, bps AS BPS FROM fundamental WHERE date>?", c, params=(OLD_END,)); c.close()
        c = ro(DATA / "kis" / "market.db"); s = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE date>='20260101'", c); c.close()
        s["short_ratio"] = pd.to_numeric(s.short_ratio, errors="coerce"); s = s.sort_values(["ticker", "date"])
        g = s.groupby("ticker", sort=False).short_ratio
        s["sr20"] = g.transform(lambda x: x.rolling(20).mean())
        s["srd"] = (g.transform(lambda x: x.rolling(5).mean()) < s.sr20).astype(object)
        few = g.transform(lambda x: x.rolling(20).count()) < 20
        s.loc[few, "srd"] = np.nan; s.loc[few, "sr20"] = np.nan
        self.SR = s[["ticker", "date", "sr20", "srd"]]

    def sector_of(self, dates, tickers):
        # ⚠ 20260828 스냅샷은 코스피 917종목뿐이고 세분류(76묶음)라 옛 묶음(26묶음)과 끊긴다(옛 판 8/28 행이 그렇다).
        #   u ≤ -10·-20 문턱은 옛 묶음으로 잰 값이다 → 온전한 마지막 스냅샷(20260715)을 쓰고, 없으면 현재 분류.
        full = self.SNAPS[self.NSNAP >= 3000]
        i = np.clip(np.searchsorted(full, np.asarray(dates), side="right") - 1, 0, len(full) - 1)
        snap = full[i]
        return [self.SHMAP.get((s, t)) or self.SECT.get(t) for s, t in zip(snap, tickers)]


def derive(df, ST):
    """build_panel.build() 의 파생값. df 는 ticker,date 정렬·연속 인덱스."""
    g = df.groupby("ticker", sort=False)
    V, C = df.volume.astype(float), df.close.astype(float)
    df["vm1"] = V; df["vm3"] = g["volume"].transform(lambda x: x.rolling(3).mean())
    df["a40"] = g["volume"].transform(lambda x: x.shift(3).rolling(40).mean())
    df["a240"] = g["volume"].transform(lambda x: x.shift(43).rolling(240).mean())
    df["r16"] = df.a40 / df.a240 * 100
    df["rw1"] = df.vm3 / df.a40 * 100
    df["su1"] = df.vm1 / g["volume"].transform(lambda x: x.shift(1).rolling(20).mean())
    amt = V * C
    df["amt20"] = amt.groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
    df["amt"] = amt.groupby(df.ticker).transform(lambda x: x.rolling(40).mean()).shift(3) / 1e8
    for w in (5, 20, 60):
        vs = g["volume"].transform(lambda x, w=w: x.rolling(w).sum()).replace(0, np.nan)
        df["fw%d" % w] = g["frgn"].transform(lambda x, w=w: x.fillna(0).rolling(w).sum()) / vs * 100
        df["ow%d" % w] = g["organ"].transform(lambda x, w=w: x.fillna(0).rolling(w).sum()) / vs * 100
    for n in (3, 5, 10, 20, 60, 120):
        df["ret%d" % n] = g.close.transform(lambda x, n=n: x / x.shift(n) - 1) * 100
    for w in (5, 20, 60, 120):
        df["ma%d" % w] = g.close.transform(lambda x, w=w: x.rolling(w).mean())
        df["dma%d" % w] = (C / df["ma%d" % w] - 1) * 100
    df["hi250"] = g.close.transform(lambda x: x.rolling(250, min_periods=60).max())
    df["lo250"] = g.close.transform(lambda x: x.rolling(250, min_periods=60).min())
    df["fromhi"] = (C / df.hi250 - 1) * 100
    df["fromlo"] = (C / df.lo250 - 1) * 100
    df["vol20"] = g.close.transform(lambda x: (x / x.shift(1) - 1).rolling(20).std()) * 100
    df["rng"] = (df.high - df.low) / C * 100
    df["clv"] = np.where(df.high > df.low, (C - df.low) / (df.high - df.low), 0.5)
    df.loc[df.high.isna(), ["rng", "clv"]] = np.nan
    df["hi60"] = g.close.transform(lambda x: x.rolling(60, min_periods=20).max())
    df["dd"] = (C / df.hi60 - 1) * 100
    df["mdd60"] = df.dd.groupby(df.ticker).transform(lambda x: x.rolling(60, min_periods=20).min())
    df["y"] = df.date.str[:4].astype(int)
    df["buy"] = g.open.shift(-1)
    df["gap"] = (df.buy / C - 1) * 100
    df["cost"] = 0.23 + np.select([df.amt20 >= 100, df.amt20 >= 50, df.amt20 >= 20, df.amt20 >= 10], [.20, .30, .50, .70], default=1.00)
    return df


def flags(df, ST, dates):
    DI = {d: i for i, d in enumerate(dates)}
    ds = pd.to_datetime(df.date); dil = np.zeros(len(df), bool)
    for t, idx in df.groupby("ticker").indices.items():
        L = pd.to_datetime(ST.DIL.get(t, []))
        if len(L) == 0: continue
        v = ds.values[idx]
        dil[idx] = ((L.values[None, :] >= v[:, None] - np.timedelta64(90, "D")) & (L.values[None, :] <= v[:, None])).any(axis=1)
    df["dil"] = dil
    df["bb"] = [(t, d) in ST.BBSET for t, d in zip(df.ticker, df.date)]
    ins = np.zeros(len(df), np.int32); pos60 = df.date.map(DI).values
    for t, idx in df.groupby("ticker").indices.items():
        L = ST.INS.get(t)
        if not L: continue
        lp = np.sort([DI[x] for x in L if x in DI])
        if not len(lp): continue
        v = pos60[idx]
        ins[idx] = np.searchsorted(lp, v, side="right") - np.searchsorted(lp, v - 60, side="left")
    df["ins60"] = ins
    return df


def forward(df, dates):
    """buy·gap·n{h} — build_panel + fix_panels(②·②-b·②-c) 를 합친 식. df 는 정렬돼 있다."""
    DI = {d: i for i, d in enumerate(dates)}
    g = df.groupby("ticker", sort=False)
    C = df.close.astype(float)
    mypos = df.date.map(DI).astype(np.int64)
    lastpos = g.date.transform("max").map(DI); lastclose = g.close.transform("last")
    buy = g.open.shift(-1)
    nxt = g.date.shift(-1).map(DI)
    bad = (nxt - mypos != 1) & (mypos != lastpos)
    pc = g.close.shift(1)
    lim = np.where(df.date.values < "20150615", 0.15, 0.30) + 0.10
    ca = ((buy.notna() & ((buy / C > 1 + lim) | (buy / C < 1 - lim))) | (pc.notna() & ((C / pc > 1 + lim) | (C / pc < 1 - lim))))
    bad = bad | ca | (g.volume.shift(-1).fillna(0) <= 0)
    cs = ca.astype(np.int32).groupby(df.ticker, sort=False).cumsum()
    out = {"gap": (buy / C - 1) * 100}
    for h in HZ:
        sell = g.close.shift(-h).where(~(mypos + h > lastpos), lastclose)
        span = (mypos + h <= lastpos) & (g.date.shift(-h).map(DI) - mypos != h)
        thru = (cs.groupby(df.ticker, sort=False).shift(-h) - cs > 0).fillna(False)
        sv0 = g.volume.shift(-h).fillna(1) <= 0
        out["n%d" % h] = ((sell / buy - 1) * 100 - df.cost).where(~(bad | span | thru | sv0))
    out["buy"] = buy.where(~bad)
    return out, mypos, lastpos, ca


def extend(fn, mk, N, ST):
    log(f"── {fn} ──")
    P = pd.read_pickle(base(fn))
    attrs = dict(P.attrs)
    log(f"  옛 판 {len(P):,}행 · {P.date.max()} · attrs {attrs}")
    n_mk = N[N.mk == mk]
    ud = sorted(P.date.unique()); wstart = ud[-430]; olddays = [d for d in ud if d >= wstart]
    W = P.loc[P.date >= wstart, BASECOLS].copy()
    W["_old"] = True
    X = n_mk[BASECOLS].copy(); X["_old"] = False
    X["name"] = X.name.where(X.name.notna(), X.ticker.map(P.drop_duplicates("ticker", keep="last").set_index("ticker").name))
    # 시장을 옮긴 종목 등 — 같은 (종목,날짜) 는 옛 판이 이긴다
    D = pd.concat([W, X], ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
    assert not D.duplicated(["ticker", "date"]).any()
    for c in ("open", "high", "low", "close", "volume", "frgn", "organ", "marcap", "shares"): D[c] = pd.to_numeric(D[c], errors="coerce").astype(float)
    dates = sorted(D.date.unique())
    D = derive(D, ST); D = flags(D, ST, dates)
    # 업종·재무·밸류·공매도는 새 행에만 붙인다
    isnew = ~D._old
    D["up"] = None
    D.loc[isnew, "up"] = pd.Series(ST.sector_of(D.date[isnew].values, D.ticker[isnew].values), index=D.index[isnew])
    oldk = P.loc[P.date >= wstart, ["ticker", "date", "up"]].rename(columns={"up": "up_o"})
    D = D.merge(oldk, on=["ticker", "date"], how="left"); D["up"] = D.up.where(D.up.notna(), D.up_o); D = D.drop(columns=["up_o"])
    d2 = D[D.up.notna()].dropna(subset=["ret60"])
    gm = d2.groupby(["date", "up"]).ret60
    m = gm.median()[gm.size() >= 5]
    D["u"] = pd.MultiIndex.from_arrays([D.date, D.up]).map(m)
    fwd, mypos, lastpos, ca = forward(D, dates)
    for k, v in fwd.items(): D["f_" + k] = v
    # ── 앞부분 대조: 옛 값을 파생식으로 다시 계산해 같은지 ──
    OC = ["amt20", "amt", "a40", "a240", "r16", "rw1", "su1", "fw5", "fw20", "fw60", "ow5", "ow20", "ow60", "ret3", "ret5", "ret10", "ret20", "ret60", "ret120", "dma5", "dma20", "dma60", "dma120", "fromhi", "fromlo", "vol20", "rng", "clv", "dd", "mdd60", "cost", "dil", "bb", "ins60", "u"]
    chk0 = dates[dates.index(ud[-1]) - 60]
    Q = D[D._old & (D.date >= chk0)]
    S = P.loc[P.date >= chk0, ["ticker", "date"] + OC + ["buy", "gap"] + ["n%d" % h for h in HZ]]
    M = Q.merge(S, on=["ticker", "date"], suffixes=("", "_s"))
    res = {}
    for c in OC:
        a = pd.to_numeric(M[c], errors="coerce").astype(float); b = pd.to_numeric(M[c + "_s"], errors="coerce").astype(float)
        both = a.notna() & b.notna()
        res[c] = dict(n=int(both.sum()), diff=int((np.abs(a[both] - b[both]) > np.maximum(1e-4, np.abs(b[both]) * 1e-3)).sum()), nan_mis=int((a.isna() != b.isna()).sum()))
    # 옛 판 안에서 보유가 끝나는 선행수익은 같아야 한다
    oldpos = {d: i for i, d in enumerate(ud)}; M["_p"] = M.date.map(oldpos)
    tl = P.groupby("ticker").date.max().map(oldpos); M["_lp"] = M.ticker.map(tl)
    for c, h in [("buy", 1)] + [("n%d" % h, h) for h in HZ]:
        inside = M._p + h <= M._lp
        a = M["f_" + c].where(inside); b = M[c + "_s" if c + "_s" in M.columns else c].where(inside)
        both = a.notna() & b.notna()
        res["fwd_" + c] = dict(n=int(both.sum()), diff=int((np.abs(a[both] - b[both]) > 1e-3 * np.maximum(1, np.abs(b[both]))).sum()), nan_mis=int((a[inside].isna() != b[inside].isna()).sum()))
    print(pd.DataFrame(res).T.to_string())
    save(f"recheck_{mk}.json", res)
    # ── 옛 행 고치기: 보유가 옛 패널 끝을 넘어 '마지막 종가 청산' 으로 들어간 것만 진짜 값으로 ──
    nt = set(X.ticker)
    tail = D[D._old & D.ticker.isin(nt) & (D.date >= dates[dates.index(ud[-1]) - 70])].copy()
    tail["_p"] = tail.date.map({d: i for i, d in enumerate(dates)})
    allpos = {d: i for i, d in enumerate(dates)}
    tail["_lp"] = tail.ticker.map(P[P.ticker.isin(nt)].groupby("ticker").date.max().map(allpos))
    upd = {}
    idx = P.index[P.date >= tail.date.min()]
    Pmap = pd.Series(idx, index=pd.MultiIndex.from_frame(P.loc[idx, ["ticker", "date"]]))
    tail["_ix"] = Pmap.reindex(pd.MultiIndex.from_frame(tail[["ticker", "date"]])).values
    tail = tail.dropna(subset=["_ix"]); tail["_ix"] = tail._ix.astype(np.int64)
    changed = {}
    for h in HZ:
        c = "n%d" % h
        m_ = tail._p + h > tail._lp
        changed[c] = int(m_.sum())
        P.loc[tail._ix[m_].values, c] = tail["f_" + c][m_].values
    m_ = tail._p == tail._lp
    P.loc[tail._ix[m_].values, "buy"] = tail.f_buy[m_].values; P.loc[tail._ix[m_].values, "gap"] = tail.f_gap[m_].values
    log(f"  옛 행 선행수익 교체: 끝 행 {int(m_.sum()):,} · n60 {changed['n60']:,}행 · n5 {changed['n5']:,}행 · 끝이 패널 밖")
    pd.to_pickle(tail[["ticker", "date", "_p", "_lp", "f_buy", "f_gap"] + ["f_n%d" % h for h in (5, 10, 20, 40, 60)]], WORK / f"tail_{mk}.pkl")
    # ── 새 행 ──
    Y = D[~D._old].copy()
    Y = Y.merge(ST.SR, on=["ticker", "date"], how="left")
    _L = Y[["ticker", "date"]].copy(); _L["daten"] = _L.date.astype(int); _L = _L.sort_values("daten")
    _M = pd.merge_asof(_L, ST.FIN, left_on="daten", right_on="availn", by="ticker", direction="backward")
    Y["부채비율"] = pd.Series(_M.dbt.values, index=_L.index).reindex(Y.index)
    Y = Y.merge(ST.VAL, on=["ticker", "date"], how="left")
    for k in ("buy", "gap"): Y[k] = Y["f_" + k]
    for h in HZ: Y["n%d" % h] = Y["f_n%d" % h]
    pc = Y.groupby("ticker", sort=False).close.shift(1)
    jj = (Y.close / pc).where(pc > 0); Y["bad"] = ((jj > 1.32) | (jj < 0.68)).fillna(False)
    Yc = Y.reindex(columns=P.columns)
    log(f"  새 행 {len(Yc):,} · {Yc.date.min()}~{Yc.date.max()} · {Yc.ticker.nunique()}종목")
    print("  새 행 결측률", Yc.isna().mean().round(3).loc[lambda s: s > 0.02].to_dict())
    jump = Y[np.isin(Y.index, np.flatnonzero(False))]
    ca_new = D.loc[ca & ~D._old, ["ticker", "date", "close"]]
    print("  새 구간 가격제한폭 초과(분할·병합 후보)", len(ca_new), ca_new.head(30).to_dict("records"))
    N2 = pd.concat([P, Yc], ignore_index=True)
    N2.attrs = attrs
    # 정렬은 옛 판과 같게(ticker,date)
    N2 = N2.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True); N2.attrs = attrs
    out = fn.replace(".pkl", "_new.pkl")
    tmp = DATA / (out + ".tmp"); N2.to_pickle(tmp); tmp.replace(DATA / out)
    log(f"  저장 {out} · {len(N2):,}행")
    # kr_scan 용 창 자료
    W2 = D[["ticker", "date", "close", "_old"]].copy(); W2["mk"] = mk
    W2.to_pickle(WORK / f"win_{mk}.pkl")
    Yc.to_pickle(WORK / f"newrows_{mk}.pkl")
    del P, D, N2, Q, M; gc.collect()


COLS = ["date", "ticker", "open", "high", "low", "close", "volume", "amt20", "buy", "cost", "up", "u", "n5", "n10", "n20", "n40", "n60", "dma5", "dma20", "dma60", "dma120",
        "ret3", "ret5", "ret10", "ret20", "ret60", "ret120", "fromhi", "fromlo", "dd", "mdd60", "vol20", "rng", "clv", "gap", "vm1", "vm3", "a40", "a240", "r16", "rw1", "su1",
        "PBR", "PER", "부채비율", "marcap", "sr20", "srd", "dil"]


def build_scan():
    log("── kr_scan_new ──")
    A = pd.read_pickle(base("kr_scan.pkl")); attrs = dict(A.attrs)
    cols = list(A.columns)
    out = []
    for mk in ("KOSPI", "KOSDAQ"):
        Y = pd.read_pickle(WORK / f"newrows_{mk}.pkl")[COLS].copy(); Y["mk"] = mk
        W = pd.read_pickle(WORK / f"win_{mk}.pkl")
        W = W.sort_values(["ticker", "date"]).reset_index(drop=True)
        g = W.groupby("ticker", sort=False)
        W["ret250"] = (W.close / g.close.shift(250) - 1) * 100
        W["dev25"] = (W.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
        pc = g.close.shift(1); lim = 0.40
        ca = (pc.notna() & ((W.close / pc > 1 + lim) | (W.close / pc < 1 - lim))).astype(np.int32)
        cs = ca.groupby(W.ticker).cumsum()
        W["jw"] = ((cs - cs.groupby(W.ticker).shift(250).fillna(0)) > 0).values
        ma20 = g.close.transform(lambda s: s.rolling(20).mean())
        W["above20"] = (W.close > ma20).groupby(W.ticker).transform(lambda s: s.rolling(250, min_periods=60).mean()) * 100
        # 옛 값 재현 점검(창 앞 250행 뒤의 옛 행)
        Z = W[W._old & (W.date >= "20260601")].merge(A[A.date >= "20260601"][["ticker", "date", "ret250", "dev25", "jw", "above20"]], on=["ticker", "date"], suffixes=("", "_s"))
        print(mk, "kr_scan 파생 재현", {c: int((np.abs(Z[c].astype(float) - Z[c + "_s"].astype(float)) > 1e-2).sum()) for c in ("ret250", "dev25", "above20")}, "jw 다름", int((Z.jw != Z.jw_s).sum()), "/", len(Z))
        Y = Y.merge(W.loc[~W._old, ["ticker", "date", "ret250", "dev25", "jw", "above20"]], on=["ticker", "date"], how="left")
        tail = pd.read_pickle(WORK / f"tail_{mk}.pkl")
        out.append((Y, tail))
    Y = pd.concat([o[0] for o in out], ignore_index=True); Y["pref"] = ~Y.ticker.str.endswith("0")
    tail = pd.concat([o[1] for o in out], ignore_index=True)
    # 옛 행 교체
    ix = A.index[A.date >= tail.date.min()]
    mp = pd.Series(ix, index=pd.MultiIndex.from_frame(A.loc[ix, ["ticker", "date"]]))
    tail["_ix"] = mp.reindex(pd.MultiIndex.from_frame(tail[["ticker", "date"]])).values
    tail = tail.dropna(subset=["_ix"]); tail["_ix"] = tail._ix.astype(np.int64)
    for h in (5, 10, 20, 40, 60):
        m_ = tail._p + h > tail._lp
        A.loc[tail._ix[m_].values, "n%d" % h] = tail["f_n%d" % h][m_].values.astype(np.float32)
    m_ = tail._p == tail._lp
    A.loc[tail._ix[m_].values, "buy"] = tail.f_buy[m_].values.astype(np.float32); A.loc[tail._ix[m_].values, "gap"] = tail.f_gap[m_].values.astype(np.float32)
    Y = Y.reindex(columns=cols)
    for c in Y.columns:
        if A[c].dtype == np.float32: Y[c] = pd.to_numeric(Y[c], errors="coerce").astype("float32")
    Y["dil"] = Y.dil.astype(bool); Y["pref"] = Y.pref.astype(bool); Y["jw"] = Y.jw.fillna(False).astype(bool)
    N = pd.concat([A, Y], ignore_index=True).sort_values(["ticker", "date"], kind="stable").reset_index(drop=True); N.attrs = attrs
    tmp = DATA / "kr_scan_new.pkl.tmp"; N.to_pickle(tmp); tmp.replace(DATA / "kr_scan_new.pkl")
    log(f"저장 kr_scan_new.pkl · {len(N):,}행 · {N.date.max()} · 열 {len(N.columns)}")
    print(N.dtypes.astype(str).value_counts().to_dict(), "옛", A.dtypes.astype(str).value_counts().to_dict())


def verify_old():
    """옛 판 전체 대조 — 같은 날·같은 종목 값이 달라지면 안 된다. 허용: 패널 끝을 넘긴 선행수익."""
    log("── 앞부분 전수 대조 ──")
    rep = {}
    for old, new in (("kr_scan.pkl", "kr_scan_new.pkl"), ("panel_kp.pkl", "panel_kp_new.pkl"), ("panel_kq.pkl", "panel_kq_new.pkl")):
        A = pd.read_pickle(base(old)); B = pd.read_pickle(DATA / new)
        B = B[B.date <= OLD_END].reset_index(drop=True); A = A.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
        assert len(A) == len(B) and (A.ticker.values == B.ticker.values).all() and (A.date.values == B.date.values).all(), (old, len(A), len(B))
        dif = {}
        ud = sorted(A.date.unique())
        for c in A.columns:
            a, b = A[c], B[c]
            if a.dtype == object:
                ne = ~((a == b) | (a.isna() & b.isna()))
            else:
                x, y = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
                ne = ~((x == y) | (np.isnan(x) & np.isnan(y)))
            n = int(np.sum(ne))
            if n:
                dd = A.date[ne]
                dif[c] = dict(n=n, first=str(dd.min()), last=str(dd.max()))
        rep[old] = dict(rows=len(A), diff=dif, days61=ud[-61])
        print(old, "행", len(A), "다른 열", dif)
        del A, B; gc.collect()
    save("verify_old.json", rep)


def stage_kr():
    N = pd.read_pickle(WORK / "new_base.pkl")
    ST = Static()
    extend("panel_kp.pkl", "KOSPI", N, ST)
    extend("panel_kq.pkl", "KOSDAQ", N, ST)
    build_scan()
    verify_old()


def run_audit(what):
    """audit_contam.py 를 파일 이름만 바꿔 돌린다(원본 수정 없음)."""
    src = (BASE / "audit_contam.py").read_text(encoding="utf-8")
    for lab, a, b in what:
        s = src.replace('"kr_scan.pkl"', '"%s"' % a).replace('"us_scan.pkl"', '"%s"' % a)
        print("\n########## %s (%s) ##########" % (lab, a), flush=True)
        sys.argv = ["audit_contam.py", b]
        ns = {"__file__": str(BASE / "audit_contam.py"), "__name__": "__main__"}
        exec(compile(s, "audit_contam.py", "exec"), ns)
        gc.collect()



# ═══════════════════════════════════════════════════════════════════════
# 3. 미장 — 토스 미지원 판별
# ═══════════════════════════════════════════════════════════════════════
def us_kind(n, b=""):
    u = (n or "").upper()
    if not u: return "이름없음"
    if re.search(r"\bWARRANTS?\b|\bWTS?\b", u): return "워런트"
    if re.search(r"\bRIGHTS?\b(?! AGREEMENT)", u): return "권리"
    if re.search(r"\bUNITS?\b", u):
        # MLP(CQP·WES·EVEP)·묶음 주식(STAY) 은 SPAC 유닛이 아니다 — 토스에도 MLP 는 있다(PAA 등)
        if (len(b) >= 4 and b.endswith("U")) or re.search(r"ACQUISITION|TANGIBLE|EQUITY UNIT|UNITS? \(|UNIT 1|\bSPAC\b|MERGER", u): return "유닛"
        return "MLP·묶음유닛"
    if re.search(r"\bNOTES?\b|\bDEBENTURE|\bBONDS?\b|SENIOR SUB|\bDUE 20\d\d|\bDUE \d\d/", u): return "채권형"
    if "AMERICAN DEPOSIT" in u: return "기타"          # ADR 은 토스에 있다(유형 DEPOSITARY_RECEIPT)
    if re.search(r"PREFERRED|\bPFD\b|\bPREF\b|\bPRF\b|PREFERENCE|DEPOSITARY SH|DEPOSITORY SH|PERPETUAL|CAPITAL SECURITIES|\bTOPRS\b|CUMULATIVE|NON-?CUM", u): return "우선주류"
    if re.search(r"ACQUISITION|\bSPAC\b|MERGER CORP|BLANK CHECK", u): return "SPAC보통주"
    return "기타"


def stage_us():
    log("── 미장 판별 ──")
    U = pd.read_pickle(DATA / "us_scan_full.pkl")
    tk = U.drop_duplicates("ticker", keep="last")[["ticker", "grp", "date"]].rename(columns={"date": "last"}).reset_index(drop=True)
    T = pd.read_csv(DATA / "us" / "toss_us.csv", dtype=str, keep_default_na=False); ts = set(T.symbol)
    c = ro(DATA / "us" / "tiingo_dead.db"); nm = pd.read_sql("select ticker,name from names", c); mp = pd.read_sql("select ticker,name from metap", c); c.close()
    tc = pd.read_pickle(DATA / "us" / "tiingo_cik.pkl")[["ticker", "name"]]
    L = pd.read_csv(DATA / "us" / "tickers.csv", dtype=str, keep_default_na=False).rename(columns={"Symbol": "ticker", "Name": "name"})[["ticker", "name"]]
    fm = pd.read_csv(DATA / "us" / "tiingo_fund_meta.csv", dtype=str, keep_default_na=False)[["ticker", "name"]]
    names = pd.concat([L, tc, nm, mp, fm], ignore_index=True).dropna(subset=["name"]); names = names[names.name.str.len() > 0].drop_duplicates("ticker").set_index("ticker").name
    tk["b"] = tk.ticker.str.replace("^D", "", regex=False)
    tk["name"] = tk.b.map(names)
    tk["kind"] = [us_kind(n if isinstance(n, str) else None, b) for n, b in zip(tk.name, tk.b)]
    # 폐지 종목은 이름이 없어도 티커 꼴(5글자 U·W·R)로 본다 — 나스닥 유닛·워런트·권리 표기
    five = (tk.b.str.len() == 5) & (tk.kind == "이름없음")
    tk.loc[five & tk.b.str[-1].eq("U"), "kind"] = "유닛"; tk.loc[five & tk.b.str[-1].eq("W"), "kind"] = "워런트"; tk.loc[five & tk.b.str[-1].eq("R"), "kind"] = "권리"
    tk["in_toss"] = tk.b.isin(ts) | tk.b.str.replace("-", ".").isin(ts) | tk.b.str.replace(".", "-", regex=False).isin(ts)
    live = tk.grp == "생존"
    cov = tk[live].groupby("kind").in_toss.agg(["size", "sum"]); cov["토스있음%"] = (cov["sum"] / cov["size"] * 100).round(1)
    print("살아 있는 종목의 유형별 토스 커버리지"); print(cov.to_string())
    print("폐지 유형 분포", tk[~live].kind.value_counts().to_dict())
    DROPK = ("유닛", "권리", "워런트", "채권형")            # 살아 있는 종목 기준 토스 커버리지가 12% 이하인 유형(워런트는 살아 있는 표본 자체가 없음)
    tk["V1"] = live & ~tk.in_toss                        # 지금 명단 밖(살아 있는 종목만)
    tk["V2"] = tk.V1 | (~live & tk.kind.isin(DROPK))     # 본판: + 폐지 종목 중 같은 유형
    tk["V3"] = ~tk.in_toss                               # 글자 그대로(폐지 전멸 — 생존편향, 참고만)
    tk["V4"] = tk.V2 & ~(live & (tk.kind == "기타"))     # 본판에서 '보통주처럼 보이는데 지금 명단에 없는' 살아 있는 종목은 남긴 판(민감도)
    tk.to_pickle(WORK / "us_kinds.pkl")
    print(tk[["V1", "V2", "V3", "V4"]].sum().to_dict(), "· V1 유형", tk[tk.V1].kind.value_counts().to_dict(), "· V2 폐지분 유형", tk[tk.V2 & ~live].kind.value_counts().to_dict())
    drop = set(tk[tk.V2].ticker)
    m = ~U.ticker.isin(drop).to_numpy()
    uni = ((U.groupby("date").amt20.rank(pct=True) >= .6) & (U.rawclose >= 3)).to_numpy()
    print("행 제거", int((~m).sum()), "/", len(U), "· 유니버스($3↑·거래대금 상위 40%) 안 비중", round(float((~m & uni).sum() / uni.sum()) * 100, 3), "%"); del uni
    cnt = pd.Series(U.date.to_numpy()[m]).value_counts().sort_index(); med = cnt.rolling(60, min_periods=20, center=True).median()
    thin = list(cnt[cnt < med * 0.6].index); print("반쪽 수집일", thin)
    keep = m & ~U.date.isin(thin).to_numpy(); del m
    CHK = ("date", "ticker", "close", "rawclose", "volume", "ret20", "PBR", "amt20", "cost")
    h0 = {c: _hash(U[c].to_numpy()[keep]) for c in CHK}
    idx = np.flatnonzero(keep); n = len(idx); del keep
    for b_ in U._mgr.blocks:                             # 제자리 당기기 — 복사본을 안 만들어 RAM 을 아낀다
        v = b_.values
        assert v.ndim == 2
        for j in range(v.shape[0]): v[j, :n] = v[j, idx]
    del idx
    P = U.iloc[:n]; P.index = pd.RangeIndex(n); gc.collect()
    h1 = {c: _hash(P[c].to_numpy()) for c in CHK}
    print("당긴 뒤 값 대조(열 해시)", {c: h0[c] == h1[c] for c in CHK})
    assert h0 == h1
    a_ = pd.factorize(P.date)[0].astype(np.int64); b2 = pd.factorize(P.up)[0].astype(np.int64)
    key = a_ * 100000 + b2; r = P.ret60.to_numpy(dtype=np.float64); ok = (b2 >= 0) & ~np.isnan(r)
    med_ = pd.Series(r[ok]).groupby(key[ok]).median()
    un = pd.Series(key).map(med_).where(b2 >= 0).to_numpy(dtype=np.float32)
    du = np.abs(un - P.u.to_numpy()); print("u 바뀐 크기 |차이| 중앙", round(float(np.nanmedian(du)), 3), "· 99%", round(float(np.nanquantile(du, .99)), 3), "· 최대", round(float(np.nanmax(du)), 2)); del a_, b2, key, r, ok, med_, du
    P["u"] = un; del un
    _repair_us(P); peak("수리")
    tmp = DATA / "us_scan_full_notoss.pkl.tmp"; P.to_pickle(tmp); tmp.replace(DATA / "us_scan_full_notoss.pkl")
    log(f"저장 us_scan_full_notoss.pkl · {len(P):,}행 · {P.ticker.nunique():,}종목 · 폐지 {P[P.grp == '폐지'].ticker.nunique():,} · 끝 {P.date.max()}"); peak("저장")


def smoke():
    """run_spec.load_market 이 새 판을 읽는지 — 코드 수정 없이 경로만 바꿔 실행."""
    import importlib
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
    s = (ROOT / "run_spec.py").read_text(encoding="utf-8")
    a = s.index("def load_market(mk):"); b = s.index("def old_signals(mk):")
    src = s[a:b].replace('"data/kr_scan.pkl"', '"data/kr_scan_new.pkl"')
    ns = dict(pd=pd, np=np, BASE=BASE, TR0="20160101", log=log)
    exec(src, ns)
    A, uni, since = ns["load_market"]("KR")
    print("KR load_market", len(A), A.date.max(), "유니버스", int(uni.sum()), "끝 날 유니버스", int(uni[A.date == A.date.max()].sum()), "· 새 구간 gap0 결측", round(float(A[A.date > OLD_END].gap0.isna().mean()), 3)); del A, uni; gc.collect()
    os.environ["US_PANEL"] = "us_scan_full_notoss.pkl"
    A, uni, since = ns["load_market"]("US"); print("US load_market", len(A), A.date.max(), "유니버스", int(uni.sum()))


# ═══════════════════════════════════════════════════════════════════════
# 4. 미장 규칙 — 포함/제외 (H0306 = research/us_rules_recheck.py 정의 그대로)
#    다른 점: 지수는 네트워크 대신 research/cache/us500.pkl(종가). 시가가 없어 '매수일 시가' 를 전날 종가로 갈음.
#    trials·보고서 파일은 건드리지 않는다.
# ═══════════════════════════════════════════════════════════════════════
def stage_us_rules():
    import contextlib, io, zipfile
    X = pd.read_pickle(ROOT / "cache" / "us500.pkl")[["Close"]].copy(); X["Open"] = X.Close.shift(1)
    fake = types.ModuleType("FinanceDataReader"); fake.DataReader = lambda sym, start=None, *a, **k: X[X.index >= pd.Timestamp(start)].copy() if sym == "US500" else (_ for _ in ()).throw(RuntimeError("네트워크 금지 " + sym))
    sys.modules["FinanceDataReader"] = fake
    sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
    argv0 = sys.argv
    tk = pd.read_pickle(WORK / "us_kinds.pkl")
    DROP = {"V2": set(tk[tk.V2].ticker), "V4": set(tk[tk.V4].ticker)}     # V0·V1·V3 은 앞선 실행 그대로(명단이 안 바뀌었다)
    A2 = pd.read_pickle(DATA / "us_full_2007.pkl")[["ticker", "date", "sic2", "ret60"]].sort_values(["ticker", "date"]).reset_index(drop=True)
    gc.collect()
    for v, drop in DROP.items():
        am = ~A2.ticker.isin(drop)
        ua = A2[am].groupby(["date", "sic2"]).ret60.transform("median").reindex(A2.index).to_numpy(dtype=np.float32)
        np.save(WORK / f"u_{v}.npy", ua); del ua, am
    del A2; gc.collect(); peak("u 미리 계산")
    sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20090101"]
    src = (BASE / "us_surv_measure.py").read_text(encoding="utf-8").split("RES = {}")[0]    # 끝의 생존/폐지 표는 안 돌린다
    ns_ = {"__file__": str(BASE / "us_surv_measure.py"), "__name__": "us_surv_measure"}
    exec(compile(src, "us_surv_measure.py", "exec"), ns_)
    M = types.SimpleNamespace(**ns_); sys.argv = argv0; peak("재료")
    K = M.K; G = K.groupby("ticker", sort=False); ud = np.array(sorted(K.date.unique()))
    log(f"재료 K {len(K):,}행")
    print("패널 종목 중 us_full 에 없는 판별 종목", len(set(tk.ticker) - set(K.ticker)), "· K 종목 판별 없음", len(set(K.ticker) - set(tk.ticker)))
    if True:                                          # 공통 재료(한 번만)
        v5 = G.volume.transform(lambda s: s.rolling(5).mean()); v60 = G.volume.transform(lambda s: s.rolling(60).mean())
        E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(DATA / "us/analyst/*.pkl")))], ignore_index=True)
        E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
        E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
        E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
        E = E.drop_duplicates(["ticker", "edate"], keep="last")
        E["bdate"] = [ud[i] if i < len(ud) else None for i in np.searchsorted(ud, E.edate.values, "right")]
        E = E.dropna(subset=["bdate"]); E["sur"] = E["Surprise(%)"].astype(float)
        ret1 = (K.close / G.close.shift(1) - 1) * 100
        c60 = G.close.shift(60); lo60 = G.close.transform(lambda s: s.rolling(60).min())
        recv = (lo60 <= c60 * 0.8) & (K.close >= lo60 + 0.25 * (c60 - lo60)) & (K.close < c60)
        ev = {}
        z = zipfile.ZipFile(DATA / "us/submissions.zip")
        for nm in z.namelist():
            b = z.read(nm)
            if b'"10-12B' not in b: continue
            j = json.loads(b)
            cik = int(j.get("cik") or re.search(r"CIK(\d+)", nm).group(1))
            rec = j["filings"]["recent"] if "filings" in j else j
            dates = [d for f, d in zip(rec.get("form", []), rec.get("filingDate", [])) if str(f).startswith("10-12B")]
            if not dates: continue
            d0, tks = min(dates), set(j.get("tickers") or [])
            if cik in ev: d0 = min(d0, ev[cik][0]); tks |= ev[cik][1]
            ev[cik] = (d0, tks)
        mm = pd.read_pickle(DATA / "us/sec_cik.pkl")
        for c_, t_ in zip(mm.cik, mm.tickers):
            if c_ in ev and isinstance(t_, (list, tuple)): ev[c_] = (ev[c_][0], ev[c_][1] | set(t_))
        try:
            tc = pd.read_pickle(DATA / "us/tiingo_cik.pkl")
            cc = [c for c in tc.columns if "cik" in c.lower()][0]; tcol = [c for c in tc.columns if "ticker" in c.lower()][0]
            for t_, c_ in zip(tc[tcol], tc[cc]):
                try: c_ = int(c_)
                except Exception: continue
                if c_ in ev: ev[c_] = (ev[c_][0], ev[c_][1] | {str(t_).upper()})
        except Exception: pass
        first = G.date.first(); n_ = G.cumcount()
        okt = set()
        for d0, tks in ev.values():
            d0 = d0.replace("-", "")
            for t_ in tks:
                f = first.get(str(t_).upper())
                if f is None or f <= "20070701" or f < d0: continue
                if (pd.Timestamp(f) - pd.Timestamp(d0)).days > 365: continue
                okt.add(str(t_).upper())
        N8 = (K.ticker.isin(okt) & (n_ == 24)).values
        log(f"분사 상장 {len(okt)}종목")
        SE = pd.read_csv(DATA / "us/sp500/ticker_start_end.csv", dtype=str)
        endc = [c for c in SE.columns if "end" in c.lower()][0]; tkc = [c for c in SE.columns if "ticker" in c.lower() or c.lower() == "symbol"][0]
        SE = SE.dropna(subset=[endc]); SE["end"] = pd.to_datetime(SE[endc], errors="coerce").dt.strftime("%Y%m%d")
        n9 = np.zeros(len(K), bool)
        kidx = pd.DataFrame({"index": np.arange(len(K)), "ticker": K.ticker.values, "date": K.date.values, "close": K.close.values})
        byt = {t: g for t, g in kidx.groupby("ticker")}
        for r in SE.dropna(subset=["end"]).itertuples():
            g = byt.get(getattr(r, tkc))
            if g is None: continue
            j = np.searchsorted(g.date.values, r.end, "left")
            if j >= len(g) or len(g) - j < 31: continue
            base = g.close.values[j - 1] if j > 0 and g.date.values[j - 1] <= r.end else g.close.values[j]
            k = j + 21
            if k < len(g) and g.close.values[k] <= base: n9[g["index"].values[k]] = True
        del byt, kidx
    NAME = {"N1": "상승장 신고가", "N2": "낙폭과대(폐기)", "N3": "저PBR 낙폭", "N4": "자사주 낙폭(폐기)", "N5": "잔잔한 급등주", "N6": "실적 서프라이즈", "N8": "분사주", "N9": "S&P 편출"}
    HOLD = {"N1": 40, "N2": 20, "N3": 60, "N4": 60, "N5": 60, "N6": 60, "N8": 250, "N9": 40}
    io_ = dict(zip(X.index.strftime("%Y%m%d"), X.Open)); ic_ = dict(zip(X.index.strftime("%Y%m%d"), X.Close))
    # 지수 시가 없음 → 전날 종가 / us500 끝(09-18) 뒤 신호는 지수 칸 비움
    cl = K.px.values; bu = K.buy.values; cost = K.cost.values; di = K.di.values; tkv = K.ticker.values; gv = K.grp.values; dv = K.date.values
    HAS = {h: (f"n{h}" in K.columns) for h in (20, 40, 60, 250)}
    NV = {h: K[f"n{h}"].values for h in HAS if HAS[h]}
    kpos = np.arange(len(K))

    def trades(cond, h):
        m = np.asarray(cond, bool) & (bu > 0)
        idx = kpos[m]; idx = idx[np.argsort(di[idx], kind="stable")]
        rows, last = [], {}
        for p in idx:
            t = tkv[p]
            if last.get(t, -10 ** 9) >= di[p]: continue
            last[t] = di[p] + h
            if HAS.get(h):
                ret = NV[h][p]
                if ret != ret: continue
            else:
                q = p + h
                if q >= len(K) or tkv[q] != t:
                    q = p
                    while q + 1 < len(K) and tkv[q + 1] == t: q += 1
                    if di[p] + h < len(ud) - 1 and gv[p] != "폐지": continue
                ret = (cl[q] / bu[p] - 1) * 100 - cost[p]
            if di[p] + h >= len(ud): continue
            d_in, d_out = ud[di[p] + 1], ud[di[p] + h]
            ixr = (ic_[d_out] / io_[d_in] - 1) * 100 if d_in in io_ and d_out in ic_ else np.nan
            rows.append((dv[p], t, ret, ixr))
        return pd.DataFrame(rows, columns=["date", "ticker", "ret", "idx"])

    ALL = pd.read_pickle(WORK / "us_rules_trades.pkl"); ALL = {k: ALL[k] for k in ("V0", "V1", "V3")}
    for v, drop in DROP.items():
        t1 = time.time()
        mask = ~K.ticker.isin(drop)
        K["u_v"] = np.load(WORK / f"u_{v}.npy")[K.index.values]
        C = M.rules(mask, "u_v")
        amtq = K.amt20.where(mask).groupby(K.date).rank(pct=True); usliq = (amtq >= 0.60).fillna(False) & mask
        volq = K.volume.where(usliq).groupby(K.date).rank(pct=True)
        C["N1"] = (C["N1"] & (volq >= 0.8) & (v5 <= 0.8 * v60)).fillna(False)
        Ev = E[~E.ticker.isin(drop)].copy()
        Ev = Ev[Ev.groupby("bdate").sur.transform("size") >= 5]; Ev["q"] = Ev.groupby("bdate").sur.rank(pct=True)
        peadq = (K.ticker + K.date).map(dict(zip(Ev.ticker + Ev.bdate, Ev.q)))
        C["N6"] = (usliq & (peadq >= 0.7) & (ret1 >= 3) & recv).fillna(False)
        C["N8"] = N8 & mask.values; C["N9"] = n9 & mask.values
        ALL[v] = {rid: trades(np.asarray(pd.Series(C[rid]).fillna(False).values, bool), HOLD[rid]) for rid in NAME}
        log(f"  {v} 끝 {sum(len(x) for x in ALL[v].values()):,}건 · {time.time() - t1:.0f}초")
    pd.to_pickle(ALL, WORK / "us_rules_trades2.pkl"); peak("규칙")
    PER = (("옛날 2009~15", "20090101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"), ("2016~ 전체", "20160101", "20991231"))
    rows = []
    for rid in NAME:
        for lab, a, b in PER:
            r_ = dict(rule=NAME[rid], hold=HOLD[rid], per=lab)
            for v in ALL:
                z = ALL[v][rid]; z = z[(z.date >= a) & (z.date <= b)].dropna(subset=["ret"])
                if not len(z): r_.update({v + "_n": 0}); continue
                up, dn = z.ret[z.ret > 0].sum(), -z.ret[z.ret < 0].sum(); zi = z.dropna(subset=["idx"])
                r_.update({v + "_n": len(z), v + "_avg": z.ret.mean(), v + "_med": z.ret.median(), v + "_win": (z.ret > 0).mean() * 100, v + "_pf": up / dn if dn else np.nan,
                           v + "_trim": z.ret[z.ret <= z.ret.quantile(.95)].mean(), v + "_ix": zi.idx.mean(), v + "_ex": (zi.ret - zi.idx).mean()})
            rows.append(r_)
    R = pd.DataFrame(rows); R.to_pickle(WORK / "us_rules_table.pkl")
    print(R.round(2).to_string())
    # 빠진 거래 해부(V0 → V2)
    kd = tk.set_index("ticker").kind; o = []
    for rid in NAME:
        a = ALL["V0"][rid]; b = ALL["V2"][rid]
        ka = set(zip(a.ticker, a.date)); kb = set(zip(b.ticker, b.date))
        out = a[[k not in kb for k in zip(a.ticker, a.date)]]; new = b[[k not in ka for k in zip(b.ticker, b.date)]]
        o.append(dict(rule=NAME[rid], V0=len(a), V2=len(b), 빠짐=len(out), 빠짐평균=out.ret.mean(), 유형=out.ticker.map(kd).value_counts().to_dict(), 새로듦=len(new), 새로듦평균=new.ret.mean(), 예=sorted(set(out.sort_values("ret", ascending=False).ticker))[:8]))
    O = pd.DataFrame(o); O.to_pickle(WORK / "us_rules_out.pkl"); print(O.round(2).to_string())


# ═══════════════════════════════════════════════════════════════════════
# 5. 국장 건강 진단
# ═══════════════════════════════════════════════════════════════════════
KR_RULES = {"P1": ("조용한 신고가", 40, "KOSPI"), "P2": ("조정매집", 10, "KOSPI"), "P3": ("폭락반등", 20, "KOSPI"), "P4": ("업종붕괴 이탈", 5, "KOSPI"), "P5": ("A1 자사주 낙폭", 10, "BOTH"), "P8": ("A2 자사주 신탁 급락", 10, "BOTH"),
            "P6": ("깊은 이격", 5, "KOSPI"), "P7": ("외인 매집", 60, "KOSPI"), "D1": ("낙폭과대", 20, "KOSDAQ"), "D2": ("저PBR 낙폭", 40, "KOSDAQ")}


def load_gate():
    j = json.load(open(DATA / "factory" / "kospi.json", encoding="utf-8"))
    X = pd.Series(j).sort_index().astype(float).rename("c").to_frame()
    X["ma20"] = X.c.rolling(20).mean(); X["ma60"] = X.c.rolling(60).mean()
    return X


FCOLS = ["date", "ticker", "name", "open", "close", "volume", "buy", "cost", "marcap", "amt", "amt20", "fw5", "fw20", "fw60", "ow20", "ow60", "r16", "rw1", "su1", "vol20", "ret3", "ret5", "ret10", "ret20", "ret60",
         "dma5", "dma20", "fromhi", "fromlo", "mdd60", "dd", "up", "u", "srd", "sr20", "dil", "bb", "ins60", "PBR", "부채비율"] + ["n%d" % h for h in (5, 10, 20, 40, 60)]


def fr_cache(f, mk):
    """규칙 평가용 창만 따로 — 큰 패널을 매번 읽지 않는다(RAM)."""
    p = WORK / f"fr_{mk}.pkl"
    src = DATA / f
    if p.exists() and p.stat().st_mtime > src.stat().st_mtime: return pd.read_pickle(p)
    P = pd.read_pickle(src); Q = P.loc[P.date >= "20250101", FCOLS].sort_values(["ticker", "date"]).reset_index(drop=True); del P; gc.collect()
    Q.to_pickle(p); return Q


def site_group():
    import csv as _c
    return {r["ticker"]: r["industry"] for r in _c.DictReader(open(DATA / "industry.csv", encoding="utf-8-sig")) if r.get("ticker") and r.get("industry")}


def frames(close_from=None):
    """규칙 평가용 창. close_from: 코스피 종가를 사이트 기준 값으로 바꿔 파생값을 다시 계산.
       u 열: 패널 옛 업종 묶음 · u_site 열: 사이트 정의(industry.csv 세분류·시장별·회원 5↑·기타 제외)."""
    out = {}; IND = site_group()
    for f, mk in (("panel_kp_new.pkl", "KOSPI"), ("panel_kq_new.pkl", "KOSDAQ")):
        P = fr_cache(f, mk)
        if close_from is not None and mk == "KOSPI":
            m = P[["ticker", "date"]].merge(close_from, on=["ticker", "date"], how="left")
            P["close"] = m.alt.where(m.alt.notna(), P.close).values
            g = P.groupby("ticker", sort=False); C = P.close.astype(float)
            for n in (3, 5, 10, 20, 60):
                P["ret%d" % n] = g.close.transform(lambda x, n=n: x / x.shift(n) - 1) * 100
            for w in (5, 20):
                P["dma%d" % w] = (C / g.close.transform(lambda x, w=w: x.rolling(w).mean()) - 1) * 100
            hi = g.close.transform(lambda x: x.rolling(250, min_periods=60).max()); lo = g.close.transform(lambda x: x.rolling(250, min_periods=60).min())
            P["fromhi"] = (C / hi - 1) * 100; P["fromlo"] = (C / lo - 1) * 100
            P["vol20"] = g.close.transform(lambda x: (x / x.shift(1) - 1).rolling(20).std()) * 100
            hi60 = g.close.transform(lambda x: x.rolling(60, min_periods=20).max()); P["dd"] = (C / hi60 - 1) * 100
            P["mdd60"] = P.dd.groupby(P.ticker).transform(lambda x: x.rolling(60, min_periods=20).min())
        g = P.groupby("ticker", sort=False)
        P["pref"] = ~P.ticker.str.endswith("0")
        P["ret250"] = (P.close / g.close.shift(250) - 1) * 100
        ma20 = g.close.transform(lambda s: s.rolling(20).mean())
        P["above20"] = (P.close > ma20).groupby(P.ticker).transform(lambda s: s.rolling(250, min_periods=80).mean()) * 100
        P["dev25"] = (P.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
        r = (P.close / g.close.shift(1))
        badj = ~((r > 0.68) & (r < 1.32)) & r.notna()
        P["disc"] = badj.astype(int).groupby(P.ticker).transform(lambda s: s.rolling(25, min_periods=1).sum()) > 0
        P["capo"] = np.where(P.marcap < 1e9, P.marcap, P.marcap / 1e8)   # 억 단위로 맞춤(옛 행 단위 섞임)
        P["mk"] = mk
        P["upS"] = P.ticker.map(IND).where(lambda s: s != "기타")
        d2 = P[P.upS.notna() & P.ret60.notna() & (P.date > "20260601")]
        gm = d2.groupby(["date", "upS"]).ret60; m_ = gm.median()[gm.size() >= 5]
        P["u_site"] = pd.MultiIndex.from_arrays([P.date, P.upS]).map(m_)
        out[mk] = P
    return out


def credit():
    c = ro(DATA / "kis" / "market.db"); a = pd.read_sql("SELECT date,ticker,loan_rmnd lb FROM credit WHERE date>='20260501'", c); c.close()
    c = ro(DATA / "toss.db"); b = pd.read_sql("SELECT date,ticker,loan_bal lb FROM credit WHERE date>='20260501'", c); c.close()
    def ch(x):
        x = x.sort_values(["ticker", "date"]); x["crc"] = (x.lb / x.groupby("ticker", sort=False).lb.shift(20) - 1) * 100; return x[["ticker", "date", "crc"]]
    A, B = ch(a), ch(b)
    m = A.merge(B, on=["ticker", "date"], suffixes=("", "_t")).dropna()
    print("신용 20일 변화 KIS vs 토스: 겹침", len(m), "상관", round(float(m.crc.corr(m.crc_t)), 4), "· -15% 판정 일치", round(float(((m.crc <= -15) == (m.crc_t <= -15)).mean()) * 100, 2), "%")
    miss = B[~B.date.isin(set(A.date))]
    print("KIS 신용 끝", A.date.max(), "· 토스로 메운 날", sorted(miss.date.unique()))
    return pd.concat([A, miss], ignore_index=True)


def eval_kr(F, gate, cr, bbt, ucol="u"):
    up20 = gate.c > gate.ma20; up60 = gate.c > gate.ma60
    res = []
    for mk, K in F.items():
        K = K.merge(cr, on=["ticker", "date"], how="left")
        K = K.merge(bbt.assign(bbt=True), on=["ticker", "date"], how="left"); K["bbt"] = K.bbt.fillna(False).astype(bool)
        U20 = K.date.map(up20); U60 = K.date.map(up60); UU = K[ucol]
        dn20, dn60, on60 = (U20 == False), (U60 == False), (U60 == True)
        srd = K.srd == True
        cln = ~K.dil.fillna(False) & ~K.disc & ~K.pref
        C = {}
        if mk == "KOSPI":
            C["P1"] = cln & (K.fromhi >= -10) & (K.r16 < 120) & (K.rw1 <= 120) & (K.fw5 >= 3) & (K.fw60 >= 1) & (K.vol20 <= 2) & (K.sr20 <= .5) & (K.ret20 <= 5) & (K.amt20 >= 200) & (K.dma5 <= 1) & ~((K.above20 > 70) & (K.ret250 > 120))
            C["P2"] = cln & (K.r16 < 30) & (K.rw1 >= 200) & (K.fw5 >= 2) & (K.amt >= 3) & (K.ret3 <= -5) & (K.ret10 <= 0) & dn20 & srd
            C["P3"] = cln & (K.ret20 <= -25) & (K.su1 >= 1.5) & (K.fw60 >= 1) & (K.amt20 >= 3) & dn60 & (UU <= -10) & (K.crc <= -15) & srd
            C["P4"] = cln & dn60 & (UU <= -20) & (K.dma20 <= -10) & (K.mdd60 <= -40) & srd & (K.crc <= -15) & (K.amt20 >= 5) & (K.close >= 1000)
            C["P6"] = cln & dn60 & (K.dev25 <= -25) & (UU <= -20) & (K.amt20 >= 10) & (K.close >= 1000)
            C["P7"] = cln & on60 & (K.capo >= 10000) & (K.capo < 100000) & (K.fw20 >= 1) & (K.ow60 < .4) & (K.r16 >= 100) & (K.r16 < 150) & (K.fromhi >= -15) & (K.fromlo >= 70) & (K.ins60 > 0)
        else:
            C["D1"] = cln & (K.ret20 <= -30) & (K.su1 >= 1.5) & (K.fw60 >= 1) & (K.amt20 >= 2) & dn60 & (UU <= -20) & srd & (K.close >= 1000) & (K.ow20 >= 0) & (K["부채비율"].isna() | (K["부채비율"] <= 200))
            C["D2"] = cln & (K.PBR <= .8) & (K.ret20 <= -10) & (K.su1 >= 2) & (UU <= -10) & dn60 & (K.ow20 >= 0) & srd & (K.amt20 >= 5) & (K.close >= 1000)
        C["P5"] = ~K.pref & K.bb & (K.ret60 <= -20) & dn60
        C["P8"] = ~K.pref & K.bbt & (K.ret20 <= -10) & (K.ret5 <= -10)
        for r, c in C.items():
            z = K[c.fillna(False) & (K.date > OLD_END)]
            hz = KR_RULES[r][1]
            res.append(z.assign(rid=r, hold=hz, ret=z["n%d" % hz])[["date", "ticker", "name", "mk", "rid", "hold", "close", "buy", "ret"]])
    return pd.concat(res, ignore_index=True)


def site_orders():
    """autotrade 실행 기록 — 사이트 __filters__ 에서 실제로 받은 국장 매수 대기."""
    L = open(DATA / "autotrade" / "run.log", encoding="utf-8", errors="ignore").read().split("\n")
    rows, none = [], []
    for l in L:
        m = re.match(r"(\d{4})-(\d\d)-(\d\d) \d\d:\d\d:\d\d 매수 주문: KR (\w+) (\w+) ", l)
        if m and "[DRY]" not in l: rows.append((m[1] + m[2] + m[3], m[4], m[5]))
        m = re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d KR 살 것 없음 · 신호일 (\d{8})", l)
        if m: none.append(m[1])
    return pd.DataFrame(rows, columns=["bday", "rid", "ticker"]).drop_duplicates(), sorted(set(none))


def health_table(S, F, gate, tag):
    alldays = sorted(set(F["KOSPI"].date)); DI = {d_: i for i, d_ in enumerate(alldays)}; lastpos = len(alldays) - 1
    S = S.copy(); S["di"] = S.date.map(DI)
    B = {}
    for mk, K in F.items():
        Q = K[K.date > "20260601"]
        uni = (Q.groupby("date").amt20.rank(pct=True) >= .6) & (Q.close >= 1000) & ~Q.pref & Q.buy.notna()
        B[mk] = Q.loc[uni, ["date", "n5", "n10", "n20", "n40", "n60"]]
    A0 = pd.concat(B.values(), ignore_index=True)
    def base(mk, h):
        return (A0 if mk == "BOTH" else B[mk]).groupby("date")["n%d" % h].mean()
    KC = gate.c
    def kospi_ret(d_, h):
        i = DI[d_]
        if i + h > lastpos: return np.nan
        return (KC.get(alldays[i + h], np.nan) / KC.get(alldays[i], np.nan) - 1) * 100
    rows = []; trades = []
    for rid, (nm, h, mk) in KR_RULES.items():
        X = S[S.rid == rid].sort_values(["di", "ticker"])
        keep, last = [], {}
        for ix, t, i in zip(X.index, X.ticker, X.di):
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + h; keep.append(ix)
        T = X.loc[keep].copy()
        T["done"] = T.di + h + 1 <= lastpos
        T["bl"] = T.date.map(base(mk, h)); T["kx"] = [kospi_ret(a, h) for a in T.date]; T["ex"] = T.ret - T.bl
        D = T[T.done & T.ret.notna()]; O = T[~T.done & T.ret.notna()]
        rows.append(dict(규칙=f"[{nm}]", id=rid, 보유=h, 신호=len(X), 중복뺌=len(T), 완료=len(D), 평균=D.ret.mean(), 중앙=D.ret.median(), 승률=(D.ret > 0).mean() * 100 if len(D) else np.nan,
                         기준선=D.bl.mean(), 초과=D.ex.mean(), 코스피=D.kx.mean(), 진행중=len(O), 진행평가=O.ret.mean(), 진행기준선=O.bl.mean(), 못잼=int(T.ret.isna().sum()), 달=",".join(sorted(set(T.date.str[:6])))))
        trades.append(T)
    R = pd.DataFrame(rows); R.to_pickle(WORK / f"kr_health_{tag}.pkl"); print(f"\n=== 건강표 {tag} ==="); print(R.round(2).to_string())
    TT = pd.concat(trades, ignore_index=True); TT.to_pickle(WORK / f"kr_health_trades_{tag}.pkl")
    return R, TT


def stage_kr_health():
    gate = load_gate(); cr = credit()
    d = ro(DATA / "dart" / "disclosures.db")
    z = pd.read_sql("SELECT stock_code ticker, rcept_dt, report_nm FROM disclosure WHERE length(stock_code)=6 AND rcept_dt>='20260801' AND replace(report_nm,' ','') LIKE '%자기주식취득신탁계약체결결정%'", d); d.close()
    z = z[~z.report_nm.str.replace(" ", "", regex=False).str.contains("정정")]
    N = pd.read_pickle(WORK / "new_base.pkl")[["ticker", "date", "mk", "csv_close"]]
    days = np.array(sorted(N.date.unique()))
    z["date"] = [days[i] if i < len(days) else None for i in np.searchsorted(days, z.rcept_dt.values, "left")]
    bbt = z.dropna(subset=["date"])[["ticker", "date"]].drop_duplicates()
    print("신탁 공시 신호", len(bbt))
    F = frames(); peak("frames")
    SA = eval_kr(F, gate, cr, bbt, "u")
    RA, TA = health_table(SA, F, gate, "A")
    alt = N[(N.mk == "KOSPI") & N.csv_close.notna() & (N.date >= "20260914")][["ticker", "date", "csv_close"]].rename(columns={"csv_close": "alt"})
    F2 = frames(alt); peak("frames2")
    SB = eval_kr(F2, gate, cr, bbt, "u_site")
    RB, TB = health_table(SB, F, gate, "B")     # 수익은 어느 쪽이든 KRX 시가·종가(F) 기준 패널 n{h}
    SC = eval_kr(F, gate, cr, bbt, "u_site"); print("KRX 종가 + 사이트 업종 신호", len(SC))
    alldays = sorted(set(F["KOSPI"].date)); KC = gate.c
    d0, d1 = OLD_END, alldays[-1]
    g2 = gate[gate.index > OLD_END]
    print("코스피", d0, KC[d0], d1, KC[d1], round((KC[d1] / KC[d0] - 1) * 100, 2), "% · 60일선 아래 날", int((g2.c < g2.ma60).sum()), "/", len(g2), "· 20일선 아래", int((g2.c < g2.ma20).sum()))
    for mk, K in F.items():
        Q = K[K.date == d0]; uni = Q[(Q.amt20.rank(pct=True) >= .6) & (Q.close >= 1000) & ~Q.pref]
        a = uni.set_index("ticker").close; b = K[K.date == d1].set_index("ticker").close; idx = a.index.intersection(b.index); rr = (b[idx] / a[idx] - 1) * 100
        print(mk, "유니버스 기간 수익 평균", round(rr.mean(), 2), "중앙", round(rr.median(), 2), "n", len(rr))
    O, none = site_orders()
    prev = {b: a for a, b in zip(alldays[:-1], alldays[1:])}
    O["date"] = O.bday.map(prev)
    print("실제 주문", len(O), "· 살 것 없음 신호일", none)
    p = SA[["date", "rid", "ticker", "name", "close"]].assign(A=True).merge(SB[["date", "rid", "ticker"]].assign(B=True), on=["date", "rid", "ticker"], how="outer").merge(SC[["date", "rid", "ticker"]].assign(C=True), on=["date", "rid", "ticker"], how="outer").merge(O.assign(site=True)[["date", "rid", "ticker", "site"]], on=["date", "rid", "ticker"], how="outer")
    q = p[p.date >= "20261002"].copy(); q.to_pickle(WORK / "kr_site_cmp.pkl")
    print(q.fillna({"A": False, "B": False, "C": False, "site": False}).groupby("rid")[["A", "B", "C", "site"]].sum().to_string())
    print(q.fillna({"A": False, "B": False, "C": False, "site": False}).sort_values(["date", "rid"])[["date", "rid", "ticker", "name", "A", "C", "B", "site"]].to_string())
    print("9/14 뒤 신호 수 A", int((SA.date >= "20260914").sum()), "B", int((SB.date >= "20260914").sum()), "C", int((SC.date >= "20260914").sum()), "· 9/13 까지 A", int((SA.date < "20260914").sum()), "B", int((SB.date < "20260914").sum()))
    # 재현 안 된 주문의 재료값
    KK = pd.concat([F2["KOSPI"], F2["KOSDAQ"]], ignore_index=True).merge(cr, on=["ticker", "date"], how="left")
    miss = O.merge(SB[["date", "rid", "ticker"]].assign(B=True), on=["date", "rid", "ticker"], how="left"); miss = miss[miss.B.isna()]
    print("사이트 기준으로도 재현 안 된 주문"); print(miss.merge(KK[["ticker", "date", "name", "mk", "close", "dev25", "u", "u_site", "upS", "amt20", "srd", "crc", "ret20", "su1", "fw60", "dil", "disc", "dma20", "mdd60", "fw5", "r16", "rw1", "ret3", "ret10"]], on=["ticker", "date"], how="left").round(2).to_string())
    over = q[q.site.isna() & q.B.notna()].merge(KK[["ticker", "date", "fw5", "amt", "r16", "rw1", "ret3", "ret10", "srd", "ret5", "ret20", "dil", "disc"]], on=["ticker", "date"], how="left")
    print("사이트 기준 재현에만 있는 신호(주문 없음)"); print(over.round(2).to_string())
    # 실제 체결가 vs 패널 시가
    l = json.load(open(DATA / "autotrade" / "ledger.json", encoding="utf-8"))["orders"]
    L = pd.DataFrame([x for x in l if x.get("mk") == "KR" and x.get("side") == "BUY"])
    L = L.rename(columns={"t": "ticker"})[["date", "ticker", "rid", "ap", "status"]]
    KR = pd.concat([F["KOSPI"], F["KOSDAQ"]], ignore_index=True)[["ticker", "date", "open"]]
    m = L.merge(KR, on=["ticker", "date"], how="left"); m["차이%"] = (m.ap.astype(float) / m.open - 1) * 100
    print("실제 체결가 vs 패널 시가"); print(m.round(3).to_string())
    del F, F2, KK, KR; gc.collect()
    # [지수 덮개] — 코스피200 대신 069500 1분봉 정규장 종가(네트워크 없이 쓸 수 있는 유일한 재료)
    x = pd.concat([agg_m1(pd.read_parquet(DATA / "m1" / "KR" / "bf" / "069500.parquet"))] + [agg_m1(pd.read_parquet(f, filters=[("t", "==", "069500")])) for f in sorted(glob.glob(str(DATA / "m1" / "KR" / "day" / "*.parquet")))], ignore_index=True)
    x = x.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    c = x.close.values; ma = pd.Series(c).rolling(60).mean().values; s = np.zeros(len(c), bool); on = False
    for i in range(len(c)):
        if np.isnan(ma[i]): continue
        if not on and c[i] > ma[i] * 1.03: on = True
        elif on and c[i] < ma[i] * 0.97: on = False
        s[i] = on
    x["ma60"] = ma; x["on"] = s; x["dev"] = (x.close / x.ma60 - 1) * 100
    x["sw"] = x.on != x.on.shift(1)
    print("069500", x.date.min(), x.date.max(), len(x))
    print("상태 바뀐 날(2026~)"); print(x[(x.sw) & (x.date >= "20260101")][["date", "close", "dev", "on"]].round(2).to_string())
    print(x[x.date >= "20261015"].iloc[::2][["date", "close", "ma60", "dev", "on"]].round(2).to_string())
    x.to_pickle(WORK / "ix1.pkl")
    w = x[x.date >= OLD_END].reset_index(drop=True)
    sw = w[w.sw].index.tolist(); pos = []
    for i in sw:
        if i + 1 < len(w): pos.append((w.date[i], bool(w.on[i]), w.date[i + 1], float(w.open[i + 1])))
    print("체결(다음날 시가)", pos)
    if len(pos) >= 2:
        r = (pos[1][3] / pos[0][3] - 1) * 100
        print("들어갔다 나온 왕복 수익", round(r, 2), "% · 같은 구간 코스피", round((KC[pos[1][2]] / KC[pos[0][2]] - 1) * 100, 2), "%")
    print("8/28→끝 그냥 보유", round((w.close.iloc[-1] / w.close.iloc[0] - 1) * 100, 2), "%")
    # 데이 규칙 후보 기록
    rr = []
    for f in sorted(glob.glob(str(DATA / "day" / "snap_*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        for c_ in j.get("cand", []):
            rr.append(dict(date=j.get("date"), t=c_.get("t"), name=c_.get("name"), t1=c_.get("t1"), t2=c_.get("t2"), t3=c_.get("t3"), u1=c_.get("u1"), bought=c_.get("bought"), ret=c_.get("ret"), open=c_.get("open"), close=c_.get("close")))
    D = pd.DataFrame(rr); D.to_pickle(WORK / "day_snap.pkl")
    Fk = pd.concat([pd.read_pickle(WORK / f"newrows_{m_}.pkl")[["ticker", "date", "open", "close", "amt20"]] for m_ in ("KOSPI", "KOSDAQ")], ignore_index=True)
    Fk = Fk[(Fk.close >= 1000) & Fk.ticker.str.endswith("0") & Fk.open.notna()]
    Fk["oc"] = (Fk.close / Fk.open - 1) * 100 - 0.23
    bl = Fk[Fk.groupby("date").amt20.rank(pct=True) >= .6].groupby("date").oc.mean()
    print("데이 스냅", D.date.min(), D.date.max(), len(D))
    for nm, m_ in (("T1", D.t1 != False), ("T2", D.t2 == True), ("T3", D.t3 == True)):
        z_ = D[m_ & D.ret.notna()]
        if not len(z_): print(nm, "기록 없음"); continue
        rt = pd.to_numeric(z_.ret, errors="coerce")
        print(nm, "건수", len(z_), "날", z_.date.nunique(), "평균", round(rt.mean(), 2), "중앙", round(rt.median(), 2), "승률", round((rt > 0).mean() * 100, 0), "같은 날 유니버스 시가→종가", round(z_.date.map(bl).mean(), 2), "· 실매수", int((z_.bought == True).sum()), "기간", z_.date.min(), z_.date.max())
    print("t4_log", open(DATA / "day" / "t4_log.csv", encoding="utf-8-sig").read()[:300])
    peak("kr_health")


# ═══════════════════════════════════════════════════════════════════════
# 6. 감사 ❌ 수리 — RAM 을 아끼려고 만든 새 판 위에서 고친다(스크립트당 6GB 안팎 목표)
# ═══════════════════════════════════════════════════════════════════════
def peak(lab=""):
    try:
        import psutil
        m = psutil.Process().memory_info(); log(f"{lab} 메모리 현재 {m.rss/2**30:.1f}GB · 최고 {getattr(m, 'peak_wset', 0)/2**30:.1f}GB")
    except Exception: pass


def stage_patch_kr():
    """① 12종목(코스닥→코스피 이전)은 옛 판에 2018~ 이력이 없다 — 새 행만 붙이면 8년 공백을 건너뛴 가짜 점프가 된다 → 새 행에서 뺀다.
       ② 8월 안에 끊겼다가 새 구간에서 재개한 종목: 옛 '마지막 종가 청산' 값이 공백을 건넌 값이 되므로 결측(fix_panels ② 와 같은 처리)."""
    S = pd.read_pickle(DATA / "kr_scan_new.pkl"); attrs = dict(S.attrs)
    new = S[S.date > OLD_END]; old_last = S[S.date <= OLD_END].groupby("ticker").date.max()
    oldmk = S[S.date <= OLD_END].drop_duplicates("ticker", keep="last").set_index("ticker").mk
    nk = new.drop_duplicates("ticker").set_index("ticker").mk
    MOVED = sorted(t for t in nk.index if t in oldmk.index and oldmk[t] != nk[t])
    yrs = S[S.ticker.isin(MOVED) & (S.date <= OLD_END)].groupby("ticker").date.agg(["min", "max", "size"])
    print("시장 옮긴 종목 — 옛 판 이력:"); print(yrs.to_string())
    save("moved.json", MOVED)
    T = sorted(t for t in nk.index if t in old_last.index and old_last[t] < OLD_END and t not in MOVED)
    print("재개 종목", len(T), {t: old_last[t] for t in T[:40]})
    save("resumed.json", T)
    L = {t: old_last[t] for t in T}
    def fix(P, hs):
        ud = sorted(P.date.unique()); DI = {d: i for i, d in enumerate(ud)}
        ix = P.index[P.ticker.isin(T) & (P.date <= OLD_END)]
        Z = P.loc[ix, ["ticker", "date"]]
        p = Z.date.map(DI).values; lp = Z.ticker.map(L).map(DI).values
        cnt = 0
        for h in hs:
            c = "n%d" % h
            m = (p + h > lp) & P.loc[ix, c].notna().values
            cnt += int(m.sum()); P.loc[ix[m], c] = np.nan
        return cnt
    print("kr_scan 결측 처리", fix(S, (5, 10, 20, 40, 60)))
    k0 = len(S); S = S[~((S.date > OLD_END) & S.ticker.isin(MOVED))].reset_index(drop=True); S.attrs = attrs
    log(f"kr_scan_new {k0:,} → {len(S):,}행 · {S.ticker.nunique()}종목")
    tmp = DATA / "kr_scan_new.pkl.tmp"; S.to_pickle(tmp); tmp.replace(DATA / "kr_scan_new.pkl"); del S, new; gc.collect()
    for f in ("panel_kp_new.pkl", "panel_kq_new.pkl"):
        P = pd.read_pickle(DATA / f); attrs = dict(P.attrs)
        print(f, "결측 처리", fix(P, HZ))
        m = (P.date > OLD_END) & P.ticker.isin(MOVED)
        if m.any():
            P = P[~m].reset_index(drop=True); P.attrs = attrs
        tmp = DATA / (f + ".tmp"); P.to_pickle(tmp); tmp.replace(DATA / f)
        log(f"{f} {len(P):,}행"); del P; gc.collect()
    peak("patch_kr")


def _hash(arr):
    import hashlib
    if arr.dtype == object:
        return pd.util.hash_array(pd.Series(arr).astype(str).values).tobytes().__hash__() if False else hashlib.md5(pd.util.hash_array(pd.Series(arr).fillna("§").astype(str).values, categorize=True).tobytes()).hexdigest()
    return hashlib.md5(np.nan_to_num(np.asarray(arr, dtype=np.float64), nan=-9.87654321e300).tobytes()).hexdigest()


def stage_verify2():
    """앞부분 전수 대조(저메모리): 옛 판을 해시로 줄여 두고 새 판과 비교. 선행 열은 2026 행만 값으로 대조."""
    rep = {}
    FW = re.compile(r"^(n\d+|buy|gap)$")
    for old, new in (("kr_scan.pkl", "kr_scan_new.pkl"), ("panel_kp.pkl", "panel_kp_new.pkl"), ("panel_kq.pkl", "panel_kq_new.pkl")):
        res = {}; tail = {}
        for side, f in (("old", old), ("new", new)):
            P = pd.read_pickle(base(f) if side == "old" else DATA / f)
            o = np.lexsort((P.date.to_numpy(dtype=object).astype(str), P.ticker.to_numpy(dtype=object).astype(str))) if False else None
            m = (P.date <= OLD_END).to_numpy()
            key = (P.ticker.astype(str) + P.date.astype(str))[m]
            o = np.argsort(key.to_numpy(dtype=object), kind="stable"); del key
            idx = np.flatnonzero(m)[o]; dates = P.date.to_numpy()[idx]; t26 = dates >= "20260101"
            r = {"rows": len(idx)}
            for c in P.columns:
                a = P[c].to_numpy()[idx]
                if FW.match(c):
                    r[c] = _hash(a[~t26]); tail[(side, c)] = a[t26].astype(float)
                else:
                    r[c] = _hash(a)
            res[side] = r
            del P, idx, m, o; gc.collect()
        a, b = res["old"], res["new"]
        dif = [c for c in a if a[c] != b[c]]
        fw = {}
        for (sd, c) in list(tail):
            if sd == "old":
                x, y = tail[("old", c)], tail[("new", c)]
                ne = ~((x == y) | (np.isnan(x) & np.isnan(y)))
                nn = ~np.isnan(x)
                if ne.any(): fw[c] = dict(달라짐=int(ne.sum()), 옛값있던행중=int((ne & nn).sum()))
        rep[old] = dict(rows_old=a["rows"], rows_new=b["rows"], 다른열=dif, 선행2026=fw)
        print(old, rep[old], flush=True)
        del tail; gc.collect()
    save("verify2.json", rep); peak("verify2")


def _repair_us(P):
    """패널 오염 수리와 같은 처리(가격·재무 값은 안 바꾼다): ④ 공백을 건넌 n{h} 결측 · F 거래량 0 매수·매도 결측 · ⑧ fromhi/fromlo 부호."""
    tk = pd.factorize(P.ticker)[0].astype(np.int32); ud = sorted(P.date.unique()); d = P.date.map({x: i for i, x in enumerate(ud)}).to_numpy(dtype=np.int32)
    vol = P.volume.to_numpy(dtype=np.float64)
    nxt_same = np.r_[tk[1:] == tk[:-1], False]
    buybad = nxt_same & (np.r_[vol[1:], np.zeros(1)] <= 0)
    lastd = pd.Series(d).groupby(tk).transform("max").to_numpy(dtype=np.int32)
    log(f"F 매수 불가 {int(buybad.sum()):,}행 · buy 있던 행 {int((buybad & P.buy.notna().to_numpy()).sum()):,}")
    tot = {}
    for h in (5, 10, 20, 40, 60):
        c = "n%d" % h
        a = P[c].to_numpy().copy()
        same = np.r_[tk[h:] == tk[:-h], np.zeros(h, bool)]
        dd = np.r_[d[h:] - d[:-h], np.zeros(h, np.int32)]
        vh = np.r_[vol[h:], np.ones(h)]
        # 행으로는 종목 끝을 넘지만 달력으로는 안 넘는 자리(끝 근처에 공백) — 역시 공백을 건넌 값이다
        bad = (same & (dd != h)) | (same & (vh <= 0)) | buybad | (~same & (d + h <= lastd))
        tot[c] = int((bad & ~np.isnan(a)).sum())
        a[bad] = np.nan; P[c] = a; del a, same, dd, vh, bad
    print("결측 처리", tot)
    b_ = P.buy.to_numpy().copy(); b_[buybad] = np.nan; P["buy"] = b_; del b_
    g_ = P.gap.to_numpy().copy(); g_[buybad] = np.nan; P["gap"] = g_; del g_
    fh = P.fromhi.to_numpy().copy(); fl = P.fromlo.to_numpy().copy()
    print("부호 고침 fromhi>0", int(np.nansum(fh > 0)), "· fromlo<0", int(np.nansum(fl < 0)))
    P["fromhi"] = np.where(fh > 0, 0, fh).astype(np.float32); P["fromlo"] = np.where(fl < 0, 0, fl).astype(np.float32); del fh, fl
    gc.collect()


def run_audit_light(lab, f, what):
    """audit_contam 을 정렬 복사 없이(새 판은 이미 ticker,date 정렬) 돌린다."""
    src = (BASE / "audit_contam.py").read_text(encoding="utf-8")
    s = src.replace('"kr_scan.pkl"', '"%s"' % f).replace('"us_scan.pkl"', '"%s"' % f)
    s = s.replace('K = K.sort_values(["ticker", "date"]).reset_index(drop=True)', 'pass')
    print("\n########## %s (%s) ##########" % (lab, f), flush=True)
    sys.argv = ["audit_contam.py", what]
    exec(compile(s, "audit_contam.py", "exec"), {"__file__": str(BASE / "audit_contam.py"), "__name__": "__main__"})
    peak("audit")


if __name__ == "__main__":
    st = sys.argv[1] if len(sys.argv) > 1 else ""
    if st == "raw": stage_raw()
    elif st == "kr": stage_kr()
    elif st == "kr_lite":                                              # 매일 실행용 — 옛·새 판을 같이 올리는 verify_old 는 빼고(앞부분 대조는 verify2 가 저메모리로)
        N_ = pd.read_pickle(WORK / "new_base.pkl"); ST_ = Static()
        extend("panel_kp.pkl", "KOSPI", N_, ST_); peak("kp"); extend("panel_kq.pkl", "KOSDAQ", N_, ST_); peak("kq"); del N_, ST_; gc.collect()
        build_scan(); peak("scan")
    elif st == "scan": build_scan(); verify_old()
    elif st == "verify": verify_old()
    elif st == "audit_kr": run_audit([("옛 판", "kr_scan.pkl", "kr"), ("새 판", "kr_scan_new.pkl", "kr")])
    elif st == "us": stage_us()
    elif st == "patch_kr": stage_patch_kr()
    elif st == "verify2": stage_verify2()
    elif st == "audit_kr2": run_audit_light("새 판(수리 뒤)", "kr_scan_new.pkl", "kr")
    elif st == "audit_us2": run_audit_light("새 판(수리 뒤)", "us_scan_full_notoss.pkl", "us")
    elif st == "audit_us": run_audit([("옛 판", "us_scan_full.pkl", "us"), ("새 판", "us_scan_full_notoss.pkl", "us")])
    elif st == "smoke": smoke()
    elif st == "us_rules": stage_us_rules()
    elif st == "kr_health": stage_kr_health()
    log("끝 %.1f분" % ((time.time() - T0) / 60))
