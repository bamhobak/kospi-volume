# -*- coding: utf-8 -*-
"""덜 알려진 외국 기법 → 등록부 + 명세 (2026-09-25 사용자 요청: "외국 사이트들 안 유명한 거 위주로 기법 찾아서 실측").

조사 에이전트 여섯 갈래(일본·중화권·유럽/남미·영어권 옛 기술적분석가·논문 이상현상·인도/동남아/터키)가 모은
기법을 **run_spec 조건식**으로 옮긴다. 기법마다 국내·미장 두 명세를 만든다(한쪽 전용이면 한쪽만).

번역 원칙
  · 진입은 전부 '신호일 다음날 시가' — 원전의 스톱 매수(다음날 고가 돌파)·장중 체결은 재현 못 한다. 해당 기법은 이름에 [근사].
  · 청산도 고정 보유(5·10·20·40·60일)만 — 원전의 지표 청산·손절은 못 쓴다.
  · 모호한 문턱은 원전에 가장 가까운 값을 원안으로, 다른 해석은 이웃(variants)으로 미리 적는다.
  · 공통 부품(ADX·ATR·종가위치 등)은 PARTS 에서 필요한 것만 derive 에 넣는다.

    python research/intl_specs.py            # 등록 + 명세 파일 쓰기(이미 등록된 키는 건너뜀)
    python research/intl_specs.py --list
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry

SPECS = ROOT / "specs"
MAP = ROOT / "cache" / "intl_map.json"          # 기법키·시장 → 가설 번호

# ── 공통 부품 (derive 에 순서대로 들어간다 — 뒤 부품이 앞 부품을 쓸 수 있다) ─────────────
PARTS = {
    "pc":    "lag(close, 1)",
    "r1":    "(close / pc - 1) * 100",
    "pos":   "(close - low) / (high - low + 1e-9)",                  # 종가 위치 0~1
    "opos":  "(open - low) / (high - low + 1e-9)",                   # 시가 위치 0~1
    "tr":    "np.maximum(high - low, np.maximum(np.abs(high - pc), np.abs(low - pc)))",
    "atr10": "rma(tr, 10)",
    "atr14": "rma(tr, 14)",
    "atr40": "rma(tr, 40)",
    "upm":   "high - lag(high, 1)",
    "dnm":   "lag(low, 1) - low",
    "pdm":   "upm * ((upm > dnm) & (upm > 0))",
    "mdm":   "dnm * ((dnm > upm) & (dnm > 0))",
    "pdi":   "100 * rma(pdm, 14) / (atr14 + 1e-9)",
    "mdi":   "100 * rma(mdm, 14) / (atr14 + 1e-9)",
    "adx":   "rma(100 * np.abs(pdi - mdi) / (pdi + mdi + 1e-9), 14)",
    "ma10":  "rmean(close, 10)",
    "ma50":  "rmean(close, 50)",
    "ma200": "rmean(close, 200)",
    "ins":   "(high < lag(high, 1)) & (low > lag(low, 1))",
    "amt":   "close * volume",
}


def need(*names):
    """부품 이름들 → 순서 보존 derive dict (의존 부품 자동 포함)"""
    out = {}
    order = list(PARTS)
    want = set(names)
    changed = True
    while changed:                       # 부품 식 안에 나오는 다른 부품도 끌어온다
        changed = False
        for k in list(want):
            for o in order:
                if o not in want and o in PARTS[k].replace("(", " ").replace(")", " ").replace(",", " ").split():
                    want.add(o); changed = True
    for k in order:
        if k in want:
            out[k] = PARTS[k]
    return out


def D(parts, **extra):
    d = need(*parts)
    d.update(extra)
    return d


# ── 기법 목록 ─────────────────────────────────────────────────────────────
# key · name · family · src · mech · derive · cond · variants[(label, cond)] · holds · main · mk(KR/US/both) · diff
T = []


def add(**kw):
    kw.setdefault("mk", "both"); kw.setdefault("holds", [5, 10, 20]); kw.setdefault("main", 10)
    T.append(kw)


# ═════ 영어권 옛 기술적분석가 · 소형 퀀트 블로그 ═════
add(key="dv2", name="DV2 (Varadi·CSS Analytics) 종가/고저중간 2일 평균 과매도", family=["보조지표", "낙폭반전"],
    src="cssanalytics.wordpress.com 2008~2010 'RSI(2) 대안' DV2",
    mech="종가가 당일 고저 중간값 아래로 이틀 머물면 과매도 — 종가끼리 비교하는 RSI2 와 상관이 낮다고 주장",
    derive=D([], x="close / ((high + low) / 2) - 1", dv="rmean(x, 2)",
             dvb="(dv - rmin(dv, 252)) / (rmax(dv, 252) - rmin(dv, 252) + 1e-9)", ma200="rmean(close, 200)"),
    cond="dvb < 0.10",
    variants=[("DVB<0.20", "dvb < 0.20"), ("DVB<0.10 & 200일선 위", "(dvb < 0.10) & (close > ma200)"),
              ("DVB<0.05", "dvb < 0.05")],
    holds=[5, 10, 20], main=5,
    diff="RSI2·IBS(H00xx 기각)와 달리 종가를 고저 중간값과 비교하고 252일 백분위(최소-최대 근사)로 정규화")

add(key="aggm", name="Aggregate M (Varadi) 장기 추세 강함 + 단기 눌림 합성", family=["보조지표", "눌림"],
    src="cssanalytics.wordpress.com 2009-11 'Aggregate M'",
    mech="252일 위치(추세)와 10일 역위치(평균회귀)를 평균·평활 — 장기로 강하고 단기로 눌린 종목",
    derive=D([], lt="(close - rmin(low, 252)) / (rmax(high, 252) - rmin(low, 252) + 1e-9)",
             st="1 - (close - rmin(low, 10)) / (rmax(high, 10) - rmin(low, 10) + 1e-9)",
             mr="(lt + st) / 2", m="rma(mr, 1.6667)"),
    cond="(m > 0.5) & (lag(m, 1) <= 0.5)",
    variants=[("M>0.5 & 전일보다 낮음(추세 안 눌림)", "(m > 0.5) & (m < lag(m, 1)) & (lt > 0.8)"),
              ("M 0.6 상향돌파", "(m > 0.6) & (lag(m, 1) <= 0.6)"), ("M 0.55 상향", "(m > 0.55) & (lag(m, 1) <= 0.55)")],
    holds=[5, 10, 20], main=10, diff="단순 스토캐스틱·이평 눌림과 달리 장기 위치와 단기 역위치를 합성")

add(key="c180", name="Jeff Cooper '180' 약세봉→강세봉 하루 반전(10·50일선 위) [근사]", family=["캔들", "눌림"],
    src="Jeff Cooper 'Hit and Run Trading'(1996) · hitnrun.de/180.htm",
    mech="어제 종가가 하단 25%, 오늘 종가가 상단 25%로 180도 뒤집힘 — 10·50일선 위(추세 안)에서만",
    derive=D(["pos", "ma10", "ma50"]),
    cond="(lag(pos, 1) <= 0.25) & (pos >= 0.75) & (close > ma10) & (close > ma50)",
    variants=[("하단/상단 33%", "(lag(pos, 1) <= 0.33) & (pos >= 0.67) & (close > ma10) & (close > ma50)"),
              ("50일선만", "(lag(pos, 1) <= 0.25) & (pos >= 0.75) & (close > ma50)"),
              ("+ 오늘 상승", "(lag(pos, 1) <= 0.25) & (pos >= 0.75) & (close > ma10) & (close > ma50) & (close > lag(close, 1))")],
    holds=[5, 10, 20], main=5, diff="원전은 다음날 고가 돌파 스톱 매수 — 여기선 다음날 시가로 근사")

add(key="boomer", name="Jeff Cooper 'Boomer' ADX>30 추세 속 이틀 연속 인사이드데이 [근사]", family=["패턴", "추세추종"],
    src="Jeff Cooper · hitnrun.de/boomers.htm",
    mech="강한 추세의 짧은 휴지기(이틀 연속 압축) 뒤 추세 재개",
    derive=D(["adx", "pdi", "mdi", "ins"]),
    cond="(adx > 30) & (pdi > mdi) & ins & lag(ins, 1)",
    variants=[("ADX>25", "(adx > 25) & (pdi > mdi) & ins & lag(ins, 1)"),
              ("인사이드 1일", "(adx > 30) & (pdi > mdi) & ins"),
              ("ADX>35", "(adx > 35) & (pdi > mdi) & ins & lag(ins, 1)")],
    holds=[5, 10, 20], main=5, diff="평범한 인사이드데이(기각)와 달리 ADX 추세 게이트 + 2연속")

add(key="lizard", name="Jeff Cooper 'Lizard' 시가·종가 상단 25% + 10일 신저가(긴 아래꼬리)", family=["캔들", "낙폭반전"],
    src="hitnrun.de/lizards.htm · prorealcode 'Lizards Jeff Cooper'",
    mech="신저가를 찍었지만 시가·종가가 모두 위쪽 — 매도세 흡수",
    derive=D(["pos", "opos"]),
    cond="(pos >= 0.75) & (opos >= 0.75) & (low <= rmin(low, 10))",
    variants=[("상단 33%", "(pos >= 0.67) & (opos >= 0.67) & (low <= rmin(low, 10))"),
              ("20일 신저가", "(pos >= 0.75) & (opos >= 0.75) & (low <= rmin(low, 20))"),
              ("+ 폭이 평소보다 큼", "(pos >= 0.75) & (opos >= 0.75) & (low <= rmin(low, 10)) & ((high - low) > 1.2 * rmean(high - low, 20))")],
    holds=[5, 10, 20], main=5, diff="전일 고저 이탈 후 재진입·스윕(기각)과 달리 한 봉의 시가·종가 위치 + 10일 신저가")

add(key="c1234", name="Jeff Cooper '1-2-3-4' ADX≥30 추세 속 저가 3연속 하락 눌림", family=["눌림", "추세추종"],
    src="WH SelfInvest '1-2-3-4 trader Jeff Cooper' · tradingfreaks 1-2-3-4er",
    mech="급등주는 며칠 쉬었다 다시 간다 — 추세 강도(ADX)로 게이트한 3일 눌림",
    derive=D(["adx", "pdi", "mdi", "ma50"]),
    cond="(adx >= 30) & (pdi > mdi) & (low < lag(low, 1)) & (lag(low, 1) < lag(low, 2)) & (lag(low, 2) < lag(low, 3))",
    variants=[("ADX>25", "(adx >= 25) & (pdi > mdi) & (low < lag(low, 1)) & (lag(low, 1) < lag(low, 2)) & (lag(low, 2) < lag(low, 3))"),
              ("+ 고가도 3연속 하락", "(adx >= 30) & (pdi > mdi) & (low < lag(low, 1)) & (lag(low, 1) < lag(low, 2)) & (lag(low, 2) < lag(low, 3)) & (high < lag(high, 1)) & (lag(high, 1) < lag(high, 2))"),
              ("+ 50일선 위", "(adx >= 30) & (pdi > mdi) & (low < lag(low, 1)) & (lag(low, 1) < lag(low, 2)) & (lag(low, 2) < lag(low, 3)) & (close > ma50)")],
    holds=[5, 10, 20], main=5, diff="연속 하락일(종가 기준·기각)과 달리 ADX 추세 게이트 + 저가 기준")

add(key="pocket", name="Pocket Pivot (Kacher·Morales) 하락일 최대 거래량을 넘는 상승일", family=["거래량", "추세추종"],
    src="powerofthepivot.wordpress.com 2014 · chartmill Pocket Pivots",
    mech="최근 매도 거래량을 넘는 매수 거래량 = 기관 매집 흔적, 베이스 안에서 신고가 전에 산다",
    derive=D(["ma10", "ma50"], dvol="volume * (close < lag(close, 1))"),
    cond="(close > lag(close, 1)) & (volume > lag(rmax(dvol, 10), 1)) & (close > ma50) & (close > ma10) & (close <= 1.05 * ma10)",
    variants=[("20일 하락일 최대", "(close > lag(close, 1)) & (volume > lag(rmax(dvol, 20), 1)) & (close > ma50) & (close > ma10) & (close <= 1.05 * ma10)"),
              ("+ 52주 고가 -15% 이내", "(close > lag(close, 1)) & (volume > lag(rmax(dvol, 10), 1)) & (close > ma50) & (close > ma10) & (close <= 1.05 * ma10) & (fromhi >= -15)"),
              ("과열 조건 빼기", "(close > lag(close, 1)) & (volume > lag(rmax(dvol, 10), 1)) & (close > ma50) & (close > ma10)")],
    holds=[10, 20, 40], main=20, diff="Stockbee 4% 버스트·거래량 급증 돌파(기각)와 달리 가격폭 조건 없고 거래량 비교 대상이 '하락일 최대'")

add(key="bgu", name="Buyable Gap-Up (Kacher·Morales) ATR 0.75배 갭 상승 + 거래량 1.5배", family=["돌파", "이벤트"],
    src="powerofthepivot.wordpress.com · ThinkOrSwim BuyableGapUp study",
    mech="재료로 생긴 기관 수요의 갭은 메워지지 않고 이어진다(PEAD 류)",
    derive=D(["atr40"], vavg="lag(rmean(volume, 50), 1)"),
    cond="((open - pc) >= 0.75 * lag(atr40, 1)) & (volume >= 1.5 * vavg)",
    variants=[("갭 4%↑ & 거래량 1.75배", "(gap0 >= 4) & (volume >= 1.75 * vavg)"),
              ("+ 종가 상단 절반", "((open - pc) >= 0.75 * lag(atr40, 1)) & (volume >= 1.5 * vavg) & ((close - low) / (high - low + 1e-9) >= 0.5)"),
              ("+ 60일 고가 부근", "((open - pc) >= 0.75 * lag(atr40, 1)) & (volume >= 1.5 * vavg) & (close >= 0.95 * rmax(high, 60))")],
    holds=[10, 20, 40], main=20, diff="갭 하락 매수(기각)의 정반대 방향 · 거래량 동반 갭 상승")

add(key="smash", name="Larry Williams Smash Day(히든) 상승 마감인데 종가 하단 25% · 50일선 위 [근사]", family=["캔들", "눌림"],
    src="mql5 articles 21127·21391 · RoboForex 'Smash Day'",
    mech="감정의 극단을 가격이 곧바로 부정하면 반대로 간다 — 추세 방향 스매시만",
    derive=D(["pos", "ma50"]),
    cond="(close > lag(close, 1)) & (pos <= 0.25) & (close > ma50)",
    variants=[("네이키드: 종가<전일저가 & 50일선 위", "(close < lag(low, 1)) & (close > ma50) & ~((high > lag(high, 1)) & (low < lag(low, 1)))"),
              ("히든 엄격(종가<시가)", "(close > lag(close, 1)) & (pos <= 0.25) & (close < open) & (close > ma50)"),
              ("네이키드 3봉", "(close < lag(rmin(low, 3), 1)) & (close > ma50)")],
    holds=[5, 10, 20], main=5, diff="원전은 다음날 스매시봉 고가 돌파 매수 — 여기선 다음날 시가")

add(key="volbrk", name="Larry Williams 일봉 변동성 돌파 k=0.6 발생일 추종 [근사]", family=["돌파", "변동성"],
    src="mql5 20745 · WH SelfInvest 'Volatility break-out Larry Williams'",
    mech="레인지 확장은 방향성의 시작 — 원전은 장중 체결·다음날 시가 청산(재현 불가), 여기선 돌파일 다음날부터 추종",
    derive=D(["pc"], rg1="lag(high - low, 1)", ma20="rmean(close, 20)"),
    cond="(high >= open + 0.6 * rg1) & (close > ma20)",
    variants=[("k=0.5", "(high >= open + 0.5 * rg1) & (close > ma20)"), ("k=1.0", "(high >= open + 1.0 * rg1) & (close > ma20)"),
              ("종가도 돌파선 위", "(close >= open + 0.6 * rg1) & (close > ma20)")],
    holds=[5, 10, 20], main=5, diff="원전의 장중 체결 수익은 못 잰다 — 돌파 뒤 며칠의 지속만 본다")

add(key="td9", name="DeMark TD Sequential 매수 셋업 9 완성(퍼펙트)", family=["패턴", "낙폭반전"],
    src="demark.com · Perl 'DeMark Indicators' 발췌 · mql5 blog 742282",
    mech="9봉 연속 4일 전보다 낮은 종가 = 추세 소진",
    derive=D([], c4="close < lag(close, 4)", cnt="streak(c4)",
             perf="np.minimum(low, lag(low, 1)) <= np.minimum(lag(low, 2), lag(low, 3))"),
    cond="(cnt == 9) & perf",
    variants=[("퍼펙트 조건 없음", "cnt == 9"), ("13 연속(연장)", "cnt == 13"),
              ("9 + 200일선 위", "(cnt == 9) & perf & (close > rmean(close, 200))")],
    holds=[5, 10, 20], main=10, diff="연속 하락일(전일 대비·기각)과 달리 4일 전 대비 비교 + 저가 퍼펙트 조건")

add(key="force", name="Elder Force Index 2일 음수 눌림 + 65일 EMA 상승 + 임펄스 빨강 아님", family=["보조지표", "눌림"],
    src="StockCharts ChartSchool Force Index · Elder Impulse System",
    mech="상승 추세 안에서 거래량 실린 단기 매도 압력의 소진",
    derive=D([], fi="(close - lag(close, 1)) * volume", fi2="ema(fi, 2)", e65="ema(close, 65)", e13="ema(close, 13)",
             mh="(ema(close, 12) - ema(close, 26)) - ema(ema(close, 12) - ema(close, 26), 9)",
             red="(e13 < lag(e13, 1)) & (mh < lag(mh, 1))"),
    cond="(fi2 < 0) & (e65 > lag(e65, 1)) & ~red",
    variants=[("FI2 60일 최저", "(fi2 <= rmin(fi2, 60)) & (e65 > lag(e65, 1))"),
              ("빨강→첫 비빨강", "lag(red, 1) & ~red & (e65 > lag(e65, 1))"),
              ("임펄스 조건 빼기", "(fi2 < 0) & (e65 > lag(e65, 1))")],
    holds=[5, 10, 20], main=5, diff="이평 눌림(기각)과 달리 거래량×가격변화(Force) 음수 구간 + 임펄스")

add(key="lrsi", name="Ehlers Laguerre RSI(γ=0.5) 0.2 상향돌파", family=["보조지표", "낙폭반전"],
    src="Ehlers 'Cybernetic Analysis'(2004) · backtrader lrsi",
    mech="4단 라게르 필터로 지연 없이 부드러운 RSI — 과매도 탈출",
    derive=D([], l0="rma(close, 2)", l1="rma((lag(l0, 1) - 0.5 * l0) / 0.5, 2)",
             l2="rma((lag(l1, 1) - 0.5 * l1) / 0.5, 2)", l3="rma((lag(l2, 1) - 0.5 * l2) / 0.5, 2)",
             cu="np.maximum(l0 - l1, 0) + np.maximum(l1 - l2, 0) + np.maximum(l2 - l3, 0)",
             cd="np.maximum(l1 - l0, 0) + np.maximum(l2 - l1, 0) + np.maximum(l3 - l2, 0)",
             lr="cu / (cu + cd + 1e-12)",
             k0="rma(close, 3.3333)", k1="rma((lag(k0, 1) - 0.7 * k0) / 0.3, 3.3333)",
             k2="rma((lag(k1, 1) - 0.7 * k1) / 0.3, 3.3333)", k3="rma((lag(k2, 1) - 0.7 * k2) / 0.3, 3.3333)",
             kr="(np.maximum(k0 - k1, 0) + np.maximum(k1 - k2, 0) + np.maximum(k2 - k3, 0)) / (np.abs(k0 - k1) + np.abs(k1 - k2) + np.abs(k2 - k3) + 1e-12)"),
    cond="(lr > 0.2) & (lag(lr, 1) <= 0.2)",
    variants=[("γ=0.7 · 0.15 상향", "(kr > 0.15) & (lag(kr, 1) <= 0.15)"), ("0 에서 처음 벗어남", "(lr > 0.02) & (lag(lr, 1) <= 0.02)"),
              ("+ 200일선 위", "(lr > 0.2) & (lag(lr, 1) <= 0.2) & (close > rmean(close, 200))")],
    holds=[5, 10, 20], main=5, diff="RSI2(기각)와 필터 구조가 달라 신호일이 다르다")

add(key="fisher", name="Ehlers Fisher Transform(10) -1.5 아래에서 트리거 상향", family=["보조지표", "낙폭반전"],
    src="LuxAlgo 'Fisher Transform' · TradingView Ehlers Fisher backtest",
    mech="가격 분포를 가우시안화해 극단 전환점을 날카롭게",
    derive=D([], mid="(high + low) / 2", sn="(mid - rmin(mid, 10)) / (rmax(mid, 10) - rmin(mid, 10) + 1e-9)",
             v="np.clip(rma(2 * (sn - 0.5), 3.0303), -0.999, 0.999)", fz="rma(np.log((1 + v) / (1 - v)), 2)"),
    cond="(lag(fz, 1) < -1.5) & (fz > lag(fz, 1)) & (lag(fz, 1) <= lag(fz, 2))",
    variants=[("문턱 -2.0", "(lag(fz, 1) < -2.0) & (fz > lag(fz, 1)) & (lag(fz, 1) <= lag(fz, 2))"),
              ("문턱 -1.0", "(lag(fz, 1) < -1.0) & (fz > lag(fz, 1)) & (lag(fz, 1) <= lag(fz, 2))"),
              ("+ 200일선 위", "(lag(fz, 1) < -1.5) & (fz > lag(fz, 1)) & (lag(fz, 1) <= lag(fz, 2)) & (close > rmean(close, 200))")],
    holds=[5, 10, 20], main=5, diff="스토캐스틱·%R(기각)과 달리 피셔 변환 극단 + 방향 전환")

add(key="qband", name="Quantitativo '2.11 Sharpe' 10일 고점-2.5×평균폭 밴드 이탈 + IBS<0.3", family=["낙폭반전", "변동성"],
    src="quantitativo.com 'A mean reversion strategy with 2.11 Sharpe' + robustness 글",
    mech="최근 고점에서 평소 폭의 2.5배 이상 급락하고 그날도 저가권 마감",
    derive=D(["pos"], rr="rmean(high - low, 25)", band="rmax(high, 10) - 2.5 * rr"),
    cond="(close < band) & (pos < 0.3)",
    variants=[("배수 2.0", "(close < rmax(high, 10) - 2.0 * rr) & (pos < 0.3)"), ("배수 3.0", "(close < rmax(high, 10) - 3.0 * rr) & (pos < 0.3)"),
              ("IBS<0.2", "(close < band) & (pos < 0.2)")],
    holds=[5, 10, 20], main=5, diff="단순 IBS·25일선 이격(기각)과 달리 기준이 10일 고점, 폭은 변동성 정규화")

add(key="h3lr", name="Michael Harris 3L-R 저가 2연속 하락 뒤 4번째 봉 고가가 1번째 봉 고가 돌파", family=["패턴"],
    src="Harris 'Stock Trading Techniques Based on Price Patterns'(2000) · thepatternsite.com/3L-R.html",
    mech="Bulkowski 통계 상승장 평균 +9%·승률 57%",
    derive=D([]),
    cond="(lag(low, 3) > lag(low, 2)) & (lag(low, 2) > lag(low, 1)) & (high > lag(high, 3))",
    variants=[("+ 오늘 저가도 낮음(바깥 반전형)", "(lag(low, 3) > lag(low, 2)) & (lag(low, 2) > lag(low, 1)) & (high > lag(high, 3)) & (low < lag(low, 1))"),
              ("종가가 1번 봉 고가 위", "(lag(low, 3) > lag(low, 2)) & (lag(low, 2) > lag(low, 1)) & (close > lag(high, 3))"),
              ("+ 50일선 위", "(lag(low, 3) > lag(low, 2)) & (lag(low, 2) > lag(low, 1)) & (high > lag(high, 3)) & (close > rmean(close, 50))")],
    holds=[10, 20, 40], main=20, diff="Harris 가격패턴 — 캔들 한 봉이 아니라 4봉 구조")

add(key="gap2h", name="Michael Harris Gap-2H 갭 상승 뒤 고가 경신·되밀림 3봉 지속형", family=["패턴", "돌파"],
    src="thepatternsite.com/Gap2H.html (Harris 패턴·Bulkowski 통계 평균 +10%·72% 지속)",
    mech="갭 상승 뒤 쉬어가는 추세 지속형",
    derive=D([]),
    cond="(lag(low, 2) > lag(high, 3)) & (lag(high, 1) > lag(high, 2)) & (lag(low, 1) > lag(low, 2)) & (high > lag(high, 1)) & (low < lag(high, 1))",
    variants=[("+ 종가가 전일 고가 위", "(lag(low, 2) > lag(high, 3)) & (lag(high, 1) > lag(high, 2)) & (lag(low, 1) > lag(low, 2)) & (high > lag(high, 1)) & (low < lag(high, 1)) & (close > lag(high, 1))"),
              ("둘째 봉 조건 완화", "(lag(low, 2) > lag(high, 3)) & (lag(high, 1) > lag(high, 2)) & (high > lag(high, 1)) & (low < lag(high, 1))"),
              ("+ 거래량 평균 위", "(lag(low, 2) > lag(high, 3)) & (lag(high, 1) > lag(high, 2)) & (lag(low, 1) > lag(low, 2)) & (high > lag(high, 1)) & (low < lag(high, 1)) & (volume > rmean(volume, 20))")],
    holds=[10, 20, 40], main=20, diff="Harris 3봉 지속 패턴 — 박스·신고가 돌파(기각)와 다른 구조")

add(key="tko", name="Dave Landry Trend Knockout 강추세 중 2봉 저가 이탈 장대봉(WRB)", family=["눌림", "추세추종"],
    src="proactiveadvisormagazine 'Trend Knockout' · davelandry.com",
    mech="강추세 중 급락 한 방이 약한 손을 털어낸다",
    derive=D(["atr10"], hi20="rmax(high, 20)"),
    cond="(ret20 >= 10) & (rmax(high, 5) >= hi20) & (low < lag(low, 1)) & (low < lag(low, 2)) & (tr > 1.5 * lag(atr10, 1)) & (tr < 3 * lag(atr10, 1))",
    variants=[("추세 +15%", "(ret20 >= 15) & (rmax(high, 5) >= hi20) & (low < lag(low, 1)) & (low < lag(low, 2)) & (tr > 1.5 * lag(atr10, 1)) & (tr < 3 * lag(atr10, 1))"),
              ("WRB 1.2배", "(ret20 >= 10) & (rmax(high, 5) >= hi20) & (low < lag(low, 1)) & (low < lag(low, 2)) & (tr > 1.2 * lag(atr10, 1)) & (tr < 3 * lag(atr10, 1))"),
              ("극단 폭락 제외 없음", "(ret20 >= 10) & (rmax(high, 5) >= hi20) & (low < lag(low, 1)) & (low < lag(low, 2)) & (tr > 1.5 * lag(atr10, 1))")],
    holds=[5, 10, 20], main=5, diff="이평 눌림(기각)이 아니라 가격 구조(2봉 저가 이탈 + 장대봉)")

# ═════ 논문 이상현상 (매수 쪽) ═════
add(key="hvrp", name="고거래량 수익 프리미엄(Gervais 외 2001) 5일/250일 거래량 비 상위 10%", family=["거래량"],
    src="Gervais·Kaniel·Mingelgrin (2001, JF) · 한국은 저거래량 프리미엄(Chae·Kang 2019, PBFJ)",
    mech="가시성 상승 → 신규 수요(미국). 한국은 주의 매수 뒤 되돌림이라 반대 예상",
    derive=D([], vr="rmean(volume, 5) / (lag(rmean(volume, 250), 5) + 1)"),
    cond="xrank(vr) >= 0.9",
    variants=[("상위 5%", "xrank(vr) >= 0.95"), ("상위 20%", "xrank(vr) >= 0.8"), ("하위 10%(저거래량 프리미엄)", "xrank(vr) <= 0.1")],
    holds=[20, 40, 60], main=20, diff="거래량 급증 돌파 추격(기각)과 달리 가격 조건 없는 거래량 단면 순위")

add(key="liqshock", name="유동성 충격(Bali 외 2014) Amihud 비유동성 급개선 상위 10%", family=["유동성"],
    src="Bali·Peng·Shen·Tang (2014, RFS) · 한국 Jang (2022, AJFS)",
    mech="주의 부족으로 유동성 개선 정보가 천천히 반영(최대 6개월)",
    derive=D(["amt"], il="np.abs(close / lag(close, 1) - 1) / (amt + 1)", i21="rmean(il, 21)",
             i250="lag(rmean(il, 250), 21)", shock="-(i21 - i250) / (i250 + 1e-15)"),
    cond="xrank(shock) >= 0.9",
    variants=[("상위 5%", "xrank(shock) >= 0.95"), ("상위 20%", "xrank(shock) >= 0.8"),
              ("+ 21일 수익 양수 아님", "(xrank(shock) >= 0.9) & (ret20 <= 0)")],
    holds=[20, 40, 60], main=40, diff="거래량 절대 급증이 아니라 가격충격 비용(|수익|/거래대금)의 개선")

add(key="season", name="같은 달 계절성(Heston·Sadka 2008) 과거 5년 같은 시기 수익 상위 10%", family=["캘린더"],
    src="Heston·Sadka (2008, JFE) · Li·Zhang·Zheng (2018) 42개국",
    mech="실적발표·배당·리밸런싱 같은 반복 수요의 달력 패턴",
    derive=D([], s1="lag(close, 231) / lag(close, 252) - 1", s2="lag(close, 483) / lag(close, 504) - 1",
             s3="lag(close, 735) / lag(close, 756) - 1", s4="lag(close, 987) / lag(close, 1008) - 1",
             s5="lag(close, 1239) / lag(close, 1260) - 1", sm="(s1 + s2 + s3 + s4 + s5) / 5",
             sm3="(s1 + s2 + s3) / 3"),
    cond="xrank(sm) >= 0.9",
    variants=[("상위 5%", "xrank(sm) >= 0.95"), ("3년 평균 상위 10%", "xrank(sm3) >= 0.9"),
              ("5년 전부 양수", "(s1 > 0) & (s2 > 0) & (s3 > 0) & (s4 > 0) & (s5 > 0)")],
    holds=[20], main=20, diff="월말월초·휴일 전(기각)과 달리 종목별 같은 달 과거 수익")

add(key="mad", name="이동평균 거리 MAD(Avramov 외 2021) 21일/200일 이평 비 상위 10%", family=["추세추종", "이평"],
    src="Avramov·Kaplanski·Subrahmanyam (2021, RFE) 'Moving Average Distance'",
    mech="장기 이평에 앵커링한 과소반응 — 모멘텀·52주 신고가로 설명 안 된다고 주장",
    derive=D([], mad="rmean(close, 21) / rmean(close, 200)"),
    cond="xrank(mad) >= 0.9",
    variants=[("상위 5%", "xrank(mad) >= 0.95"), ("상위 20%", "xrank(mad) >= 0.8"),
              ("상위 10% & 20일 급등 아님", "(xrank(mad) >= 0.9) & (xrank(ret20) <= 0.8)")],
    holds=[20, 40, 60], main=20, diff="이평 돌파·정배열(기각)과 달리 단면 순위(상위 10%)로 쓴다")

add(key="co", name="연속 과잉반응 CO(Byun·Lim·Yun 2016) 부호×거래량 가중합 상위 10%", family=["거래량", "추세추종"],
    src="Byun·Lim·Yun (2016, JFQA) · 가격제한폭 시장 PBFJ 2017",
    mech="과신 투자자가 같은 방향으로 계속 사들여 더 밀어올린다",
    derive=D([], sv="np.sign(close - lag(close, 1)) * volume", co="ema(sv, 120) / (rmean(volume, 250) + 1)"),
    cond="xrank(co) >= 0.9",
    variants=[("상위 5%", "xrank(co) >= 0.95"), ("60일 가중", "xrank(ema(sv, 60) / (rmean(volume, 250) + 1)) >= 0.9"),
              ("상위 20%", "xrank(co) >= 0.8")],
    holds=[20, 40, 60], main=40, diff="가격 모멘텀(기각)이 아니라 부호 거래량 누적")

add(key="stmom", name="회전율 상위 10% 안 21일 수익 상위 10%(Medhat·Schmeling 2022 단기 모멘텀)", family=["거래량", "급등추격"],
    src="Medhat·Schmeling (2022, RFS) 'Short-term Momentum'",
    mech="거래 많은 쪽은 단기 모멘텀, 적은 쪽은 반전",
    derive=D(["amt"], to21="rmean(amt, 21) / (marcap + 1)"),
    cond="(xrank(to21) >= 0.9) & (xrank(ret20) >= 0.9)",
    variants=[("회전율 상위 20%", "(xrank(to21) >= 0.8) & (xrank(ret20) >= 0.9)"), ("수익 상위 20%", "(xrank(to21) >= 0.9) & (xrank(ret20) >= 0.8)"),
              ("반대칸: 저회전 & 하위 10% 수익(반전)", "(xrank(to21) <= 0.3) & (xrank(ret20) <= 0.1)")],
    holds=[5, 10, 20], main=20, diff="단순 1개월 반전·모멘텀(기각)과 달리 회전율 칸에 따라 방향이 다름")

add(key="stlowrev", name="저회전 30% 안 21일 수익 하위 10% 반전(Medhat·Schmeling 반대칸)", family=["낙폭반전", "거래량"],
    src="Medhat·Schmeling (2022, RFS) · Conrad·Hameed·Niden (1994, JF)",
    mech="거래 적은 급락은 유동성 공급 보상으로 되돌림",
    derive=D(["amt"], to21="rmean(amt, 21) / (marcap + 1)"),
    cond="(xrank(to21) <= 0.3) & (xrank(ret20) <= 0.1)",
    variants=[("저회전 20%", "(xrank(to21) <= 0.2) & (xrank(ret20) <= 0.1)"), ("수익 하위 5%", "(xrank(to21) <= 0.3) & (xrank(ret20) <= 0.05)"),
              ("저회전 40%", "(xrank(to21) <= 0.4) & (xrank(ret20) <= 0.1)")],
    holds=[5, 10, 20], main=20, diff="단순 1개월 반전(기각)과 달리 저회전 칸만")

add(key="indrev", name="업종조정 잔차 반전(Hameed·Mian 2015) 업종 대비 60일 수익 하위 10% & 업종은 안 무너짐", family=["낙폭반전", "업종"],
    src="Hameed·Mian (2015, JFQA) 'Industries and Stock Return Reversals' · Da·Liu·Schaumburg (2014)",
    mech="업종 요인을 빼면 비정보성 주문 불균형의 반전이 드러난다",
    derive=D([], rel="ret60 - u"),
    cond="(xrank(rel) <= 0.1) & (xrank(u) >= 0.3)",
    variants=[("하위 5%", "(xrank(rel) <= 0.05) & (xrank(u) >= 0.3)"), ("업종 조건 없음", "xrank(rel) <= 0.1"),
              ("업종 상위 절반", "(xrank(rel) <= 0.1) & (xrank(u) >= 0.5)")],
    holds=[5, 10, 20], main=20, diff="시장 대비 단순 반전(기각)과 달리 업종 대비 잔차 + 업종은 멀쩡한 경우")

add(key="tug", name="낮 되돌림 줄다리기(Akbas 외 2022) 21일 중 '밤 상승·낮에 더 큰 하락' 빈도 상위 10%", family=["캔들"],
    src="Akbas·Boehmer·Jiang·Koch (2022, JFE) · Lou·Polk·Skouras (2019) · 한국 Ham 외 (2023, FRL)",
    mech="밤 소음매수를 낮 차익거래자가 과잉교정 — 빈도가 높을수록 이후 수익 높다고 주장(한국은 부호 확인 필요)",
    derive=D([], on="open / lag(close, 1) - 1", idr="close / open - 1",
             nr="rsum(((on > 0) & (idr < -on)) * 1.0, 21)", pr="rsum(((on < 0) & (idr > -on)) * 1.0, 21)"),
    cond="xrank(nr) >= 0.9",
    variants=[("상위 20%", "xrank(nr) >= 0.8"), ("NR - PR 상위 10%", "xrank(nr - pr) >= 0.9"),
              ("하위 10%(반대 부호)", "xrank(nr) <= 0.1")],
    holds=[20, 40], main=20, diff="오버나잇 단순 수익(기각)이 아니라 밤·낮 충돌 빈도")

add(key="flowshock", name="거래량 5배 폭발일 + 기관 5일 순매수 강함(한국 HVRP 투자자별, arXiv 2512.14134)", family=["거래량", "수급"],
    src="arXiv 2512.14134 'Sources and Nonlinearity of HVRP — Investor Identity vs Trading Intensity' (한국 2020~24)",
    mech="이벤트일 기관·외인 순매수 강도가 셀수록 50일 초과 +12~13% (개인은 평평)",
    derive=D([]), cond="(su1 >= 5) & (q_org5 >= 10)",
    variants=[("외국인 5일 ≥10%", "(su1 >= 5) & (q_frgn5 >= 10)"), ("거래량 3배", "(su1 >= 3) & (q_org5 >= 10)"),
              ("기관+외인 모두 양수", "(su1 >= 5) & (q_org5 >= 5) & (q_frgn5 >= 5)")],
    holds=[20, 40, 60], main=40, mk="KR", features=["q_org5", "q_frgn5"],
    diff="[외인 매집](외인 60일 누적)과 달리 거래량 5배 이벤트일의 기관 순매수 강도")


# ═════ 중화권 (淘股吧·通达信 공식·大华/华安 보고서·대만 FinLab) ═════
BIG = {"KR": "r1 >= 15", "US": "(r1 >= 10) & (su1 >= 1.5)"}        # A주 상한가(+9.9%) 번역 — 국내 ±30% · 미장 무제한

add(key="xrzl", name="仙人指路 갭상승 긴 윗꼬리 준비일 → 이튿날 갭 안 메우고 상승 확인", family=["캔들", "돌파"],
    src="通达信 공식 공유(jiemiaobi.com/archives/24182 · chaogu1688.com/2803)",
    mech="긴 윗꼬리로 위 매물을 떠본 뒤 갭을 지키며 올라가면 주포 진입 — 저자 기본 승률 50%, 필터 후 90% 주장",
    derive=D(["ma10"], ma5="rmean(close, 5)", ma20="rmean(close, 20)", bt="np.maximum(close, open)", bb="np.minimum(close, open)",
             xz1="(low > lag(high, 1)) & (close / open >= 0.98) & (close / open <= 1.045) & (high / bt > 1.03) & (bb / low < 1.02) & (volume >= 1.1 * lag(volume, 1)) & (volume <= 4 * lag(volume, 1)) & (close > ma5) & (close > ma10) & (close > ma20) & (close >= rmax(close, 7))"),
    cond="lag(xz1, 1) & (open / lag(close, 1) > 0.98) & (low > lag(high, 2)) & (close > lag(bt, 1) * 1.01)",
    variants=[("준비일만(확인 없이)", "xz1"),
              ("갭 조건 없는 해석(a)", "((high - bt) >= 2 * np.abs(close - open)) & (volume >= 1.5 * rmean(volume, 5)) & (close <= 1.3 * rmin(low, 60)) & (close > ma20)"),
              ("확인일 갭 조건 완화", "lag(xz1, 1) & (low > lag(low, 1)) & (close > lag(bt, 1) * 1.01)")],
    holds=[5, 10, 20], main=20, diff="윗꼬리 매물 테스트 + 이튿날 확인 — 돌파 추격(기각)과 달리 갭 유지가 핵심")

add(key="ztsx", name="涨停双响炮 30일 안 두 번째 큰 장대양봉(국내 +15%·미장 +10%&거래량)", family=["급등추격", "패턴"],
    src="xiarj.com/19957 공식 · 知乎 p/638273066 (5일 승률 69.49% 주장)",
    mech="첫 상한가 뒤 조정을 버틴 종목의 두 번째 상한가 = 주포 재가동",
    derive=D(["pc", "r1"], big=None), cond="big & (rsum(big, 30) == 2) & (rsum(big, 6) == 1)",
    over={mk: {"derive_set": {"big": BIG[mk]}} for mk in BIG},
    variants=[("사이 조용함(5일 |등락|<9%)", "big & (rsum(big, 30) == 2) & (rsum(big, 6) == 1) & (lag(rmax(np.abs(r1), 5), 1) < 9)"),
              ("사이 저가가 첫 봉 저가 안 깸 근사", "big & (rsum(big, 30) == 2) & (rsum(big, 6) == 1) & (lag(rmin(low, 20), 1) >= lag(rmin(low, 30), 1))"),
              ("간격 3일↑", "big & (rsum(big, 30) == 2) & (rsum(big, 4) == 1)")],
    holds=[5, 10, 20], main=5, diff="신고가·급등 추격(기각)과 달리 30일 안 '두 번째' 장대양봉")

add(key="dfp", name="多方炮 양-음-양 세 봉(두 양봉이 음봉을 낀다) + 거래량 축소·재확대", family=["캔들"],
    src="blog.sina.com.cn/s/blog_1648b1ae60102x0ij · 知乎 p/629398151",
    mech="양봉-쉼-양봉 세 봉으로 매도세 소화 확인",
    derive=D([], br="np.abs(close - open) / (high - low + 1e-9)",
             p3="(lag(br, 2) > 0.5) & (lag(close, 2) > lag(open, 2)) & (lag(close, 1) < lag(open, 1)) & (lag(close, 1) < lag(close, 2)) & (br > 0.5) & (close > open) & (close > lag(close, 2)) & (close > lag(open, 1))"),
    cond="p3 & (lag(volume, 1) < lag(volume, 2)) & (volume > lag(volume, 1))",
    variants=[("거래량 조건 없음", "p3"), ("+ 30일선 위", "p3 & (lag(volume, 1) < lag(volume, 2)) & (volume > lag(volume, 1)) & (close > rmean(close, 30))"),
              ("+ 첫 양봉이 20일 신고가", "p3 & (lag(high, 2) >= lag(rmax(high, 20), 2))")],
    holds=[5, 10, 20], main=10, diff="캔들 한 봉(기각)이 아니라 세 봉 구조 + 거래량 순서")

add(key="cyzz", name="长阴短柱 -5% 이상 장대음봉인데 거래량은 전일의 절반 이하(저거래량 급락)", family=["낙폭반전", "거래량"],
    src="量学(유가오) 계열 · blog.sina.com.cn/s/blog_5734d4a50100sbpj",
    mech="거래량 없는 급락은 투매가 아니라 세력의 흔들기",
    derive=D(["pc", "r1"]), cond="(r1 <= -5) & (volume < lag(volume, 1) / 1.9)",
    variants=[("-7% & 10일 최대 거래량 60% 미만 & 10일 안 +15%(B)", "(r1 <= -7) & (volume < 0.6 * rmax(volume, 10)) & (lag(rmax(r1, 10), 1) >= 15)"),
              ("+ 60일선 위(역배열 제외)", "(r1 <= -5) & (volume < lag(volume, 1) / 1.9) & (close > rmean(close, 60))"),
              ("-4% & 거래량 0.6배", "(r1 <= -4) & (volume < 0.6 * lag(volume, 1))")],
    holds=[5, 10, 20], main=5, diff="하루 폭락 반등(기각)과 달리 '거래량이 줄어든' 급락만")

add(key="hjz", name="倍量柱→黄金柱 거래량 2배 양봉 뒤 3일 거래량 줄며 저가 지킴·상승", family=["거래량", "눌림"],
    src="동방재부 블로그 my_xclf · goodgupiao 9522 · 55188 topics-71915",
    mech="배량 양봉(장군주) 뒤 거래량 축소 조정이 그 저가를 지키면 매집 완료",
    derive=D([], bv="(volume >= 1.9 * lag(volume, 1)) & (close > open)"),
    cond="lag(bv, 3) & (rmax(volume, 3) < lag(volume, 3)) & (rmin(close, 3) > lag(low, 3)) & (close > lag(close, 1))",
    variants=[("3일 연속 거래량↓·종가↑(동남아판)", "lag(bv, 3) & (volume < lag(volume, 1)) & (lag(volume, 1) < lag(volume, 2)) & (lag(volume, 2) < lag(volume, 3)) & (close > lag(close, 1)) & (lag(close, 1) > lag(close, 2)) & (lag(close, 2) > lag(close, 3))"),
              ("배량 1.5배", "lag((volume >= 1.5 * lag(volume, 1)) & (close > open), 3) & (rmax(volume, 3) < lag(volume, 3)) & (rmin(close, 3) > lag(low, 3)) & (close > lag(close, 1))"),
              ("확인 2일", "lag(bv, 2) & (rmax(volume, 2) < lag(volume, 2)) & (rmin(close, 2) > lag(low, 2)) & (close > lag(close, 1))")],
    holds=[5, 10, 20], main=10, diff="거래량 급증 당일 추격(기각)과 달리 급증 뒤 거래량 축소 확인 후 진입")

add(key="yycsx", name="一阳穿三线 시가는 5·10·20일선 아래, 종가는 셋 다 위(+3% 양봉)", family=["이평", "캔들"],
    src="cnblogs ma-dongdong 17775209 · chaogu1688.com/186",
    mech="한 양봉이 세 이평을 한 번에 관통 = 추세 전환", derive=D(["ma10"], ma5="rmean(close, 5)", ma20="rmean(close, 20)", ma60="rmean(close, 60)"),
    cond="(open < np.minimum(np.minimum(ma5, ma10), ma20)) & (close > np.maximum(np.maximum(ma5, ma10), ma20)) & (close / open > 1.03)",
    variants=[("+ 20>60 정배열·+5%", "(open < np.minimum(np.minimum(ma5, ma10), ma20)) & (close > np.maximum(np.maximum(ma5, ma10), ma20)) & (close / open > 1.05) & (ma20 > ma60)"),
              ("네 선(60일 포함)", "(open < np.minimum(np.minimum(ma5, ma10), np.minimum(ma20, ma60))) & (close > np.maximum(np.maximum(ma5, ma10), np.maximum(ma20, ma60))) & (close / open > 1.03)"),
              ("양봉 폭 조건 없음", "(open < np.minimum(np.minimum(ma5, ma10), ma20)) & (close > np.maximum(np.maximum(ma5, ma10), ma20))")],
    holds=[5, 10, 20], main=10, diff="이평 하나 돌파·골든크로스(기각)와 달리 한 봉이 세 선을 동시 관통")

add(key="jxnh", name="均线粘合向上发散 5·10·20·30일선 1% 안 수렴 뒤 +3% 양봉·거래량 증가·정배열", family=["이평", "변동성"],
    src="cnblogs ma-dongdong 17775189",
    mech="이평 수렴(변동성 수축) 뒤 위로 발산",
    derive=D(["ma10"], ma5="rmean(close, 5)", ma20="rmean(close, 20)", ma30="rmean(close, 30)", ma120="rmean(close, 120)",
             cv="np.maximum(np.maximum(ma5, ma10), np.maximum(ma20, ma30)) / np.minimum(np.minimum(ma5, ma10), np.minimum(ma20, ma30)) - 1"),
    cond="(rmin(cv, 10) < 0.01) & (close > ma120) & (close / lag(close, 1) > 1.03) & (volume > rmean(volume, 5)) & (ma5 > ma10) & (ma10 > ma20) & (ma5 > lag(ma5, 1))",
    variants=[("수렴 1.5%", "(rmin(cv, 10) < 0.015) & (close > ma120) & (close / lag(close, 1) > 1.03) & (volume > rmean(volume, 5)) & (ma5 > ma10) & (ma10 > ma20) & (ma5 > lag(ma5, 1))"),
              ("수렴 3%", "(rmin(cv, 10) < 0.03) & (close > ma120) & (close / lag(close, 1) > 1.03) & (volume > rmean(volume, 5)) & (ma5 > ma10) & (ma10 > ma20) & (ma5 > lag(ma5, 1))"),
              ("+ 20일 고가 돌파", "(rmin(cv, 10) < 0.01) & (close > ma120) & (close / lag(close, 1) > 1.03) & (volume > rmean(volume, 5)) & (ma5 > ma10) & (ma10 > ma20) & (close > lag(rmax(high, 20), 1))")],
    holds=[5, 10, 20], main=10, diff="이평 스퀴즈(기각 H0031, 넓을수록 좋았음)와 같은 축 — 네 선 1% 수렴 + 발산 양봉으로 더 좁힘")

add(key="ysg", name="银山谷 10일 안 5×10·5×20·10×20 골든크로스 순서 완성(삼각형)", family=["이평"],
    src="cnblogs doseoer 18758622 · sohu 454706237",
    mech="단기 이평 세 쌍의 교차가 순서대로 → 삼각형 계곡 완성",
    derive=D(["ma10"], ma5="rmean(close, 5)", ma20="rmean(close, 20)", ma60="rmean(close, 60)",
             x510="(ma5 > ma10) & (lag(ma5, 1) <= lag(ma10, 1))", x520="(ma5 > ma20) & (lag(ma5, 1) <= lag(ma20, 1))",
             x1020="(ma10 > ma20) & (lag(ma10, 1) <= lag(ma20, 1))"),
    cond="x1020 & (rsum(x510, 10) >= 1) & (rsum(x520, 10) >= 1)",
    variants=[("은계곡(60일선 아래)", "x1020 & (rsum(x510, 10) >= 1) & (rsum(x520, 10) >= 1) & (ma20 < ma60)"),
              ("금계곡(60일선 위)", "x1020 & (rsum(x510, 10) >= 1) & (rsum(x520, 10) >= 1) & (ma20 > ma60)"),
              ("+ 20일선 상승", "x1020 & (rsum(x510, 10) >= 1) & (rsum(x520, 10) >= 1) & (ma20 > lag(ma20, 3))")],
    holds=[5, 10, 20], main=10, diff="50/60/200 교차(기각)와 달리 단기 이평 세 쌍의 교차 순서")

add(key="rcx", name="揉搓线 윗꼬리 봉 → 아래꼬리 봉(작은 몸통 두 개) · 20>60 추세 안", family=["캔들"],
    src="chaogu1688.com/14346 · 9fzt.com",
    mech="위아래로 흔들어 매물을 주무름 — 추세 안에서 드물지만 신뢰도 높다고 주장",
    derive=D(["pc"], bt="np.maximum(close, open)", bb="np.minimum(close, open)", body="np.abs(close - open)",
             us="(high - bt) >= 2 * body", ls="(bb - low) >= 2 * body", sm="body / pc < 0.02",
             ma20="rmean(close, 20)", ma60="rmean(close, 60)"),
    cond="lag(us & sm & ((bb - low) < (high - bt)), 1) & ls & sm & ((high - bt) < (bb - low)) & (ma20 > ma60) & (close > ma20)",
    variants=[("꼬리 1.5배", "lag(((high - bt) >= 1.5 * body) & sm, 1) & ((bb - low) >= 1.5 * body) & sm & (ma20 > ma60) & (close > ma20)"),
              ("꼬리 3배", "lag(((high - bt) >= 3 * body) & sm, 1) & ((bb - low) >= 3 * body) & sm & (ma20 > ma60) & (close > ma20)"),
              ("추세 조건 없음", "lag(us & sm & ((bb - low) < (high - bt)), 1) & ls & sm & ((high - bt) < (bb - low))")],
    holds=[5, 10, 20], main=5, diff="캔들 한 봉(기각)이 아니라 윗꼬리→아래꼬리 두 봉 순서")

add(key="myss", name="蚂蚁上树 이평 13·34·55 수렴 바닥권에서 5연속 소양봉 뒤 55일선 돌파", family=["이평", "캔들"],
    src="baike.baidu.com 蚂蚁上树 · 网易 기사",
    mech="바닥권에서 개미처럼 조금씩 오르는 연속 소양봉 = 조용한 매집",
    derive=D(["pc", "r1"], m13="rmean(close, 13)", m34="rmean(close, 34)", m55="rmean(close, 55)",
             cv="np.maximum(np.maximum(m13, m34), m55) / np.minimum(np.minimum(m13, m34), m55) - 1",
             sy="(r1 > 0) & (r1 < 3) & (close > open)"),
    cond="(rsum(sy, 5) >= 5) & (close >= m55) & (lag(cv, 5) < 0.03)",
    variants=[("수렴 5%", "(rsum(sy, 5) >= 5) & (close >= m55) & (lag(cv, 5) < 0.05)"), ("4연속", "(rsum(sy, 4) >= 4) & (close >= m55) & (lag(cv, 4) < 0.03)"),
              ("+ 거래량 점증", "(rsum(sy, 5) >= 5) & (close >= m55) & (lag(cv, 5) < 0.03) & (rmean(volume, 5) > lag(rmean(volume, 5), 5))")],
    holds=[10, 20, 40], main=20, diff="[조용한 신고가]류 잔잔함 축과 비슷하나 바닥권 이평 수렴 + 연속 소양봉")

add(key="yjfb", name="阴极反包 -2% 넘게 빠진 다음날 첫 장대양봉(국내 +15%·미장 +10%&거래량) 고가 마감", family=["낙폭반전", "급등추격"],
    src="gushichanghong.com/page/2646 (전체 코드)",
    mech="급락 직후 첫 상한가 반전 — 돌파·거래량 조건 없이 '급락 직후'가 핵심",
    derive=D(["pc", "r1"], big=None), cond="big & (close >= 0.99 * high) & ((close - open) / pc > 0.01) & (lag(r1, 1) < -2) & (lag(rsum(big, 30), 1) == 0)",
    over={mk: {"derive_set": {"big": BIG[mk]}} for mk in BIG},
    variants=[("고가 마감 조건 없음", "big & (lag(r1, 1) < -2) & (lag(rsum(big, 30), 1) == 0)"),
              ("전날 -5%", "big & (close >= 0.99 * high) & (lag(r1, 1) < -5) & (lag(rsum(big, 30), 1) == 0)"),
              ("30일 안 한 번 허용", "big & (close >= 0.99 * high) & (lag(r1, 1) < -2) & (lag(rsum(big, 30), 1) <= 1)")],
    holds=[5, 10, 20], main=5, diff="급등 추격(기각)과 달리 '전날 급락' 직후 첫 장대양봉")

add(key="sbsl", name="首板缩量回调 첫 장대양봉 다음날 거래량 줄며 -5~+3% 조정 → 그 다음날 시가 매수", family=["눌림", "거래량"],
    src="华安证券 금융공학 보고서(2026-03, 표본 안 1,089건 연 18.2%·표본 밖 20.7%) · sina 2026-03-20",
    mech="첫 상한가 뒤 거래량 줄인 조정은 매물 소화 — 거래량비 0.3배 미만 평균 +7.44%",
    derive=D(["pc", "r1", "pos"], big=None), cond="lag(big, 1) & (lag(rsum(big, 20), 2) == 0) & (lag(high, 1) > lag(low, 1)) & (r1 >= -5) & (r1 <= 3) & (pos < 0.8) & (volume < lag(volume, 1))",
    over={mk: {"derive_set": {"big": BIG[mk]}} for mk in BIG},
    variants=[("거래량비 0.5배 미만", "lag(big, 1) & (lag(rsum(big, 20), 2) == 0) & (r1 >= -5) & (r1 <= 3) & (pos < 0.8) & (volume < 0.5 * lag(volume, 1))"),
              ("종가 위치 조건 없음", "lag(big, 1) & (lag(rsum(big, 20), 2) == 0) & (r1 >= -5) & (r1 <= 3) & (volume < lag(volume, 1))"),
              ("거래량 조건 없음", "lag(big, 1) & (lag(rsum(big, 20), 2) == 0) & (r1 >= -5) & (r1 <= 3) & (pos < 0.8)")],
    holds=[5, 10], main=5, diff="首阴(첫 음봉·기각)과 인접하나 '거래량 축소'와 '종가 위치 80% 미만' 조건 — 보고서 표본 밖 검증 있음")

add(key="tuyang", name="土洋對作 투신 20일 순매수 + 외국인 20일 순매도(대만 FinLab)", family=["수급"],
    src="finlab.finance/blog/institutional-strategy (대만 2015~26: 20일 중앙 +0.46%·승률 52%, 동조매수보다 나음)",
    mech="외국인이 파는 걸 국내 기관(투신)이 받는 종목 — 외국인 동조 매수는 오히려 최악",
    derive=D([]), cond="(q_tru20 > 0) & (q_frgn20 < 0)",
    variants=[("5일판", "(q_tru5 > 0) & (q_frgn5 < 0)"), ("투신 강하게(≥5%)", "(q_tru20 >= 5) & (q_frgn20 < 0)"),
              ("기관 합계판", "(q_org20 > 0) & (q_frgn20 < 0)")],
    holds=[20, 40, 60], main=20, mk="KR", features=["q_tru20", "q_frgn20", "q_tru5", "q_frgn5", "q_org20"],
    diff="외인·기관 동조 순매수(기각)와 반대 — 두 주체가 엇갈리는 조합")

add(key="fsell", name="外資大賣 역발상 외국인 5일 순매도가 거래대금의 20% 넘음(대만 FinLab)", family=["외인", "낙폭반전"],
    src="finlab.finance/blog/institutional-strategy (86만 건, 매도 강도 셀수록 20일 성과 단조 개선)",
    mech="외국인 대량 투매는 과잉 — 20일 뒤 되돌림",
    derive=D([]), cond="q_frgn5 <= -20",
    variants=[("-10% 이하", "q_frgn5 <= -10"), ("-30% 이하", "q_frgn5 <= -30"), ("사흘 늦춰 진입", "lag(q_frgn5 <= -20, 3)")],
    holds=[20, 40, 60], main=20, mk="KR", features=["q_frgn5"],
    diff="외인 순매수 추종([외인 매집])과 반대 방향 — 외국인 대량 매도를 산다")

# ═════ 유럽·남미 (브라질 스토르메르·팔렉스·QuantBrasil, 프랑스 일목, 러시아 smart-lab) ═════
add(key="s91", name="셋업 9.1(브라질판 래리 윌리엄스) EMA9 하락→상승 전환", family=["이평", "눌림"],
    src="atpalex.blogspot.com 2014/08 setup-91 · scannerdabolsa · 브라질 논문 revistagt 2496(승률 67% 주장)",
    mech="EMA9 기울기 반전 = 짧은 조정 끝",
    derive=D([], e9="ema(close, 9)", e8="ema(close, 8)", e80="ema(close, 80)", ma200="rmean(close, 200)"),
    cond="(e9 > lag(e9, 1)) & (lag(e9, 1) <= lag(e9, 2))",
    variants=[("+ 200일선 위", "(e9 > lag(e9, 1)) & (lag(e9, 1) <= lag(e9, 2)) & (close > ma200)"),
              ("+ 에덴 필터(EMA8·80 상승)", "(e9 > lag(e9, 1)) & (lag(e9, 1) <= lag(e9, 2)) & (e8 > lag(e8, 1)) & (e80 > lag(e80, 1))"),
              ("+ 3일 이상 하락 뒤", "(e9 > lag(e9, 1)) & (rsum(lag(e9, 1) < lag(e9, 2), 3) >= 3)")],
    holds=[5, 10, 20], main=10, diff="원전은 신호봉 고가 돌파 체결·EMA9 하락 전환 청산 — 여기선 다음날 시가·고정 보유")

add(key="s92", name="셋업 9.2 EMA9 상승 중 종가가 전일 저가 아래(얕은 눌림)", family=["눌림"],
    src="scannerdabolsa setup-9-2 · flj.com.br 9.2·9.3",
    mech="EMA9 기울기가 유지되는 1봉짜리 조정",
    derive=D([], e9="ema(close, 9)", e8="ema(close, 8)", e80="ema(close, 80)"),
    cond="(e9 > lag(e9, 1)) & (close < lag(low, 1))",
    variants=[("9.4 EMA9 하루 꺾였다 바로 복귀", "(lag(e9, 1) < lag(e9, 2)) & (lag(e9, 2) > lag(e9, 3)) & (e9 > lag(e9, 1)) & (low >= lag(low, 1))"),
              ("+ 에덴", "(e9 > lag(e9, 1)) & (close < lag(low, 1)) & (e8 > lag(e8, 1)) & (e80 > lag(e80, 1))"),
              ("+ 200일선 위", "(e9 > lag(e9, 1)) & (close < lag(low, 1)) & (close > rmean(close, 200))")],
    holds=[5, 10, 20], main=5, diff="50/60/200 이평 눌림(기각)과 달리 EMA9 기울기 유지 + 1봉 조정")

add(key="ifr2m", name="수정 IFR2(브라질 alsant0z) RSI2<5 & EMA99 위 → 추세 끝날 때까지 길게", family=["보조지표", "낙폭반전"],
    src="alsant0z.blogspot.com 2010/01 'setup do IFR2 modificado' (185회·승률 67.5%·건당 +6.03% 주장)",
    mech="과매도로 들어가 추세추종으로 나간다 — Connors RSI2 와 청산이 다르다",
    derive=D([], dup="np.maximum(close - lag(close, 1), 0)", ddn="np.maximum(lag(close, 1) - close, 0)",
             rsi2="100 * rma(dup, 2) / (rma(dup, 2) + rma(ddn, 2) + 1e-12)", e99="ema(close, 99)"),
    cond="(rsi2 < 5) & (close > e99)",
    variants=[("RSI2<10", "(rsi2 < 10) & (close > e99)"), ("RSI2≤25(브라질 주류)", "(rsi2 <= 25) & (close > e99)"),
              ("RSI2<5 & 200일선", "(rsi2 < 5) & (close > rmean(close, 200))")],
    holds=[20, 40, 60], main=40, diff="Connors RSI2(기각)는 짧게 청산 — 이건 20~60일 길게 가져가는 판")

add(key="b123", name="123 매수 + 에덴 필터(스토르메르) 가운데 봉 저가가 최저인 3봉 · EMA8·80 상승", family=["패턴", "눌림"],
    src="quantbrasil.com.br '123 de compra' 백테스트(BBDC4 48회 승률 54%, 인사이드바판 12회 67%)",
    mech="짧은 V자 저점 + 두 이평 상승",
    derive=D(["ins"], e8="ema(close, 8)", e80="ema(close, 80)", eden="(e8 > lag(e8, 1)) & (e80 > lag(e80, 1))"),
    cond="(lag(low, 1) < lag(low, 2)) & (lag(low, 1) < low) & eden",
    variants=[("셋째 봉 인사이드", "(lag(low, 1) < lag(low, 2)) & (lag(low, 1) < low) & eden & ins"),
              ("에덴 없이", "(lag(low, 1) < lag(low, 2)) & (lag(low, 1) < low)"), ("+ 셋째 봉 양봉", "(lag(low, 1) < lag(low, 2)) & (lag(low, 1) < low) & eden & (close > open)")],
    holds=[5, 10, 20], main=5, diff="원전은 셋째 봉 고가 돌파 체결 — 여기선 다음날 시가")

add(key="pfr", name="PFR 종가 반전(스토르메르) 2봉 신저가인데 종가는 전일보다 높음", family=["캔들", "낙폭반전"],
    src="quantbrasil.com.br 'Preço de Fechamento de Reversão'",
    mech="신저가를 찍고도 종가는 전일 위 — 한 봉짜리 반전",
    derive=D([], e8="ema(close, 8)", e80="ema(close, 80)"),
    cond="(low < lag(low, 1)) & (low < lag(low, 2)) & (close > lag(close, 1))",
    variants=[("+ 양봉", "(low < lag(low, 1)) & (low < lag(low, 2)) & (close > lag(close, 1)) & (close > open)"),
              ("+ 에덴", "(low < lag(low, 1)) & (low < lag(low, 2)) & (close > lag(close, 1)) & (e8 > lag(e8, 1)) & (e80 > lag(e80, 1))"),
              ("5봉 신저가", "(low < lag(rmin(low, 5), 1)) & (close > lag(close, 1))")],
    holds=[5, 10, 20], main=5, diff="전일 고저 이탈 후 재진입(기각)과 달리 신저가 + 종가 전일 초과를 한 봉 안에서")

add(key="trap", name="이동평균 함정(Trap na Média) 저가가 EMA21 위였던 5봉 뒤 처음 선을 건드린 봉", family=["눌림", "이평"],
    src="quantbrasil.com.br 'Trap na Média de Compra' · 'Trap no Candle'",
    mech="처음으로 선을 건드린 봉 + 즉시 되돌림만",
    derive=D([], e21="ema(close, 21)", s20="rmean(close, 20)", e9="ema(close, 9)"),
    cond="(lag(rmin(low - e21, 5), 1) > 0) & (low < e21) & (close > e21)",
    variants=[("SMA20·10봉", "(lag(rmin(low - s20, 10), 1) > 0) & (low < s20) & (close > s20)"),
              ("EMA9·3봉", "(lag(rmin(low - e9, 3), 1) > 0) & (low < e9) & (close > e9)"),
              ("종가 조건 없음", "(lag(rmin(low - e21, 5), 1) > 0) & (low < e21)")],
    holds=[5, 10, 20], main=5, diff="단순 이평 눌림(기각)과 달리 'N봉 만에 처음' 건드린 봉만")

add(key="tm3", name="세 이동평균(브라질판 윌리엄스 3-bar) 종가 < 저가 SMA3 & SMA30 상승", family=["낙폭반전", "이평"],
    src="quantbrasil.com.br 'Três Médias' · 'Máximas e Mínimas'(EQTL3 204회 승률 79%·평균 3.2일)",
    mech="고저 3일 채널 하단 이탈 평균회귀 — 추세 안에서만",
    derive=D([], ml3="rmean(low, 3)", s30="rmean(close, 30)", s21="rmean(close, 21)"),
    cond="(close < ml3) & (s30 > lag(s30, 1))",
    variants=[("SMA21 상승", "(close < ml3) & (s21 > lag(s21, 1))"), ("2일 최저가 이탈", "(low < lag(rmin(low, 2), 1)) & (s30 > lag(s30, 1))"),
              ("종가 < 저가 SMA3 × 0.99", "(close < 0.99 * ml3) & (s30 > lag(s30, 1))")],
    holds=[5, 10], main=5, diff="IBS(기각)와 달리 기준이 고가·저가 3일 평균 채널")

add(key="didi", name="디디 바늘(Agulhada do Didi) SMA3·8·20이 한 봉 몸통을 동시에 통과한 뒤 3>8>20 정렬", family=["이평", "변동성"],
    src="nelogica 'Didi Index' · tradergrafico blog id=22",
    mech="세 선이 한 봉에 수렴(수축) 후 방향 결정",
    derive=D(["adx"], m3="rmean(close, 3)", m8="rmean(close, 8)", m20="rmean(close, 20)", bt="np.maximum(close, open)", bb="np.minimum(close, open)",
             nd="(m3 >= bb) & (m3 <= bt) & (m8 >= bb) & (m8 <= bt) & (m20 >= bb) & (m20 <= bt)",
             al="(m3 > m8) & (m8 > m20)", bup="rmean(close, 20) + 2 * rstd(close, 20)"),
    cond="(rsum(nd, 3) >= 1) & al & ~lag(al, 1)",
    variants=[("+ ADX 상승 & >20", "(rsum(nd, 3) >= 1) & al & ~lag(al, 1) & (adx > 20) & (adx > lag(adx, 1))"),
              ("+ 볼린저 상단 돌파", "(rsum(nd, 3) >= 1) & al & ~lag(al, 1) & (close > bup)"),
              ("바늘 5봉 안", "(rsum(nd, 5) >= 1) & al & ~lag(al, 1)")],
    holds=[5, 10, 20], main=10, diff="단순 이평 교차(기각)와 달리 세 선이 한 봉 몸통에 수렴한 뒤의 정렬")

add(key="pavio", name="심지 캔들(Candle Pavio) 도지 다음날 +1% 갭상승 [근사]", family=["캔들", "변동성"],
    src="quantbrasil.com.br 'Candle Pavio de Compra'",
    mech="수축봉(도지) 뒤 갭 = 방향 결정 — 원전은 당일 시가 매수·종가 매도(재현 불가)",
    derive=D([], doji="np.abs(close - open) <= 0.2 * (high - low)"),
    cond="lag(doji, 1) & (gap0 >= 1)",
    variants=[("갭 2%", "lag(doji, 1) & (gap0 >= 2)"), ("갭 3%", "lag(doji, 1) & (gap0 >= 3)"), ("+ 갭 유지(종가>시가)", "lag(doji, 1) & (gap0 >= 1) & (close > open)")],
    holds=[5, 10, 20], main=5, diff="갭 하락 매수(기각)와 반대 방향 · 도지 전제")

add(key="bbx", name="볼린저 밴드 확장(브라질) 종가가 상단(20,2) 밖으로 처음 나감", family=["변동성", "돌파"],
    src="quantbrasil.com.br 'Abertura das Bandas de Bollinger'",
    mech="표준편차 밖으로 처음 나간 날 = 변동성 확장의 시작",
    derive=D([], mb="rmean(close, 20)", sb="rstd(close, 20)",
             dup="np.maximum(close - lag(close, 1), 0)", ddn="np.maximum(lag(close, 1) - close, 0)",
             rsi14="100 * rma(dup, 14) / (rma(dup, 14) + rma(ddn, 14) + 1e-12)"),
    cond="(close > mb + 2 * sb) & (lag(close, 1) <= lag(mb + 2 * sb, 1))",
    variants=[("1.5σ", "(close > mb + 1.5 * sb) & (lag(close, 1) <= lag(mb + 1.5 * sb, 1))"),
              ("+ RSI14 ≤ 70(초기만)", "(close > mb + 2 * sb) & (lag(close, 1) <= lag(mb + 2 * sb, 1)) & (rsi14 <= 70)"),
              ("2.5σ", "(close > mb + 2.5 * sb) & (lag(close, 1) <= lag(mb + 2.5 * sb, 1))")],
    holds=[5, 10, 20], main=10, diff="박스·신고가 돌파(기각)와 달리 표준편차 기준 — 겹침 확인 필요")

add(key="corsem", name="주간 조정 매수(브라질 Trader Rodrigo) 상대강도 상위 11% 종목이 고점 대비 -14~-28% 조정 중 양봉", family=["눌림", "추세추종"],
    src="traderrodrigo.com.br estrategias-setup-entradas (보베스파 자동 백테스트로 정했다고 주장)",
    mech="강한 종목의 1~7주 조정 끝",
    derive=D([], rs="xrank(ret120)", dd35="(close / rmax(high, 35) - 1) * 100"),
    cond="(rs >= 0.89) & (dd35 <= -14) & (dd35 >= -28) & (close > open)",
    variants=[("1년 강도", "(xrank(ret250) >= 0.89) & (dd35 <= -14) & (dd35 >= -28) & (close > open)"),
              ("조정 -10~-20%", "(rs >= 0.89) & (dd35 <= -10) & (dd35 >= -20) & (close > open)"),
              ("강도 상위 20%", "(rs >= 0.8) & (dd35 <= -14) & (dd35 >= -28) & (close > open)")],
    holds=[10, 20, 40], main=20, diff="Minervini·RS 추격(기각, RS≥70 역방향)과 달리 강한 종목의 '조정 중' 매수")

add(key="ichi", name="일목 5조건 동시 충족 첫날(프랑스 카렌 펠루아유 체크리스트)", family=["보조지표", "추세추종"],
    src="captain-trading.com 2023/03 ichimoku-formation · ichimoku-kinko-hyo.info (Karen Péloille)",
    mech="기준선·전환선·후행스팬·구름·미래 구름 다섯 조건 동시 충족 = 추세 확인",
    derive=D([], tk9="(rmax(high, 9) + rmin(low, 9)) / 2", kj26="(rmax(high, 26) + rmin(low, 26)) / 2",
             sa="(tk9 + kj26) / 2", sbb="(rmax(high, 52) + rmin(low, 52)) / 2",
             ok5="(close > kj26) & (tk9 > kj26) & (close > lag(close, 26)) & (close > lag(rmax(high, 5), 22)) & (close > np.maximum(lag(sa, 26), lag(sbb, 26))) & (sa > sbb)"),
    cond="ok5 & ~lag(ok5, 1)",
    variants=[("후행스팬 장애물 3봉", "(close > kj26) & (tk9 > kj26) & (close > lag(close, 26)) & (close > lag(rmax(high, 3), 24)) & (close > np.maximum(lag(sa, 26), lag(sbb, 26))) & (sa > sbb) & ~lag(ok5, 1)"),
              ("미래 구름 조건 빼기", "(close > kj26) & (tk9 > kj26) & (close > lag(close, 26)) & (close > np.maximum(lag(sa, 26), lag(sbb, 26))) & ~lag(ok5, 1)"),
              ("충족 상태면 매일", "ok5")],
    holds=[10, 20, 40], main=20, diff="이평 교차(기각)와 달리 일목 다섯 조건의 동시 충족")

add(key="sushi", name="수시 롤(Mark Fisher) 최근 5봉이 앞 5봉을 감싸고 상승 마감", family=["패턴", "낙폭반전"],
    src="smart-lab.ru/blog/15717 (Mark Fisher 'Logical Trader' 주간 외바 반전)",
    mech="앞 5일 범위를 위아래로 다 넘고 위에서 끝남 = 반전",
    derive=D([], h5="rmax(high, 5)", l5="rmin(low, 5)"),
    cond="(h5 > lag(h5, 5)) & (l5 < lag(l5, 5)) & (close > lag(close, 5))",
    variants=[("+ 종가가 앞 5봉 고가 위", "(h5 > lag(h5, 5)) & (l5 < lag(l5, 5)) & (close > lag(h5, 5))"),
              ("주간판 금요일만 근사(5일마다) 대신 3봉", "(rmax(high, 3) > lag(rmax(high, 3), 3)) & (rmin(low, 3) < lag(rmin(low, 3), 3)) & (close > lag(close, 3))"),
              ("+ 20일 하락 뒤", "(h5 > lag(h5, 5)) & (l5 < lag(l5, 5)) & (close > lag(close, 5)) & (ret20 < 0)")],
    holds=[10, 20, 40], main=20, diff="바깥봉 한 개(기각 계열)가 아니라 5봉 묶음 외바")

# ═════ 인도·동남아·태국 ═════
add(key="openlow", name="Open=Low BTST(인도 TradingQnA) 시가가 저가 · 양봉 [근사]", family=["캔들"],
    src="tradingqna.com/t/btst-buy-today-sell-tomorrow 43659 (2007~18 하루 28건 적중 50%·손익비 1.3 주장)",
    mech="장중 시가 아래로 한 번도 안 내려감 = 매수 우위 — 원전은 당일 종가 매수·다음날 매도(재현 불가)",
    derive=D([]), cond="(low >= open * 0.999) & (close > open)",
    variants=[("+ 200일선 위", "(low >= open * 0.999) & (close > open) & (close > rmean(close, 200))"),
              ("+ 52주 고가 -10% 이내", "(low >= open * 0.999) & (close > open) & (fromhi >= -10)"), ("양봉 조건 없음", "low >= open * 0.999")],
    holds=[5, 10, 20], main=5, diff="원전의 하룻밤 수익은 못 잰다 — 이후 며칠 지속만")

add(key="rsi60", name="RSI 60-40 범위 이동(인도 Bharat Jhunjhunwala) 일봉 RSI14 60 상향돌파 + 고가 EMA20 위 양봉", family=["보조지표", "추세추종"],
    src="prorsi.com 스윙 PDF · chartink 'rsi-swing-trading-by-bharat-jhunjhunwala'",
    mech="상승장에서 RSI 는 40~80 을 오간다 — 60 돌파는 추세 확인",
    derive=D([], dup="np.maximum(close - lag(close, 1), 0)", ddn="np.maximum(lag(close, 1) - close, 0)",
             rsi14="100 * rma(dup, 14) / (rma(dup, 14) + rma(ddn, 14) + 1e-12)",
             rsiw="100 * rma(np.maximum(close - lag(close, 5), 0), 70) / (rma(np.maximum(close - lag(close, 5), 0), 70) + rma(np.maximum(lag(close, 5) - close, 0), 70) + 1e-12)",
             eh20="ema(high, 20)"),
    cond="(rsi14 >= 60) & (lag(rsi14, 1) < 60) & (close > eh20) & (close > open)",
    variants=[("+ 주봉 RSI>55 근사", "(rsi14 >= 60) & (lag(rsi14, 1) < 60) & (close > eh20) & (close > open) & (rsiw > 55)"),
              ("60 이상 상태(돌파 아님)", "(rsi14 >= 60) & (rsi14 < 70) & (close > eh20) & (close > open)"),
              ("EMA 조건 없이", "(rsi14 >= 60) & (lag(rsi14, 1) < 60) & (close > open)")],
    holds=[5, 10, 20], main=10, diff="RSI 과매도(기각)와 반대 — 60 상향을 추세 신호로")

add(key="ema5alert", name="5-EMA 경고봉(인도 Power of Stocks) 봉 전체가 EMA5 아래였던 다음날 그 고가 돌파 [근사]", family=["보조지표", "낙폭반전"],
    src="tradingqna.com/t/can-we-recreate-5-ema-strategy 194600 (원래 15분봉)",
    mech="과매도 봉이 EMA5 로 되돌아오는 성질",
    derive=D([], e5="ema(close, 5)", al="high < e5"),
    cond="lag(al, 1) & (high > lag(high, 1))",
    variants=[("종가도 경고봉 고가 위", "lag(al, 1) & (close > lag(high, 1))"), ("경고봉 2연속 뒤", "lag(al, 1) & lag(al, 2) & (high > lag(high, 1))"),
              ("+ 200일선 위", "lag(al, 1) & (high > lag(high, 1)) & (close > rmean(close, 200))")],
    holds=[5, 10], main=5, diff="원전은 돌파 순간 체결·1:3 목표 — 여기선 다음날 시가·고정 보유")

add(key="bsjp", name="BSJP(인도네시아 Stockbit) 장중 +10% 뒤 고가권 마감·거래대금 2배·10·20일선 위 [근사]", family=["급등추격", "거래량"],
    src="Stockbit @hafidh.riza PDF · stockbit.com/sahambsjp",
    mech="오후 강세 종목을 종가에 사서 다음날 아침 판다 — 원전의 하룻밤 수익은 재현 불가, 이후 지속만",
    derive=D(["amt", "pos", "pc", "r1", "ma10"], ma20="rmean(close, 20)"),
    cond="(pos >= 0.8) & (amt >= 2 * lag(rmean(amt, 20), 1)) & (close > ma10) & (close > ma20) & (high >= 1.1 * pc) & (r1 > 2)",
    variants=[("종가 위치 0.9·+5%", "(pos >= 0.9) & (amt >= 2 * lag(rmean(amt, 20), 1)) & (close > ma10) & (close > ma20) & (high >= 1.1 * pc) & (r1 > 5)"),
              ("TikTok판 +5%·거래량 2배", "(r1 >= 5) & (close > rmean(close, 5)) & (close >= open) & (volume >= 2 * lag(rmean(volume, 20), 1)) & (volume >= lag(volume, 1))"),
              ("+ 60일선 위", "(pos >= 0.8) & (amt >= 2 * lag(rmean(amt, 20), 1)) & (close > ma10) & (close > ma20) & (high >= 1.1 * pc) & (r1 > 2) & (close > rmean(close, 60))")],
    holds=[5, 10], main=5, diff="거래량 급증 돌파 추격(기각)과 겹친다 — 하룻밤 보유가 본질이라 여기선 지속 여부만")

add(key="cdc", name="CDC Action Zone(태국) OHLC4 EMA2→EMA12·26 첫 초록 구간", family=["이평", "추세추종"],
    src="chaloke.com CDC Action Zone · TradingView 'CDC Action Zone V.2'",
    mech="빠른선>느린선 & 가격>빠른선 = 초록(매수 구간)의 첫날",
    derive=D([], ap="ema((open + high + low + close) / 4, 2)", fa="ema(ap, 12)", sl="ema(ap, 26)",
             grn="(fa > sl) & (ap > fa)", yel="(fa > sl) & (ap < fa)", blu="(fa < sl) & (ap > fa)"),
    cond="grn & ~lag(grn, 1)",
    variants=[("노랑→초록(추세 재개)", "grn & lag(yel, 1)"), ("파랑 첫날(선행)", "blu & ~lag(blu, 1)"), ("초록 첫날 + 200일선 위", "grn & ~lag(grn, 1) & (close > rmean(close, 200))")],
    holds=[5, 10, 20], main=10, diff="50/60/200 교차(기각)와 같은 계통 — 12·26 EMA + 가격 위치로 구간을 나눔")

add(key="wrsi30", name="주봉 RSI14<30 근사(말레이시아 i3investor) 5일 수익 기반 70일 RSI < 30", family=["보조지표", "낙폭반전"],
    src="klse.i3investor.com DividendGuy67 2024-08-20 (BAT 5전 5승 — 표본 극소)",
    mech="주봉 과매도는 일봉 과매도와 시간축이 다르다",
    derive=D([], wu="np.maximum(close - lag(close, 5), 0)", wd="np.maximum(lag(close, 5) - close, 0)",
             rsiw="100 * rma(wu, 70) / (rma(wu, 70) + rma(wd, 70) + 1e-12)"),
    cond="(rsiw < 30) & (lag(rsiw, 1) >= 30)",
    variants=[("<30 상태", "rsiw < 30"), ("<35 진입", "(rsiw < 35) & (lag(rsiw, 1) >= 35)"), ("<25 진입", "(rsiw < 25) & (lag(rsiw, 1) >= 25)")],
    holds=[20, 40, 60], main=40, diff="일봉 RSI 과매도(기각)와 시간축이 다르다(근사: 5일 변화의 70일 평활)")

add(key="nosupply", name="VSA No Supply(베트남) 상승 추세 속 작은 몸통 하락봉 + 거래량이 직전 두 봉보다 작음", family=["거래량", "눌림"],
    src="dnse.com.vn/hoc/phuong-phap-vsa · thuvienchungkhoan.vn/test-cung",
    mech="팔 사람이 없는 하락 = 공급 고갈",
    derive=D(["pos"], body="np.abs(close - open)"),
    cond="(close < lag(close, 1)) & (body < 0.5 * rmean(body, 20)) & (volume < lag(volume, 1)) & (volume < lag(volume, 2)) & (close > lag(close, 20))",
    variants=[("Test cung(아래꼬리·저거래량·고점 -15% 이내)", "(pos >= 0.7) & ((np.minimum(close, open) - low) >= 2 * body) & (volume < 0.8 * rmean(volume, 20)) & (close >= 0.85 * rmax(high, 60))"),
              ("몸통 조건 완화(0.7배)", "(close < lag(close, 1)) & (body < 0.7 * rmean(body, 20)) & (volume < lag(volume, 1)) & (volume < lag(volume, 2)) & (close > lag(close, 20))"),
              ("+ 50일선 위", "(close < lag(close, 1)) & (body < 0.5 * rmean(body, 20)) & (volume < lag(volume, 1)) & (volume < lag(volume, 2)) & (close > rmean(close, 50))")],
    holds=[5, 10, 20], main=10, diff="거래량 침체 매수([조용한 신고가]의 r16)와 비슷한 축 — 하락봉 한정")

add(key="dybp", name="单阳不破(중화권) +5% 거래량 양봉 뒤 5봉이 그 저가를 안 깨고 ±3% 안에서 쉼", family=["눌림", "거래량"],
    src="wiki.mbalib.com 单阳不破 · 163.com GEO2EJ1J · sina 2025-01-02",
    mech="큰 양봉 하나가 깨지지 않으면 세력이 지키는 가격 — 80% 성공 주장(미검증)",
    derive=D(["pc", "r1"], ma30="rmean(close, 30)",
             b0="(r1 >= 5) & (volume >= 1.5 * lag(rmean(volume, 5), 1)) & (ma30 > lag(ma30, 3))"),
    cond="lag(b0, 5) & (rmin(low, 5) >= lag(low, 5)) & (rmax(np.abs(r1), 5) <= 3)",
    variants=[("엄격 +9.5%", "lag(b0 & (r1 >= 9.5), 5) & (rmin(low, 5) >= lag(low, 5)) & (rmax(np.abs(r1), 5) <= 3)"),
              ("쉬는 기간 4봉", "lag(b0, 4) & (rmin(low, 4) >= lag(low, 4)) & (rmax(np.abs(r1), 4) <= 3)"),
              ("+ 종가가 큰 양봉 고가 돌파", "lag(b0, 5) & (rmin(low, 5) >= lag(low, 5)) & (close > lag(high, 5))")],
    holds=[5, 10, 20], main=10, diff="기준봉 눌림(기각 H00xx)과 같은 계열 — 5봉 동안 저가 유지·등락 3% 이내로 좁힘")


# ═════ 일본 (systemtrade-kabu 株の教科書 전수 검증 · イザナミ 블로그 · 개인 블로그) ═════
add(key="dnvol", name="下落日の出来高急増 하락일인데 거래량 20일 평균의 3~5배(일본 25년 전수 +0.57%·PF1.25)", family=["거래량", "낙폭반전"],
    src="systemtrade-kabu.com/volume-spike-next-day · turnover-surge-next-day (도쿄 전 종목 2000~2024, N=255,558)",
    mech="하락일 대량거래는 투매를 받아낸 것 — 단 10배 이상은 오히려 나쁨(비단조)",
    derive=D(["pc"]), cond="(close < pc) & (su1 >= 3) & (su1 < 5)",
    variants=[("2.5~4배", "(close < pc) & (su1 >= 2.5) & (su1 < 4)"), ("3~6배", "(close < pc) & (su1 >= 3) & (su1 < 6)"),
              ("10배 이상(대조)", "(close < pc) & (su1 >= 10)")],
    holds=[5, 10, 20], main=5, diff="거래량 급증 돌파(상승일·기각)와 반대로 '하락일' 거래량 3~5배만")

add(key="sanku", name="三空叩き込み 사흘 연속 갭하락 음봉 4개(酒田五法, 일본 2000~16 N=481 5일 +6.44%)", family=["캔들", "낙폭반전"],
    src="kabu.jyohokyoku.net/6606 (イザナミ 검증 개인 블로그)",
    mech="세 번 연속 갭으로 두들겨 맞은 투매의 끝",
    derive=D([], bear="(close / open - 1) <= -0.01", gd="gap0 <= -1"),
    cond="(rsum(bear, 4) >= 4) & (rsum(gd, 3) >= 3)",
    variants=[("진짜 창(고가<전일 저가)", "(rsum(close < open, 4) >= 4) & (rsum(high < lag(low, 1), 3) >= 3)"), ("갭 -2%", "(rsum(bear, 4) >= 4) & (rsum(gap0 <= -2, 3) >= 3)"),
              ("음봉 조건 C<O", "(rsum(close < open, 4) >= 4) & (rsum(gd, 3) >= 3)")],
    holds=[5, 10, 20], main=5, diff="연속 하락일(기각·종가 기준)과 달리 '갭' 하락 3연속 투매")

add(key="stopma", name="ストップ高×위치 상한가(국내 +29%·미장 +20%)인데 전일 종가는 25일선 아래·200일선 위", family=["급등추격", "눌림"],
    src="systemtrade-kabu.com/stop-ma-position (N=6,214, C군 5일 +5.3% · 200일선 ±10% 이내 +6.5%)",
    mech="상승 추세 속 눌림에서 나온 상한가만 — 과열·반등 초기 상한가는 약함",
    derive=D([], ma25="rmean(close, 25)", ma200="rmean(close, 200)", big=None),
    cond="big & (lag(close, 1) < lag(ma25, 1)) & (lag(close, 1) > lag(ma200, 1))",
    over={"KR": {"derive_set": {"big": "(close / lag(close, 1) - 1) * 100 >= 29"}},
          "US": {"derive_set": {"big": "(close / lag(close, 1) - 1) * 100 >= 20"}}},
    variants=[("+ 200일선 ±10% 이내", "big & (lag(close, 1) < lag(ma25, 1)) & (lag(close, 1) > lag(ma200, 1)) & (np.abs(close / ma200 - 1) <= 0.10)"),
              ("문턱 +15%", "((close / lag(close, 1) - 1) * 100 >= 15) & (lag(close, 1) < lag(ma25, 1)) & (lag(close, 1) > lag(ma200, 1))"),
              ("문턱 +20%(국내)·+15%(미장)", "((close / lag(close, 1) - 1) * 100 >= 17) & (lag(close, 1) < lag(ma25, 1)) & (lag(close, 1) > lag(ma200, 1))")],
    holds=[5, 10, 20], main=5, diff="상한가 다음날 추격(일본에서도 -1.42%)과 달리 추세 속 눌림 위치 필터 — 수익 기준점이 다음날 시가라 원전보다 불리")

add(key="bbwalk", name="ボリンジャー 수축→밴드타기 수축(σ/평균 2%·4.5%) 뒤 사흘 연속 +1σ~+3σ", family=["변동성", "추세추종"],
    src="kabutore0721.com/boriban (전 종목 2010~23 N=103,058 승률 52.5%)",
    mech="변동성 수축 뒤 밴드를 타고 오르는 추세 초입",
    derive=D([], mb="rmean(close, 20)", sb="rstd(close, 20)", inb="(close >= mb + sb) & (close <= mb + 3 * sb)"),
    cond="(lag(sb / mb, 3) <= 0.02) & (lag(sb / mb, 2) <= 0.045) & (rsum(inb, 3) >= 3)",
    variants=[("수축 3%·6%", "(lag(sb / mb, 3) <= 0.03) & (lag(sb / mb, 2) <= 0.06) & (rsum(inb, 3) >= 3)"),
              ("수축 조건 없이 3일 밴드타기", "rsum(inb, 3) >= 3"), ("2일 밴드타기", "(lag(sb / mb, 2) <= 0.02) & (lag(sb / mb, 1) <= 0.045) & (rsum(inb, 2) >= 2)")],
    holds=[5, 10, 20], main=5, diff="볼린저 첫 이탈(bbx)과 달리 수축 뒤 3일 연속 밴드 안쪽 상단")

add(key="psyline", name="サイコロジカルライン 심리선 10일 중 상승일 2일 이하(닛케이225 승률 63.6%)", family=["보조지표", "낙폭반전"],
    src="systemtrade-kabu.com/psychological-line",
    mech="'연속'이 아니라 '비율'로 본 과매도",
    derive=D(["pc"], upd="close > pc"), cond="rsum(upd, 10) <= 2",
    variants=[("12일 중 3일 이하", "rsum(upd, 12) <= 3"), ("12일 중 2일 이하", "rsum(upd, 12) <= 2"), ("10일 중 1일 이하", "rsum(upd, 10) <= 1")],
    holds=[5, 10, 20], main=10, diff="연속 하락일(기각)과 상관 높음 — '비율'이라 사이에 반등이 끼어도 잡힌다")

add(key="vratio", name="ボリュームレシオ VR 25일 상승일/하락일 거래량 비 ≤ 70(닛케이225 승률 64%·+4.44%)", family=["거래량", "낙폭반전"],
    src="systemtrade-kabu.com/volume-ratio · kabusensor signal 12",
    mech="하락일 거래량이 상승일보다 훨씬 많음 = 매도 과잉",
    derive=D(["pc"], vu="volume * (close > pc)", vd="volume * (close < pc)", vf="volume * (close == pc)",
             vr1="100 * (rsum(vu, 25) + 0.5 * rsum(vf, 25)) / (rsum(vd, 25) + 0.5 * rsum(vf, 25) + 1)",
             vr2="100 * (rsum(vu, 25) + 0.5 * rsum(vf, 25)) / (rsum(volume, 25) + 1)"),
    cond="vr1 <= 70",
    variants=[("VR2 ≤ 30", "vr2 <= 30"), ("VR1 ≤ 50", "vr1 <= 50"), ("VR1 70 하향 돌파일", "(vr1 <= 70) & (lag(vr1, 1) > 70)")],
    holds=[10, 20], main=10, diff="일본 고유 지표 — 가격이 아니라 상승·하락일 거래량 비")

add(key="shino", name="篠原レシオ 강약 레시오 A·B 가 120 넘던 뒤 둘 다 70 아래로 급락", family=["보조지표", "낙폭반전"],
    src="sevendata.co.jp/shihyou/technical/shinohara.html (일본 고유 지표)",
    mech="시가 대비 매수·매도 에너지 비의 급냉",
    derive=D(["pc"], ra="100 * rsum(high - open, 26) / (rsum(open - low, 26) + 1e-9)",
             rb="100 * rsum(np.maximum(high - pc, 0), 26) / (rsum(np.maximum(pc - low, 0), 26) + 1e-9)"),
    cond="(lag(rmax(np.maximum(ra, rb), 20), 1) > 120) & (ra < 70) & (rb < 70)",
    variants=[("B 가 A 상향교차(둘 다 ≤70)", "(rb > ra) & (lag(rb, 1) <= lag(ra, 1)) & (ra <= 70) & (rb <= 70)"),
              ("둘 다 ≤60", "(lag(rmax(np.maximum(ra, rb), 20), 1) > 120) & (ra < 60) & (rb < 60)"), ("과거 120 조건 없이", "(ra < 70) & (rb < 70)")],
    holds=[10, 20], main=20, diff="일본 고유 지표 — 저자 수치 없음")

add(key="shitahige", name="下げの下ひげ 하락 국면 긴 아래꼬리(꼬리/몸통 ≥ 2)", family=["캔들", "낙폭반전"],
    src="note.com/agata_trader · rizumu.net/signal/下げの下ひげ (익일 상승 55.9%)",
    mech="하락 중 장중 투매를 받아내고 올라온 흔적",
    derive=D([], ma25="rmean(close, 25)", lsr="(np.minimum(open, close) - low) / np.maximum(np.abs(close - open), 0.001 * close)"),
    cond="(lsr >= 2) & ((close < ma25) | (ret5 < -5))",
    variants=[("비율 ≥ 5", "(lsr >= 5) & ((close < ma25) | (ret5 < -5))"), ("양봉만", "(lsr >= 2) & (close > open) & ((close < ma25) | (ret5 < -5))"),
              ("5일 -5% 한정", "(lsr >= 2) & (ret5 < -5)")],
    holds=[5, 10, 20], main=5, diff="IBS 역추세(기각)와 반대 방향(종가 위치 높음) — 긴 아래꼬리")

add(key="dakiin", name="最後の抱き陰線 하락 추세에서 소양봉 다음날 갭상승 뒤 그 봉을 감싸는 장대음봉", family=["캔들", "낙폭반전"],
    src="rizumu.net/signal/最後の抱き陰線 (익일 상승 56%, 1주 48.6% — 근거 약함)",
    mech="마지막 투매 음봉 = 바닥",
    derive=D([], ma25="rmean(close, 25)"),
    cond="(close < ma25) & (lag(close, 1) > lag(open, 1)) & ((lag(close, 1) - lag(open, 1)) / lag(open, 1) < 0.015) & (gap0 > 1) & (close < lag(open, 1)) & ((open - close) / open >= 0.03)",
    variants=[("몸통 2%", "(close < ma25) & (lag(close, 1) > lag(open, 1)) & (gap0 > 1) & (close < lag(open, 1)) & ((open - close) / open >= 0.02)"),
              ("갭 조건 없음", "(close < ma25) & (lag(close, 1) > lag(open, 1)) & (open > lag(close, 1)) & (close < lag(open, 1)) & ((open - close) / open >= 0.03)"),
              ("추세 조건 없음", "(lag(close, 1) > lag(open, 1)) & (gap0 > 1) & (close < lag(open, 1)) & ((open - close) / open >= 0.03)")],
    holds=[5, 10], main=5, diff="장악형 캔들 — 기존 캔들 기각과 방향·위치가 다름")


def check(mk):
    """종목 200개로 모든 조건식을 계산해 본다 — 등록 전에 오타·0건을 잡는다."""
    import numpy as np, pandas as pd
    import run_spec as R
    A, uni, since = R.load_market(mk)
    rng = np.random.default_rng(0)
    tk = rng.choice(A.ticker.unique(), 200, replace=False)
    A = A[A.ticker.isin(tk)].reset_index(drop=True)
    if mk == "KR":
        import features as FT
        FT.attach(A, sorted({f for t in T for f in t.get("features", [])}), cal=sorted(A.date.unique()))
    base = list(A.columns)
    for t in T:
        if t["mk"] not in ("both", mk):
            continue
        der = dict(t["derive"]); der.update(t.get("over", {}).get(mk, {}).get("derive_set", {}))
        spec = {"derive": der, "cond": t["cond"], "variants": [{"label": a, "cond": b} for a, b in t["variants"]]}
        try:
            C = R.evaluate(A, spec)
            print("%-10s %s" % (t["key"], " · ".join("%s %d" % (k[:10], v.sum()) for k, v in C.items())))
        except Exception as e:
            print("%-10s ❌ %r" % (t["key"], e))
        A.drop(columns=[c for c in A.columns if c not in base], inplace=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    MAP.parent.mkdir(exist_ok=True)
    mp = json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}
    if "--check" in sys.argv:
        return check(sys.argv[sys.argv.index("--check") + 1])
    if "--list" in sys.argv:
        for t in T:
            print(t["key"], t["mk"], t["name"])
        print(len(T), "기법"); return
    new = []
    for t in T:
        mks = ["KR", "US"] if t["mk"] == "both" else [t["mk"]]
        for mk in mks:
            k = f"{t['key']}_{mk}"
            if k in mp:
                continue
            der = dict(t["derive"])
            der.update(t.get("over", {}).get(mk, {}).get("derive_set", {}))
            assert all(v is not None for v in der.values()), (k, [n for n, v in der.items() if v is None])
            hid = registry.add(name=f"{t['name']} [{mk}]", family=t["family"], market=mk, source=t["src"],
                               mechanism=t["mech"], data="일봉 OHLCV" + (" · 수급" if t.get("features") else ""),
                               date="2026-09-25", memory=["rejected-strategies"])
            spec = {"id": hid, "market": mk, "derive": der, "cond": t["cond"], "holds": t["holds"],
                    "main_hold": t["main"],
                    "variants": [{"label": a, "cond": b} for a, b in t["variants"]],
                    "differs_from": t.get("diff", "외국 기법 신규 — 비슷한 기각 기록과 조건식이 다르다")}
            if t.get("features"):
                spec["features"] = t["features"]
            (SPECS / f"{hid}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            mp[k] = hid; new.append((k, hid))
    MAP.write_text(json.dumps(mp, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, h in new:
        print(h, k)
    print("새로 등록", len(new))


if __name__ == "__main__":
    main()
