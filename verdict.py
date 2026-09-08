# -*- coding: utf-8 -*-
"""다중검정 보정 판정기 — '몇 개를 시험해서 나온 후보인가' 를 반영해 문턱을 올린다.

왜 필요한가(2026-09-08, 퀀트 대회 우승자 인터뷰를 계기로 자가점검):
리포지토리에 실측 스크립트가 124개고 한 개가 수십~수백 조합을 돈다. 수천 개를 훑으면
**순전히 우연으로도** 90% 신뢰구간을 통과하는 후보가 나온다(100개 중 10개는 우연히 통과).
지금까지는 학습/검증 분리·계좌 재검증·최근 해 기준이 그 역할을 대신해 왔지만,
'몇 개 중에 고른 것인가' 를 명시적으로 세지는 않았다.

무엇을 하는가
  ① trials.json 에 시험 횟수를 누적 기록한다(스크립트별·주제별).
  ② 시험 횟수 N 을 반영해 두 가지로 판정한다.
     · 본페로니 CI — 유의수준 10% 를 N 으로 나눠 부트스트랩 백분위를 올린다.
     · Deflated Sharpe Ratio(López de Prado) — N 개를 훑을 때 '우연히 얻어지는 최대 샤프' 를
       기준선으로 삼아 그보다 유의하게 높은지 본다. 왜도·첨도까지 반영해 꼬리가 두꺼운
       수익률에서 샤프가 부풀려지는 것을 깎는다.
  ③ 기존 기준(중앙값>0 · 최근 해 양수 · 계좌 개선)과 함께 종합 판정을 낸다.

쓰는 법
    from verdict import judge, log_trials
    log_trials("bollinger", 25)                 # 이번에 25조합을 시험했다고 기록
    judge("볼린저 평균회귀", 월별수익률시리즈, n_trials=None)   # None 이면 누적 기록에서 읽는다
"""
import io, json, math, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as st

BASE = Path(__file__).parent
LOG = BASE / "data" / "trials.json"
EULER = 0.5772156649015329

def _load():
    if LOG.exists():
        try: return json.load(open(LOG, encoding="utf-8"))
        except Exception: pass
    return {"total": 0, "by_topic": {}}

def log_trials(topic, n):
    """이번에 시험한 조합 수를 기록한다. 후보를 '본' 순간 세야 의미가 있다."""
    d = _load()
    d["total"] = d.get("total", 0) + int(n)
    d["by_topic"][topic] = d["by_topic"].get(topic, 0) + int(n)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d["total"]

def trial_count(topic=None):
    d = _load()
    return d["by_topic"].get(topic, 0) if topic else d.get("total", 0)

def expected_max_sharpe(n_trials, sr_var):
    """N 개를 훑을 때 '실력이 0이어도' 우연히 얻어지는 최대 샤프의 기대값."""
    if n_trials < 2: return 0.0
    z1 = st.norm.ppf(1 - 1.0/n_trials)
    z2 = st.norm.ppf(1 - 1.0/(n_trials*math.e))
    return math.sqrt(max(sr_var, 1e-12)) * ((1-EULER)*z1 + EULER*z2)

def deflated_sharpe(r, n_trials):
    """Deflated Sharpe Ratio — 시험 횟수를 반영한 '진짜일 확률'. r 은 기간 수익률 시계열(%)."""
    r = pd.Series(r).dropna().astype(float)
    T = len(r)
    if T < 12: return None
    mu, sd = r.mean(), r.std(ddof=1)
    if sd <= 0: return None
    sr = mu / sd                                    # 기간 단위 샤프(무위험 0 가정)
    sk = st.skew(r); ku = st.kurtosis(r, fisher=False)
    sr0 = expected_max_sharpe(n_trials, 1.0/max(T-1, 1))
    denom = math.sqrt(max(1 - sk*sr + (ku-1)/4.0*sr**2, 1e-9))
    z = (sr - sr0) * math.sqrt(max(T-1, 1)) / denom
    return dict(T=T, sr=sr, sr0=sr0, dsr=float(st.norm.cdf(z)), skew=sk, kurt=ku)

def boot_ci(r, alpha=0.10, n=20000, seed=0):
    """월 블록 부트스트랩 신뢰구간 하한. alpha 를 낮추면(보정) 문턱이 올라간다."""
    r = np.asarray(pd.Series(r).dropna(), float)
    if len(r) < 8: return float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(r), (n, len(r)))
    return float(np.percentile(r[idx].mean(axis=1), alpha*100))

def judge(name, monthly_ret, n_trials=None, topic=None, median=None, last_year=None, acct=None):
    """종합 판정. monthly_ret 은 '월별' 수익률(%) 시계열이면 가장 해석이 쉽다."""
    N = n_trials if n_trials is not None else max(trial_count(topic), 1)
    r = pd.Series(monthly_ret).dropna().astype(float)
    raw = boot_ci(r, 0.10)                       # 기존 기준: 90% 하한
    adj_alpha = min(0.10 / N, 0.10)              # 본페로니
    adj = boot_ci(r, adj_alpha)
    d = deflated_sharpe(r, N)
    print(f"\n[{name}]  시험 {N:,}개 대비 보정")
    print(f"  기간 {len(r)}개 · 평균 {r.mean():+.2f}% · 표준편차 {r.std(ddof=1):.2f}%")
    print(f"  신뢰구간 하한: 보정 전(90%) {raw:+.2f}%  →  보정 후({(1-adj_alpha)*100:.3f}%) {adj:+.2f}%")
    if d:
        print(f"  샤프 {d['sr']:.3f} · 우연히 나올 최대 샤프 {d['sr0']:.3f} · "
              f"Deflated Sharpe {d['dsr']*100:.1f}%  (왜도 {d['skew']:+.2f} 첨도 {d['kurt']:.1f})")
    chk = []
    chk.append(("보정 CI 하한 > 0", adj > 0))
    if d: chk.append(("DSR ≥ 95%", d["dsr"] >= 0.95))
    if median is not None: chk.append(("중앙값 > 0", median > 0))
    if last_year is not None: chk.append(("최근 해 양수", last_year > 0))
    if acct is not None: chk.append(("계좌 개선", acct))
    for lab, ok in chk: print(f"   {'✅' if ok else '❌'} {lab}")
    passed = all(ok for _, ok in chk)
    print(f"  → {'통과' if passed else '기각'}")
    return passed


# ══════════════════════════════════════════════════════════════════════
# 경로 분포 — "일어난 일" 말고 "일어날 수 있었던 일"
# ══════════════════════════════════════════════════════════════════════
# 왜 필요한가(2026-09-09, 알고트레이딩 유튜브 dYNZ5eAoW-0 를 계기로):
# risk_curve.py 가 낸 '최대 낙폭 -14.9% · 제자리 4.0년' 은 시드 24개의 값이지만,
# 그 24개는 **어떤 신호를 담느냐만 다르고 시장이 흘러온 순서는 전부 같다**.
# 2005~26 의 역사는 하나뿐이라 우리는 '일어난 일' 만 알고 '일어날 수 있었던 일' 을 모른다.
# 실전에서 백테스트에 없던 낙폭을 만나면 시스템이 깨졌다고 오판하고 그만두게 된다.
#
# ⚠ 거래를 낱개로 섞으면 안 된다. 우리 최악의 낙폭은 폭락장에서 아홉 규칙이 한꺼번에
#   지면서 생긴다. 낱개로 섞으면 그 동시성이 깨져 낙폭이 실제보다 **얕게** 나온다
#   — 안전하다고 착각하게 만드는 방향으로 틀리므로 가장 위험한 오류다.
#   그래서 **월 단위**(같은 달 손실은 이미 합산돼 있다)로, 그것도 **연속된 블록**으로 뽑는다.
#
# ⚠ 한계: 부트스트랩은 표본에 있는 것만 재조합한다. 겪어보지 않은 종류의 위기
#   (제도 변경·거래정지·유동성 증발)는 이 분포에 안 나온다. 하한이지 상한이 아니다.

def block_paths(monthly_ret, n_paths=5000, mean_block=3, seed=0):
    """월 수익률(%)을 정상 블록 부트스트랩으로 재추출해 가상의 경로들을 만든다.

    블록 길이를 평균 mean_block 의 기하분포로 뽑아 연속된 달을 함께 가져온다
    (폭락 다음 달 반등 같은 연결이 살아남는다). 원본과 같은 길이의 경로를 만든다.
    돌려주는 것: 경로별 (최종배수, 최대낙폭%, 최장 언더워터 개월, 최악의 달%, 최장 연속손실 개월)
    """
    r = np.asarray(pd.Series(monthly_ret).dropna(), float)
    T = len(r)
    if T < 12:
        return None
    rng = np.random.default_rng(seed)
    p = 1.0 / max(mean_block, 1)
    out = np.empty((n_paths, 5))
    for k in range(n_paths):
        idx = np.empty(T, dtype=np.int64)
        i = 0
        while i < T:
            start = rng.integers(0, T)
            ln = min(int(rng.geometric(p)), T - i)
            idx[i:i + ln] = (start + np.arange(ln)) % T      # 순환식 — 끝에서 앞으로 잇는다
            i += ln
        x = r[idx]
        v = np.cumprod(1 + x / 100)
        pk = np.maximum.accumulate(v)
        dd = v / pk - 1
        under = v < pk
        # 최장 언더워터(개월)와 최장 연속손실(개월)
        best = cur = 0
        for u in under:
            cur = cur + 1 if u else 0
            if cur > best: best = cur
        lbest = lcur = 0
        for y in x:
            lcur = lcur + 1 if y < 0 else 0
            if lcur > lbest: lbest = lcur
        out[k] = (v[-1], dd.min() * 100, best, x.min(), lbest)
    return pd.DataFrame(out, columns=["nav", "mdd", "under", "worst_m", "lose_run"])


def path_report(monthly_ret, label="", actual=None, n_paths=5000, mean_block=3, seed=0):
    """경로 분포를 표로 찍는다. actual 은 실제로 겪은 값 dict(mdd=..., under=...)."""
    P = block_paths(monthly_ret, n_paths, mean_block, seed)
    if P is None:
        print(f"  {label}: 표본 부족"); return None
    yrs = len(pd.Series(monthly_ret).dropna()) / 12
    print(f"\n[{label}] 월 블록 재추출 {n_paths:,}경로 · 블록 평균 {mean_block}개월 · {yrs:.0f}년치")
    print(f"  {'':<16}{'중앙':>10}{'하위25%':>10}{'하위10%':>10}{'하위5%':>10}{'하위1%':>10}")
    def line(nm, s, fmt="{:+.1f}%", worst_is_low=True):
        q = [0.50, 0.25, 0.10, 0.05, 0.01] if worst_is_low else [0.50, 0.75, 0.90, 0.95, 0.99]
        print(f"  {nm:<16}" + "".join(f"{fmt.format(s.quantile(x)):>10}" for x in q))
    line("최대 낙폭", P.mdd)
    line("언더워터(개월)", P.under, "{:.0f}개월", False)
    line("연속손실(개월)", P.lose_run, "{:.0f}개월", False)
    line("최종 배수", P.nav, "{:.2f}배")
    # '최악의 달' 은 분위를 찍어봐야 의미가 없다 — 경로 길이가 원본과 같아 표본 최악의 달이
    # 거의 모든 경로에 한 번은 들어가므로 전 분위가 같은 값이 된다. 대신 그 사실을 적는다.
    wm = float(pd.Series(monthly_ret).dropna().min())
    print(f"  최악의 달은 {wm:+.1f}% — 표본에 있는 값이 상한이다. 부트스트랩은 겪은 것만")
    print(f"  재조합하므로 제도 변경·거래정지처럼 **겪어보지 않은 위기**는 이 표에 없다.")
    if actual:
        for k, nm, unit in (("mdd", "최대 낙폭", "%"), ("under", "언더워터", "개월")):
            if k not in actual: continue
            v = actual[k]
            pct = (P[k] <= v).mean() * 100 if k == "mdd" else (P[k] >= v).mean() * 100
            print(f"  실제 겪은 {nm} {v:.1f}{unit} → 이보다 나쁜 경로가 {pct:.0f}%")
    return P
