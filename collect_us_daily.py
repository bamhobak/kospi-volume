# -*- coding: utf-8 -*-
"""미장(나스닥·NYSE·아멕스) 전 종목 하루치 수집 → site/data/table_us.json

사이트의 '미장 전체' 조회 탭이 쓰는 파일을 만든다. 규칙 판정은 아직 하지 않는다 —
한국 규칙을 미국에 대입한 건 계좌에서 S&P500 을 못 이겨 기각했고([[us-expansion]]),
지금은 **눈으로 훑어보는 목록**이 목적이다.

한국 표와 같은 필드 이름을 쓴다(t·n·c·ch·amt20·ret20…). 그래야 사이트가 같은 표로 그린다.
없는 것(외국인·기관 수급, PER·PBR, 테마)은 null 로 둔다 — 화면은 빈칸으로 나온다.

  · 티커 목록: data/us/tickers.csv (us_collect.py 가 만든 것). 없으면 새로 받는다.
  · 시세: yfinance 1년치를 100종목씩 묶어 받는다(6,085종목 ≈ 61묶음).
  · 거래대금은 달러 기준 **백만 달러**로 넣는다(한국은 억원 — 단위가 다르니 화면에서 구분한다).

사용: python collect_us_daily.py [--chunk 100] [--limit 0]
"""
import io, json, os, sys, time, argparse, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np, pandas as pd

BASE = Path(__file__).parent
TICK = BASE / "data" / "us" / "tickers.csv"
OUT = BASE / "site" / "data" / "table_us.json"
# 사이트 주소 — 호스팅을 옮기면 여기 하나만 바꾸면 된다(환경변수 SITE_URL 로도 덮어쓴다).
SITE_URL = os.environ.get("SITE_URL", "https://kospi-volume.pages.dev").rstrip("/")
# Cloudflare Access 를 통과하려면 서비스 토큰 헤더를 붙여야 한다.
# (사이트가 Access 뒤에 있으면 헤더 없이는 로그인 화면 HTML 이 돌아온다 — JSON 인 줄 알고
#  파싱하다 죽는 게 아니라 **조용히 이상한 값**이 되므로 반드시 붙인다.)
def _cf_headers():
    # ⚠ User-Agent 를 반드시 준다. 파이썬 기본값(Python-urllib/3.x)은 Cloudflare 가
    #   봇으로 보고 **403** 을 던진다 — Access 헤더가 맞아도 막힌다.
    #   curl 은 기본 UA 로도 통과하는데 urllib 만 막혀서, 전환 직후 pipeline 의
    #   버전 읽기가 실패해 번호가 1.0.02 -> 1.0.01 로 거꾸로 갔다(2026-09-11).
    h = {"User-Agent": "Mozilla/5.0 (compatible; kospi-volume-bot)"}
    i = os.environ.get("CF_ACCESS_CLIENT_ID", "")
    s = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")
    if i and s:
        h["CF-Access-Client-Id"] = i
        h["CF-Access-Client-Secret"] = s
    return h

NDAY = 20                     # 화면 미니 차트에 쓸 최근 거래일 수


def log(m):
    print(f"[미장] {m}", flush=True)


def tickers():
    if TICK.exists():
        U = pd.read_csv(TICK)
    else:                      # 목록이 없으면 us_collect 의 만드는 함수를 그대로 쓴다
        import us_collect
        U = us_collect.build_tickers()
    U = U[U.Symbol.notna() & U.Symbol.astype(str).str.fullmatch(r"[A-Z]{1,5}")]
    return U.reset_index(drop=True)


_UNSET = object()
_OPEN = _UNSET


def open_session():
    """아직 안 끝난 미국 정규장의 날짜(YYYYMMDD)를 돌려준다. 끝났거나 장 없는 날이면 None.

    ⚠ 2026-09-11 사고: 수집이 22:21~22:30(KST)에 돌아 **개장 6분치**로 만든 봉이
      그날 종가로 표에 들어갔다. 미장 규칙은 종가로 판정하므로 6분짜리 값을 보고
      신고가·수익률을 계산한 셈이다. 터지지 않고 조용히 틀리는 부류다.

      평소엔 수집이 22:30(KST) 전에 끝나 이런 일이 없지만, 대기가 길어지거나
      수동으로 한 번 더 돌리면 개장을 넘긴다. 시각에 기대지 말고 **미완결 봉을
      아예 버린다**. 하루 늦은 표가 틀린 표보다 낫다 — 어차피 다음 수집이 채운다.

    16:05 로 잡은 건 장 마감(16:00 ET) 뒤 자료가 정리될 여유를 준 것이다.
    """
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        n = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        # tz 자료가 없으면 **보수적으로** 판단한다(EST 로 가정 → 실제보다 이른 시각으로 봄).
        # 이 방향의 오차는 멀쩡한 봉을 한 시간 더 버리는 것뿐이라 안전하다.
        from datetime import timedelta, timezone
        n = datetime.now(timezone.utc) - timedelta(hours=5)
    if n.weekday() >= 5:
        return None
    return n.strftime("%Y%m%d") if n.strftime("%H:%M") < "16:05" else None


def _shape(x):
    """두 공급처의 표를 같은 꼴로 — 종가 결측 제거 · 인덱스 YYYYMMDD · 미완결 봉 제거."""
    global _OPEN
    if _OPEN is _UNSET: _OPEN = open_session()
    try:
        x = x.dropna(subset=["Close"])
    except Exception:
        return None
    if len(x) < 25:            # 상장 직후라 지표를 못 만드는 종목은 뺀다
        return None
    try:
        x.index = x.index.strftime("%Y%m%d")
    except Exception:
        return None
    if _OPEN and len(x.index) and x.index[-1] == _OPEN:
        x = x.iloc[:-1]        # 아직 안 끝난 오늘 봉은 버린다
        if len(x) < 25:
            return None
    return x


def fetch_stooq(syms, start):
    """**주 공급처.** FinanceDataReader(Stooq) 로 받는다.

    ⚠ 2026-09-18 에 야후에서 갈아탔다. 같은 날 전 종목(6,084개)으로 나란히 재 보니:
        그날 자료 보유  야후 94.0% vs **Stooq 98.1%** (야후가 놓친 308종목을 Stooq 는 받았다)
        차단           6,084종목을 다 때려도 없음 · 7.2분
        값             시가·고가·저가·종가·거래량이 야후 **원종가와 완전히 일치**
        기준           분할 반영·배당 미조정 — 야후 auto_adjust=False 와 같다
                       (KO·XOM·JNJ 2024-01-02 로 확인: Stooq=야후 원종가, 야후 수정가와는 8~9% 차이)
      야후는 마감 뒤에도 일봉을 늦게 올린다 — 2026-09-16 에는 5시간 46분 뒤에도
      5%(303/5,683)만 올라와 표가 통째로 하루 묵었다.
    """
    import FinanceDataReader as fdr
    from concurrent.futures import ThreadPoolExecutor
    st = start[:10]

    def one(sym):
        try:
            x = fdr.DataReader(sym, st)
            if x is None or not len(x):
                return sym, None
            return sym, x[["Open", "High", "Low", "Close", "Volume"]]
        except Exception:
            return sym, None

    out = {}
    with ThreadPoolExecutor(12) as ex:
        for sym, x in ex.map(one, syms):
            if x is None:
                continue
            y = _shape(x)
            if y is not None:
                out[sym] = y
    return out


def fetch_yahoo(syms, start):
    """**보조 공급처.** Stooq 가 못 준 종목만 여기서 받는다."""
    import yfinance as yf
    d = yf.download(syms, start=start, auto_adjust=False, progress=False,
                    threads=True, group_by="ticker", timeout=60)
    if d is None or not len(d):
        return {}
    multi = isinstance(d.columns, pd.MultiIndex)
    cols = {c[0] for c in d.columns} if multi else set(syms)
    out = {}
    for s in syms:
        if s not in cols:
            continue
        try:
            x = d[s] if multi else d
        except Exception:
            continue
        y = _shape(x)
        if y is not None:
            out[s] = y
    return out


_SRC = {"stooq": 0, "yahoo": 0, "massive": 0}

# ── 최근 거래일은 Massive(옛 Polygon) 전 종목 일봉으로 덮는다 (2026-09-23) ─────────────
# ⚠ 위 '주 공급처 Stooq' 는 사실 야후다 — FinanceDataReader 0.9.202 에는 Stooq 경로가 없다.
#   그래서 '주·보조' 가 둘 다 야후였고, 야후가 늦는 날엔 둘 다 늦었다. 2026-09-23 에는 미국 장 마감
#   16.5시간 뒤에도 09-22 행의 **종가가 비어** 있어(거래량만 있음) _shape 가 그 행을 버렸고 표가 묵었다.
# Massive 무료 플랜의 grouped daily 는 **한 번 호출로 그날 미장 전 종목**(12,601)을 준다. 분당 5콜 · 2년.
#   09-08 을 우리 표와 대조: 종목 99.9% 일치 · 종가 1% 이내 95.9%(0.1% 이내 84%, 어긋남은 대부분 1달러 미만 소형주).
# 이력(1년)은 지금처럼 야후에서 받고 **최근 MV_DAYS 거래일만** Massive 값으로 덮는다 — 늦는 건 최근 며칠뿐이고,
#   야후가 마지막 날 거래량을 덜 채우던 문제([[us-source-stooq]])도 같이 풀린다. 둘 다 분할 반영 기준이라 맞물린다.
MV_DAYS = 5
_MV = None          # {YYYYMMDD: {티커: (시가, 고가, 저가, 종가, 거래량)}}


def _mv_key():
    k = os.environ.get("MASSIVE_API_KEY", "")
    if not k:
        env = BASE / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("MASSIVE_API_KEY="):
                    k = line.split("=", 1)[1].strip()
    return k


def recent_sessions(n):
    """마지막으로 끝난 거래일부터 거꾸로 n개(거래소 휴장일 규칙)."""
    from datetime import datetime as _dt, timedelta as _td
    last = last_session()
    if not last:
        return []
    d, out = _dt.strptime(last, "%Y%m%d").date(), []
    while len(out) < n:
        if d.weekday() < 5 and d not in nyse_closed_days(d.year):
            out.append(d.strftime("%Y%m%d"))
        d -= _td(1)
    return out


def massive_recent():
    """최근 MV_DAYS 거래일의 전 종목 일봉. 키가 없거나 실패하면 빈 dict — 그러면 예전처럼 야후만 쓴다."""
    global _MV
    if _MV is not None:
        return _MV
    _MV = {}
    key = _mv_key()
    if not key:
        log("  MASSIVE_API_KEY 없음 — 최근 거래일도 야후 값 그대로 쓴다")
        return _MV
    import requests
    days = recent_sessions(MV_DAYS)
    try:
        holes = [d for d in yahoo_hole_days() if d not in days]
    except Exception as e:
        holes = []; log(f"  야후 구멍 찾기 실패 — 최근 {MV_DAYS}일만 덮는다: {e!r}"[:120])
    if holes:
        log(f"  야후에 구멍 난 거래일 {len(holes)}일도 Massive 로 채운다: {', '.join(holes)}")
    for i, d in enumerate(days + holes):
        if i:
            time.sleep(12.5)                      # 무료 한도 분당 5콜
        for att in range(3):
            try:
                r = requests.get(f"https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/"
                                 f"{d[:4]}-{d[4:6]}-{d[6:]}", params={"adjusted": "true", "apiKey": key}, timeout=60)
                if r.status_code == 429:
                    time.sleep(60); continue
                j = r.json()
                break
            except Exception as e:
                j = {"status": f"실패 {e!r}"[:60]}
                time.sleep(5)
        R = {x["T"]: (x.get("o"), x.get("h"), x.get("l"), x.get("c"), x.get("v"))
             for x in (j.get("results") or []) if x.get("c")}
        log(f"  Massive {d}: {j.get('status')} · {len(R):,}종목")
        if len(R) > 5000:                          # 반쪽 응답은 안 쓴다
            _MV[d] = R
    return _MV


def yahoo_hole_days(span=260):
    """야후가 **영영 안 채운** 거래일 — 최근 MV_DAYS 창 밖으로 밀려나도 Massive 로 계속 덮기 위해서다.

    ⚠ 2026-09-25 발견: 09-22 는 사흘이 지나도 야후 S&P 일봉에 **날짜째 없고**, XOM·KO·PARR 등은 종가가 비어 있다
      (AAPL·MSFT 는 멀쩡). 최근 5일 덮기로는 09-29 부터 그날이 다시 구멍이 되어, 20일 수익률 같은 지표가
      하루 빠진 채로 계산된다. 거래소 휴장일 규칙상 거래일인데 S&P 에 없거나, 대표 10종목 중 3개 이상이
      종가를 안 가진 날을 구멍으로 본다. 표 이력이 1년이라 최근 span 거래일만 본다(Massive 무료는 2년까지).
    """
    import yfinance as yf
    last = last_session()
    if not last:
        return []
    d, cal = datetime.strptime(last, "%Y%m%d").date(), []
    while len(cal) < span:
        if d.weekday() < 5 and d not in nyse_closed_days(d.year) and d.strftime("%Y%m%d") not in SPECIAL_CLOSED:
            cal.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    start = f"{cal[-1][:4]}-{cal[-1][4:6]}-{cal[-1][6:]}"
    x = yf.download(["^GSPC"] + SCOUT, start=start, auto_adjust=False, progress=False, group_by="ticker")
    idx = {i.strftime("%Y%m%d") for i in x.index}
    sp = x["^GSPC"]["Close"]
    sp_ok = {i.strftime("%Y%m%d") for i, v in sp.items() if v == v}
    nan_n = {}
    for s in SCOUT:
        for i, v in x[s]["Close"].items():
            if v != v:
                k = i.strftime("%Y%m%d"); nan_n[k] = nan_n.get(k, 0) + 1
    out = [k for k in cal if (k not in sp_ok) or (k in idx and nan_n.get(k, 0) >= 3) or (k not in idx)]
    return sorted(k for k in out if k < last)       # 오늘 막 끝난 날은 '구멍' 이 아니라 '아직' 이다


def patch_recent(got):
    """야후 표의 최근 거래일을 Massive 값으로 덮는다(없으면 붙인다). 기준이 어긋난 종목은 건드리지 않는다."""
    MV = massive_recent()
    if not MV:
        return got
    for s, x in list(got.items()):
        add = {d: R[s] for d, R in MV.items() if s in R}
        if not add:
            continue
        # 기준 점검 — 겹치는 날 종가가 25% 넘게 다르면(분할 반영 시점 차이 등) 이 종목은 야후 그대로 둔다
        ok = True
        for d, v in add.items():
            if d in x.index:
                yc = float(x.at[d, "Close"])
                if yc > 0 and abs(v[3] / yc - 1) > 0.25:
                    ok = False; break
        if not ok:
            continue
        new = pd.DataFrame([v for v in add.values()], index=list(add.keys()),
                           columns=["Open", "High", "Low", "Close", "Volume"])
        y = pd.concat([x[~x.index.isin(new.index)], new]).sort_index()
        if _OPEN and len(y.index) and y.index[-1] == _OPEN:
            y = y.iloc[:-1]
        got[s] = y
        _SRC["massive"] += 1
    return got


def fetch(syms, start):
    """Stooq 를 먼저 받고, 빠진 종목만 야후로 메운다.

    한쪽이 놓친 것을 다른 쪽이 채우므로 어느 한쪽보다 항상 낫다.
    USE_YF=1 이면 예전처럼 야후만 쓴다(Stooq 가 막혔을 때의 탈출구).
    """
    if os.environ.get("USE_YF") == "1":
        out = fetch_yahoo(syms, start)
        _SRC["yahoo"] += len(out)
        return out
    out = fetch_stooq(syms, start)
    _SRC["stooq"] += len(out)
    miss = [s for s in syms if s not in out]
    if miss:
        try:
            got = fetch_yahoo(miss, start)
            _SRC["yahoo"] += len(got)
            out.update(got)
        except Exception as e:
            log(f"  야후 보충 실패({len(miss)}종목): {e!r}"[:110])
    return patch_recent(out)


def metrics(x, bbdates=None, edates=None):
    """한국 표와 같은 이름의 지표를 만든다. 값이 모자라면 None.

    bbdates: 그 종목의 자사주 집행 보고일(YYYYMMDD) 목록. [자사주 낙폭] 이 쓴다.
    edates : 그 종목의 실적 발표일(YYYYMMDD) 목록. [실적 서프라이즈] 가 쓴다."""
    c = x["Close"].astype(float).values
    v = x["Volume"].astype(float).values
    n = len(c)
    r = lambda k: round((c[-1] / c[-1 - k] - 1) * 100, 2) if n > k and c[-1 - k] else None
    amt = c * v / 1e6                                   # 백만 달러
    a20 = float(np.nanmean(amt[-20:])) if n >= 20 else None
    hi60 = float(np.nanmax(c[-60:])) if n >= 20 else None
    lo60 = float(np.nanmin(c[-60:])) if n >= 20 else None
    ma20 = float(np.nanmean(c[-20:])) if n >= 20 else None
    ma25 = float(np.nanmean(c[-25:])) if n >= 25 else None
    # 60일 최대낙폭 — 고점 이후 저점까지
    w = c[-60:] if n >= 60 else c
    peak = np.maximum.accumulate(w)
    mdd = float(np.min(w / peak - 1) * 100) if len(w) else None
    hi250 = float(np.nanmax(c[-250:])) if n >= 60 else None
    lo250 = float(np.nanmin(c[-250:])) if n >= 60 else None
    ret = np.diff(c) / c[:-1] * 100
    vol20 = float(np.nanstd(ret[-20:])) if len(ret) >= 20 else None
    above = float(np.mean(c[-20:] > pd.Series(c).rolling(20).mean().values[-20:]) * 100) if n >= 40 else None
    # su1 = 당일 거래량 / 직전 20일 평균 — [낙폭과대]·[저PBR 낙폭] 이 쓰는 투매 신호
    su1 = (float(v[-1] / np.nanmean(v[-21:-1])) if n >= 21 and np.nanmean(v[-21:-1]) else None)
    # nh5 = [상승장 신고가] 이벤트 — 52주 고점(고가 기준) 대비 -5% 이내에 **오늘 처음** 들어왔고
    #   최근 20거래일은 밖에 있었다. '신고가권에 있다'(상태)로 걸면 상승장에 하루 400종목이
    #   매일 다시 걸리는데, '오늘 들어왔다'(사건)로 걸면 한 종목이 한 번만 걸려 하루 10종목
    #   안팎이 된다(us_n1_reduce*.py · 2026-09-10 채택). 종목 자기 이력만으로 계산된다.
    # remo = 최근 3일 평균 거래량 ÷ 최근 한 달 평균(3일 전부터 20일). [상승장 신고가]가
    #   'remo ≤ 100' 으로 쓴다 — **거래량이 붙으며 올라온 신고가는 이미 늦었다**.
    #   실측: 재점화를 요구할수록 단조 악화(≥120% 초과 +0.62 → ≥300% -0.30), 반대로
    #   식은 채로 진입한 쪽이 +1.02 · 검증 +1.38 · 양수해 10/11 (us_n1_vol*.py · 2026-09-10).
    #   국내 [조용한 신고가]의 '최근 3거래일 ≤ 2개월 평균의 120%' 와 같은 계열이다.
    remo = None
    if n >= 23:
        _mo = float(np.nanmean(v[-23:-3]))
        if _mo > 0: remo = float(np.nanmean(v[-3:]) / _mo * 100)
    hh = x['High'].astype(float).values if 'High' in x else c
    nh5 = None
    if n >= 271:
        hi250s = pd.Series(hh).rolling(250).max().values
        within = (c / hi250s - 1) * 100 >= -5
        nh5 = bool(within[-1] and not np.any(within[-21:-1]))
    # bbnew = [자사주 낙폭] 이벤트 — 「52주 고점 -30% 이하 · 20일 -20% 이하 · 자사주 집행 중」
    #   상태에 **오늘 처음** 들어왔다(최근 20거래일은 그 상태가 아니었다).
    #   상태로 걸면 하루 평균 4.7종목(최대 92)이 매일 다시 걸리는데, 사건으로 걸면 0.64종목이
    #   되면서 성적은 그대로다 — 중앙 +6.96→+6.78 · 절삭 +4.71→+4.57 · 양수해 9/11 유지 ·
    #   스트레스(2009~15)는 오히려 +0.67→+0.79 (us_buyback5.py · 2026-09-10 채택).
    #   [상승장 신고가]의 nh5 와 같은 설계다. 유동성(그날 미장 전체 대비 백분위)은 종목 하나로는
    #   알 수 없어 사건 정의에서 빼고 화면·알림이 그날 따로 매긴다.
    bbnew = None
    if n >= 271:
        _hi = pd.Series(c).rolling(250).max().values
        _fh = (c / _hi - 1) * 100
        _r20 = np.full(n, np.nan); _r20[20:] = (c[20:] / c[:-20] - 1) * 100
        _bb = np.array(sorted(bbdates)) if bbdates else np.array([])
        _idx = x.index
        _st = np.zeros(n, bool)
        for _k in range(max(0, n - 21), n):
            if not (_fh[_k] <= -30 and _r20[_k] <= -20): continue
            if not len(_bb): continue
            _d1 = _idx[_k].strftime('%Y%m%d')
            _d0 = (_idx[_k] - pd.Timedelta(days=88)).strftime('%Y%m%d')
            _st[_k] = bool(((_bb <= _d1) & (_bb >= _d0)).any())
        bbnew = bool(_st[-1] and not _st[max(0, n - 21):n - 1].any())
    # pinr = 최근 20일 변동성 ÷ 최근 250일 변동성 (자기 과거 대비 얼마나 죽었나)
    # hl20 = 최근 20일 고저폭(%)
    #   인수 합의가 난 종목은 인수가에 못 박혀 **자기 평소보다** 조용해진다. 그런데 규칙이 보는
    #   신호(고점 근처 + 조용한 거래량)를 완벽하게 만족해 버린다 — 위로는 인수가에서 막히고
    #   아래로만 열려 있어 기대값이 0 인데도 걸린다(2026-09-10 DV: 인수가 $13.60 에 고정, pinr 0.06).
    #   **절대** 변동성으로 자르면 KO·WMT 같은 대형 우량주가 걸려 쓸모없다 — 대형주는 원래 조용하다.
    #   자기 과거 대비로 봐야 갈린다. SPAC(합병 전 $10 고정)·우선주도 같이 걸러진다.
    #   실측: 묶인 쪽 173건 초과 -0.21 · 절삭 -1.09 · 검증 -1.88 · 양수해 5/11 (us_n1_pinned2.py)
    pinr = hl20 = None
    if n >= 251:
        _r = np.diff(c) / c[:-1] * 100
        _v250 = float(np.nanstd(_r[-250:]))
        if _v250 > 0 and vol20 is not None: pinr = float(vol20 / _v250)
    if n >= 20:
        _lo = float(np.nanmin(c[-20:]))
        if _lo > 0: hl20 = float(np.nanmax(c[-20:]) / _lo - 1) * 100
    # absr = 최근 60일 **평균 |일간수익률|**(%). [잔잔한 급등주] 가 쓰는 '조용함' 지표다.
    #   Frog-in-the-Pan(정보 이산성) 계열 — 1년에 크게 올랐는데 하루하루는 잔잔한 종목이
    #   시장의 반응이 덜 끝나 뒤에 더 간다. 같은 상승폭인데 요란한 쪽(absr>=3)은 정반대로
    #   승률 40.5% · 초과 -2.59 · 중앙 -9.09 다(us_tech8~12 · 2026-09-11).
    #   ⚠ 변동성(표준편차)이 아니라 **평균 절댓값**이다. 원논문의 ID(음봉비율-양봉비율)보다
    #     이 프록시가 실측에서 더 나았다(절삭Δ +0.79 vs -0.08).
    absr = float(np.nanmean(np.abs(ret[-60:]))) if len(ret) >= 60 else None
    # qnew = [잔잔한 급등주] 이벤트 — 「1년 120%↑ · 3·6·12개월 전부 양수 · 60일 평균
    #   일간등락 1.5% 이하」에 **오늘 처음** 들어왔고 최근 20거래일은 밖에 있었다.
    #   상태로 걸면 한 종목이 평균 5.6일(최대 125일) 연속으로 다시 걸려 화면이 지저분해진다
    #   — 원시 종목-일이 중복제거 신호의 12.9배다. 사건형은 그것과 성적이 같으면서
    #   (초과 3.05→3.07) CI 가 +0.92→+1.15, 양수해가 8/11→9/11 로 조금 낫다.
    #   [상승장 신고가]의 nh5 와 같은 방식·같은 창(20일)이다. 종목 자기 이력만으로 계산한다.
    #   qage = 그 사건이 **며칠 전**이었나(0=오늘). 규칙은 qage<=3 을 후보로 본다 —
    #   놓쳐도 사흘 안에는 사도 된다. 늦게 들어가는 대가 실측(2026-09-11):
    #     당일 초과 +2.94 / 3일 +2.85 / 5일 +2.45 / **10일 +1.76** (절삭Δ +1.00→+0.23 · 9/11→6/11)
    #   이 규칙이 먹는 게 '조용히 스며드는 정보의 뒤늦은 반영' 이라 며칠 늦어도 남아 있다.
    #   여기서는 7일치까지 계산해 두고 문턱은 화면·알림이 정한다(나중에 늘리려면 코드만 바꾼다).
    qnew = None; qage = None
    if n >= 271:
        _cs = pd.Series(c)
        _ar = pd.Series(np.abs(ret)).rolling(60).mean().values            # 60일 평균 |일간등락|
        _q = np.concatenate([[np.nan], _ar])                              # ret 은 하루 짧다
        _r = lambda k: _cs / _cs.shift(k) - 1
        _own = ((_r(250) >= 1.20) & (_r(60) > 0) & (_r(120) > 0) & (_r(250) > 0)
                & (pd.Series(_q) <= 1.5)).values
        # 사건 = 오늘 조건 안에 있고 직전 20거래일은 밖에 있었다
        _pv = np.concatenate([[False], _own[:-1]])
        _ev = np.array([bool(_own[i] and not _pv[max(0, i - 19):i + 1].any())
                        for i in range(max(0, n - 8), n)])
        qnew = bool(_ev[-1])
        _w = np.where(_ev)[0]
        if len(_w): qage = int(len(_ev) - 1 - _w[-1])
    # ── [실적 서프라이즈] 재료 (2026-09-15) ────────────────────────────────
    #   발표일 **다음 거래일**이 신호일이다(장전·장후 발표가 섞여 있어 늦게 사는 쪽으로 통일).
    #   그날의 전일 대비 등락률이 '갭' 이고, 그 뒤 며칠 지났는지가 peadage 다.
    #   ⚠ 서프라이즈 **백분위**는 그날 발표한 종목 전체를 봐야 알 수 있어 여기서 못 낸다 —
    #     아래 후처리(peadq)가 채운다. 여기서는 날짜·갭·경과일만 만든다.
    #   ⚠ 수집이 주 1회라 신호가 며칠 늦는다. 실측(us_pead_delay.py)에서 **D+7 까지는
    #     성적이 사실상 그대로**였고 D+8 부터 꺾였다 — 그래서 사이트 규칙이 peadage<=7 을 본다.
    peade = peadd = peadgap = peadage = None
    if edates is not None and len(edates) and n >= 3:
        _idx = [str(z)[:10].replace('-', '') for z in x.index]
        _ed = sorted(set(str(z) for z in edates))
        for _e in reversed(_ed):
            _k = next((j for j, d0 in enumerate(_idx) if d0 > _e), None)   # 발표 **다음** 거래일
            if _k is None or _k < 1:
                continue
            peade = _e                                  # 발표일 (백분위를 매기는 기준)
            peadd = _idx[_k]
            peadgap = round((c[_k] / c[_k - 1] - 1) * 100, 2) if c[_k - 1] else None
            peadage = int(len(_idx) - 1 - _k)
            break
    ch = round(c[-1] - c[-2], 2) if n >= 2 else None
    return dict(
        c=round(float(c[-1]), 2), ch=ch,
        chpct=round((c[-1] / c[-2] - 1) * 100, 2) if n >= 2 and c[-2] else None,
        ret3=r(3), ret10=r(10), ret20=r(20), ret60=r(60), ret250=r(250),
        r1m=r(20), r3m=r(60), r6m=r(120), r1y=r(250),
        amt=round(float(amt[-1]), 2) if n else None,
        amt20=round(a20, 2) if a20 is not None else None,
        fromhi=round((c[-1] / hi250 - 1) * 100, 1) if hi250 else None,
        fromlo=round((c[-1] / lo250 - 1) * 100, 1) if lo250 else None,
        dma20=round((c[-1] / ma20 - 1) * 100, 2) if ma20 else None,
        dev25=round((c[-1] / ma25 - 1) * 100, 2) if ma25 else None,
        su1=round(su1, 2) if su1 is not None else None,
        nh5=nh5, bbnew=bbnew,
        pinr=round(pinr, 3) if pinr is not None else None,
        hl20=round(hl20, 2) if hl20 is not None else None,
        remo=round(remo, 1) if remo is not None else None,
        mdd60=round(mdd, 1) if mdd is not None else None,
        vol20=round(vol20, 2) if vol20 is not None else None,
        absr=round(absr, 3) if absr is not None else None,
        qnew=qnew, qage=qage,
        peade=peade, peadd=peadd, peadgap=peadgap, peadage=peadage,
        above20=round(above, 1) if above is not None else None,
        v=[int(z) if z == z else 0 for z in v[-NDAY:]],
    )


# 야후가 그날 일봉을 **다 올렸는지** 먼저 본다. 6천 종목을 6분 받고 나서야 아는 건 늦다.
SCOUT = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "JNJ", "WMT", "PG", "KO"]
# 휴장일 규칙에 없는 임시 휴장(대통령 국장 등) — 달력에서 뺀다. 새로 생기면 여기에 적는다.
SPECIAL_CLOSED = {"20250109"}   # 카터 전 대통령 국장


def nyse_closed_days(y):
    """뉴욕거래소 정기 휴장일(그해). 토요일 휴일은 금요일, 일요일은 월요일로 옮겨 쉰다
    (단 1월 1일이 토요일이면 전년 12/31 은 쉬지 않는다)."""
    from datetime import date, timedelta as td

    def nth(month, wd, n):          # n번째 요일 (n=-1 이면 마지막)
        if n > 0:
            d = date(y, month, 1)
            d += td((wd - d.weekday()) % 7)
            return d + td(weeks=n - 1)
        d = date(y, month + 1, 1) - td(1) if month < 12 else date(y, 12, 31)
        return d - td((d.weekday() - wd) % 7)

    def obs(d):
        return d - td(1) if d.weekday() == 5 else (d + td(1) if d.weekday() == 6 else d)

    a = y % 19; b, c = divmod(y, 100); d_, e = divmod(b, 4); f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d_ - g + 15) % 30; i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    easter = date(y, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)
    days = {nth(1, 0, 3), nth(2, 0, 3), easter - td(2), nth(5, 0, -1), obs(date(y, 7, 4)),
            nth(9, 0, 1), nth(11, 3, 4), obs(date(y, 12, 25))}
    nyd = date(y, 1, 1)
    if nyd.weekday() != 5:
        days.add(obs(nyd))
    if y >= 2022:
        days.add(obs(date(y, 6, 19)))
    return days


def last_session():
    """**마지막으로 끝난** 미장 거래일 — 선발대가 '그날 자료가 올라왔나' 를 물을 잣대다.

    ⚠ 2026-09-23 사고: 예전엔 야후 S&P500 일봉으로 정했는데, 야후가 **장 마감 16시간 뒤에도**
      09-22 봉을 안 주고(기간을 바꿔도 전부 09-21) 요청마다 답이 달랐다. 잣대가 하루 밀리니
      선발대는 '09-21 이 있다' 며 바로 통과했고, 그 시각 Stooq 는 09-22 를 0.7% 만 올려 둔 상태라
      표가 통째로 하루 묵은 채 나갔다(check_fresh 빨간불). 국내 index_cal 과 같은 병이다.
    → 데이터 소스에 기대지 않고 **거래소 휴장일 규칙으로 계산**한다. 오늘 장은 16:05(ET) 뒤에만 끝난 걸로 본다.
      규칙에 없는 임시 휴장(국장 등)이 있으면 선발대가 그날을 기다리다 경고만 남긴다 — 드물고 해가 적다.
    """
    from datetime import datetime as _dt, timedelta as _td
    try:
        from zoneinfo import ZoneInfo
        n = _dt.now(ZoneInfo("America/New_York"))
    except Exception:
        from datetime import timezone
        n = _dt.now(timezone.utc) - _td(hours=5)
    d = n.date()
    if n.strftime("%H:%M") < "16:05":
        d -= _td(1)
    for _ in range(15):
        if d.weekday() < 5 and d not in nyse_closed_days(d.year):
            return d.strftime("%Y%m%d")
        d -= _td(1)
    return None


def wait_for_data(start, tries=3, gap=300):
    """대표 종목이 마지막 거래일 자료를 가질 때까지 기다린다. 돌려주는 값은 그 거래일.

    ⚠ 2026-09-16 사고: 21:46(ET)에 수집했는데 야후가 그날 일봉을 5%(303/5,683)만
      올려 놓은 상태였다. 기준일이 최빈값이라 표가 통째로 **하루 묵은 채** 나갔고,
      그날 난 진입 이벤트가 빠져 미장 규칙이 어제 신호를 보여 줬다.
      장 마감 뒤 다섯 시간이 지나도 이런 일이 있으므로 시각에 기대면 안 된다.
      **대표 종목에게 직접 물어보고**, 아니면 기다린다. 하루 묵은 표보다 15분이 싸다.
    """
    want = last_session()
    if not want:
        log("  마지막 거래일을 못 알아냈다 — 기다리지 않고 그냥 받는다")
        return None
    # Stooq 가 전날 미장을 올리는 시각은 들쭉날쭉하다 — 09-22 엔 한국 10~13시, 09-23 엔 20:40~21:00.
    # 저녁 본 수집(한국 18~23시)에서 아직이면 **30분까지** 기다린다: 이 수집을 놓치면 21:30 예약
    # (유실이 잦다) 말고는 그날 밤 미장 개장(22:30) 전에 채울 길이 없다. 아침 수집은 어차피
    # 오전 늦게야 올라오니 오래 기다려도 헛수고라 예전처럼 짧게 본다.
    _kst = (datetime.utcnow().hour + 9) % 24
    if 18 <= _kst <= 23:
        tries, gap = max(tries, 7), 300
    global _MV
    for k in range(tries):
        if _MV is not None and want not in _MV:     # Massive 에도 아직 없었으면 이번 시도 때 다시 묻는다
            _MV = None
        try:
            got = fetch(SCOUT, start)
        except Exception as e:
            log(f"  선발대 실패({k+1}/{tries}): {e!r}"[:110]); got = {}
        have = [str(x.index[-1]) for x in got.values() if len(x.index)]
        n_ok = sum(1 for d in have if d >= want)
        log(f"  선발대 {n_ok}/{len(have)}종목이 {want} 자료를 가졌다")
        if have and n_ok >= len(have) * 0.8:
            return want
        if k < tries - 1:
            log(f"  공급처가 아직 {want} 를 다 안 올렸다 — {gap//60}분 기다린다"
                f" ({k+1}/{tries-1})")
            time.sleep(gap)
    log(f"::warning::{want} 자료가 끝내 안 올라왔다 — 묵은 표가 될 수 있다")
    return want


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    U = tickers()
    if a.limit:
        U = U.head(a.limit)
    syms = U.Symbol.tolist()
    NM = dict(zip(U.Symbol, U.Name))
    MK = dict(zip(U.Symbol, U.mk))
    IND = dict(zip(U.Symbol, U.get("Industry", pd.Series(dtype=object))))
    start = (pd.Timestamp.today() - pd.Timedelta(days=430)).strftime("%Y-%m-%d")
    log(f"{len(syms):,}종목 · {start} 이후 · {a.chunk}개씩")

    # ── 시가총액 — SEC XBRL 주식수(us_fin.py 가 만든 data/us/fin.pkl) × 종가 ─────────
    #   yfinance 는 종목마다 따로 물어야 해서 6천 종목이면 너무 느리다. 이미 받아 둔 SEC
    #   제출 주식수를 쓰면 공짜다. 티커별 **최신 제출분**만 쓰고, 없는 종목(ADR·외국기업 등)은
    #   None 으로 남겨 화면에 빈칸으로 둔다. 단위는 거래대금과 같은 **백만 달러**.
    SHR = {}
    _fp = BASE / "data" / "us" / "fin.pkl"
    if _fp.exists():
        _F = pd.read_pickle(_fp).dropna(subset=["shares"])
        _F = _F[_F.shares > 0].sort_values("filed").drop_duplicates("ticker", keep="last")
        SHR = dict(zip(_F.ticker, _F.shares))
        log(f"  주식수 {len(SHR):,}종목 (SEC XBRL) → 시가총액 계산")
    else:
        log("  data/us/fin.pkl 없음 — 시가총액은 빈칸으로 둔다")

    # ── 자사주 집행 보고일 — collect_us_buyback.py 가 만든 CSV. [자사주 낙폭] 이 쓴다 ──
    BBD = {}
    _bp = BASE / "data" / "us" / "buyback_recent.csv"
    if _bp.exists():
        try:
            _B = pd.read_csv(_bp, dtype={"filed": str})
            BBD = _B.groupby("ticker").filed.apply(lambda z: sorted(set(z))).to_dict()
            log(f"  자사주 보고 {len(BBD):,}종목 (data/us/buyback_recent.csv)")
        except Exception as e:
            log(f"  자사주 CSV 읽기 실패 — [자사주 낙폭] 은 쉰다: {e!r}"[:120])
    else:
        log("  data/us/buyback_recent.csv 없음 — [자사주 낙폭] 은 쉰다")

    # ── 실적 발표일·서프라이즈 — collect_us_earn.py 가 만든 CSV. [실적 서프라이즈] 가 쓴다 ──
    EDT, ESUR = {}, {}
    _ep = BASE / "data" / "us" / "earn_recent.csv"
    if _ep.exists():
        try:
            _E = pd.read_csv(_ep, dtype={"edate": str})
            _E = _E.dropna(subset=["surprise"])
            EDT = _E.groupby("ticker").edate.apply(lambda z: sorted(set(z))).to_dict()
            ESUR = {(a_, b_): float(c_) for a_, b_, c_ in
                    zip(_E.ticker, _E.edate, _E.surprise)}
            log(f"  실적 발표 {len(EDT):,}종목 · {len(_E):,}건 (data/us/earn_recent.csv)")
        except Exception as e:
            log(f"  실적 CSV 읽기 실패 — [실적 서프라이즈] 는 쉰다: {e!r}"[:120])
    else:
        log("  data/us/earn_recent.csv 없음 — [실적 서프라이즈] 는 쉰다")

    WANT = wait_for_data(start)

    rows, dates, t0, fail = [], [], time.time(), 0
    lastd = []          # 종목마다 마지막 거래일 — 표의 '기준일' 을 최빈값으로 정한다
    for i in range(0, len(syms), a.chunk):
        part = syms[i:i + a.chunk]
        try:
            got = fetch(part, start)
        except Exception as e:
            fail += len(part); log(f"  {i//a.chunk+1}묶음 실패: {e}"); continue
        for s, x in got.items():
            try:
                m = metrics(x, BBD.get(s), EDT.get(s))
            except Exception:
                continue
            if not dates or len(x.index) > len(dates):
                dates = list(x.index[-NDAY:])
            if len(x.index): lastd.append(str(x.index[-1]))
            m.update(t=s, n=str(NM.get(s, s)), mk="US", ex=str(MK.get(s, "")),
                     pref=False, th=[],
                     cap=(round(SHR[s] * m["c"] / 1e6, 1) if SHR.get(s) and m.get("c") else None))
            rows.append(m)
        if (i // a.chunk) % 10 == 0:
            log(f"  {i+len(part):,}/{len(syms):,} · 담은 종목 {len(rows):,} · {time.time()-t0:.0f}초")
    log(f"완료 {len(rows):,}종목 (실패 {fail:,}) · {time.time()-t0:.0f}초")
    # 어느 공급처가 얼마나 줬는지 남긴다 — 한쪽이 조용히 죽으면 여기서 먼저 보인다
    log(f"  공급처: 야후(FDR 경로) {_SRC['stooq']:,} · 야후 보충 {_SRC['yahoo']:,} · 최근 {MV_DAYS}거래일 Massive 로 덮음 {_SRC['massive']:,}")
    if not rows:
        log("한 종목도 못 받았다 — 파일을 덮어쓰지 않는다"); return 1

    # ── 기준일 가드 — 미장 표가 **뒤로 가는 것**을 막는다 ──────────────────
    # 2026-09-11 사고: 정규 수집이 09-10 이 아니라 **09-09** 자료를 받아 덮어썼다.
    # 그러면 그날 난 [상승장 신고가] 진입 이벤트(nh5)가 통째로 사라져 규칙이 조용히 0 이 된다.
    # 미장은 국내와 장 시간이 달라 '오늘' 의 뜻이 다르므로, 표 자신의 기준일로 판단해야 한다.
    from collections import Counter
    asof = Counter(lastd).most_common(1)[0][0] if lastd else None
    _stale = Counter(lastd).most_common(3)
    log(f"  기준일 {asof} (종목별 마지막 거래일 분포 {_stale})")
    if WANT and asof and str(asof) < str(WANT):
        log(f"::warning::기준일이 {asof} 라 마지막 거래일 {WANT} 보다 뒤처졌다 — "
            f"그날 난 진입 이벤트가 빠진다(선발대는 통과했는데 본진이 묵었다)")
    # ⚠ Actions 에서는 파이프라인이 site/ 를 지운 뒤에 이 스크립트가 돌아서 **로컬 파일이 없다**.
    #   그래서 비교 대상은 로컬이 아니라 **지금 서비스 중인 배포본**이어야 한다.
    #   표는 3.7MB 라 매번 받을 수 없지만 uscal.json 은 10KB 이고 같은 수집이 asof 를 적는다.
    _oa = None
    if OUT.exists():
        try:
            _old = json.load(open(OUT, encoding="utf-8"))
            _oa = _old.get("asof") or (_old.get("dates") or [None])[-1]
        except Exception as e:
            log(f"  로컬 표 확인 실패: {e!r}"[:120])
    if _oa is None:
        try:
            import urllib.request
            _u = SITE_URL + "/data/uscal.json?cb=" + str(int(time.time()))
            _c = json.loads(urllib.request.urlopen(
                urllib.request.Request(_u, headers=_cf_headers()), timeout=30).read().decode("utf-8"))
            # asof 가 있으면 표끼리 견주고, 없으면(옛 배포본) 달력의 마지막 거래일로 대신한다.
            # 대체값은 더 엄격하다 — 그날 자료를 못 받았으면 아예 안 올린다. 한 번 올라가면 asof 가 생긴다.
            _oa = _c.get("asof") or (_c.get("dates") or [None])[-1]
            log(f"  배포본 기준일 {_oa} (uscal.json)")
        except Exception as e:
            log(f"  배포본 확인 실패(계속 진행): {e!r}"[:120])
    if asof and _oa and str(asof) < str(_oa):
        log(f"::warning::받은 자료가 서비스 중인 것({_oa})보다 오래됐다({asof}) — "
            f"덮어쓰지 않는다. 미장 규칙이 하루 묵은 표로 도는 것을 막는다")
        return 0

    # ── [낙폭과대]·[저PBR 낙폭] 이 쓰는 재료 — 업종 60일 수익률 · PBR · 부채비율 ────
    #   한국 규칙을 미국에 대입했을 때 통과한 둘이다(us_rules.py). 사이트에도 얹으려면
    #   이 셋이 필요하다. 업종은 tickers.csv 의 Industry, 나머지는 SEC XBRL(fin.pkl).
    import collections
    by_ind = collections.defaultdict(list)
    for m in rows:
        ind = IND.get(m['t'])
        if ind and m.get('ret60') is not None: by_ind[ind].append(m['ret60'])
    umed = {k: float(np.median(v)) for k, v in by_ind.items() if len(v) >= 5}   # 회원 5종목 이상
    # ⚠ fin.pkl(18MB)은 **내 PC 에만** 있다 — 리포에 없으니 워크플로에서는 늘 비었고,
    #   그래서 PBR·부채비율이 전부 null 이라 [저PBR 낙폭]은 하락장에도 걸릴 수 없었다
    #   (2026-09-21 발견). 커밋되는 요약본(fin_recent.csv, us_fin.py 가 만든다)을 먼저 본다.
    FIN = {}
    _fp2 = BASE / 'data' / 'us' / 'fin.pkl'
    _fc2 = BASE / 'data' / 'us' / 'fin_recent.csv'
    if _fp2.exists():
        _F2 = pd.read_pickle(_fp2).sort_values('filed').drop_duplicates('ticker', keep='last')
        FIN = _F2.set_index('ticker')[['equity', 'liab', 'shares']].to_dict('index')
    elif _fc2.exists():
        _F2 = pd.read_csv(_fc2, dtype={'ticker': str})
        FIN = _F2.set_index('ticker')[['equity', 'liab', 'shares']].to_dict('index')
        log(f'  재무 요약본 fin_recent.csv {len(FIN):,}종목 (fin.pkl 없음)')
    nu = npbr = ndbt = 0
    for m in rows:
        ind = IND.get(m['t'])
        m['up'] = str(ind) if ind else None
        m['sr60'] = round(umed[ind], 2) if ind in umed else None      # 한국 표와 같은 열 이름
        f = FIN.get(m['t']) or {}
        eq, li, sh = f.get('equity'), f.get('liab'), f.get('shares')
        # ⚠ NaN 은 truthy 다 — `if eq and sh` 를 그냥 통과해 NaN 결과를 만든다.
        #   그러면 json 에 NaN 이 그대로 실리고, 파이썬은 읽지만 **브라우저 JSON.parse 는 못 읽어**
        #   사이트가 미장 표를 통째로 버린다(=미장 규칙 전원 사망). 2026-09-11 selftest 가 잡았다.
        _num = lambda z: (float(z) if z is not None and float(z) == float(z)
                          and abs(float(z)) != float('inf') else None)
        eq, sh, li = _num(eq), _num(sh), _num(li)
        m['pbrd'] = (round(m['c'] * sh / eq, 3) if eq and sh and eq > 0 and m.get('c') else None)
        m['dbt'] = (round(li / eq * 100, 1) if eq and li is not None and eq > 0 else None)
        nu += m['sr60'] is not None; npbr += m['pbrd'] is not None; ndbt += m['dbt'] is not None
    log(f'  업종 60일수익 {nu:,}종목 · PBR {npbr:,} · 부채비율 {ndbt:,} (전체 {len(rows):,})')

    # ── 자사주 — 마지막 집행 보고 이후 며칠 지났나 (사이트 규칙 [자사주 낙폭] 이 쓴다) ──
    # ── [실적 서프라이즈] 백분위 — **그날 발표한 종목 전체** 안에서의 순위 ──────────
    #   서프라이즈 %는 EPS 가 0 근처면 ±769,900% 같은 값이 나온다. 원값을 그대로 쓰면
    #   그 몇 건이 전부를 결정하므로 **백분위로 바꿔** 쓴다(us_pead.py 와 같은 방식).
    #   발표가 5건 미만인 날은 백분위가 의미 없어 비워 둔다.
    _nq = 0
    if ESUR:
        _t = pd.DataFrame([(k[0], k[1], v) for k, v in ESUR.items()],
                          columns=["ticker", "edate", "sur"])
        _sz = _t.groupby("edate").sur.transform("size")
        _t["q"] = _t.groupby("edate").sur.rank(pct=True)
        _t = _t[_sz >= 5]
        _ESQ = {(a_, b_): round(float(c_), 3)
                for a_, b_, c_ in zip(_t.ticker, _t.edate, _t.q)}
        for m in rows:
            _e = m.get("peade")
            m["peadq"] = _ESQ.get((m["t"], _e)) if _e else None
            _nq += m["peadq"] is not None
        log(f"  실적 서프라이즈 백분위 {_nq:,}종목")
    else:
        for m in rows:
            m["peadq"] = None

    #   collect_us_buyback.py 가 SEC XBRL 에서 뽑아 둔 data/us/buyback_recent.csv 를 읽는다.
    #   규칙은 '최근 60거래일 안에 자사주 집행을 보고했나' 를 보는데, 화면은 거래일 이력을
    #   갖고 있지 않으므로 **달력일 88일**(60거래일의 근사)로 잰다. 실측은 거래일 기준이었고
    #   이웃(20~250거래일)이 넓은 고원이라 이 근사로 결론이 바뀌지 않는다.
    nbb = 0
    _bp = BASE / 'data' / 'us' / 'buyback_recent.csv'
    if _bp.exists():
        try:
            _B = pd.read_csv(_bp, dtype={'filed': str})
            _last = _B.groupby('ticker').filed.max()
            _today = pd.Timestamp(str(dates[-1])[:10]) if dates else pd.Timestamp.today()
            _days = (_today - pd.to_datetime(_last, format='%Y%m%d')).dt.days
            _map = _days.to_dict()
            for m in rows:
                d_ = _map.get(m['t'])
                m['bbd'] = int(d_) if d_ is not None and d_ == d_ and d_ >= 0 else None
                nbb += m['bbd'] is not None
            log(f'  자사주 보고 이력 {nbb:,}종목 · 88일 이내 '
                f'{sum(1 for m in rows if (m.get("bbd") or 999) <= 88):,}종목 · '
                f'오늘 새로 걸린 종목 {sum(1 for m in rows if m.get("bbnew")):,}')
        except Exception as e:
            log(f'  자사주 읽기 실패 — 규칙이 쉰다: {e!r}'[:120])
            for m in rows: m.setdefault('bbd', None)
    else:
        log('  data/us/buyback_recent.csv 없음 — [자사주 낙폭] 은 쉰다')
        for m in rows: m['bbd'] = None

    # ── 국면 — S&P500 60일선 (사이트 규칙 [상승장 신고가] 가 쓴다) ────────────
    #   한국 표의 kospi 객체와 같은 자리다. 이게 없으면 사이트가 미장 국면을 알 수 없다.
    us_reg = {}; us_days = []; usdkrw = None
    try:
        import yfinance as _yf          # fetch() 안에서만 import 하고 있어 여기선 새로 부른다
        sp = _yf.download('^GSPC', period='2y', auto_adjust=False, progress=False)
        c = sp['Close'] if 'Close' in sp else sp.iloc[:, 0]
        c = c.squeeze().dropna()
        # ⚠ 지수와 달력은 fetch() 를 거치지 않는다 — 미완결 봉 가드를 여기에도 따로 걸어야 한다.
        #   2026-09-11 에 종목 표만 막고 여기를 빼먹어서, 표 기준일은 09/10 인데 달력에는
        #   09/11 이 들어갔다. 화면이 둘을 견주고 "표가 묵었다" 고 헛경보를 냈다.
        _os = open_session()
        if _os and len(c.index) and c.index[-1].strftime('%Y%m%d') == _os:
            c = c.iloc[:-1]
            log(f"  아직 안 끝난 미장({_os}) 봉은 지수·달력에서도 뺀다")
        ma60 = float(c.rolling(60).mean().iloc[-1])
        us_reg = {'date': c.index[-1].strftime('%Y%m%d'), 'close': float(c.iloc[-1]),
                  'ma60': ma60, 'up60': bool(float(c.iloc[-1]) > ma60)}
        # 미장 **거래일 달력** — 보유일·규칙상 매도일을 세는 데 쓴다.
        #   국내는 종목별 일봉 파일(data/stock/*.json)의 행 수로 보유일을 세는데 미장은 그 파일이
        #   없어서 늘 0일로 나왔다(2026-09-11 사용자 신고: PARR 보유일 0일). 종목 6천 개짜리
        #   파일을 만드는 대신 달력 하나만 실어 보내면 된다. 미국 휴장일은 한국과 다르므로
        #   한국 달력으로 대신할 수 없다.
        #   ⚠ 2026-09-25 발견: 야후 S&P 일봉에 **09-22 줄이 아예 없다**(빈 값도 아니고 날짜째 없음, 사흘 뒤에도).
        #   달력을 S&P 날짜로만 만들었더니 09-22 가 통째로 빠져 보유일·매도일이 하루씩 어긋났다.
        #   → 거래소 휴장일 규칙(last_session 과 같은 계산)으로 만든 날을 합친다. 규칙에 없는 임시 휴장은
        #     S&P 에도 없을 테니 SPECIAL_CLOSED 에 적어 뺀다.
        sp_days = {d.strftime('%Y%m%d') for d in c.index}
        _ls = last_session()
        _d, _end = c.index[0].date(), datetime.strptime(_ls, '%Y%m%d').date() if _ls else c.index[-1].date()
        rule_days = set()
        while _d <= _end:
            if _d.weekday() < 5 and _d not in nyse_closed_days(_d.year):
                rule_days.add(_d.strftime('%Y%m%d'))
            _d += timedelta(days=1)
        rule_days -= SPECIAL_CLOSED
        _hole = sorted(rule_days - sp_days)
        if _hole:
            log(f"  S&P 일봉에 없는 거래일 {len(_hole)}일을 달력에 채운다: {', '.join(_hole[-5:])}")
        us_days = sorted(sp_days | rule_days)[-400:]
        # 달러/원 환율 — **정렬 계산에만** 쓴다(화면에는 달러를 그대로 보여준다).
        #   보유 종목 표에는 원화와 달러가 섞여 있어 '매수금액' 같은 열을 숫자 그대로 견주면
        #   300만원과 $83 을 같은 축에 놓는 셈이 된다. 원화로 환산해 견주되 표기는 바꾸지 않는다.
        try:
            _fx = _yf.download('KRW=X', period='5d', auto_adjust=False, progress=False)
            _fc = _fx['Close'] if 'Close' in _fx else _fx.iloc[:, 0]
            usdkrw = float(_fc.squeeze().dropna().iloc[-1])
            log(f'  환율 1달러 = {usdkrw:,.1f}원 (정렬용)')
        except Exception as e:
            log(f'  환율 실패 — 정렬은 통화 섞인 채로 한다: {e!r}'[:110])
        log(f"  S&P500 {us_reg['close']:,.0f} · 60일선 {ma60:,.0f} · 60일선 위 {us_reg['up60']}")
    except Exception as e:
        log(f'  S&P500 국면 실패 — 규칙 판정이 멈춘다: {e!r}'[:120])

    # 미장 달력이 아는 마지막 거래일보다 뒤처져 있으면 로그에 띄운다(초록불 뒤에 숨지 않게).
    # us_days 는 S&P500 시세로 만들므로 이 자리에서야 값이 있다.
    if asof and us_days and str(asof) < str(us_days[-1]):
        log(f"::warning::미장 표가 묵었다 — 기준일 {asof} 인데 달력의 마지막 거래일은 {us_days[-1]} "
            f"(그날 난 진입 이벤트 nh5·qnew 가 빠져 미장 규칙이 덜 잡힌다)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # NaN·inf 청소 — 한 칸만 새어 나가도 사이트가 표 전체를 못 읽는다(브라우저는 NaN 을 거부한다).
    # allow_nan=False 로 못을 박아 두면 다음에 또 새면 조용히 나가는 대신 **여기서 터진다**.
    _bad = [0]
    def _wash(o):
        if isinstance(o, float):
            if o != o or abs(o) == float('inf'): _bad[0] += 1; return None
            return o
        if isinstance(o, dict): return {k: _wash(v) for k, v in o.items()}
        if isinstance(o, list): return [_wash(v) for v in o]
        return o
    rows = _wash(rows)
    if _bad[0]: log(f'  ⚠ NaN·inf {_bad[0]}칸을 None 으로 바꿨다 — 안 바꿨으면 사이트가 미장 표를 통째로 버린다')
    json.dump({"dates": dates, "rows": rows, "us": us_reg, "usdates": us_days,
               "asof": asof,
               "updated": datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"), allow_nan=False)
    log(f"{OUT.name} {OUT.stat().st_size/1024/1024:.1f}MB")
    # 미장 거래일 달력만 담은 작은 파일 — 10분마다 도는 엣지 함수가 보유일을 세는 데 쓴다.
    #   미장 표는 3.6MB 라 10분마다 받을 수 없다. 달력은 400줄이면 10KB 도 안 된다.
    cal = OUT.parent / "uscal.json"
    json.dump({"dates": us_days, "usdkrw": usdkrw, "asof": asof,
               "updated": datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(cal, "w", encoding="utf-8"), separators=(",", ":"))
    log(f"{cal.name} 미장 거래일 {len(us_days)}일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
