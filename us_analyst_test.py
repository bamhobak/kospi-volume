# -*- coding: utf-8 -*-
"""미국 전용 축 ② — 애널리스트 항복 · 실적 서프라이즈.

한국엔 없거나 유료라 한 번도 못 재본 두 축이다.

  A **애널리스트 항복** — 우리 스타일과 가장 잘 맞는다.
     우리는 떨어진 것을 산다. 그렇다면 '모두가 포기한 자리' 가 언제인지 알면 좋다.
     등급 하향·목표가 인하가 몰린 뒤를 잰다. 반대(상향 몰림)도 같이 잰다.
  B **실적 서프라이즈(PEAD)** — 실적발표 후 주가가 같은 방향으로 며칠 흐르는 현상.
     금융에서 가장 오래 살아남은 이상현상 중 하나다. 한국은 컨센서스가 유료라 못 쟀다.
     우리 스타일상 **음의 서프라이즈 뒤 과매도 반등** 쪽이 더 궁금하다.

⚠ 시점 주의
  · 등급 변경은 GradeDate 가 있으므로 **그날 이후**부터 쓴다.
  · 실적은 발표시각이 대개 장마감 후다. 발표일 **다음 거래일**부터 쓴다.
  둘 다 미리보기가 생기지 않게 하루씩 민다.
"""
import io, sys, glob, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HS = [5, 20, 60]

K = pd.read_pickle(BASE / "data" / "panel_us.pkl")
dates = np.array(sorted(K.date.unique()))
DI = {d: i for i, d in enumerate(dates)}
print(f"미국 패널 {len(K):,}행 · {K.ticker.nunique():,}종목")


def shift_to_next(s):
    """어떤 날짜(문자열 YYYYMMDD)를 그 **다음 거래일**로 민다."""
    i = np.searchsorted(dates, s, side="right")
    return np.where(i < len(dates), dates[np.clip(i, 0, len(dates) - 1)], None)


# ── A. 애널리스트 등급 변경 ──────────────────────────────────────────
uf = sorted(glob.glob(str(BASE / "data/us/analyst/upg_*.pkl")))
U = pd.concat([pd.read_pickle(f) for f in uf], ignore_index=True) if uf else pd.DataFrame()
U = U[U.get("ticker").notna()] if len(U) else U
if len(U):
    dc = "GradeDate" if "GradeDate" in U.columns else U.columns[0]
    U["d0"] = pd.to_datetime(U[dc], errors="coerce", utc=True).dt.strftime("%Y%m%d")
    U = U.dropna(subset=["d0"])
    U["date"] = shift_to_next(U.d0.values)            # 공시 다음 거래일부터
    U = U.dropna(subset=["date"])
    act = U.get("Action", pd.Series("", index=U.index)).astype(str).str.lower()
    U["down"] = act.str.contains("down")
    U["up"] = act.str.contains("up")
    pt_new = pd.to_numeric(U.get("currentPriceTarget"), errors="coerce")
    pt_old = pd.to_numeric(U.get("priorPriceTarget"), errors="coerce")
    U["cut"] = (pt_new < pt_old * 0.95)               # 목표가 5%↑ 인하
    G = U.groupby(["ticker", "date"]).agg(
        n_dn=("down", "sum"), n_up=("up", "sum"), n_cut=("cut", "sum"),
        n_all=("down", "size")).reset_index()
    K = K.merge(G, on=["ticker", "date"], how="left")
    for c in ("n_dn", "n_up", "n_cut", "n_all"):
        K[c] = K[c].fillna(0)
    g = K.groupby("ticker", sort=False)
    for c in ("n_dn", "n_up", "n_cut"):
        K[c + "_60"] = g[c].transform(lambda s: s.rolling(60, min_periods=1).sum())
    print(f"  등급 변경 {len(U):,}건 · {U.ticker.nunique():,}종목 · {U.d0.min()}~{U.d0.max()}")
else:
    print("  ⚠ 등급 데이터 없음 — us_analyst.py 를 먼저 돌린다")

# ── B. 실적 서프라이즈 ───────────────────────────────────────────────
ef = sorted(glob.glob(str(BASE / "data/us/analyst/earn_*.pkl")))
E = pd.concat([pd.read_pickle(f) for f in ef], ignore_index=True) if ef else pd.DataFrame()
E = E[E.get("ticker").notna()] if len(E) else E
if len(E):
    dc = [c for c in E.columns if "Earnings Date" in c or c == "index"]
    dc = dc[0] if dc else E.columns[0]
    E["d0"] = pd.to_datetime(E[dc], errors="coerce", utc=True).dt.strftime("%Y%m%d")
    E = E.dropna(subset=["d0"])
    E["date"] = shift_to_next(E.d0.values)            # 발표 다음 거래일
    sc = [c for c in E.columns if "Surprise" in c]
    E["surp"] = pd.to_numeric(E[sc[0]], errors="coerce") if sc else np.nan
    E = E.dropna(subset=["date", "surp"]).drop_duplicates(["ticker", "date"])
    K = K.merge(E[["ticker", "date", "surp"]], on=["ticker", "date"], how="left")
    print(f"  실적 {len(E):,}건 · {E.ticker.nunique():,}종목 · {E.d0.min()}~{E.d0.max()}")
else:
    K["surp"] = np.nan
    print("  ⚠ 실적 데이터 없음")


def base(amt=1.0):
    return (K.close >= 3) & (K.amt20.fillna(0) >= amt)


UNI = {h: K[base()].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HS}


def stat(m, h):
    col = f"n{h}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 200:
        return None
    X["di"] = X.date.map(DI); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h; keep.append(ix)
    X = X.loc[keep]
    if len(X) < 150:
        return None
    X["ex"] = X[col] - X.date.map(UNI[h])
    tr, va = X[X.date <= TR1], X[X.date >= VA0]
    if len(tr) < 60 or len(va) < 30:
        return None
    yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
    return dict(n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                trim=X.ex[X.ex <= X.ex.quantile(0.95)].mean(),
                ret=X[col].mean(), win=(X[col] > 0).mean() * 100,
                tr=tr.ex.mean(), va=va.ex.mean(),
                ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean(), 0.10),
                pos=int((yr > 0).sum()), ny=len(yr))


NT, ROWS = 0, []
HDR = (f"  {'조건':<32}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'절대':>8}"
       f"{'승률':>6}{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")


def show(nm, m):
    global NT
    for h in HS:
        NT += 1
        r = stat(m, h)
        if r is None:
            continue
        r["name"] = nm; r["h"] = h; ROWS.append(r)
        print(f"  {nm:<32}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}{r['trim']:>+8.2f}"
              f"{r['ret']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
              f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")


b = base()
if "n_dn_60" in K.columns:
    # ⚠ 전체 유니버스와 비교하면 **하향도 상향도 둘 다 양수**로 나온다(1차 실행에서 확인).
    #   그건 항복의 효과가 아니라 '애널리스트가 커버하는 종목 자체가 좋다' 는 것이다.
    #   실적 서프라이즈와 똑같은 함정이므로 기준선을 **커버되는 종목들**로 바꾼다.
    g = K.groupby("ticker", sort=False)
    K["n_all_60"] = g.n_all.transform(lambda s: s.rolling(60, min_periods=1).sum())
    cov = base() & (K.n_all_60 >= 1)                  # 최근 60일에 등급 액션이 있던 종목
    CB = {h: K[cov].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HS}
    print(f"  커버 기준선: 최근 60일 등급 액션이 있던 종목 {cov.mean()*100:.0f}% 의 평균")

    def stat_c(m, h):
        col = f"n{h}"
        X = K[m.fillna(False)].dropna(subset=[col]).copy()
        X = X[X.date >= TR0]
        if len(X) < 200:
            return None
        X["di"] = X.date.map(DI); X = X.sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
            if last.get(t, -10 ** 9) >= i:
                continue
            last[t] = i + h; keep.append(ix)
        X = X.loc[keep]
        if len(X) < 150:
            return None
        X["ex"] = X[col] - X.date.map(CB[h])          # 커버되는 종목들 평균 대비
        tr, va = X[X.date <= TR1], X[X.date >= VA0]
        if len(tr) < 60 or len(va) < 30:
            return None
        yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
        return dict(n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                    trim=X.ex[X.ex <= X.ex.quantile(0.95)].mean(),
                    ret=X[col].mean(), win=(X[col] > 0).mean() * 100,
                    tr=tr.ex.mean(), va=va.ex.mean(),
                    ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean(), 0.10),
                    pos=int((yr > 0).sum()), ny=len(yr))

    def show_c(nm, m):
        global NT
        for h in HS:
            NT += 1
            r = stat_c(m, h)
            if r is None:
                continue
            r["name"] = nm; r["h"] = h; ROWS.append(r)
            print(f"  {nm:<32}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
                  f"{r['trim']:>+8.2f}{r['ret']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}"
                  f"{r['va']:>+8.2f}{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")

    print("\n" + "=" * 128)
    print("A. 애널리스트 항복 — 최근 60일 하향이 몰린 뒤. **기준선은 커버되는 종목들**")
    print("=" * 128)
    print(HDR)
    show_c("A 하향 1건", b & (K.n_dn_60 >= 1))
    show_c("A 하향 3건↑", b & (K.n_dn_60 >= 3))
    show_c("A 하향 5건↑(항복)", b & (K.n_dn_60 >= 5))
    show_c("A 목표가 인하 3건↑", b & (K.n_cut_60 >= 3))
    show_c("A 하향3 + 낙폭 -20%↓", b & (K.n_dn_60 >= 3) & (K.ret20 <= -20))
    show_c("A 하향3 + 업종붕괴", b & (K.n_dn_60 >= 3) & (K.u <= -10))
    show_c("A 반대: 상향 3건↑", b & (K.n_up_60 >= 3))
    show_c("A 하향이 상향보다 3건↑ 많음", b & (K.n_dn_60 - K.n_up_60 >= 3))

if K.surp.notna().any():
    # ⚠ 전체 유니버스와 비교하면 모든 서프라이즈 구간이 양수로 나온다. 실적을 발표하는
    #   종목 자체가 크고 커버리지 좋은 회사라서지 서프라이즈의 효과가 아니다(1차 실행에서 확인).
    #   그래서 **같은 날 실적을 낸 종목들끼리** 비교하는 기준선을 따로 쓴다.
    EB = {h: K[base() & K.surp.notna()].dropna(subset=[f"n{h}"])
             .groupby("date")[f"n{h}"].mean() for h in HS}

    def stat_e(m, h):
        col = f"n{h}"
        X = K[m.fillna(False)].dropna(subset=[col]).copy()
        X = X[X.date >= TR0]
        if len(X) < 200:
            return None
        X["di"] = X.date.map(DI); X = X.sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
            if last.get(t, -10 ** 9) >= i:
                continue
            last[t] = i + h; keep.append(ix)
        X = X.loc[keep]
        if len(X) < 150:
            return None
        X["ex"] = X[col] - X.date.map(EB[h])       # 같은 날 실적 낸 종목들 평균 대비
        tr, va = X[X.date <= TR1], X[X.date >= VA0]
        if len(tr) < 60 or len(va) < 30:
            return None
        yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
        return dict(n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                    trim=X.ex[X.ex <= X.ex.quantile(0.95)].mean(),
                    ret=X[col].mean(), win=(X[col] > 0).mean() * 100,
                    tr=tr.ex.mean(), va=va.ex.mean(),
                    ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean(), 0.10),
                    pos=int((yr > 0).sum()), ny=len(yr))

    def show_e(nm, m):
        global NT
        for h in HS:
            NT += 1
            r = stat_e(m, h)
            if r is None:
                continue
            r["name"] = nm; r["h"] = h; ROWS.append(r)
            print(f"  {nm:<32}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
                  f"{r['trim']:>+8.2f}{r['ret']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}"
                  f"{r['va']:>+8.2f}{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")

    print("\n" + "=" * 128)
    print("B. 실적 서프라이즈 — 발표 다음 거래일부터. **기준선은 같은 날 실적 낸 종목들**")
    print("=" * 128)
    print(HDR)
    for lo, hi, nm in ((-9999, -20, "서프라이즈 -20%↓"), (-20, -5, "-20~-5%"),
                       (-5, 5, "-5~+5%(무난)"), (5, 20, "+5~20%"), (20, 9999, "+20%↑")):
        show_e(f"B {nm}", b & (K.surp > lo) & (K.surp <= hi))
    show_e("B 음의 서프라이즈 + 낙폭", b & (K.surp <= -5) & (K.ret20 <= -15))
    show_e("B 양의 서프라이즈 + 낙폭", b & (K.surp >= 5) & (K.ret20 <= -15))

R = pd.DataFrame(ROWS)
print("\n" + "=" * 128)
print("생존 후보 — 중앙>0 · 절삭>0 · 학습·검증 둘 다>0 · 월CI>0 · 양수해 70%↑")
print("=" * 128)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0) &
      (R.pos / R.ny >= 0.7)] if len(R) else R
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  {r['name']:<32} {r.h}일 · {r.n:>6,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} 절대 {r.ret:+.2f}% "
              f"CI{r.ci:+.2f} 양수해 {r.pos}/{r.ny}")
else:
    print("  없음")
verdict.log_trials("미국 애널리스트·실적", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
