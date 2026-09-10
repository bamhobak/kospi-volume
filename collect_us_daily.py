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
from datetime import datetime
import numpy as np, pandas as pd

BASE = Path(__file__).parent
TICK = BASE / "data" / "us" / "tickers.csv"
OUT = BASE / "site" / "data" / "table_us.json"
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


def fetch(syms, start):
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
            x = x.dropna(subset=["Close"])
        except Exception:
            continue
        if len(x) < 25:        # 상장 직후라 지표를 못 만드는 종목은 뺀다
            continue
        try:
            x.index = x.index.strftime("%Y%m%d")
        except Exception:
            continue
        out[s] = x
    return out


def metrics(x, bbdates=None):
    """한국 표와 같은 이름의 지표를 만든다. 값이 모자라면 None.

    bbdates: 그 종목의 자사주 집행 보고일(YYYYMMDD) 목록. [자사주 낙폭] 이 쓴다."""
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
        above20=round(above, 1) if above is not None else None,
        v=[int(z) if z == z else 0 for z in v[-NDAY:]],
    )


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

    rows, dates, t0, fail = [], [], time.time(), 0
    for i in range(0, len(syms), a.chunk):
        part = syms[i:i + a.chunk]
        try:
            got = fetch(part, start)
        except Exception as e:
            fail += len(part); log(f"  {i//a.chunk+1}묶음 실패: {e}"); continue
        for s, x in got.items():
            try:
                m = metrics(x, BBD.get(s))
            except Exception:
                continue
            if not dates or len(x.index) > len(dates):
                dates = list(x.index[-NDAY:])
            m.update(t=s, n=str(NM.get(s, s)), mk="US", ex=str(MK.get(s, "")),
                     pref=False, th=[],
                     cap=(round(SHR[s] * m["c"] / 1e6, 1) if SHR.get(s) and m.get("c") else None))
            rows.append(m)
        if (i // a.chunk) % 10 == 0:
            log(f"  {i+len(part):,}/{len(syms):,} · 담은 종목 {len(rows):,} · {time.time()-t0:.0f}초")
    log(f"완료 {len(rows):,}종목 (실패 {fail:,}) · {time.time()-t0:.0f}초")
    if not rows:
        log("한 종목도 못 받았다 — 파일을 덮어쓰지 않는다"); return 1

    # ── [낙폭과대]·[저PBR 낙폭] 이 쓰는 재료 — 업종 60일 수익률 · PBR · 부채비율 ────
    #   한국 규칙을 미국에 대입했을 때 통과한 둘이다(us_rules.py). 사이트에도 얹으려면
    #   이 셋이 필요하다. 업종은 tickers.csv 의 Industry, 나머지는 SEC XBRL(fin.pkl).
    import collections
    by_ind = collections.defaultdict(list)
    for m in rows:
        ind = IND.get(m['t'])
        if ind and m.get('ret60') is not None: by_ind[ind].append(m['ret60'])
    umed = {k: float(np.median(v)) for k, v in by_ind.items() if len(v) >= 5}   # 회원 5종목 이상
    FIN = {}
    _fp2 = BASE / 'data' / 'us' / 'fin.pkl'
    if _fp2.exists():
        _F2 = pd.read_pickle(_fp2).sort_values('filed').drop_duplicates('ticker', keep='last')
        FIN = _F2.set_index('ticker')[['equity', 'liab', 'shares']].to_dict('index')
    nu = npbr = ndbt = 0
    for m in rows:
        ind = IND.get(m['t'])
        m['up'] = str(ind) if ind else None
        m['sr60'] = round(umed[ind], 2) if ind in umed else None      # 한국 표와 같은 열 이름
        f = FIN.get(m['t']) or {}
        eq, li, sh = f.get('equity'), f.get('liab'), f.get('shares')
        m['pbrd'] = (round(m['c'] * sh / eq, 3) if eq and sh and eq > 0 and m.get('c') else None)
        m['dbt'] = (round(li / eq * 100, 1) if eq and li is not None and eq > 0 else None)
        nu += m['sr60'] is not None; npbr += m['pbrd'] is not None; ndbt += m['dbt'] is not None
    log(f'  업종 60일수익 {nu:,}종목 · PBR {npbr:,} · 부채비율 {ndbt:,} (전체 {len(rows):,})')

    # ── 자사주 — 마지막 집행 보고 이후 며칠 지났나 (사이트 규칙 [자사주 낙폭] 이 쓴다) ──
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
    us_reg = {}; us_days = []
    try:
        import yfinance as _yf          # fetch() 안에서만 import 하고 있어 여기선 새로 부른다
        sp = _yf.download('^GSPC', period='2y', auto_adjust=False, progress=False)
        c = sp['Close'] if 'Close' in sp else sp.iloc[:, 0]
        c = c.squeeze().dropna()
        ma60 = float(c.rolling(60).mean().iloc[-1])
        us_reg = {'date': c.index[-1].strftime('%Y%m%d'), 'close': float(c.iloc[-1]),
                  'ma60': ma60, 'up60': bool(float(c.iloc[-1]) > ma60)}
        # 미장 **거래일 달력** — 보유일·규칙상 매도일을 세는 데 쓴다.
        #   국내는 종목별 일봉 파일(data/stock/*.json)의 행 수로 보유일을 세는데 미장은 그 파일이
        #   없어서 늘 0일로 나왔다(2026-09-11 사용자 신고: PARR 보유일 0일). 종목 6천 개짜리
        #   파일을 만드는 대신 달력 하나만 실어 보내면 된다. 미국 휴장일은 한국과 다르므로
        #   한국 달력으로 대신할 수 없다.
        us_days = [d.strftime('%Y%m%d') for d in c.index][-400:]
        log(f"  S&P500 {us_reg['close']:,.0f} · 60일선 {ma60:,.0f} · 60일선 위 {us_reg['up60']}")
    except Exception as e:
        log(f'  S&P500 국면 실패 — 규칙 판정이 멈춘다: {e!r}'[:120])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"dates": dates, "rows": rows, "us": us_reg, "usdates": us_days,
               "updated": datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"{OUT.name} {OUT.stat().st_size/1024/1024:.1f}MB")
    # 미장 거래일 달력만 담은 작은 파일 — 10분마다 도는 엣지 함수가 보유일을 세는 데 쓴다.
    #   미장 표는 3.6MB 라 10분마다 받을 수 없다. 달력은 400줄이면 10KB 도 안 된다.
    cal = OUT.parent / "uscal.json"
    json.dump({"dates": us_days, "updated": datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(cal, "w", encoding="utf-8"), separators=(",", ":"))
    log(f"{cal.name} 미장 거래일 {len(us_days)}일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
