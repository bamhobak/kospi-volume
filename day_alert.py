# -*- coding: utf-8 -*-
"""데이 첫 규칙 후보 [갭 하락 조용주] — **알림만**(실제 주문 없음) · 2026-10-03 (research H0285).

규칙(일봉 2005~2026 실측, 비용 0.22% 뒤 하루 평균: 학습 16~22 +0.37% 7/7해 · 검증 23~ +0.39% 4/4해 · 05~15 +0.67% 11/11해):
  유니버스 = 국장 보통주 중 20일 평균 거래대금 상위 40%
  ① 그중 거래대금 아래 2/3(중소형)         — 위 1/3(대형)은 효과 없음
  ② 오늘 갭(시가 ÷ 어제 종가)이 유니버스 하위 10%
  ③ 어제 거래량 ÷ 그 전 20일 평균이 유니버스 하위 30%(조용했던 종목)
  → **시가 단일가에 사서 같은 날 종가 단일가에 판다.** 1분봉으로 보면 09:05 에만 사도 효과가 사라진다 → 장전에 골라야 한다.
⚠ 오늘 시가는 장 전에 모른다. 토스 API 에 '예상 체결가' 칸이 없어 두 가지로 미리 짐작하고, 장 끝나고 실제 시가와 맞춰 어느 쪽이 맞는지 잰다.
   NXT = 넥스트레이드 장전(08:00~08:50) 마지막 체결가 · 호가 = 08:50 이후 장전 단일가 호가 1단계 가운데값

  python day_alert.py morning   08:40 — 전 종목 일봉 25개(약 6분) → 08:52 예상 시가 → 후보 텔레그램 · 사이트(__day__)
  python day_alert.py review    16:25 — 오늘 실제 시가·종가로 후보 성적 + 예상 시가가 맞았는지 → data/day/log.csv · 텔레그램
"""
import csv, datetime as dt, json, math, os, re, sys, time, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "day"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
import collect_m1 as M          # 토스 호출(속도 조절·재시도·토큰 공용), 국장 종목 목록
import autotrade as AT          # 주문·체결 확인·장 시각·사이트 상태(같은 토큰을 쓴다)

KST = M.KST
DAY_PER = 500_000                                 # 2026-10-04 사용자: 데이는 건당 50만원으로 실매수 시작(.env DAY_MODE=live)
DAY_QTY = 1                                       # 2026-10-14 사용자: 당분간 테스트라 데이는 **종목당 1주씩만**(돈 제대로 넣으면 다시 말해 준다 → None 이면 DAY_PER 금액만큼)
DAY_BASE = 500_000                                # 실전 기준금액(배율 1배일 때 한 종목 금액) · 10-19 '나중에' → 10-21 사용자 50만(research/t1_grid_1021.py: 70만↑는 체결 손해로 1년 손익이 준다)
#   금액 = 기준 × 깊이 배율(1.5~5) × 거래대금 배율 — 테스트(DAY_QTY) 동안은 주수만 1~5주, 이 금액은 DAY_QTY=None 일 때 쓴다
LIQ_LO, LIQ_HI = 0.3, 3.0                         # 10-21 사용자: 거래대금 배율 = 20일 평균 거래대금 ÷ 그날 후보 중앙값(0.3~3배) — 거래 많은 종목에 더 넣어 체결률을 고르게
#   (research/t1_size_liq_1021.py: 같은 돈에서 1년 손익 +4~8% · 시총·전날 거래대금 기준은 오히려 나쁨)
DAY_MULT_MAX = 5.0                                # 배율 상한 — 10-19 처음 10 → 같은 날 사용자 5: -5%p 넘게는 건당 수익이 +2% 안팎에서 멈추고 -10%p↓는 오히려 나쁨(t1 -10%p 표)
DEEP_REL, DEEP_MULT = -10.0, 5.0                  # 시장 대비 -10%p 넘게: 10-19 2.5배였다가 같은 날 사용자 5배로 되돌림 — 대신 그중 악재 공시 있는 것만 안 산다(DEEP_BAD)
# 10-19 사용자(research H0363): -10%p 넘게 빠진 후보 중 어제·오늘 악재 공시(DART)가 있는 것만 안 산다 — 2016~ 악재 30건 -0.62% vs 없음 60건 +2.00%
BAD_RE = r"횡령|배임|감사의견|의견거절|한정|상장폐지|상장적격성|매매거래정지|거래정지|불성실공시|회생|파산|부도|소송|유상증자|전환사채|신주인수권|관리종목|투자주의환기|최대주주변경|조회공시"
NOBUY_GAP = -27.5                                 # 10-19 사용자: 예상 시가 갭이 이 이하(하한가 근처)면 처음부터 안 산다 — 사자마자 손절에 걸림(처음 -28 → 같은 날 -27.5)
STOP_PCT = -29.0                                  # 10-19 사용자: 데이로 산 종목이 장중 전일 종가 대비 -29% 에 닿으면 바로 시장가 매도(하한가 묶임 피하기)
DAY_MAX = None                                    # 하루 최대 종목 수 — None = 제한 없음(후보 전부 주문) · 10-13 10→20 · 10-19 20→50 · 10-21 사용자 제한 없앰: 실행 실측(종목당 100만 체결 89%)상 종목 수를 막을 이유가 없다
COST = 0.23                                     # 토스 실제 왕복: 수수료 0.015×2 + 거래세 0.20 (index.html DEFFEE)
RULE = "갭 하락 조용주"
RNAME = {"T1": "갭 하락 조용주", "T2": "갭 하락 조용주 +", "T3": "갭 하락 조용주 ++", "T4": "미장 폭락 과잉 갭"}
# 2026-10-18 T4(사용자 '둘 다 적용' · research H0352): 나스닥 전날 -2.5%↓ 인 날만 — 작은 종목(유니버스 아래 1/3) 중
#   예상 갭 -2%↓ & 짝 미장으로 본 예상 갭보다 더 빠진 정도(덜 반영 = 갭 − 짝 예상)가 유니버스 하위 10% → 시가 단일가 지정가(어제 종가 -2%) → 종가.
#   2016~22 1,285건 건당 +1.75% · 승률 69% · PF 2.99 / 2023~ 296건 +2.44% · 74% · PF 5.32 · 연 약 9일 · 그날 15종목쯤. [갭 하락 조용주]와 겹치면 한 번만 산다.
U_NAS, U_GAP, U_RQ, U_MAX = -2.5, -2.0, 0.10, None   # U_MAX None = 제한 없음(10-21 사용자, 원래 20)
U_LIQ = 1 / 2                                     # T4 크기 문턱 — 유니버스 거래대금 아래 1/2(10-21 사용자, 원래 1/3 · research/t1_uni2_1021.py: 새로 걸린 몫 학습 +1.43%·검증 +2.39%)
W_NAS, W_GAP = -1.5, -3.0                          # 넓은 판(나스닥 -1.5%↓ · 갭 -3%↓) — 사지 않고 기록만(저녁 결과에 비교)
T2_CUT = -1.0                                     # 2026-10-06 H0297: 어제 14:00→종가 이 값 이하면 T2(한 번 더 산다)
#  2026-10-11 T3(사용자 '추천대로' · research H0313): 그 종목의 짝 미장 종목으로 본 예상 갭(전이표 tr_pred)이 이 값 이하면
#  T3 로 한 번 더 산다 — 학습 307건 +2.37%·71% / 검증 192건 +2.05%·71%.
#  2026-10-11 사용자 "둘 다 겹치면 둘 다 사는 조건으로"(research/t1_overlap.py): T2·T3 겹치면 덤도 둘 다(T1 포함 3번) —
#  겹친 종목 검증 연 13~14건 +2.4~2.7%·승률 68~70%(T2만 +1.8~2.2 · T3만 +1.2~1.6), 대신 나쁜 5% 거래 -8%(한 종목에 3배가 실린다).
T3_CUT = -0.5
#  2026-10-11 지정가 매수(사용자 '반영해줘' · research H0321 t1_limit.py·t1_limit_ext.py): 08:52 예상 갭으로 고르면 예상이 빗나간 종목도
#  섞인다(3일 실측 오차 평균절대 0.7%p — 예상 ≤-2 로 고른 것 중 실제도 ≤-2 는 45%). 시장가 대신 지정가 = 어제 종가 × (1 + 예상 시장 갭 + LIMIT_THR)
#  로 내 '실제로 시장보다 1%p↑ 빠져 열린' 것만 시가에 산다. 시뮬(검증, 덤 포함) 연 1,236만 → 1,305만원(150만원씩)·승률 +4~6%p·거래 30%↓.
#  시가에 안 사지면 09:01 에 취소 — 장중에 지정가 닿은 몫은 문턱 -1~-2.5 모두 건당 -0.1~-0.2%(학습·검증)라 사지 않는다.
LIMIT_THR = -1.5                                  # 2026-10-13 사용자 "넓히는 쪽으로" — 후보는 넓게(CAND_*), 체결은 시장 대비 -1.5%p 로 엄격하게 (10-11 -1 → -0.75 → 10-13 -1.5)
#  그물은 넓게·체결은 엄격(research/t1_widen.py): 예상가가 얕게 빗나가 후보에 못 들던 진짜 T1 을 95% 잡는다. 실제 시가 기준 과거 실측(갭 하위 20%·시장 대비 -1.5):
#  학습 연 794건 +0.88%·62% / 검증 983건 +0.94%·61%(지금 T1 417건 +1.28%) — 새로 더해지는 -1.5~-2 몫도 2010~2026 17년 모두 플러스(+0.5~0.6%).
T1_LIQ = 4 / 9                                    # 10-21 사용자: 본체 크기 문턱 유니버스 거래대금 아래 1/3 → 4/9 · 덤(T2·T3)은 1/3 안에서만(research/t1_extra_1021.py: 5천 계좌 1년 손익 학습 +15%·검증 +10%)
CAND_Q, CAND_REL = 0.40, -1.5                      # 10-21 사용자 20→40%(research/t1_loosen_1021.py: 새로 걸린 몫 연 48건 +0.66% — 시장 대비 -1.5 가 이미 거의 다 거른다) · 후보 = 예상 갭 유니버스 하위 40% · 예상 시장 대비 -1.5%p 이하(상승·하락장 공통) — 전엔 하위 10%·-2(하락장 -1.5)


def kr_tick(p):
    """국장 호가 단위(2023-01-25~ 코스피·코스닥 같음)."""
    for lim, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if p < lim: return t
    return 1000


def limit_price(pc, mg):
    """매수 지정가 — 어제 종가(토스) × (1 + (예상 시장 갭 + LIMIT_THR)/100), 호가 단위로 내림(문턱보다 비싸게 사지 않게)."""
    p = pc * (1 + (mg + LIMIT_THR) / 100)
    t = kr_tick(p)
    return int(math.floor(p / t) * t)


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def env():
    e = {}
    f = BASE / ".env"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1); e[k.strip()] = v.strip()
    return e


def telegram(text):
    e = env()
    AT.tg_send(e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID"), text)   # 다시 하기·못 보낸 건 쌓아 두기(10-06)


def supa_set(pin, data):
    import requests
    js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    H = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    requests.post(f"{url}/rest/v1/rpc/kospi_state_set", headers=H, json={"p_pin": pin, "p_data": data}, timeout=30).raise_for_status()


def today_session():
    cal = M.get("/api/v1/market-calendar/KR")
    it = (cal.get("today") or {}).get("integrated")
    return (cal["today"]["date"].replace("-", ""), it, cal["previousBusinessDay"]["date"].replace("-", "")) if it else (None, None, None)


def pct_rank(vals):
    """{키: 값} → {키: 0~1 백분위}(작을수록 0)."""
    ks = sorted(vals, key=lambda k: vals[k]); n = len(ks)
    return {k: (i + 1) / n for i, k in enumerate(ks)}


def prep(today):
    """전 종목 일봉 25개 → 어제 종가·20일 평균 거래대금·어제 거래량 배수."""
    U = M.universe("KR"); R = {}; t0 = time.time()
    for s in U:
        c = (M.get("/api/v1/candles", symbol=s, interval="1d", count=25) or {}).get("candles") or []
        c = sorted([x for x in c if x["timestamp"][:10].replace("-", "") < today], key=lambda x: x["timestamp"])
        if len(c) < 22: continue
        v = [float(x["volume"]) for x in c]; cl = [float(x["closePrice"]) for x in c]
        amt20 = sum(a * b for a, b in zip(cl[-20:], v[-20:])) / 20
        base = sum(v[-21:-1]) / 20
        if base <= 0 or cl[-1] <= 0: continue
        R[s] = dict(pc=cl[-1], amt20=amt20, vm=v[-1] / base, pdate=c[-1]["timestamp"][:10].replace("-", ""),
                    d5=(cl[-1] / (sum(cl[-5:]) / 5) - 1) * 100)          # 어제 종가의 5일선 대비 — 낮을수록 기대 큼(day2.py)
    log("준비: %d종목 · %.1f분" % (len(R), (time.time() - t0) / 60))
    return R


def yday_lasth(syms, prev):
    """어제 14:00 가격 → 종가 등락(%) — 어제 1분봉에서. 못 받은 종목은 빠진다(T2 만 안 걸린다, T1 은 그대로)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(s):
        try:
            rows = M.fetch_day("KR", s, prev)
        except Exception:
            return s, None
        if len(rows) < 200: return s, None
        rows.sort(key=lambda r: r[1])
        hm = [dt.datetime.fromtimestamp(r[1], KST).strftime("%H%M") for r in rows]
        p14 = [r[5] for r, h in zip(rows, hm) if h <= "1400"]
        if not p14: return s, None
        return s, (rows[-1][5] / p14[-1] - 1) * 100
    with ThreadPoolExecutor(M.WORKERS) as ex:
        return {s: v for s, v in ex.map(one, syms) if v is not None}


def us_pred(today):
    """그 종목 짝 미장 종목으로 본 오늘 예상 갭(%) {티커: 값} — 공장 전이표(research/factory/transfer.py).
    공장 아침 작업(07:50)이 남긴 data/factory/transfer/<오늘>.json 이 있으면 읽고, 없으면 여기서 계산한다
    (미장 일봉 최근 10개만 받아 붙임 · 짝·기울기 표는 transfer_fit.json). 실패하면 {} — T3 만 안 걸리고 T1·T2 는 그대로."""
    f = BASE / "data" / "factory" / "transfer" / ("%s.json" % today)
    j = None
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        try:
            sys.path.insert(0, str(BASE / "research" / "factory"))
            import transfer as TRF
            j = TRF.morning(today)
        except Exception as ex:
            log("짝 미장 예상 갭 못 구함(T3 쉼):", repr(ex)[:200])
            return {}
    out = {}
    for t, v in ((j or {}).get("pred") or {}).items():
        try:
            if v and v[3] is not None: out[t] = float(v[3])
        except Exception:
            pass
    return out


def nasdaq_last(today):
    """오늘 아침 전에 끝난 나스닥 종합지수 하루 등락(%) — FDR(야후) IXIC, 못 받으면 전이표 미장 일봉의 QQQ. 실패하면 None(T4 쉼)."""
    try:
        import FinanceDataReader as fdr
        X = fdr.DataReader("IXIC", (dt.datetime.now(KST) - dt.timedelta(days=15)).strftime("%Y-%m-%d"))
        X = X[(X.Close > 0) & (X.index.strftime("%Y%m%d") < today)]
        if len(X) >= 2: return float((X.Close.iloc[-1] / X.Close.iloc[-2] - 1) * 100), "IXIC " + X.index[-1].strftime("%m/%d")
    except Exception as ex:
        log("나스닥 못 받음(IXIC):", repr(ex)[:150])
    try:
        import pandas as pd
        A = pd.read_parquet(BASE / "data" / "factory" / "us_daily.parquet")
        q = A[(A.sym == "QQQ") & (A.date < today)].sort_values("date")
        if len(q) >= 2: return float((q.close.iloc[-1] / q.close.iloc[-2] - 1) * 100), "QQQ " + q.date.iloc[-1][4:]
    except Exception as ex:
        log("나스닥 못 받음(QQQ):", repr(ex)[:150])
    return None, None


def bad_news(tickers, prev, today):
    """어제(직전 거래일)~오늘 DART 공시 중 악재 키워드(BAD_RE) — {티커: 공시 제목}. 실패하면 None(거르지 않고 그대로 산다 + 알림)."""
    if not tickers: return {}
    import requests
    key = env().get("DART_API_KEY")
    if not key: log("DART_API_KEY 없음 — 악재 공시 못 봄"); return None
    out, page = {}, 1
    try:
        while page <= 60:
            r = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=15, params={
                "crtfc_key": key, "bgn_de": prev, "end_de": today, "page_no": page, "page_count": 100}).json()
            if r.get("status") not in ("000", "013"): raise RuntimeError("DART %s %s" % (r.get("status"), r.get("message")))
            for it in r.get("list") or []:
                t = it.get("stock_code") or ""
                nm = (it.get("report_nm") or "").replace(" ", "")
                if t in tickers and re.search(BAD_RE, nm): out.setdefault(t, it.get("report_nm", "").strip())
            if page >= int(r.get("total_page") or 1): break
            page += 1; time.sleep(0.15)
        return out
    except Exception as ex:
        log("악재 공시 조회 실패:", repr(ex)[:200]); return None


def floor_tick(p):
    t = kr_tick(p)
    return int(math.floor(p / t) * t)


def morning():
    today, it, prev = today_session()
    if not today:
        log("국장 휴장 — 건너뜀"); return
    R = prep(today)
    names = {}
    # 유니버스: 20일 평균 거래대금 상위 40% (1,000원 미만 제외 — 연구와 같게)
    R = {k: v for k, v in R.items() if v["pc"] >= 1000 and v["pdate"] == prev}
    liq = pct_rank({k: v["amt20"] for k, v in R.items()})
    uni = [k for k in R if liq[k] >= 0.60]
    uliq = pct_rank({k: R[k]["amt20"] for k in uni})
    small = [k for k in uni if uliq[k] <= 2 / 3]
    vmq = pct_rank({k: R[k]["vm"] for k in uni})
    pre = [k for k in small if vmq[k] <= 0.30]                 # ①③ 은 장 전에 확정 — 갭만 남는다
    # 2026-10-04 좁힘(사용자 '2번' · research H0291): 중소형 중 **더 작은 쪽(유니버스 거래대금 아래 1/3)** + 시장보다 2%p 이상 더 빠짐
    #   승률 55% → 학습 63.5% · 검증 63.9% · 건당 +1.19/+1.41% · 하루 1.4~1.8종목(신호 없는 날 약 40%)
    tiny = {k for k in uni if uliq[k] <= 1 / 3}                # 덤(T2·T3)은 이 안에서만
    t1u = {k for k in uni if uliq[k] <= T1_LIQ}                # [갭 하락 조용주] 본체(10-21~ 4/9)
    log("유니버스 %d · 중소형 %d · 조용(거래량 하위30%%) %d" % (len(uni), len(small), len(pre)))
    # 2026-10-06 T2(H0297): 어제 막판 1시간(14:00→종가) — 후보가 될 수 있는 조용한 작은 종목만 어제 1분봉을 받아 둔다(~70종목·10초)
    lh = yday_lasth([k for k in pre if k in tiny], prev)
    log("어제 막판 1시간 받음 %d/%d · -1%%↓ %d" % (len(lh), len([k for k in pre if k in tiny]), sum(1 for v in lh.values() if v <= T2_CUT)))
    # 2026-10-11 T3(H0313): 짝 미장으로 본 예상 갭 — 08:52 전에 계산해 둔다(미장 일봉 56종목·수 초)
    up = us_pred(today)
    log("짝 미장 예상 갭 %d종목 · %.1f%%↓ %d" % (len(up), T3_CUT, sum(1 for k in pre if k in tiny and up.get(k, 0) <= T3_CUT)))
    # 08:52 까지 기다렸다 예상 시가 — NXT 장전 체결가(08:50 마감) + 장전 단일가 호가
    at = dt.datetime.now(KST).replace(hour=8, minute=52, second=0, microsecond=0)
    w = (at - dt.datetime.now(KST)).total_seconds()
    if w > 0:
        log("08:52 까지 기다림 %.0f초" % w); time.sleep(w)
    if env().get("DAY_MODE", "notify") == "live":               # 어제까지 못 판 데이 종목(하한가 묶임 등) — 오늘 시가에 판다(10-19 사용자)
        try: carry_sell(today)
        except Exception as ex:
            log("넘어온 데이 종목 매도 실패:", repr(ex)[:200]); telegram("⚠ 어제 못 판 데이 종목 처리 실패: %s" % str(ex)[:150])
    nxt = {}
    for i in range(0, len(uni), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(uni[i:i + 200])) or []:
            ts = x.get("timestamp") or ""
            if ts[:10].replace("-", "") == today:
                nxt[x["symbol"]] = float(x["lastPrice"])
    ob = {}
    for s in uni:                                              # 갭 순위는 유니버스 전체에서 매긴다 → 전부 본다
        r = M.get("/api/v1/orderbook", symbol=s) or {}
        a = (r.get("asks") or [{}])[0].get("price"); b = (r.get("bids") or [{}])[0].get("price")
        if a and b: ob[s] = (float(a) + float(b)) / 2
        elif a or b: ob[s] = float(a or b)
    exp = {s: nxt.get(s, ob.get(s)) for s in uni}
    src = {s: ("NXT" if s in nxt else ("호가" if s in ob else None)) for s in uni}
    gap = {s: (exp[s] / R[s]["pc"] - 1) * 100 for s in uni if exp[s]}
    gq = pct_rank(gap)
    # 순서(2026-10-03 day2.py): 시장보다 더 빠진 순 — 시장 대비 -3%p 이상이면 하루 +0.9~1.0%(학습·검증), 그 안은 +0.3%
    mg = sorted(gap.values())[len(gap) // 2] if gap else 0.0           # 오늘 유니버스 갭 중앙 = 시장 갭
    d5q = pct_rank({k: R[k]["d5"] for k in uni})
    base_c = [s for s in pre if s in gq and gq[s] <= 0.10]                       # 예전 T1(넓은 조건) — 결과 비교용으로 남긴다
    # 2026-10-04 국면별 기준(사용자): 코스피 전날 종가가 60일선 위(상승장) → 시장보다 2%p↑ · 아래(하락장) → 1.5%p↑ 더 빠진 것
    #   상승장 날 건당 +0.56/+1.32%·승률 61/63% · 하락장 날 +1.03/+1.37%·62/65% (학습/검증). 지수를 못 받으면 엄격한 2%p.
    kup = None
    try:
        import index_cal as IC
        kc = IC.naver_closes("KOSPI", 200); ks = [kc[d] for d in sorted(kc) if d < today]
        if len(ks) >= 60: kup = ks[-1] > sum(ks[-60:]) / 60
    except Exception as ex:
        log("코스피 지수 못 받음:", ex)
    thr = -1.5 if kup is False else -2.0
    # thr(연구 T1 기준)은 리뷰의 '실제 시가로 골랐다면' 목표선에만 쓴다 — 매수 후보는 넓은 그물(CAND_Q·CAND_REL) + 지정가(LIMIT_THR)
    cand = sorted([s for s in pre if s in t1u and s in gq and gq[s] <= CAND_Q and gap[s] - mg <= CAND_REL], key=lambda s: gap[s] - mg)
    nm = {}
    for i in range(0, len(cand), 100):
        for x in M.get("/api/v1/stocks", symbols=",".join(cand[i:i + 100])) or []:
            nm[x["symbol"]] = x.get("name") or x["symbol"]
    L = [dict(t=s, name=nm.get(s, s), gap=round(gap[s], 2), rel=round(gap[s] - mg, 2), vm=round(R[s]["vm"], 2), d5=round(R[s]["d5"], 2),
              d5low=d5q[s] <= 0.30, exp=exp[s], pc=R[s]["pc"], src=src[s], lim=limit_price(R[s]["pc"], mg),
              lh=(round(lh[s], 2) if s in lh else None), t2=(s in tiny and s in lh and lh[s] <= T2_CUT),
              up=(round(up[s], 2) if s in up else None), t3=(s in tiny and s in up and up[s] <= T3_CUT), t1=True,
              a20=round(R[s]["amt20"] / 1e8, 2)) for s in cand]
    if L:                                                                  # 거래대금 배율(10-21) — 그날 후보 중앙 대비
        md = sorted(x["a20"] for x in L)[len(L) // 2] or 1.0
        for x in L: x["lm"] = round(min(LIQ_HI, max(LIQ_LO, x["a20"] / md)), 2)
    # ── T4 [미장 폭락 과잉 갭] ──
    nas, nas_src = nasdaq_last(today)
    res = {s: gap[s] - up[s] for s in uni if s in gap and s in up}          # 덜 반영 = 예상 갭 − 짝 미장으로 본 예상 갭
    rq = pct_rank(res) if res else {}
    t4set = {k for k in uni if uliq[k] <= U_LIQ}
    pick = lambda nc, gc: sorted([s for s in t4set if s in rq and rq[s] <= U_RQ and gap[s] <= gc], key=lambda s: gap[s]) if (nas is not None and nas <= nc) else []
    u_sel, u_wide = pick(U_NAS, U_GAP), pick(W_NAS, W_GAP)
    have = {x["t"]: x for x in L}
    U = []
    for s in u_sel[:U_MAX]:
        if s in have:
            have[s]["u1"] = True; continue                                   # [갭 하락 조용주]와 겹치면 한 번만 산다
        U.append(dict(t=s, name=s, gap=round(gap[s], 2), rel=round(gap[s] - mg, 2), vm=round(R[s]["vm"], 2), d5=round(R[s]["d5"], 2), d5low=False,
                      exp=exp[s], pc=R[s]["pc"], src=src[s], lim=floor_tick(R[s]["pc"] * (1 + U_GAP / 100)),
                      up=round(up[s], 2), res=round(res[s], 2), t1=False, u1=True))
    if U:
        for i in range(0, len(U), 100):
            for x in M.get("/api/v1/stocks", symbols=",".join(u["t"] for u in U[i:i + 100])) or []:
                for u in U:
                    if u["t"] == x["symbol"]: u["name"] = x.get("name") or u["name"]
    # 예상 시가가 하한가 근처(-28% 이하)면 안 산다 — 사자마자 -29% 손절에 걸려 비용만 낸다(10-19 사용자)
    near = [(x["name"], x["gap"]) for x in L + U if x.get("gap") is not None and x["gap"] <= NOBUY_GAP]
    if near:
        L = [x for x in L if x["gap"] > NOBUY_GAP]; U = [x for x in U if x["gap"] > NOBUY_GAP]
        log("하한가 근처라 뺌:", near)
    # 시장 대비 -10%p 넘게 빠진 후보 중 어제·오늘 악재 공시가 있는 것만 뺀다(10-19 사용자 · H0363)
    deep = [x["t"] for x in L + U if x.get("rel") is not None and x["rel"] <= DEEP_REL]
    bn = bad_news(set(deep), prev, today) if deep else {}
    dropped = []
    if bn:
        dropped = [(x["name"], bn[x["t"]]) for x in L + U if x["t"] in bn]
        L = [x for x in L if x["t"] not in bn]; U = [x for x in U if x["t"] not in bn]
        log("악재 공시로 뺌:", dropped)
    elif bn is None and deep:
        telegram("⚠ 데이: -10%%p 넘게 빠진 후보 %d종목 악재 공시를 못 봤다(DART 실패) — 그대로 산다" % len(deep))
    log("T4 나스닥 %s(%s) · 덜 반영 %d종목 · 고른 것 %d(겹침 %d) · 넓은 판 기록 %d" % (
        "%+.2f%%" % nas if nas is not None else "모름", nas_src, len(res), len(u_sel), len(u_sel) - len(U), len(u_wide)))
    snap = dict(date=today, prev=prev, made=dt.datetime.now(KST).strftime("%H:%M"), rule=RULE, n_uni=len(uni), n_gap=len(gap), mgap=round(mg, 2),
                cut=round(sorted(gap.values())[max(int(len(gap) * 0.10) - 1, 0)], 2) if gap else None,
                src_n={"NXT": sum(1 for s in src.values() if s == "NXT"), "호가": sum(1 for s in src.values() if s == "호가")}, cand=L + U,
                n_base=len(base_c), kup=kup, thr=thr, nas=(round(nas, 2) if nas is not None else None), nas_src=nas_src,
                u_sel=u_sel, u_wide=u_wide,
                all={s: dict(gap=round(gap[s], 3), src=src[s], pre=s in pre, tiny=s in tiny, t1u=s in t1u) for s in gap})
    (OUT / ("snap_%s.json" % today)).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    try:
        supa_set("__day__", {k: v for k, v in snap.items() if k != "all"})
    except Exception as ex:
        log("사이트 기록 실패:", ex)
    log("후보 %d · 예상가 NXT %d · 호가 %d · 갭 10%% 선 %s%%" % (len(L), snap["src_n"]["NXT"], snap["src_n"]["호가"], snap["cut"]))
    live = env().get("DAY_MODE", "notify") == "live"
    head = "🌅 <b>데이 [%s] %s</b> %s/%s 08:52" % (RULE, "실매수" if live else "알림만", today[4:6], today[6:])
    body = [("후보 %d종목 — %s종목 %s씩 시가 단일가 지정가 매수(시장보다 %g%%p↑ 빠져 열릴 때만 · 못 사면 09:01 취소) → 오늘 종가 매도" % (
                len(L), ("전" if DAY_MAX is None else "위에서 %d" % min(len(L), DAY_MAX)), ("1~5주(시장 대비 깊이만큼)" if DAY_QTY else "기준금액 × 깊이 배율"), -LIMIT_THR)) if live
            else ("후보 %d종목 — 시가 단일가 매수 → 종가 매도 (실제 주문 없음 · 검증 중)" % len(L)),
            "오늘 시장 갭 %+.1f%%%s" % (mg, " — 다 같이 빠진 날(과거 기대 큼)" if mg <= -1 else "")]
    for x in L[:15]:
        body.append("· %s%s(%s) 예상 갭 %+.1f%%(시장 대비 %+.1f) · 지정가 %s원 · 거래량 %.1f배%s%s%s [%s]" % (
            ("⭐" if x.get("t2") else "") + ("🌙" if x.get("t3") else ""), x["name"], x["t"], x["gap"], x["rel"], f"{x['lim']:,}", x["vm"],
            " · 5일선 아래" if x["d5low"] else "",
            (" · 어제 막판 %+.1f%%" % x["lh"]) if x.get("lh") is not None else "",
            (" · 짝 미장 %+.1f%%" % x["up"]) if x.get("up") is not None else "", x["src"]))
    if len(L) > 15: body.append("… 외 %d" % (len(L) - 15))
    n2 = sum(1 for x in L if x.get("t2"))
    n3 = sum(1 for x in L if x.get("t3"))
    if n2: body.append("⭐ = [갭 하락 조용주 +] 도 걸림(어제 14:00→종가 %.0f%%↓) — %d종목은 한 번 더 산다" % (T2_CUT, n2))
    if n3: body.append("🌙 = [갭 하락 조용주 ++] 도 걸림(짝 미장으로 본 예상 갭 %.1f%%↓) — %d종목은 한 번 더 산다(⭐🌙 둘 다면 두 번 더)" % (T3_CUT, n3))
    body.append("후보 = 조용한 작은 종목 중 예상 갭 하위 %d%% · 시장보다 %g%%p↑ 더 빠질 것 → 실제로 %g%%p↑ 빠져 열린 것만 체결 (코스피 %s)" % (
        CAND_Q * 100, -CAND_REL, -LIMIT_THR, {True: "상승장", False: "하락장", None: "국면 모름"}[kup]))
    if nas is not None and nas <= W_NAS:
        body.append("🇺🇸 <b>[%s]</b> 나스닥 %+.1f%%(%s) — %s" % (RNAME["T4"], nas, nas_src,
                    ("%d종목(겹침 %d는 한 번만) 어제 종가 -2%% 지정가 매수 → 종가" % (len(u_sel), len(u_sel) - len(U))) if nas <= U_NAS
                    else "-2.5%% 안 돼 오늘은 안 삼(넓은 판 %d종목은 기록만)" % len(u_wide)))
        for x in U[:10]:
            body.append("· 🇺🇸 %s(%s) 예상 갭 %+.1f%% · 짝 예상 %+.1f%% · 더 빠짐 %+.1f%%p · 지정가 %s원" % (x["name"], x["t"], x["gap"], x["up"], x["res"], f"{x['lim']:,}"))
    if near:
        body.append("⛔ 예상 시가가 하한가 근처(%g%% 이하)라 안 삼: " % NOBUY_GAP + " · ".join("%s(%+.1f%%)" % z for z in near[:5]))
    if dropped:
        body.append("⛔ 시장 대비 -10%%p 넘게 빠졌는데 악재 공시가 있어 안 삼: " + " · ".join("%s(%s)" % (n_, r_[:20]) for n_, r_ in dropped[:5]))
    body.append("갭 하위 10%% 조용한 종목 %d개 · 후보 %d%s" % (len(base_c), len(L), " — 오늘은 안 산다" if not L else ""))
    body.append("갭 하위 10%% 선 %s%% · 예상가 NXT %d·호가 %d / 유니버스 %d" % (snap["cut"], snap["src_n"]["NXT"], snap["src_n"]["호가"], len(uni)))
    telegram("\n".join([head] + body))
    try: M.BUSY.unlink()                                       # 고르는 건 끝났다 — 1분봉 과거 채우기를 다시 돌게 둔다
    except Exception: pass
    if live and (L or U):
        trade(L[:DAY_MAX] + U, today)


# ── 실매수(2026-10-04) — 시가 단일가(OPG) 매수 → 같은 날 종가 단일가 매도 · 사이트 데이 보유(positions_scalp)에 기록 ──
LEDGER = OUT / "ledger.json"


def _led():
    try: return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception: return {"orders": []}


def _led_save(L):
    if AT.DRY: return
    tmp = LEDGER.with_suffix(".tmp"); tmp.write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(LEDGER)


def scalp_update(mutate, why):
    """사이트 데이 보유 목록(positions_scalp)을 읽고 고쳐 쓴다 — 스윙 목록(positions)은 건드리지 않는다."""
    for att in range(3):
        d = AT.site_state()
        pos = d.get("positions_scalp") if isinstance(d.get("positions_scalp"), list) else []
        if not mutate(pos): return
        d["positions_scalp"] = pos; d["updated"] = int(time.time() * 1000)
        if AT.DRY:
            log("사이트 쓰기(보내지 않음):", why); return
        AT.rpc("kospi_state_set", {"p_pin": AT._sb["pin"], "p_data": d})
        if AT.site_state().get("updated") == d["updated"]:
            log("사이트 기록:", why); return
        time.sleep(1)
    log("⚠ 사이트 기록 실패:", why)


def day_mult(x):
    """2026-10-19 사용자: 시장보다 더 빠진 만큼 더 산다 — 배율 = 08:52 예상 '시장 대비'(%p)의 크기 그대로(-1.5 → 1.5배 · -2.2 → 2.2배 · -5 → 5배),
    최소 1배 · 최대 DAY_MULT_MAX(5)배. 테스트 동안은 주수 = 배율의 정수 부분(1~5주). research t1_weight_1019.py: 큰 금액이면 깊은 종목은
    시가에 덜 사지고 비싸게 사져 효과가 줄어든다 — 실전 기준금액은 종목당 상한과 함께 정할 것."""
    try: r = float(x.get("rel"))
    except (TypeError, ValueError): return 1.0
    if r <= DEEP_REL: return DEEP_MULT                     # 10-19 사용자: -10%p 넘게는 2023~ 건당 +0.72%·승률 51%로 약해져 2.5배로 줄임
    return min(DAY_MULT_MAX, max(1.0, -r))


def extras(x):
    """덤 매수 규칙 목록 — T2(어제 막판 약세)·T3(짝 미장 하락). 2026-10-11 사용자: 둘 다 걸리면 둘 다 산다(T1 포함 3번)."""
    return [r for r, k in (("T2", "t2"), ("T3", "t3")) if x.get(k)]


def order_list(L):
    # 2026-10-18: T4 전용 후보(t1=False)는 T4 로 한 번만 — 덤(T2·T3)은 [갭 하락 조용주] 후보에만
    return [(x, "T1" if x.get("t1", True) else "T4") for x in L] + [(x, r) for x in L if x.get("t1", True) for r in extras(x)]


def trade(L, today):
    if (AT.OUT / "STOP").exists():
        telegram("⛔ 데이 실매수 멈춤(data/autotrade/STOP)"); return
    S = AT.session("KR")
    if not S or S["date"] != today or AT.now() >= S["start"]:
        log("데이 매수 시각 지남 — 건너뜀"); return
    Lg = _led(); done = {(o["t"], o.get("rid", "T1")) for o in Lg["orders"] if o.get("date") == today and o.get("side") == "BUY"}
    placed, skip = [], []
    # 2026-10-06 T2(사용자 '1번'): 어제 막판 1시간 -1%↓ 인 후보는 T2 로 한 번 더 산다 — 규칙마다 따로 주문·기록
    # 2026-10-11 T3: 짝 미장 예상 갭 -0.5%↓ 도 한 번 더 — T2 와 둘 다면 둘 다(사용자 10-11)
    orders = order_list(L)
    # 원화가 없으면 토스가 422 로 하나씩 거절한다(10-06: 매수가능 7,821원에 3건 다 거절) — 미리 보고 이유를 똑바로 알린다
    try: bp = AT.buying_power("KRW")
    except AT.TossErr: bp = None
    if bp is not None and L and bp < min(float(x.get("lim") or x["exp"] or x["pc"]) for x in L):
        telegram("⚠ 데이 매수 0건 — 원화 매수가능 %s원 — 후보 %d종목 모두 1주도 못 삼(토스 계좌에 원화 입금 필요)" % (f"{bp:,.0f}", len(L)))
        log("원화 부족 — 매수가능", bp); return
    for x, rid in orders:
        if (x["t"], rid) in done: continue
        lim = int(x.get("lim") or limit_price(x["pc"], 0.0))
        px = float(lim)                                       # 지정가 = 최대로 낼 값 → 주수·매수가능도 이걸로
        mult = day_mult(x)
        if DAY_QTY:                                        # 테스트: 1주 × 배율의 정수 부분(1~5주)
            q = max(DAY_QTY, min(int(DAY_MULT_MAX), int(mult)))
        else:                                              # 실전: 기준금액 × 깊이 배율 × 거래대금 배율(T4 전용 후보는 1)
            base = DAY_BASE or DAY_PER
            q = math.floor(base * mult * float(x.get("lm") or 1.0) / px)
            if q < 1 and px <= base * 2: q = 1
        x.setdefault("mult", round(mult, 2))
        if q < 1:
            skip.append((x["name"] + ("" if rid == "T1" else "[%s]" % RNAME.get(rid, rid)), "1주가 너무 비쌈")); continue
        # 2026-10-06 사용자: 돈이 모자라면 1주씩만 산다(규칙이 제대로 도는지 보는 게 먼저)
        if bp is not None and q * px > bp:
            if px > bp:
                skip.append((x["name"] + ("" if rid == "T1" else "[%s]" % RNAME.get(rid, rid)), "매수가능 부족")); continue
            log("매수가능 부족 — 1주만:", x["t"], "%d→1주" % q); q = 1
        cid = re.sub(r"[^A-Za-z0-9_-]", "", f"db{today}{x['t']}" + ("" if rid == "T1" else rid))[:36]
        o = dict(side="BUY", date=today, t=x["t"], name=x["name"], qty=q, cid=cid, rid=rid, lim=lim, pc=x.get("pc"), at=AT.now().isoformat())
        body = {"clientOrderId": cid, "symbol": x["t"], "side": "BUY", "orderType": "LIMIT", "timeInForce": "OPG", "price": str(lim), "quantity": str(q)}
        try:
            try:
                o["oid"] = AT.place(body)
            except AT.TossErr as ex:
                if ex.code != "insufficient-buying-power" or q == 1: raise
                # 시장가는 토스가 넉넉히 잡아 둬서 모자랄 수 있다 → 1주로 한 번 더
                log("매수가능 부족 거절 — 1주로 다시:", x["t"])
                q = 1; body.update(quantity="1", clientOrderId=(cid + "o")[:36]); o.update(qty=1, cid=body["clientOrderId"])
                o["oid"] = AT.place(body)
        except AT.TossErr as ex:
            o["oid"] = None; o["err"] = ex.code or str(ex)[:100]
            skip.append((x["name"] + ("" if rid == "T1" else "[%s]" % RNAME.get(rid, rid)), "주문 거부 " + str(o["err"])))
            Lg["orders"].append(o); _led_save(Lg)
            if ex.code == "insufficient-buying-power" and bp is not None: bp = min(bp, px * 0.999)   # 이보다 비싼 건 건너뛴다
            continue                                          # 시가 단일가를 놓치면 사지 않는다(09:05 만 늦어도 효과가 사라진다)
        Lg["orders"].append(o); _led_save(Lg); placed.append(o)
        if bp is not None: bp -= q * px
        time.sleep(0.3)
    if not placed:
        if skip: telegram("⚠ 데이 매수 0건 — " + " · ".join("%s(%s)" % s_ for s_ in skip[:6]))
        return
    AT.sleep_until(S["start"] - dt.timedelta(seconds=30), "후보 호가 스냅샷(시가 직전)")
    try: book_snap(today, "am", [x["t"] for x in L])
    except Exception as ex: log("시가 직전 호가 스냅샷 실패:", repr(ex)[:200])
    AT.sleep_until(S["start"], "데이 시가 단일가")
    open_guard(placed, today)                              # 시가가 찍히자마자 '시가 > 지정가' 주문을 바로 취소(10-12 장중 체결 3건)
    AT.sleep_until(S["start"] + dt.timedelta(seconds=60), "데이 시가 체결 확인")
    cancel_left(placed)                                    # 남은 것 마지막 정리
    AT.wait_fills([o for o in placed if not o.get("canceled")])
    for o in placed:                                       # 취소한 주문은 한 번만 본다(PENDING 으로 남아 2분씩 기다려 10-13 알림이 09:16 에 왔다)
        if not o.get("canceled"): continue
        try:
            ex_ = ((AT.detail(o["oid"]) or {}).get("execution") or {})
            o["fq"] = float(ex_.get("filledQuantity") or 0); o["ap"] = float(ex_.get("averageFilledPrice") or 0); o["status"] = "CANCELED"
        except Exception:
            o["fq"], o["ap"], o["status"] = 0.0, 0.0, "CANCELED"
    got = [o for o in placed if o["fq"] > 0 and o["ap"] > 0]
    for o in got:                                          # 그래도 장중에 사진 것 — 시가보다 싸게(=지정가에) 체결됐다
        op_ = (o.get("open") or 0)
        if op_ and o.get("lim") and op_ > o["lim"]: o["intraday"] = True
    for i, o in enumerate(got):
        o["pos"] = {"id": int(time.time() * 1000) + i, "code": o["t"], "name": o["name"], "date": today, "price": o["ap"],
                    "qty": int(o["fq"]), "filters": [o.get("rid", "T1")], "auto": True, "day": True, "oid": o["oid"]}
    _led_save(Lg)
    if got:
        scalp_update(lambda P: (P.extend(dict(o["pos"]) for o in got) or True), "데이 매수 %d건" % len(got))
    try: mark_snap(today, placed, got)
    except Exception as ex: log("후보 시가 표시 실패:", repr(ex)[:200])
    lines = ["🌅 <b>데이 매수</b> %s/%s 시가" % (today[4:6], today[6:])]
    lines += ["✅ [%s] %s %d주 @ %s원 = %s원%s" % (RNAME.get(o.get("rid", "T1"), ""), o["name"], int(o["fq"]), f"{o['ap']:,.0f}", f"{o['fq'] * o['ap']:,.0f}",
                                                 (" ⚠ 장중 체결(시가 %s > 지정가 — 취소 전에 사짐)" % f"{o['open']:,.0f}") if o.get("intraday") else "") for o in got]
    lines += [("⏭ [%s] %s 시가가 지정가 %s원 위 — 안 삼(취소)" % (RNAME.get(o.get("rid", "T1"), ""), o["name"], f"{o['lim']:,}"))
              if o.get("canceled") else ("❌ %s 미체결(%s)" % (o["name"], o.get("status"))) for o in placed if o not in got]
    if skip: lines.append("못 산 것: " + " · ".join("%s(%s)" % s_ for s_ in skip[:6]))
    telegram("\n".join(lines))
    if not got: return
    close_sell(got, Lg, S, today)


def krx_open(sym, today, late=False):
    """KRX 시가 단일가 = 토스 1분봉에서 '09:01' 봉(봉 끝 시각 표기 — 09:00:00~59, 시가 단일가 체결이 여기 든다) 중 거래량 있는 첫 봉의 시가.
    ⚠ 2026-10-13: '09:00' 봉은 장전 마지막 값으로 채운 거래량 0 빈 봉인데 그걸 시가로 읽어 에이럭스·나노팀·이랜시스·레몬헬스케어
      (실제 시가가 다 지정가 아래)를 잘못 취소했다. 봉이 아직 없으면 시세의 마지막 체결이 09:00:00~05 이면 그 값(=시가 단일가)."""
    if late:                                              # 장 끝난 뒤 — 그날 정규장 봉을 처음부터(최근 200봉만으론 09:01 까지 못 닿는다)
        rows = sorted((r for r in M.fetch_day("KR", sym, today) if r[6] > 0), key=lambda r: r[1])
        return float(rows[0][2]) if rows else None
    c = (M.get("/api/v1/candles", symbol=sym, interval="1m", count=3) or {}).get("candles") or []
    c = [x for x in c if x["timestamp"][:10].replace("-", "") == today and "09:01" <= x["timestamp"][11:16] <= "15:31"
         and float(x.get("volume") or 0) > 0]
    if c: return float(min(c, key=lambda x: x["timestamp"])["openPrice"])
    for x in M.get("/api/v1/prices", symbols=sym) or []:
        ts = x.get("timestamp") or ""
        if ts[:10].replace("-", "") == today and "09:00:00" <= ts[11:19] <= "09:00:05": return float(x["lastPrice"])
    return None


def mark_snap(today, placed, got):
    """2026-10-13 사용자: 시가가 지정가보다 높아 안 산 후보는 그날 사도 의미 없다 → 사이트에서 숨긴다.
    후보마다 실제 시가(open)를 적고 시가 > 지정가면 skip=True → __day__ 다시 올림(사이트 dayCand 가 skip 은 뺀다).
    주문을 못 낸 후보(원화 부족)는 1분봉 첫 봉으로 시가를 따로 본다."""
    f = OUT / ("snap_%s.json" % today)
    snap = json.loads(f.read_text(encoding="utf-8"))
    op = {o["t"]: o["open"] for o in placed if o.get("open")}
    bought = {o["t"] for o in got}
    snap["closed"] = True                                  # 시가가 지났다 — 사이트는 안 산 후보(이유 무관)를 매수 대기에서 뺀다(10-13 사용자)
    for x in snap.get("cand") or []:
        x["rules"] = sorted({o.get("rid", "T1") for o in got if o["t"] == x["t"]})   # 실제로 산 규칙
        t = x["t"]
        if t in bought:
            x["bought"] = True; continue
        if t not in op:
            try:
                v = krx_open(t, today, late=True)
                if v: op[t] = v
            except Exception:
                pass
        if t in op:
            x["open"] = op[t]
            if x.get("lim") and op[t] > x["lim"]: x["skip"] = True
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    supa_set("__day__", {k: v for k, v in snap.items() if k != "all"})
    log("후보 시가 표시: 산 것 %d · 시가>지정가(숨김) %d" % (len(bought), sum(1 for x in snap.get("cand") or [] if x.get("skip"))))


def open_guard(placed, today, until_s=40):
    """2026-10-12 첫 실전: 토스 OPG 지정가는 시가에 안 사지면 **장중까지 살아 있어** 09:00~09:01 사이 3종목이 지정가에 장중 체결됐다
    (나이스정보통신·진양화학·셀비온 — 시가가 지정가보다 10~30원 위). → 09:00 부터 1초마다 그 종목 1분봉 첫 봉(=시가 단일가)을 보고
    시가 > 지정가면 바로 취소한다. 시가 단일가에서 이미 체결된 주문은 취소가 '이미 체결'로 거절될 뿐이라 손해 없음."""
    if AT.DRY or not placed: return
    from concurrent.futures import ThreadPoolExecutor
    left = {o["oid"]: o for o in placed if o.get("oid")}
    t_end = time.time() + until_s

    def first_open(sym):
        return krx_open(sym, today)

    def one(o):
        try:
            st = (AT.detail(o["oid"]) or {}).get("status")
            if st in AT.FINAL or st == "PARTIALLY_FILLED": return o["oid"], "done"
            op_ = first_open(o["t"])
            if op_ is None: return o["oid"], "wait"
            o["open"] = op_
            if op_ <= o["lim"]: return o["oid"], "done"           # 시가 단일가에서 사질 값 — 체결 반영만 기다린다
            try:
                AT.call("POST", "/api/v1/orders/%s/cancel" % o["oid"], acct=True, body={})
                o["canceled"] = True; log("시가 %s > 지정가 %s — 바로 취소:" % (op_, o["lim"]), o["t"], o.get("rid"))
            except AT.TossErr as ex:
                log("즉시 취소 거절(%s):" % ex.code, o["t"])
            return o["oid"], "done"
        except Exception as ex:
            log("시가 확인 실패:", o["t"], repr(ex)[:120]); return o["oid"], "wait"

    while left and time.time() < t_end:
        with ThreadPoolExecutor(min(8, len(left))) as ex:
            for oid, st in ex.map(one, list(left.values())):
                if st == "done": left.pop(oid, None)
        if left: time.sleep(1.0)
    if left: log("시가 확인 못 한 주문 %d — 09:01 정리에서 취소" % len(left))


def cancel_left(placed):
    """09:01 — 시가 단일가에 안 사진(또는 일부만 사진) 지정가 주문의 남은 몫을 취소한다.
    토스 문서에 OPG 지정가 미체결분이 장중까지 남는지 안 적혀 있어 직접 지운다(장중 체결은 건당 -0.1~-0.2% — H0321)."""
    if AT.DRY: return
    bad = []
    for o in placed:
        if o.get("canceled"): continue                      # open_guard 가 이미 취소함 — 토스 조회는 취소된 장전 주문을 계속 PENDING 으로 보여 주고
        try:                                                 # 다시 취소하면 cancel-restricted(10-13 확인: 장중 저가가 지정가 아래 수백 분인데 안 사짐)
            st = (AT.detail(o["oid"]) or {}).get("status")
        except Exception as ex:
            st = None; log("주문 조회 실패(취소 판단):", o["t"], repr(ex)[:150])
        if st in AT.FINAL: continue
        for k in range(4):
            try:
                AT.call("POST", "/api/v1/orders/%s/cancel" % o["oid"], acct=True, body={})
                o["canceled"] = True; log("시가 미체결 취소:", o["t"], o.get("rid"), "지정가", o.get("lim"), "상태", st); break
            except AT.TossErr as ex:
                if ex.code in ("already-filled", "already-canceled"):
                    log("취소 불필요(%s):" % ex.code, o["t"]); break
                log("취소 실패(%s) — 다시:" % ex.code, o["t"]); time.sleep(1.5)
            except Exception as ex:
                log("취소 실패 — 다시:", o["t"], repr(ex)[:150]); time.sleep(1.5)
        else:
            bad.append(o["name"])
        time.sleep(0.3)
    if bad:
        telegram("🚨 데이 지정가 미체결 취소 못 함 — %s · 장중에 사질 수 있으니 토스에서 직접 취소" % ", ".join(bad))


def _sell_mark(pid, ap, today, why, stop=False):
    def mark(P):
        for p_ in P:
            if p_.get("id") == pid and not p_.get("sell"):
                p_["sell"] = ap; p_["sellDate"] = today
                if stop: p_["stop"] = True
                return True
        return False
    scalp_update(mark, why)


def _stop_done(so, o, today):
    _sell_mark(o["pos"]["id"], so["ap"], today, "데이 -29% 손절", stop=True)
    r = (so["ap"] / o["ap"] - 1) * 100 - COST
    telegram("🧯 <b>데이 -29%% 손절</b> [%s] %s %d주 %s → %s원 %+.2f%% — 전일 종가 %s원의 %.0f%% 에 닿아 팜(하한가 묶임 피하기)" % (
        RNAME.get(o.get("rid", "T1"), ""), o["name"], int(so["fq"]), f"{o['ap']:,.0f}", f"{so['ap']:,.0f}", r, f"{float(o['pc']):,.0f}", 100 + STOP_PCT))


def _poll(so):
    """주문 한 번 조회 — 체결 수량·가격·상태를 so 에 적는다."""
    try:
        d = AT.detail(so["oid"], so["t"], so["qty"]) or {}
        ex_ = d.get("execution") or {}
        so["status"] = d.get("status"); so["fq"] = float(ex_.get("filledQuantity") or 0); so["ap"] = float(ex_.get("averageFilledPrice") or 0)
    except Exception as ex:
        log("주문 조회 실패:", so.get("t"), repr(ex)[:100])
    return so


def stop_watch(got, Lg, S, today):
    """10-19 사용자: 데이로 산 종목이 장중 전일 종가 대비 STOP_PCT(-29%) 이하면 바로 시장가 매도 — 하한가(-30%)에 묶여 종가에 못 파는 걸 피한다.
    종가 단일가 30초 전까지 15초마다 시세를 본다(-29% 를 건너뛰고 하한가로 가도 '이하'라 다음 확인에 걸린다).
    하한가에 묶여 바로 안 팔리면 주문은 그대로 두고(살 사람이 나오면 팔린다) 매 확인마다 체결을 다시 본다 — 팔리는 순간 사이트에 기록.
    반환 (손절 주문 낸 매수 목록, 아직 안 팔린 손절 [(so, o)]) — 둘 다 종가 매도에서 뺀다."""
    until = S["close_auction"] + dt.timedelta(seconds=30)
    left = [o for o in got if o.get("pc")]
    done, pend = [], []
    while (left or pend) and AT.now() < until:
        if left:
            try: px = AT.prices(sorted({o["t"] for o in left}))
            except Exception as ex:
                log("손절 감시 시세 실패:", repr(ex)[:120]); px = {}
            for o in [o for o in left if px.get(o["t"]) and px[o["t"]] <= float(o["pc"]) * (1 + STOP_PCT / 100)]:
                left.remove(o)
                so = dict(side="SELL", date=today, t=o["t"], name=o["name"], qty=int(o["fq"]), posId=o["pos"]["id"], cid=("dx" + o["cid"][2:])[:36], stop=True)
                try:
                    so["oid"] = AT.place({"clientOrderId": so["cid"], "symbol": o["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(int(o["fq"]))})
                except Exception as ex:
                    so["err"] = getattr(ex, "code", None) or str(ex)[:100]
                Lg["orders"].append(so); _led_save(Lg)
                if not so.get("oid"):
                    telegram("🚨 <b>데이 -29%% 손절 주문 실패</b> %s — %s · 토스에서 직접 확인" % (o["name"], so.get("err"))); continue
                done.append(o); time.sleep(3); _poll(so); _led_save(Lg)
                if so.get("fq", 0) >= so["qty"] and so.get("ap", 0) > 0: _stop_done(so, o, today)
                else:
                    pend.append((so, o))
                    telegram("⏳ <b>데이 -29%% 손절 주문 냄</b> %s %d주 — 하한가 근처라 바로 안 팔림. 주문은 걸어 두고 팔리는 대로 기록" % (o["name"], so["qty"]))
        for so, o in list(pend):
            _poll(so)
            if so.get("fq", 0) >= so["qty"] and so.get("ap", 0) > 0:
                _led_save(Lg); _stop_done(so, o, today); pend.remove((so, o))
            elif so.get("status") in ("CANCELED", "REJECTED"):
                pend.remove((so, o)); telegram("🚨 데이 -29%% 손절 주문 %s(%s) — 내일 아침 시가에 다시 판다" % (o["name"], so.get("status")))
        if left or pend: time.sleep(15)
    if done: log("손절 주문 낸 것:", [o["name"] for o in done], "· 아직 안 팔린 것", [o["name"] for _, o in pend])
    return done, pend


def carry_sell(today):
    """10-19 사용자: 전날까지 안 팔린 데이 종목(하한가 묶여 손절·종가 매도가 안 된 것)을 오늘 시가 단일가에 시장가로 판다.
    원장에서 최근 10일 체결된 데이 매수 중 매도 체결 합이 모자란 것 · 사이트에서 이미 판 것(sell)은 뺀다. 팔릴 때까지 매일 다시."""
    Lg = _led()
    lo = (dt.datetime.strptime(today, "%Y%m%d") - dt.timedelta(days=14)).strftime("%Y%m%d")
    buys = [o for o in Lg["orders"] if o.get("side") == "BUY" and o.get("pos") and (o.get("fq") or 0) > 0 and lo <= o.get("date", "") < today]
    if not buys: return []
    sold = {}
    for o in Lg["orders"]:
        if o.get("side") == "SELL" and o.get("posId"): sold[o["posId"]] = sold.get(o["posId"], 0) + float(o.get("fq") or 0)
    try: site_sold = {p.get("id") for p in (AT.site_state().get("positions_scalp") or []) if p.get("sell")}
    except Exception: site_sold = set()
    out = []
    for o in buys:
        pid = o["pos"]["id"]
        rem = int(float(o["fq"]) - sold.get(pid, 0))
        if rem < 1 or pid in site_sold: continue
        try: have = AT.sellable(o["t"]) if not AT.DRY else rem
        except Exception: have = None
        q = rem if have is None else int(min(rem, have))
        if q < 1: log("넘어온 데이 종목 매도가능 0 — 손으로 판 듯:", o["t"]); continue
        so = dict(side="SELL", date=today, t=o["t"], name=o["name"], qty=q, posId=pid, cid=("dc%s%s" % (today[2:], pid))[:36], carry=True)
        try:
            so["oid"] = AT.place({"clientOrderId": so["cid"], "symbol": o["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(q), "timeInForce": "OPG"})
        except Exception as ex:
            so["err"] = getattr(ex, "code", None) or str(ex)[:100]
        Lg["orders"].append(so); _led_save(Lg)
        if so.get("oid"): out.append((so, o))
        else: telegram("🚨 넘어온 데이 종목 %s 시가 매도 주문 실패(%s) — 토스에서 직접 확인" % (o["name"], so.get("err")))
    if out:
        telegram("🔁 <b>어제 못 판 데이 종목</b> %d개 오늘 시가에 시장가 매도: %s" % (len(out), ", ".join("%s %d주" % (o["name"], so["qty"]) for so, o in out)))

        def check():
            S = AT.session("KR")
            AT.sleep_until(S["start"] + dt.timedelta(seconds=90), "넘어온 데이 종목 체결 확인")
            L2 = _led()
            for so, o in out:
                _poll(so)
                for z in L2["orders"]:
                    if z.get("cid") == so["cid"]: z.update({k: so[k] for k in ("fq", "ap", "status") if k in so})
                if so.get("fq", 0) > 0 and so.get("ap", 0) > 0:
                    _sell_mark(o["pos"]["id"], so["ap"], today, "어제 못 판 데이 종목 매도")
                    r = (so["ap"] / o["ap"] - 1) * 100 - COST
                    telegram("🔁 %s %d주 팔림 %s → %s원 %+.2f%%(산 날 %s)" % (o["name"], int(so["fq"]), f"{o['ap']:,.0f}", f"{so['ap']:,.0f}", r, o["date"][4:]))
                else:
                    telegram("🔒 %s 오늘 시가에도 안 팔림(%s) — 내일 다시" % (o["name"], so.get("status")))
            _led_save(L2)
        import threading
        threading.Thread(target=check, daemon=False).start()
    return out


def close_sell(got, Lg, S, today):
    """같은 날 종가 단일가(15:20~15:30)에 판다 — got = 체결된 매수 주문(o['pos'] 기록 포함)."""
    try:
        stopped, spend = stop_watch(got, Lg, S, today)         # 장중 -29% 손절(10-19 사용자) — 그동안 종가까지 기다리는 역할도 한다
    except Exception as ex:
        log("손절 감시 실패:", repr(ex)[:200]); telegram("⚠ 데이 -29% 손절 감시가 죽었다: %s — 종가 매도는 그대로" % str(ex)[:120]); stopped, spend = [], []
    got = [o for o in got if o not in stopped]
    AT.sleep_until(S["close_auction"] + dt.timedelta(seconds=60), "데이 종가 매도")
    # 2026-10-06: 15:21 DNS 실패 한 번에 프로세스가 죽어 3주가 안 팔렸다 → 못 낸 주문은 15:29 까지 20초마다 다시 낸다.
    #   (네트워크 한 번의 실패는 AT.call 이 5분까지 다시 한다 · 그래도 남으면 여기서 또 · 끝내 못 팔면 알림)
    sold, pend = [], list(got)
    deadline = S["end"] - dt.timedelta(minutes=1)
    while pend:
        nxt = []
        for o in pend:
            try:
                have = AT.sellable(o["t"]) if not AT.DRY else o["fq"]
            except Exception:
                have = None
            q = int(o["fq"]) if have is None else int(min(o["fq"], have))
            if q < 1:
                log("매도가능 0 — 이미 팔렸거나 주문이 들어가 있음:", o["t"]); continue
            so = dict(side="SELL", date=today, t=o["t"], name=o["name"], qty=q, posId=o["pos"]["id"], cid=("ds" + o["cid"][2:])[:36])
            try:
                so["oid"] = AT.place({"clientOrderId": so["cid"], "symbol": o["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(q)})
                sold.append((so, o))
            except Exception as ex:
                so["err"] = getattr(ex, "code", None) or str(ex)[:100]; nxt.append(o)
                log("데이 매도 주문 실패 — 다시 할 것:", o["t"], so["err"])
            Lg["orders"].append(so); _led_save(Lg)
            time.sleep(0.3)
        pend = nxt
        if pend and AT.now() < deadline:
            time.sleep(20)
        else:
            break
    if pend:
        telegram("🚨 <b>데이 종가 매도 못 함</b> — " + ", ".join(o["name"] for o in pend) + " · 토스에서 직접 확인")
    AT.sleep_until(S["end"] + dt.timedelta(seconds=90), "데이 종가 체결 확인")
    try:
        AT.wait_fills([so for so, _ in sold])
    except Exception as ex:
        log("체결 확인 실패:", repr(ex)[:200])
        for so, _ in sold: so.setdefault("fq", 0); so.setdefault("ap", 0)
    fin = [(so, o) for so, o in sold if so["fq"] > 0 and so["ap"] > 0]
    _led_save(Lg)
    if fin:
        ids = {o["pos"]["id"]: so["ap"] for so, o in fin}

        def mark(P):
            ch = False
            for p_ in P:
                if p_.get("id") in ids and not p_.get("sell"):
                    p_["sell"] = ids[p_["id"]]; p_["sellDate"] = today; ch = True
            return ch
        scalp_update(mark, "데이 매도 %d건" % len(fin))
    lines = ["🌇 <b>데이 매도</b> %s/%s 종가" % (today[4:6], today[6:])]
    tot, rs = 0.0, []
    for so, o in fin:
        r = (so["ap"] / o["ap"] - 1) * 100 - COST
        won_ = so["fq"] * (so["ap"] - o["ap"]) - so["fq"] * (so["ap"] * 0.00215 + o["ap"] * 0.00015)
        tot += won_; rs.append(r)
        lines.append("%s [%s] %s %+.2f%% (%s원)" % ("🔺" if r > 0 else "🔻", RNAME.get(o.get("rid", "T1"), ""), o["name"], r, f"{won_:+,.0f}"))
    if rs:
        lines.append("합계 %s원 · 평균 %+.2f%% · 오른 종목 %d/%d (수수료·세금 뒤)" % (f"{tot:+,.0f}", sum(rs) / len(rs), sum(r > 0 for r in rs), len(rs)))
    fin_ids = {o["pos"]["id"] for _, o in fin}
    left = [o["name"] for o in got if o["pos"]["id"] not in fin_ids]
    if left: lines.append("⚠ 못 판 것: " + ", ".join(left) + " — 내일 아침 시가에 다시 판다(carry_sell)")
    for so, o in spend:                                    # 하한가에 묶였던 손절 — 장 끝난 뒤 마지막으로 본다
        _poll(so); _led_save(Lg)
        if so.get("fq", 0) >= so["qty"] and so.get("ap", 0) > 0: _stop_done(so, o, today)
        else: lines.append("🔒 %s -29%% 손절 주문이 오늘 안 팔림(하한가 묶임) — 내일 아침 시가에 다시 판다" % o["name"])
    if got or spend: telegram("\n".join(lines))


def book_snap(today, part, syms):
    """실행 방법 실측(day_exec.py)용 — 우리 후보 종목 호가 10단계를 단일가 직전(08:59:30 · 15:29:30)에 찍어 둔다.
    녹화기는 08:56:15·15:27:20 이 마지막이라 그 뒤 몇 분 사이 호가 변화를 놓친다(2026-10-14)."""
    import pandas as pd
    rows = []
    for s_ in syms:
        try:
            r = M.get("/api/v1/orderbook", symbol=s_) or {}
            for side, key in (("A", "asks"), ("B", "bids")):
                for i, x in enumerate(r.get(key) or []):
                    rows.append((AT.now().strftime("%H%M%S"), s_, side, i, float(x["price"]), float(x["volume"])))
        except Exception:
            pass
    if rows:
        pd.DataFrame(rows, columns=["tag", "ticker", "side", "lvl", "price", "vol"]).to_parquet(OUT / ("book_%s_%s.parquet" % (today, part)), index=False)
    log("후보 호가 스냅샷 %s %d종목" % (part, len({r[1] for r in rows})))


def close_job(today):
    """15:24 예약 — 지킴이(close_watch) 뒤 15:29:30 에 후보 호가를 찍는다(종가 단일가 직전)."""
    try: close_watch(today)
    finally:
        try:
            f = OUT / ("snap_%s.json" % today)
            S = AT.session("KR")
            if f.exists() and S and S["date"] == today:
                syms = [x["t"] for x in json.loads(f.read_text(encoding="utf-8")).get("cand") or []]
                AT.sleep_until(S["end"] - dt.timedelta(seconds=30), "후보 호가 스냅샷(종가 직전)")
                book_snap(today, "pm", syms)
        except Exception as ex:
            log("종가 직전 호가 스냅샷 실패:", repr(ex)[:200])


def close_watch(today):
    """15:24 예약 — 아침 프로세스가 죽었어도(10-06 DNS 실패로 사망) 오늘 산 데이 종목을 종가 단일가에 판다.
    원장에 오늘 체결된 매수 중 **매도 주문(oid)이 아직 없는 것**만. 아침 프로세스가 이미 냈으면 아무것도 안 한다
    (같은 clientOrderId 라 겹쳐 내도 토스가 한 번만 받는다)."""
    S = AT.session("KR")
    if not S or S["date"] != today:
        log("국장 휴장 — 건너뜀"); return
    if not (S["close_auction"] <= AT.now() < S["end"] - dt.timedelta(minutes=1)):
        log("종가 단일가 시간 아님 — 건너뜀"); return
    Lg = _led()
    sold_pos = {o.get("posId") for o in Lg["orders"] if o.get("side") == "SELL" and o.get("date") == today and o.get("oid")}
    got = [o for o in Lg["orders"] if o.get("side") == "BUY" and o.get("date") == today and o.get("pos")
           and (o.get("fq") or 0) > 0 and o["pos"]["id"] not in sold_pos]
    if not got:
        log("지킴이: 오늘 팔 데이 종목 없음(또는 이미 주문됨)"); return
    log("지킴이: 매도 주문 없는 데이 %d종목 — 지금 판다" % len(got))
    telegram("🛟 데이 지킴이: 아침 프로세스가 못 판 %d종목을 종가 단일가로 매도" % len(got))
    close_sell(got, Lg, S, today)


def late(today):
    """2026-10-06 사용자: 원화가 없어 아침 시가 주문이 다 거절된 날, 입금 뒤 **지금 시장가로 1주씩** 사고 종가에 판다.
    규칙(시가 매수)과 다른 체결이라 기록에 late=True 를 붙인다 — 규칙 성적과 섞어 보지 말 것."""
    S = AT.session("KR")
    if not S or S["date"] != today or not (S["start"] <= AT.now() < S["close_auction"] - dt.timedelta(minutes=5)):
        log("장중(종가 단일가 5분 전까지)이 아님 — 건너뜀"); return
    snap = json.loads((OUT / ("snap_%s.json" % today)).read_text(encoding="utf-8"))
    L = snap.get("cand") or []
    Lg = _led()
    done = {(o["t"], o.get("rid", "T1")) for o in Lg["orders"] if o.get("date") == today and o.get("side") == "BUY" and o.get("oid")}
    placed, skip = [], []
    for x, rid in order_list(L[:DAY_MAX]):
        if (x["t"], rid) in done: continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "", f"dl{today}{x['t']}" + ("" if rid == "T1" else rid))[:36]
        o = dict(side="BUY", date=today, t=x["t"], name=x["name"], qty=1, cid=cid, rid=rid, late=True, pc=x.get("pc"), at=AT.now().isoformat())
        try:
            o["oid"] = AT.place({"clientOrderId": cid, "symbol": x["t"], "side": "BUY", "orderType": "MARKET", "quantity": "1"})
        except AT.TossErr as ex:
            o["oid"] = None; o["err"] = ex.code or str(ex)[:100]; skip.append((x["name"], "주문 거부 " + str(o["err"])))
        Lg["orders"].append(o); _led_save(Lg)
        if o["oid"]: placed.append(o)
        time.sleep(0.3)
    AT.wait_fills(placed)
    got = [o for o in placed if o["fq"] > 0 and o["ap"] > 0]
    for i, o in enumerate(got):
        o["pos"] = {"id": int(time.time() * 1000) + i, "code": o["t"], "name": o["name"], "date": today, "price": o["ap"],
                    "qty": int(o["fq"]), "filters": [o.get("rid", "T1")], "auto": True, "day": True, "late": True, "oid": o["oid"]}
    _led_save(Lg)
    if got:
        scalp_update(lambda P: (P.extend(dict(o["pos"]) for o in got) or True), "데이 늦은 매수 %d건" % len(got))
    lines = ["🕚 <b>데이 늦은 매수</b> %s/%s 지금 시장가 1주씩(시가 아님)" % (today[4:6], today[6:])]
    lines += ["✅ %s %d주 @ %s원" % (o["name"], int(o["fq"]), f"{o['ap']:,.0f}") for o in got]
    lines += ["❌ %s 미체결(%s)" % (o["name"], o.get("status")) for o in placed if o not in got]
    if skip: lines.append("못 산 것: " + " · ".join("%s(%s)" % s_ for s_ in skip[:6]))
    telegram("\n".join(lines))
    if got: close_sell(got, Lg, S, today)


def review():
    today, it, prev = today_session()
    if not today:
        log("국장 휴장 — 건너뜀"); return
    f = OUT / ("snap_%s.json" % today)
    if not f.exists():
        log("오늘 아침 기록 없음 — 건너뜀"); return
    snap = json.loads(f.read_text(encoding="utf-8"))
    syms = list(snap["all"].keys())
    act, prevc = {}, {}                                    # 오늘 KRX (시가 단일가, 종가 단일가) · 어제 종가(아침 계산과 같은 토스 종가)
    # 2026-10-13: 전엔 오늘 시가·종가도 토스 일봉에서 받았다 → NXT 종목은 시가 = NXT 장전 08:00 첫 체결, 종가 = 16시대 NXT 장후 가격이라
    #   후보 성적·'실제 시가로 골랐다면'·예상 시가 오차(NXT 2.54%p)가 다 틀렸다. KRX 값은 1분봉(16:11 저장 전 종목 파일)에서:
    #   첫 봉(09:01 끝) 시가 = 시가 단일가, 마지막 봉(15:31 끝) 종가 = 종가 단일가.
    mf = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % today)
    if mf.exists():
        import pandas as pd
        D = pd.read_parquet(mf, columns=["t", "ts", "o", "c"]).sort_values(["t", "ts"])
        g = D.groupby("t")
        act = {t: (float(o), float(c)) for t, o, c in zip(g.o.first().index, g.o.first().values, g.c.last().values)}
    for s in syms:
        c = (M.get("/api/v1/candles", symbol=s, interval="1d", count=3) or {}).get("candles") or []
        c = sorted(c, key=lambda x: x["timestamp"])
        t = [x for x in c if x["timestamp"][:10].replace("-", "") == today]
        b = [x for x in c if x["timestamp"][:10].replace("-", "") < today]
        if t and s not in act and not mf.exists(): act[s] = (float(t[0]["openPrice"]), float(t[0]["closePrice"]))   # 1분봉 파일이 없을 때만(통합 봉)
        if b: prevc[s] = float(b[-1]["closePrice"])
    for x in snap["cand"]:                                 # 파일에 없는 후보는 그 종목만 1분봉을 받는다
        if x["t"] not in act:
            try:
                rows = M.fetch_day("KR", x["t"], today)
                if rows: rows = sorted(rows, key=lambda r: r[1]); act[x["t"]] = (rows[0][2], rows[-1][5])
            except Exception:
                pass
    log("리뷰 시가·종가: KRX 1분봉 %s · %d종목" % ("파일" if mf.exists() else "없음(토스 일봉으로)", len(act)))
    # 예상 시가가 맞았나 — 예상 갭 vs 실제 갭(같은 어제 종가 기준) · 실제 갭으로 다시 고르면 후보가 얼마나 겹치나
    real_gap = {s: (act[s][0] / prevc[s] - 1) * 100 for s in syms if s in act and s in prevc}
    errs = {"NXT": [], "호가": []}
    for s, g in real_gap.items():
        a = snap["all"].get(s)
        if a and a.get("src") in errs: errs[a["src"]].append(a["gap"] - g)
    rq = pct_rank(real_gap)
    rmg = sorted(real_gap.values())[len(real_gap) // 2] if real_gap else 0.0
    real_cand = {s for s in real_gap if rq[s] <= 0.10 and snap["all"].get(s, {}).get("pre") and snap["all"].get(s, {}).get("tiny")
                 and real_gap[s] - rmg <= snap.get("thr", -2.0)}
    mine = {x["t"] for x in snap["cand"] if x.get("t1", True)}
    rets, urets = [], []
    for x in snap["cand"]:
        if x["t"] in act:
            o, c = act[x["t"]]; r = (c / o - 1) * 100 - COST
            (rets if x.get("t1", True) else urets).append(r)
            x["open"], x["close"], x["ret"] = o, c, round(r, 3)
    # T4 고른 것 전체(겹침 포함)·넓은 판 — 실제 시가→종가(시가가 지정가 -2% 위면 '안 사짐' 으로 따로 셈)
    def tset(ts, cut):
        rr, nf = [], 0
        for s in ts or []:
            if s not in act or s not in prevc: continue
            o, c = act[s]
            if (o / prevc[s] - 1) * 100 > cut: nf += 1; continue
            rr.append((c / o - 1) * 100 - COST)
        return rr, nf
    u_r, u_nf = tset(snap.get("u_sel"), U_GAP)
    w_r, w_nf = tset(snap.get("u_wide"), W_GAP)
    real_rets = [(act[s][1] / act[s][0] - 1) * 100 - COST for s in real_cand if s in act]
    avg = lambda L: sum(L) / len(L) if L else float("nan")
    mae = lambda L: sum(abs(v) for v in L) / len(L) if L else float("nan")
    lf = OUT / "log.csv"; new = not lf.exists()
    with open(lf, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new: w.writerow(["날짜", "후보수", "후보 평균(비용 뒤)", "실제 갭 기준 후보수", "그 평균", "겹친 수", "NXT 갭 오차(평균 절대 %p)", "호가 갭 오차", "NXT 수", "호가 수"])
        w.writerow([today, len(rets), round(avg(rets), 3), len(real_rets), round(avg(real_rets), 3), len(mine & real_cand),
                    round(mae(errs["NXT"]), 3), round(mae(errs["호가"]), 3), len(errs["NXT"]), len(errs["호가"])])
    snap["review"] = dict(rets=rets, real_n=len(real_cand), overlap=len(mine & real_cand))
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    try:
        supa_set("__day__", {k: v for k, v in snap.items() if k != "all"})
    except Exception as ex:
        log("사이트 기록 실패:", ex)
    L = ["📊 <b>데이 [%s] 오늘 결과</b> %s/%s (후보 전체 기준 · 예상 시가 점검)" % (RULE, today[4:6], today[6:]),
         "아침 후보 %d종목 시가→종가 평균 <b>%+.2f%%</b>(비용 뒤) · 오른 종목 %d/%d" % (len(rets), avg(rets), sum(r > 0 for r in rets), len(rets)),
         "실제 시가로 골랐다면 %d종목 평균 %+.2f%% · 아침 후보와 겹침 %d" % (len(real_rets), avg(real_rets), len(mine & real_cand)),
         "예상 시가 오차(갭 %%p): NXT %.2f(%d종목) · 호가 %.2f(%d종목)" % (mae(errs["NXT"]), len(errs["NXT"]), mae(errs["호가"]), len(errs["호가"]))]
    if snap.get("u_sel") or snap.get("u_wide"):
        L.append("🇺🇸 [%s] 나스닥 %s%% — 고른 %d종목 중 시가 -2%%↓로 열린 %d종목 평균 <b>%+.2f%%</b>(안 사짐 %d) · 넓은 판(기록만) %d종목 평균 %+.2f%%(안 사짐 %d)" % (
            RNAME["T4"], snap.get("nas"), len(snap.get("u_sel") or []), len(u_r), avg(u_r), u_nf, len(w_r), avg(w_r), w_nf))
        uf = OUT / "t4_log.csv"; new_u = not uf.exists()
        with open(uf, "a", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            if new_u: w.writerow(["날짜", "나스닥", "고른 수", "체결 가능 수", "평균(비용 뒤)", "넓은 판 수", "넓은 판 체결 가능", "넓은 판 평균"])
            w.writerow([today, snap.get("nas"), len(snap.get("u_sel") or []), len(u_r), round(avg(u_r), 3), len(snap.get("u_wide") or []), len(w_r), round(avg(w_r), 3)])
    try:                                                  # 실행 방법 실측(금액별 매수·매도 방법 — day_exec.py, 10-14)
        import day_exec as DX
        DX.run(today, quiet=True); DX.summary()
        L.append(DX.brief())
    except Exception as ex:
        log("실행 방법 실측 실패:", repr(ex)[:200])
        L.append("⚠ 실행 방법 실측 실패: %s" % str(ex)[:120])      # 조용히 죽지 않게(매일 그림자 테스트 — 사용자 10-14)
    telegram("\n".join(L))
    log("리뷰:", L[1], "|", L[2], "|", L[3])


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] in (["morning"], ["review"]):
            # 도는 동안 1분봉 과거 채우기를 쉬게 한다 — 토스 시세 호출은 초당 10회를 같이 쓴다(아침은 08:56 전에 끝나야 한다)
            M.BUSY.write_text("day")
            try:
                morning() if a[0] == "morning" else review()
            finally:
                try: M.BUSY.unlink()
                except Exception: pass
        elif a[:1] == ["late"]:
            late(AT.now().strftime("%Y%m%d"))
        elif a[:1] == ["close"]:
            close_job(AT.now().strftime("%Y%m%d"))
        else: log("사용법: python day_alert.py morning | review | late | close")
    except Exception as ex:
        log("실패:", repr(ex)[:500])
        telegram("⚠ 데이 알림 실패: %s" % str(ex)[:300]); raise
