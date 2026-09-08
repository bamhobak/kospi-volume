# -*- coding: utf-8 -*-
"""초단기 2단계 — 갭하락 축을 우리 재료로 조이고, 실행 현실을 반영해 다시 잰다.

1단계(short_scan.py) 결과: 204셀 중 7개 생존, 그중 6개가 **갭하락** 축.
코스닥 갭-5%↓ 1일 초과 +2.23%p / 코스피 +1.36%p. 반대편(갭상승)은 확실히 음수.

그러나 그대로는 규칙이 못 된다. 두 가지를 해결해야 한다.
  ① **신호가 너무 많다** — 코스닥 14,942건은 하루 4건꼴. 우리 재료로 조인다.
  ② **실행 현실** — 갭은 시가가 나와야 안다. 백테스트는 그 시가(buy)에 샀다고 계산한다.
     실제로는 09:00 시가를 보고 그 직후 시장가로 사므로 체결이 밀린다.
     그래서 **불리하게 민 가격**으로도 재본다(시가 대비 +0.3% / +0.5% 에 체결).

조이는 재료는 우리가 이미 검증한 것만 쓴다 — 업종 60일·25일선 이격·공매도·기관·외국인·
거래대금·신용잔고·국면. 새 재료를 여기서 발명하지 않는다.
"""
import io, sys, warnings, sqlite3
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"


def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["dev25"] = (K.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
    # 다음날 시가에 사서 그날 종가에 판다. 체결이 밀리는 경우도 만들어 둔다.
    nxt_o = g.open.shift(-1)
    nxt_c = g.close.shift(-1)
    for slip, tag in ((0.0, ""), (0.003, "_s3"), (0.005, "_s5")):
        K[f"r1{tag}"] = (nxt_c / (nxt_o * (1 + slip)) - 1) * 100 - K.cost
    return K


KP = load("panel_kp.pkl", "KOSPI")
KQ = load("panel_kq.pkl", "KOSDAQ")

_cc = sqlite3.connect(f"file:{BASE}/data/kis/market.db?mode=ro", uri=True, timeout=600)
_CR = pd.read_sql("SELECT date,ticker,loan_rmnd FROM credit", _cc); _cc.close()
_CR = _CR.sort_values(["ticker", "date"])
_CR["cr_chg20"] = (_CR.loan_rmnd / _CR.groupby("ticker", sort=False).loan_rmnd.shift(20) - 1) * 100
for _K in (KP, KQ):
    _M = _K.merge(_CR[["date", "ticker", "cr_chg20"]], on=["ticker", "date"], how="left")
    _K["cr_chg20"] = _M.cr_chg20.values
del _CR, _M

IX = fdr.DataReader("KS11", "2004-06-01")
IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
UP60 = dict(zip(IX.date, IX.Close > IX.ma60))
for K in (KP, KQ):
    K["up60"] = K.date.map(UP60)

UNI = {}
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    for tag in ("", "_s3", "_s5"):
        UNI[(mk, tag)] = K.dropna(subset=[f"r1{tag}"]).groupby("date")[f"r1{tag}"].mean()


def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))


def stat(K, mk, m, name, tag=""):
    col = f"r1{tag}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 60:
        return None
    X["ex"] = X[col] - X.date.map(UNI[(mk, tag)])
    tr, va = X[X.date <= TR1].ex, X[X.date >= VA0].ex
    if len(tr) < 30 or len(va) < 15:
        return None
    cut = X.ex.quantile(0.95)
    mo = X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean()
    ly = X[X.date >= "20260101"].ex
    yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
    return dict(name=name, n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                trim=X[X.ex <= cut].ex.mean(), tr=tr.mean(), va=va.mean(),
                ci=verdict.boot_ci(mo, 0.10), ly=ly.mean() if len(ly) >= 5 else np.nan,
                win=(X[col] > 0).mean() * 100, months=X.date.str[:6].nunique(),
                pos_years=int((yr > 0).sum()), n_years=len(yr))


def tighten(K):
    """갭하락 -3% 이하를 출발점으로, 우리가 검증한 재료를 하나씩·둘씩 얹는다."""
    b = base(K)
    g3 = b & (K.gap <= -3)
    g5 = b & (K.gap <= -5)
    A = {"갭 -3%↓ (기준)": g3, "갭 -5%↓ (기준)": g5}
    for tag, g in (("-3", g3), ("-5", g5)):
        A[f"갭{tag} + 업종60일 -10%↓"] = g & (K.u <= -10)
        A[f"갭{tag} + 25일선 -12%↓"] = g & (K.dev25 <= -12)
        A[f"갭{tag} + 공매도 감소"] = g & (K.srd == True)
        A[f"갭{tag} + 기관20일 0%↑"] = g & (K.ow20 >= 0)
        A[f"갭{tag} + 외국인5일 0%↑"] = g & (K.fw5 >= 0)
        A[f"갭{tag} + 신용 -15%↓"] = g & (K.cr_chg20 <= -15)
        A[f"갭{tag} + 하락장(60일선아래)"] = g & (K.up60 == False)
        A[f"갭{tag} + 거래대금 50억↑"] = g & (K.amt20 >= 50)
        A[f"갭{tag} + 거래량 2배↑"] = g & (K.su1 >= 2)
        # 둘 얹기 — 정찰에서 가장 셌던 축들끼리
        A[f"갭{tag} + 업종 + 이격"] = g & (K.u <= -10) & (K.dev25 <= -12)
        A[f"갭{tag} + 업종 + 기관"] = g & (K.u <= -10) & (K.ow20 >= 0)
        A[f"갭{tag} + 이격 + 기관"] = g & (K.dev25 <= -12) & (K.ow20 >= 0)
        A[f"갭{tag} + 하락장 + 이격"] = g & (K.up60 == False) & (K.dev25 <= -12)
        A[f"갭{tag} + 업종+이격+기관"] = g & (K.u <= -10) & (K.dev25 <= -12) & (K.ow20 >= 0)
    return A


NT = 0
ROWS = []
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    A = tighten(K)
    print("\n" + "=" * 122)
    print(f"[{mk}] 갭하락 조이기 — 보유 1일 · 유니버스 대비 초과(2016~) · 체결 밀림 없음")
    print("=" * 122)
    print(f"  {'조건':<26}{'건수':>7}{'월':>4}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
          f"{'학습':>8}{'검증':>8}{'월CI':>8}{'26년':>8}{'양수해':>7}")
    for nm, m in A.items():
        NT += 1
        r = stat(K, mk, m, nm)
        if r is None:
            continue
        r["mk"] = mk
        ROWS.append(r)
        print(f"  {nm:<26}{r['n']:>7,}{r['months']:>4}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
              f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
              f"{r['ci']:>+8.2f}{r['ly']:>+8.2f}{r['pos_years']:>4}/{r['n_years']}")

R = pd.DataFrame(ROWS)
print("\n" + "=" * 122)
print("1차 생존 — 중앙>0 · 절삭>0 · 학습·검증 둘 다>0 · 월CI>0 · 양수해 70%↑")
print("=" * 122)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0) &
      (R.pos_years / R.n_years >= 0.7)]
for _, r in G.sort_values("ci", ascending=False).iterrows():
    print(f"  [{r.mk}] {r['name']:<26} {r.n:>6,}건 초과{r.ex:+.2f} 중앙{r.med:+.2f} "
          f"절삭{r.trim:+.2f} CI{r.ci:+.2f} 양수해 {r.pos_years}/{r.n_years}")
if not len(G):
    print("  없음")

print("\n" + "=" * 122)
print("체결 밀림 검사 — 시가를 보고 사면 그 가격에 못 산다. 0.3% / 0.5% 불리하게 밀어본다")
print("=" * 122)
print(f"  {'조건':<32}{'밀림없음':>12}{'+0.3%':>12}{'+0.5%':>12}")
for _, r in G.iterrows():
    K = KP if r.mk == "KOSPI" else KQ
    m = tighten(K)[r["name"]]
    cells = ""
    for tag in ("", "_s3", "_s5"):
        NT += 1
        z = stat(K, r.mk, m, r["name"], tag)
        cells += f"{z['ex']:>+11.2f}%" if z else f"{'—':>12}"
    print(f"  [{r.mk[:3]}] {r['name']:<26}{cells}")

R.to_pickle(BASE / "data" / "short_build.pkl")
verdict.log_trials("초단기 갭 조이기", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
