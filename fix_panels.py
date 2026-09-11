# -*- coding: utf-8 -*-
"""연구 패널 두 가지 오염을 수리한다 (2026-09-12 발견).

**① 시장 오염** — build_panel.py 가 폐지 DB(delisted.db·delisted_kd.db)를 **시장 구분 없이**
   양쪽 패널에 다 붙였다. kospi.db 는 `market=?` 로 거르는데 폐지 DB 에는 그 필터가 없다.
   그 결과 panel_kp 에 코스닥 196종목(157,972행 · 3.2%), panel_kq 에 코스피 106종목
   (116,438행 · 2.0%)이 섞였다. 둘을 이어붙인 kr_scan.pkl 은 **6.5%가 중복 행**이었다
   (같은 종목·같은 날이 KOSPI/KOSDAQ 두 번, 시장별 비용 가정이 달라 선행수익이 0.8%p 갈림).

**② 거래정지 구간을 건너뛴 선행수익** — buy 는 '다음 **행**의 시가' 인데, 정지 구간이
   패널에 없으면 다음 행이 몇 달 뒤가 된다. 그 사이 감자·병합이 있으면 미조정 가격이라
   수익률이 터무니없어진다(세미콘라이트 2017: 종가 1,305 → '다음날' 389,560 → n60 +47,498%).
   이런 자리가 1,093곳. 유니버스의 0.02~0.06% 인데 **2017 평균을 22.3%p 끌어올렸다**.

   원칙은 [[panel-data-gaps]] 와 같다 — **'졌다' 와 '못 쟀다' 를 구분한다.** 정지 중에는
   애초에 살 수도 팔 수도 없으므로 그 구간을 건너뛴 값은 성적이 아니라 결측이다.

수리 방법은 '다시 만들기' 가 아니라 '고쳐 쓰기' 다. 패널이 3GB 라 재빌드가 몇 시간이고,
이 두 오염은 원본 DB 를 다시 읽지 않아도 패널 안에서 정확히 식별된다.
원본은 *.bak 으로 남긴다.

    python fix_panels.py [--dry]      # --dry 는 재보기만 하고 저장하지 않는다
"""
import gc, shutil, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
DRY = "--dry" in sys.argv
HZ = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 40, 50, 60]


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


# ── 진짜 시장 — kospi.db 의 market 열이 유일한 근거다 ────────────────────────────────
log("kospi.db 에서 시장 정보 읽는 중")
c = sqlite3.connect(f"file:{BASE}/data/kospi.db?mode=ro", uri=True, timeout=600)
mkt = pd.read_sql("SELECT ticker,market,COUNT(*) n FROM daily "
                  "WHERE market IS NOT NULL GROUP BY ticker,market", c)
c.close()
TRUTH = mkt.sort_values("n").drop_duplicates("ticker", keep="last").set_index("ticker").market
log(f"  시장이 확인되는 종목 {len(TRUTH):,}개")

# 폐지 DB 는 시장 열이 없다. kospi.db 에 없는 종목만 파일 이름으로 메운다 —
# delisted.db 는 확인된 74종목이 전부 KOSPI 였고, delisted_kd.db 는 섞여 있어(코스닥 183·코스피 70)
# 이름만으로는 못 가른다. 그래서 **kospi.db 가 먼저**고 파일은 최후 수단이다.
for f, mk in (("delisted.db", "KOSPI"), ("delisted_kd.db", "KOSDAQ")):
    p = BASE / "data" / f
    if not p.exists(): continue
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=600)
    t = pd.read_sql("SELECT DISTINCT ticker FROM daily", c); c.close()
    miss = [x for x in t.ticker if x not in TRUTH.index]
    for x in miss: TRUTH.loc[x] = mk
    log(f"  {f}: kospi.db 에 없는 {len(miss):,}종목을 {mk} 로 메움")


# 양쪽 패널에 다 들어간 종목 — 이것만이 '중복' 이고, 수리 대상이다
BOTH = None


def _both():
    a = set(pd.read_pickle(BASE / "data/panel_kp.pkl")["ticker"].unique())
    gc.collect()
    b = set(pd.read_pickle(BASE / "data/panel_kq.pkl")["ticker"].unique())
    gc.collect()
    return a & b


def fix(fn, want):
    log(f"── {fn} ({want}) ──")
    p = BASE / "data" / fn
    df = pd.read_pickle(p)
    n0 = len(df)
    log(f"  {n0:,}행 · {df.ticker.nunique():,}종목")

    # ① 시장이 다른 종목을 뺀다 — 단, **양쪽 패널에 다 있는 종목만** 손댄다.
    #    한쪽에만 있는 종목까지 건드리면, 시장을 추정으로 정한 240여 종목(폐지 DB 에만 있고
    #    kospi.db 에 없는 것들) 때문에 **진짜 이 시장 종목을 지울 수 있다**.
    #    delisted_kd.db 는 이름과 달리 섞여 있다(확인분 코스닥 183·코스피 70).
    #    고치려는 건 '중복' 이므로 중복인 자리만 고친다.
    m = df.ticker.map(TRUTH)
    drop = df.ticker.isin(BOTH) & m.notna() & (m != want)
    log(f"  ① 양쪽에 있는 종목 중 시장이 다른 {drop.sum():,}행 ({drop.mean()*100:.2f}%) · "
        f"{df[drop].ticker.nunique()}종목 제거")
    unk = df.ticker.isin(BOTH) & m.isna()
    if unk.any():
        log(f"     ⚠ 양쪽에 있는데 시장을 모르는 {df[unk].ticker.nunique()}종목({unk.sum():,}행)은 "
            f"손대지 않는다 — 추정으로 지우지 않는다")
    df = df[~drop].copy()
    del m, drop, unk; gc.collect()

    # ② 거래일이 끊긴 자리의 선행수익을 결측으로
    ud = sorted(df.date.unique())
    DI = {d: i for i, d in enumerate(ud)}
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    pos = df.date.map(DI).astype(np.int64)
    g = df.groupby("ticker", sort=False)
    nxt = g.date.shift(-1).map(DI)
    lastpos = g.date.transform("max").map(DI)
    # 다음 거래일 행이 없으면 '다음날 시가' 를 쓸 수 없다 — 종목의 마지막 행은 원래 없는 게 정상
    buybad = (nxt - pos != 1) & (pos != lastpos)
    log(f"  ② 다음 거래일이 비어 매수 불가 {int(buybad.sum()):,}행 ({buybad.mean()*100:.2f}%)")
    # ②-b 가격제한폭을 넘는 가격 변화 = 감자·병합·액면분할(미조정)
    #     국내는 하루 ±30%(2015-06-15 이전 ±15%)가 상한이라 그 이상은 물리적으로 불가능하다.
    #     공백 없이 튀는 것도 있어서(037030: 종가 15원 → 다음날 시가 10,100원, 공백 0일)
    #     ②-a 의 '거래일 공백' 만으로는 못 잡는다. 여유를 10%p 더 준다.
    pc = g.close.shift(1)
    lim = np.where(df.date.values < "20150615", 0.15, 0.30) + 0.10
    onb = df.buy.notna() & ((df.buy / df.close > 1 + lim) | (df.buy / df.close < 1 - lim))
    ddb = pc.notna() & ((df.close / pc > 1 + lim) | (df.close / pc < 1 - lim))
    ca = (onb | ddb).values          # 이 날을 '가격 기준이 끊긴 날' 로 본다
    log(f"  ②-b 가격제한폭 초과 {int(ca.sum()):,}행 ({ca.mean()*100:.3f}%) · "
        f"{df[ca].ticker.nunique():,}종목 — 감자·병합으로 본다")
    # 종목 안에서 '앞으로 h일 안에 그런 날이 있는가' 를 누적합으로 센다
    cs = pd.Series(ca.astype(np.int32), index=df.index).groupby(df.ticker, sort=False).cumsum()
    buybad = buybad | pd.Series(ca, index=df.index)   # 그날 자체도 매수 기준이 깨졌다

    cnt = {}
    for h in HZ:
        col = "n%d" % h
        if col not in df.columns: continue
        sp = g.date.shift(-h).map(DI)
        # 보유 구간이 달력상 h 일과 맞아야 한다. 종목 끝을 넘는 경우는 원래 마지막 종가로
        # 청산하도록 되어 있으므로(폐지 처리) 그대로 둔다.
        endlife = (pos + h) > lastpos
        spanbad = (~endlife) & (sp - pos != h)
        # 보유 구간(오늘~h일 뒤) 안에 가격 기준이 끊긴 날이 하나라도 있으면 결측
        csh = g.date.shift(-h).notna() & (cs.groupby(df.ticker, sort=False).shift(-h) - cs > 0)
        bad = buybad | spanbad | csh.fillna(False)
        before = df[col].notna().sum()
        df.loc[bad & df[col].notna(), col] = np.nan
        cnt[h] = (int(bad.sum()), before - df[col].notna().sum())
    for h in (5, 20, 60):
        if h in cnt: log(f"     n{h}: 결측 처리 {cnt[h][1]:,}행")
    df.loc[buybad, "buy"] = np.nan

    ex = df[[c for c in ("n20", "n60") if c in df.columns]]
    for c_ in ex.columns:
        s = df[c_].dropna()
        log(f"     {c_} 남은 {len(s):,}행 · 최대 {s.max():,.0f}% · 1000%↑ {int((s>1000).sum()):,}건")

    if DRY:
        log("  (--dry) 저장하지 않음")
    else:
        bak = p.with_suffix(".pkl.bak")
        if not bak.exists():
            log(f"  원본 백업 → {bak.name}")
            shutil.copy2(p, bak)
        df.to_pickle(p)
        log(f"  저장 {len(df):,}행 (원본 {n0:,} · -{n0-len(df):,})")
    del df; gc.collect()


BOTH = _both()
log(f"양쪽 패널에 다 있는 종목 {len(BOTH):,}개 — 수리 대상은 여기뿐이다")
fix("panel_kp.pkl", "KOSPI")
fix("panel_kq.pkl", "KOSDAQ")
log("끝. kr_scan.pkl 은 kr_scan_cache.py 로 다시 만들어야 한다.")
