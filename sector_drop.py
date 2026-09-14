# -*- coding: utf-8 -*-
"""**의료·바이오를 빼면 계좌가 어떻게 되나** (2026-09-14 요청).

물음: "지금 조건 다 그대로 가져가되, 의료나 바이오 쪽 종목들은 빼고 실측하면 어떻게 바뀌나"

규칙은 손대지 않는다. **유니버스에서 그 종목들만 지우고** 같은 규칙을 돌린다.
빠진 자리는 다른 종목이 채운다 — 그래서 규칙 단위 평균이 아니라 **계좌로 판정한다**.

읽는 법
  ① 신호의 몇 %가 의료·바이오인가 · 업종을 모르는 신호는 몇 %인가(= 실측의 한계)
  ② 의료·바이오 **만** 모아 돌리면 어떤가 — 여기가 나쁘지 않으면 뺄 이유가 없다
  ③ 계좌: 기준 vs 제외. 자리가 비면 노출이 줄어 수익도 주는 게 당연하므로
     **같은 노출로 맞춘 짝비교**를 함께 본다
  ④ 랜덤 시드 짝비교 — 같은 시드에서 둘을 견줘 자리 경쟁의 운을 지운다
  ⑤ 규칙별·연도별

⚠ 한계: 업종 자료는 **현재 스냅샷**이다. 폐지된 종목은 업종을 모르고, 모르는 것은
   '의료·바이오가 아니다' 로 취급해 **남는다**. 즉 이 실측은 제외를 조금 **덜** 한 쪽이다.

    python sector_drop.py            (시드 12)
    python sector_drop.py 30         (시드 30)
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
W = 96


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


# ── 의료·바이오 집합 — 서로 다른 세 자료의 합집합 ──────────────────────────
# 하나만 쓰면 구멍이 크다: KRX 표준산업분류(industry.csv)는 현재 상장분뿐이고,
# GICS 풍 업종(upjong)은 '기타' 가 1,237종목이다. 셋 중 하나라도 부르면 뺀다.
KRX_H = {"기초 의약물질 제조업", "의료용 기기 제조업", "의료용품 및 기타 의약 관련제품 제조업",
         "의약품 제조업", "자연과학 및 공학 연구개발업"}
UPJ_H = {"제약", "건강관리장비와용품", "생물공학", "생명과학도구및서비스",
         "건강관리업체및서비스", "건강관리기술"}
THM_H = {"바이오텍(biotechnology)", "의료기기", "제약업체", "바이오시밀러(복제 바이오의약품)",
         "의료AI", "코로나19(진단/치료제/백신 개발 등)", "코로나19(진단키트)",
         "백신/진단시약/방역(신종플루, AI 등)"}
# 생명보험·손해보험은 뺀다 — 분류상 금융이지 의료·바이오가 아니다.


def kr_health():
    ind = pd.read_csv(BASE / "data/industry.csv", dtype={"ticker": str})
    a = set(ind[ind.industry.isin(KRX_H)].ticker)
    sec_ = pd.read_pickle(BASE / "data/upjong_input.pkl")["sector"].copy()
    sec_["ticker"] = sec_.ticker.astype(str).str.zfill(6)
    u = sec_[sec_.kind == "upjong"]
    b = set(u[u.gname.isin(UPJ_H)].ticker)
    t = sec_[sec_.kind == "theme"]
    c = set(t[t.gname.isin(THM_H)].ticker)
    known = set(ind.ticker) | set(u.ticker)          # 업종을 아는 종목(테마는 일부뿐이라 뺀다)
    return (a | b | c), known, dict(KRX=len(a), 업종=len(b), 테마=len(c))


HEALTH, KNOWN, BRK = kr_health()
print(f"의료·바이오 {len(HEALTH):,}종목 (자료별 {BRK}) · 업종을 아는 종목 {len(KNOWN):,}")

# ── portfolio.py 를 그대로 쓴다 (규칙·패널·시뮬 전부 정본) ────────────────
t0 = time.time()
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS", 1)[0]
G = {"__name__": "pf", "__file__": str(BASE / "portfolio.py")}
exec(compile(SRC, "portfolio.py", "exec"), G)
S0, simulate, dates = G["S"], G["simulate"], G["dates"]
print(f"  패널·신호 준비 {time.time()-t0:.0f}초")

isH = S0.ticker.isin(HEALTH)
isK = S0.ticker.isin(KNOWN)
sec("① 신호에서 의료·바이오가 차지하는 몫")
print(f"  {'규칙':<5}{'전체신호':>9}{'의료·바이오':>11}{'비중':>7}{'업종 미상':>10}{'미상비중':>9}")
for rid in sorted(S0.rid.unique()):
    z = S0.rid == rid
    n, h, k = int(z.sum()), int((z & isH).sum()), int((z & ~isK).sum())
    print(f"  {rid:<5}{n:>9,}{h:>11,}{h/n:>7.1%}{k:>10,}{k/n:>9.1%}")
n, h, k = len(S0), int(isH.sum()), int((~isK).sum())
print(f"  {'전체':<5}{n:>9,}{h:>11,}{h/n:>7.1%}{k:>10,}{k/n:>9.1%}")
print("  ⚠ '업종 미상' 은 제외되지 않고 남는다 — 그만큼 이 실측은 제외를 덜 한 쪽이다")

# ── ② 의료·바이오만 모아 돌리면 ──────────────────────────────────────────
sec("② 의료·바이오 '만' 으로 돌린 계좌 — 여기가 멀쩡하면 뺄 이유가 없다")
G["S"] = S0[isH].reset_index(drop=True)
simulate(1.0, 1.0, "의료·바이오만")
G["S"] = S0[~isH].reset_index(drop=True)
simulate(1.0, 1.0, "의료·바이오 제외")
G["S"] = S0
CB, LB = simulate(1.0, 1.0, "기준(지금 그대로)")

# ── ③ 같은 노출로 맞춘 짝비교 ────────────────────────────────────────────
sec("③ 같은 노출로 맞춰 견주기 — 자리가 비어 노출이 준 것과 성적이 준 것은 다르다")
base_expo = CB.expo.mean()
G["S"] = S0[~isH].reset_index(drop=True)
lo, hi = 1.0, 3.0
for _ in range(12):                                   # 노출이 기준과 같아지는 배율을 찾는다
    mid = (lo + hi) / 2
    C, _L = simulate(1.0, mid, "", quiet=True)
    if C.expo.mean() < base_expo: lo = mid
    else: hi = mid
scale = (lo + hi) / 2
print(f"  기준 평균노출 {base_expo*100:.0f}% 에 맞추는 배율 {scale:.2f}배")
simulate(1.0, 1.0, "기준", quiet=False) if False else None
G["S"] = S0; simulate(1.0, 1.0, "기준")
G["S"] = S0[~isH].reset_index(drop=True); simulate(1.0, scale, f"제외 · 비중 {scale:.2f}배")

# ── ④ 랜덤 시드 짝비교 ───────────────────────────────────────────────────
sec(f"④ 랜덤 시드 짝비교 ({SEEDS}시드) — 같은 시드 안에서 둘을 견준다")
print("  자리 경쟁 순서를 무작위로 바꿔 '거래대금 큰 순' 이라는 한 경로의 운을 지운다")


def shuffled(S, seed):
    z = S.sample(frac=1.0, random_state=seed)
    return z.sort_values("di", kind="stable").reset_index(drop=True)


rows = []
for s in range(SEEDS):
    G["S"] = shuffled(S0, s);            a, _ = simulate(1.0, 1.0, "", quiet=True)
    G["S"] = shuffled(S0[~isH], s);      b, _ = simulate(1.0, 1.0, "", quiet=True)
    fa, fb = a.nav.iloc[-1], b.nav.iloc[-1]
    da = ((a.nav / a.nav.cummax()) - 1).min() * 100
    db = ((b.nav / b.nav.cummax()) - 1).min() * 100
    rows.append((fa, fb, da, db))
    print(f"  시드 {s:>2}  기준 {fa:>6.2f}배(낙폭 {da:>5.1f}%)   제외 {fb:>6.2f}배(낙폭 {db:>5.1f}%)"
          f"   {'제외 승' if fb > fa else '기준 승'}")
R = pd.DataFrame(rows, columns=["기준", "제외", "낙폭기준", "낙폭제외"])
print(f"\n  중앙값   기준 {R.기준.median():.2f}배 · 제외 {R.제외.median():.2f}배")
print(f"  최종자산 제외 승 {int((R.제외 > R.기준).sum())}/{len(R)}"
      f" · 낙폭 제외 승(덜 아픔) {int((R.낙폭제외 > R.낙폭기준).sum())}/{len(R)}")

# ── ⑤ 규칙별·연도별 ──────────────────────────────────────────────────────
sec("⑤ 규칙별 기여 · 연도별 (거래대금 큰 순 · 설정 그대로)")
G["S"] = S0[~isH].reset_index(drop=True)
CD, LD = simulate(1.0, 1.0, "제외", quiet=True)
print(f"  {'규칙':<5}{'체결(기준)':>11}{'체결(제외)':>11}{'평균%(기준)':>12}{'평균%(제외)':>12}"
      f"{'승률(기준)':>11}{'승률(제외)':>11}{'기여%p(기준)':>13}{'기여%p(제외)':>13}")
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    x, y = LB[LB.rid == rid], LD[LD.rid == rid]
    if not len(x) and not len(y): continue
    f = lambda z, c: (f"{c(z):>11.2f}" if len(z) else f"{'-':>11}")
    print(f"  {rid:<5}{len(x):>11,}{len(y):>11,}"
          f"{(x.ret.mean() if len(x) else float('nan')):>12.2f}{(y.ret.mean() if len(y) else float('nan')):>12.2f}"
          f"{(x.ret > 0).mean():>10.0%}{(y.ret > 0).mean() if len(y) else float('nan'):>11.0%}"
          f"{(x.amt*x.ret/100).sum()*100:>13.1f}{(y.amt*y.ret/100).sum()*100:>13.1f}")
print(f"\n  {'연도':<6}{'기준':>10}{'제외':>10}{'차이':>10}{'노출기준':>10}{'노출제외':>10}")
for C, col in ((CB, "기준"), (CD, "제외")): C["yr"] = C.date.str[:4]
for y in sorted(CB.yr.unique()):
    a, b = CB[CB.yr == y], CD[CD.yr == y]
    ra = (a.nav.iloc[-1] / a.nav.iloc[0] - 1) * 100
    rb = (b.nav.iloc[-1] / b.nav.iloc[0] - 1) * 100
    print(f"  {y:<6}{ra:>+9.2f}%{rb:>+9.2f}%{rb-ra:>+9.2f}%p"
          f"{a.expo.mean()*100:>9.0f}%{b.expo.mean()*100:>9.0f}%")
print(f"\n총 {time.time()-t0:.0f}초")

# ══════════════════════════════════════════════════════════════════════════
# ⑥ 부분 제외 — ⑤ 에서 **좋아진 규칙에만** 걸어 본다
#
# ⚠ 결과를 보고 나서 고른 조합이다(사후 선택). 좋게 나와도 '유망' 일 뿐 채택 근거가
#    아니다. 판정은 ①~④ 의 전면 제외다. 미장 짝(sector_drop_us.py ⑥)은 기각됐다
#    — 자산 8/30 · 낙폭 3/30.
sec("⑥ [참고·사후선택] 낙폭 계열에만 걸면 — P3·P4·P5·P6·D1·D2 에만 제외 적용")
HIT = {"P3", "P4", "P5", "P6", "D1", "D2"}
S_PART = S0[~(S0.rid.isin(HIT) & isH)].reset_index(drop=True)
print(f"  신호 {len(S0):,} → {len(S_PART):,}건 (전면 제외는 {int((~isH).sum()):,})")
G["S"] = S_PART; simulate(1.0, 1.0, "부분 제외(낙폭 계열만)")
G["S"] = S0;     simulate(1.0, 1.0, "기준")
pw, pd_ = [], []
for s in range(SEEDS):
    G["S"] = shuffled(S0, s);       x, _ = simulate(1.0, 1.0, "", quiet=True)
    G["S"] = shuffled(S_PART, s);   y, _ = simulate(1.0, 1.0, "", quiet=True)
    pw.append(y.nav.iloc[-1] - x.nav.iloc[-1])
    pd_.append(((y.nav/y.nav.cummax())-1).min()*100 - ((x.nav/x.nav.cummax())-1).min()*100)
pw, pd_ = np.array(pw), np.array(pd_)
print(f"  같은 시드에서 자산 큼 {int((pw>0).sum())}/{SEEDS} (차이 중앙 {np.median(pw):+.2f}배)"
      f" · 낙폭 얕음 {int((pd_>0).sum())}/{SEEDS} (차이 중앙 {np.median(pd_):+.1f}%p)")
