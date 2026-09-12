# -*- coding: utf-8 -*-
"""연구 패널 오염 전수 점검 (2026-09-12). 오늘 잡은 둘(시장 중복·미조정 가격) 말고
다른 길로 들어온 오염이 있는지 **한국·미국 패널과 원본 DB** 를 같은 잣대로 훑는다.

항목:
  ① (ticker,date) 중복                     ⑧ 피처 상식 검사(fromhi≤0 · fromlo≥0 · 수익률 범위)
  ② 선행수익 극단값 상위 — 진짜인가        ⑨ 선행수익 재계산 대조(저장값 vs 종가열로 다시 계산)
  ③ 하룻밤·일간 가격 점프                   ⑩ 이음새 — 2016·2018 경계일의 전종목 점프 분포
  ④ 거래일 공백을 넘는 선행수익(수리 후)    ⑪ 원본 DB(kospi.db) 자체 — 중복·0가격·시장 NULL
  ⑤ 거래량 0 행이 매수 신호를 만드는가      ⑫ buy == 다음 행 시가 인가
  ⑥ 날짜별 종목 수 — 반쪽 수집일           ⑬ 미국 티커 표기 중복(BRK.B vs BRK-B)·짧은 종목
  ⑦ 주요 피처 연도별 결측률                 ⑭ 폐지 청산가 — 마지막 종가로 파는 가정이 과한가

    python audit_contam.py [kr|us|db|all]
"""
import gc, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
WHAT = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
W = 110


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)
def flag(ok, msg): print(("  ✅ " if ok else "  ❌ ") + msg)


def audit_panel(name, f, mk, lim_fn):
    sec(f"[{name}] {f}")
    K = pd.read_pickle(BASE / "data" / f)
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    log(f"{len(K):,}행 · {K.ticker.nunique():,}종목 · {K.date.min()}~{K.date.max()}")
    ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
    pos = K.date.map(DI).astype(np.int64)
    g = K.groupby("ticker", sort=False)

    # ① 중복
    dup = K.duplicated(subset=["ticker", "date"], keep=False)
    flag(dup.sum() == 0, f"① (ticker,date) 중복 {int(dup.sum()):,}행")

    # ② 극단값 — 상위 10건을 종목·날짜·가격까지 찍어 진짜인지 볼 수 있게
    print("  ② 선행수익 극단값")
    for h in (5, 20, 60):
        c = f"n{h}"
        if c not in K.columns: continue
        s = K[c].dropna().astype(float)
        print(f"     n{h}: 300%↑ {int((s > 300).sum()):,} · 1000%↑ {int((s > 1000).sum()):,} · 최대 {s.max():,.0f}% · 최소 {s.min():,.0f}%")
    top = K.dropna(subset=["n60"]).nlargest(8, "n60")[["date", "ticker", "close", "buy", "n60", "volume"]]
    top = top.assign(sell_px=lambda d: d.buy * (1 + d.n60 / 100))
    print("     n60 상위 8 (매수가 → 60일 뒤 매도가 환산):")
    for _, r in top.iterrows():
        print(f"       {r.date} {r.ticker:<8} 종가 {r.close:>10,.2f} 매수 {r.buy:>10,.2f} → 매도 {r.sell_px:>12,.2f}  n60 {r.n60:>8,.0f}%  거래량 {r.volume:,.0f}")

    # ③ 가격 점프
    pc = g.close.shift(1)
    lim = lim_fn(K)
    r_on = K.buy / K.close; r_dd = K.close / pc
    onb = r_on.notna() & ((r_on > 1 + lim) | (r_on < 1 - lim))
    ddb = r_dd.notna() & ((r_dd > 1 + lim) | (r_dd < 1 - lim))
    print(f"  ③ 가격 점프(허용 ±{lim if np.isscalar(lim) else '제한폭+10%p'}): 하룻밤 {int(onb.sum()):,}행 · 일간 {int(ddb.sum()):,}행 · 종목 {K[onb | ddb].ticker.nunique():,}")
    bad_span = K[(onb | ddb)]
    if len(bad_span):
        # 그 자리에 선행수익이 남아 있나 (수리가 안 된 곳)
        left = bad_span.n20.notna().sum()
        if mk == "US":   # 미국은 제한폭이 없어 ±50% 가 진짜 사건(임상 결과)일 수 있다 — 결측 처리 안 함
            print(f"     점프 자리에 n20 있는 행 {int(left):,} (미국은 정상 — 진짜 사건 포함)")
        else:
            flag(left == 0, f"   점프 자리에 n20 이 남아 있는 행 {int(left):,} (0 이어야 수리 완료)")

    # ④ 공백을 넘는 선행수익
    nxt = g.date.shift(-1).map(DI)
    lastpos = g.date.transform("max").map(DI)
    gap_next = (nxt - pos != 1) & (pos != lastpos)
    print(f"  ④ 다음 거래일 행이 빈 자리 {int(gap_next.sum()):,}행")
    flag(int((gap_next & K.buy.notna()).sum()) == 0,
         f"   그 자리에 buy 가 남아 있는 행 {int((gap_next & K.buy.notna()).sum()):,} (0 이어야 정상)")
    for h in (20, 60):
        sp = g.date.shift(-h).map(DI)
        endlife = (pos + h) > lastpos
        spanbad = (~endlife) & (sp - pos != h) & K[f"n{h}"].notna()
        flag(int(spanbad.sum()) == 0, f"   보유 {h}일 구간이 공백을 지나는데 n{h} 가 남은 행 {int(spanbad.sum()):,}")

    # ⑤ 거래량 0
    v0 = K.volume.fillna(0) <= 0
    print(f"  ⑤ 거래량 0 행 {int(v0.sum()):,} ({v0.mean()*100:.2f}%) · 그 중 buy 있음 {int((v0 & K.buy.notna()).sum()):,} · n20 있음 {int((v0 & K.n20.notna()).sum()):,}")
    # 거래량 0 이 며칠씩 이어지는 종목-구간(정지)이 몇 개인가
    v0s = v0.astype(int)
    runs = (v0s.groupby([K.ticker, (v0s != v0s.groupby(K.ticker).shift()).cumsum()]).sum())
    print(f"     거래량 0 이 5일 이상 이어진 구간 {int((runs >= 5).sum()):,}개")

    # ⑥ 날짜별 종목 수
    cnt = K.groupby("date").size()
    med = cnt.rolling(60, min_periods=20, center=True).median()
    thin = cnt[(cnt < med * 0.6)]
    flag(len(thin) == 0, f"⑥ 종목 수가 주변 중앙값의 60% 미만인 날 {len(thin)}일" + (f" — 예: {', '.join(f'{d}({n})' for d, n in list(thin.items())[:6])}" if len(thin) else ""))

    # ⑦ 연도별 결측률
    print("  ⑦ 주요 피처 연도별 결측률(%)")
    feats = [c for c in ("amt20", "marcap", "PBR", "PER", "srd", "부채비율", "u", "up") if c in K.columns]
    yr = K.date.str[:4]
    tab = K[feats].isna().groupby(yr).mean().mul(100).round(0)
    show = tab.loc[[y for y in tab.index if y in ("2005", "2010", "2015", "2016", "2018", "2020", "2023", "2026")]]
    print("     " + show.to_string().replace("\n", "\n     "))

    # ⑧ 피처 상식
    print("  ⑧ 피처 상식 검사")
    if "fromhi" in K: flag(K.fromhi.max() <= 0.5, f"   fromhi 최대 {K.fromhi.max():.2f} (≤0 이어야)")
    if "fromlo" in K: flag(K.fromlo.min() >= -0.5, f"   fromlo 최소 {K.fromlo.min():.2f} (≥0 이어야)")
    for c in ("ret20", "ret60", "ret250"):
        if c in K:
            s = K[c].dropna(); print(f"     {c}: 최소 {s.min():,.0f} · 최대 {s.max():,.0f} · 100%↑ {int((s > 100).sum()):,}")
    if "dma20" in K: print(f"     dma20 |x|>50%: {int((K.dma20.abs() > 50).sum()):,}행")

    # ⑨ 선행수익 재계산 대조 — 공백 없는 자리 2,000개 표본
    ok_rows = K.index[(~gap_next) & K.n20.notna() & K.buy.notna()]
    if len(ok_rows):
        smp = np.random.default_rng(0).choice(ok_rows, min(2000, len(ok_rows)), replace=False)
        cl20 = g.close.shift(-20)
        re = (cl20.loc[smp] / K.buy.loc[smp] - 1) * 100 - K.cost.loc[smp]
        dif = (re - K.n20.loc[smp]).abs()
        big = int((dif > 0.05).sum())
        flag(big == 0, f"⑨ n20 재계산 불일치(>0.05%p) {big}/{len(smp)}  (최대 차이 {dif.max():.3f}%p)")
        if big:
            ex = K.loc[smp][dif > 0.05].head(3)[["date", "ticker", "n20"]]
            print("     예:", ex.to_dict("records"))

    # ⑩ 이음새
    print("  ⑩ 이음새 — 경계일 전종목 하룻밤 변화 분포 (중앙값 · |1%|↑ 비율)")
    ud_arr = np.array(ud)
    for b in ("20151230", "20160104", "20171228", "20180102", "20221229", "20230102"):
        i = np.searchsorted(ud_arr, b)
        if i >= len(ud_arr) or i == 0: continue
        d1, d0 = ud_arr[i], ud_arr[i - 1]
        a = K[K.date == d0].set_index("ticker").close
        c = K[K.date == d1].set_index("ticker").close
        j = a.index.intersection(c.index)
        if len(j) < 100: continue
        ch = (c[j] / a[j] - 1) * 100
        print(f"     {d0}→{d1}: {len(j):,}종목 · 중앙 {ch.median():+.2f}% · |5%|↑ {(ch.abs() > 5).mean()*100:.1f}% · |30%|↑ {(ch.abs() > 30).mean()*100:.2f}%")

    # ⑫ buy == 다음 행 시가?
    if "open" in K.columns:
        nopen = g.open.shift(-1)
        m = K.buy.notna() & nopen.notna()
        mis = int(((K.buy - nopen).abs() > 1e-3)[m].sum())
        flag(mis == 0, f"⑫ buy ≠ 다음 행 시가 {mis:,}/{int(m.sum()):,}")
    else:
        print("  ⑫ open 열 없음 — buy 검증 생략")

    # ⑬ 미국 티커 표기
    if mk == "US":
        t = pd.Series(K.ticker.unique())
        norm = t.str.replace(".", "-", regex=False)
        dups = norm[norm.duplicated(keep=False)]
        flag(len(dups) == 0, f"⑬ '.'/'-' 표기만 다른 티커 쌍 {len(dups)//2}개" + (f" 예 {list(t[norm.isin(dups)][:6])}" if len(dups) else ""))
        few = g.size(); print(f"     행 수 60 미만 종목 {int((few < 60).sum()):,}개 (신규상장·ETF 껍데기)")
        if "pref" in K: print(f"     우선주 표시 {int(K.pref.fillna(False).sum()):,}행")

    # ⑭ 폐지 청산 — 마지막 행 근처에서 n60 이 마지막 종가로 대체된 행들
    endl = (pos + 60) > lastpos
    endl = endl & K.n60.notna() & (lastpos < len(ud) - 61)   # 패널 끝(현재)이 아니라 '진짜 끊긴' 종목만
    if endl.sum():
        s = K.n60[endl]
        print(f"  ⑭ 데이터가 끊긴 종목의 끝 60일 안 신호 {int(endl.sum()):,}행 · n60 평균 {s.mean():+.1f}% · 중앙 {s.median():+.1f}% · -50%↓ {(s < -50).mean()*100:.1f}%")
        print("     (마지막 종가로 팔았다고 가정한 값 — 정리매매 후 0 근처면 이미 손실이 반영된 것, 인수합병이면 이익)")
    del K, g; gc.collect()


def kr_lim(K):
    return np.where(K.date.values < "20150615", 0.15, 0.30) + 0.10


def us_lim(K):
    return 0.50   # 미국은 제한폭이 없다 — 하룻밤 ±50% 는 분할 미조정이거나 진짜 사건


def audit_db():
    sec("[DB] kospi.db 원본")
    c = sqlite3.connect(f"file:{BASE}/data/kospi.db?mode=ro", uri=True, timeout=600)
    q = lambda s: pd.read_sql(s, c)
    n = q("SELECT COUNT(*) n FROM daily").n[0]
    dup = q("SELECT COUNT(*) n FROM (SELECT ticker,date FROM daily GROUP BY ticker,date HAVING COUNT(*)>1)").n[0]
    z = q("SELECT COUNT(*) n FROM daily WHERE close<=0 OR close IS NULL").n[0]
    o0 = q("SELECT COUNT(*) n FROM daily WHERE open<=0 OR open IS NULL").n[0]
    nm = q("SELECT COUNT(*) n FROM daily WHERE market IS NULL").n[0]
    v0 = q("SELECT COUNT(*) n FROM daily WHERE volume=0").n[0]
    nn = q("SELECT COUNT(*) n FROM daily WHERE name IS NULL").n[0]
    print(f"  행 {n:,}")
    flag(dup == 0, f"⑪ (ticker,date) 중복 키 {dup:,}")
    print(f"     close≤0/NULL {z:,} · open≤0/NULL {o0:,} · market NULL {nm:,} · volume 0 {v0:,} · name NULL {nn:,}")
    # 하룻밤 제한폭 초과 (수정주가 미적용 흔적) — DB 단계에서 얼마나 있나
    j = q("""SELECT COUNT(*) n FROM (
             SELECT ticker,date,close, LAG(close) OVER (PARTITION BY ticker ORDER BY date) pc FROM daily
           ) WHERE pc>0 AND (close/pc>1.4 OR close/pc<0.6)""").n[0]
    print(f"     일간 ±40% 초과 변화 {j:,}행 (감자·병합·액면분할 미조정 후보)")
    # 시장별·연도별 종목 수 (수집이 빠진 해)
    t = q("SELECT substr(date,1,4) y, market, COUNT(DISTINCT ticker) k FROM daily WHERE market IS NOT NULL GROUP BY y, market")
    piv = t.pivot(index="y", columns="market", values="k").fillna(0).astype(int)
    print("     연도별 종목 수:")
    print("     " + piv.T.to_string().replace("\n", "\n     "))
    c.close()


if WHAT in ("kr", "all"): audit_panel("KR", "kr_scan.pkl", "KR", kr_lim)
if WHAT in ("us", "all"): audit_panel("US", "us_scan.pkl", "US", us_lim)
if WHAT in ("db", "all"): audit_db()
log("끝")
