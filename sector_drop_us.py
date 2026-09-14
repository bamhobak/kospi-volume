# -*- coding: utf-8 -*-
"""**미장에서 의료·바이오를 빼면 어떻게 되나** (2026-09-14 요청).

국내판(sector_drop.py)의 미장 짝. 규칙 N1~N5 는 손대지 않고 **유니버스에서 의료·바이오만
지운 뒤** 같은 규칙을 돌린다. 미장은 그 몫이 훨씬 크다(전체 6,085종목 중 1,055 = 17%).

규칙 재구성은 us_verify.py 를 그대로 쓴다 — 사이트 신호 건수와 대조까지 끝난 정본이다.
⚠ 단 [자사주 낙폭](N4)은 재구성이 사이트의 2.35배로 헐겁다(us_verify 가 스스로 찍는다).
   그 규칙 하나의 수치는 약하게 볼 것.

⚠ 업종 자료(data/us/tickers.csv)는 **현재 상장 스냅샷**이다. 상장폐지·인수된 종목은
   업종을 몰라 '의료·바이오가 아니다' 로 남는다. 제외를 조금 덜 한 쪽으로 치우친다.

신호표는 캐시한다 — 패널(11.5GB)을 읽고 재료를 만드는 데만 몇 분이 걸리고, 실제로
2026-09-14 에 한 번 중간에 죽어 처음부터 다시 돌렸다. 캐시 파일을 지우면 다시 만든다.

    python sector_drop_us.py          (시드 30)
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CACHE = BASE / "data" / "sector_drop_us_sig.pkl"
W = 100
t0 = time.time()


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


# ── 의료·바이오 집합 ─────────────────────────────────────────────────────
# '생명 및 건강 보험' 은 뺀다 — 분류상 금융이고, 국내에서 생명보험을 남긴 것과 같은 잣대.
H_IND = {"생명 공학 및 의학 연구", "제약", "의료 장비, 물품 및 유통", "첨단 의료 장비 및 기술",
         "의료 시설 및 서비스", "의료 관리", "의약품 소매"}
TK = pd.read_csv(BASE / "data/us/tickers.csv")
HEALTH = set(TK[TK.Industry.isin(H_IND)].Symbol.astype(str))
KNOWN = set(TK.Symbol.astype(str))
print(f"미국 의료·바이오 {len(HEALTH):,}종목 / 업종 아는 종목 {len(KNOWN):,}")

# ── 신호표 (캐시) ────────────────────────────────────────────────────────
if CACHE.exists():
    with open(CACHE, "rb") as f: C = pickle.load(f)
    print(f"  캐시 사용 — 신호 {len(C['S']):,}건 · 거래일 {len(C['DS']):,}")
else:
    print("  캐시 없음 — us_verify.py 로 신호표를 만든다 (몇 분 걸린다)")
    SRC = (BASE / "us_verify.py").read_text(encoding="utf-8").split('NO4 = ["N1"', 1)[0]
    G = {"__name__": "uv", "__file__": str(BASE / "us_verify.py")}
    exec(compile(SRC, "us_verify.py", "exec"), G)
    C = {"S": G["build"](G["ALL5"], None), "DS": G["DS"], "ADI": G["ADI"],
         "ALL5": G["ALL5"], "PCT": {r: G["RULES"][r]["pct"] for r in G["ALL5"]}}
    with open(CACHE, "wb") as f: pickle.dump(C, f)
    print(f"  캐시 저장 {CACHE.name} ({CACHE.stat().st_size/1e6:.0f}MB)")

S_ALL, DS, ADI, ALL5, PCT = C["S"], C["DS"], C["ADI"], C["ALL5"], C["PCT"]


def sim(S, ds, scale=1.0, seed=None, cash_cap=1.0):
    """us_verify.sim 과 같은 규칙 — 자리 상한·비중·현금 제약. 캐시만으로 돌게 옮겨 왔다."""
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] * scale for k in held) / 100)
        g = byd.get(d)
        if g is None: continue
        # 기본은 거래대금 큰 순(정본 정책). 시드를 주면 무작위 — 자리 경쟁의 운을 지운다.
        g = (g.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
             else g.sort_values("amt20", ascending=False, na_position="last"))
        for r in g.itertuples():
            if cnt.get(r.rid, 0) >= r.mx: continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            if sum(PCT[x[0]] * scale for x in held) / 100 + r.pct * scale / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret * r.pct * scale / 100); cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values(): nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


isH = S_ALL.ticker.isin(HEALTH)
isK = S_ALL.ticker.isin(KNOWN)
S_EX = S_ALL[~isH].reset_index(drop=True)     # 의료·바이오 제외
S_ONLY = S_ALL[isH].reset_index(drop=True)    # 의료·바이오만

sec("① 신호에서 의료·바이오가 차지하는 몫 (2016~ · 중복제거 후)")
print(f"  {'규칙':<5}{'전체신호':>9}{'의료·바이오':>11}{'비중':>7}{'업종 미상':>10}{'미상비중':>9}")
for rid in ALL5:
    z = S_ALL.rid == rid
    n, h, k = int(z.sum()), int((z & isH).sum()), int((z & ~isK).sum())
    print(f"  {rid:<5}{n:>9,}{h:>11,}{h/max(n,1):>7.1%}{k:>10,}{k/max(n,1):>9.1%}")
n, h, k = len(S_ALL), int(isH.sum()), int((~isK).sum())
print(f"  {'전체':<5}{n:>9,}{h:>11,}{h/n:>7.1%}{k:>10,}{k/n:>9.1%}")

sec("② 의료·바이오 '만' 으로 돌린 계좌 — 여기가 멀쩡하면 뺄 이유가 없다")
nav, mdd, ex = sim(S_ONLY, DS, 1.0)
print(f"  의료·바이오만   신호 {len(S_ONLY):>6,}건 · 노출 {ex*100:>3.0f}% · {nav:>6.2f}배 · 낙폭 {mdd:>6.1f}%")
print(f"  {'규칙':<5}{'건수':>7}{'평균%':>9}{'중앙%':>9}{'승률':>7}   (비교: 전체)")
for rid in ALL5:
    z, a = S_ONLY[S_ONLY.rid == rid], S_ALL[S_ALL.rid == rid]
    if not len(z): continue
    print(f"  {rid:<5}{len(z):>7,}{z.ret.mean():>+9.2f}{z.ret.median():>+9.2f}{(z.ret>0).mean():>7.0%}"
          f"   전체 평균 {a.ret.mean():>+6.2f} · 중앙 {a.ret.median():>+6.2f} · 승률 {(a.ret>0).mean():>3.0%}")

sec("③ 계좌 — 배율을 바꿔 **같은 노출**에서 견준다 (거래대금 큰 순 · 기준 2016~)")
SCA = (0.6, 0.8, 1.0, 1.2, 1.5, 2.0)
OUT = {}
print(f"  {'구성':<22}{'배율':>5}{'노출':>7}{'자산':>9}{'낙폭':>8}")
for nm, S in (("지금 그대로", S_ALL), ("의료·바이오 제외", S_EX)):
    for sc in SCA:
        nav, mdd, ex = sim(S, DS, sc)
        OUT[(nm, sc)] = (ex * 100, nav, mdd)
        print(f"  {nm if sc == SCA[0] else '':<22}{sc:>5.1f}{ex*100:>6.0f}%{nav:>8.2f}배{mdd:>7.1f}%")
    print(f"    신호 {len(S):,}건")


def at(nm, t):
    p = sorted(OUT[(nm, s)] for s in SCA); xs = [a[0] for a in p]
    if t < xs[0] or t > xs[-1]: return None
    for i in range(len(p) - 1):
        if xs[i] <= t <= xs[i + 1]:
            w = (t - xs[i]) / max(xs[i + 1] - xs[i], 1e-9)
            return p[i][1] + w * (p[i + 1][1] - p[i][1]), p[i][2] + w * (p[i + 1][2] - p[i][2])


TGT = OUT[("지금 그대로", 1.0)][0]
print(f"\n  같은 노출({TGT:.0f}%)로 맞추면")
for nm in ("지금 그대로", "의료·바이오 제외"):
    v = at(nm, TGT)
    print(f"    {nm:<22}" + (f"{v[0]:>8.2f}배   낙폭 {v[1]:>6.1f}%" if v else "   (범위 밖)"))

sec(f"④ 랜덤 {NS}시드 짝비교 (배율 1.0) — 자리 경쟁의 운을 지운다")
res = {}
for nm, S in (("지금 그대로", S_ALL), ("의료·바이오 제외", S_EX)):
    res[nm] = pd.DataFrame([sim(S, DS, 1.0, seed=k) for k in range(NS)],
                           columns=["nav", "mdd", "expo"])
    d = res[nm]
    print(f"  {nm:<20} 중앙 {d.nav.median():>6.2f}배 · 최악 {d.nav.min():>5.2f} · 최고 {d.nav.max():>5.2f}"
          f" · 낙폭 중앙 {d.mdd.median():>6.1f}% · 노출 {d.expo.mean()*100:>3.0f}%")
a, b = res["지금 그대로"], res["의료·바이오 제외"]
dn = b.nav.values - a.nav.values; dm = b.mdd.values - a.mdd.values
print(f"\n  같은 시드에서 제외한 쪽이 자산 큼 {int((dn>0).sum())}/{NS} · 차이 중앙 {np.median(dn):+.2f}배")
print(f"  같은 시드에서 제외한 쪽이 낙폭 얕음 {int((dm>0).sum())}/{NS} · 차이 중앙 {np.median(dm):+.1f}%p")

sec("⑤ 규칙별 — 제외가 어느 규칙을 건드리나")
print(f"  {'규칙':<5}{'신호(지금)':>11}{'신호(제외)':>11}{'평균%지금':>11}{'평균%제외':>11}"
      f"{'중앙%지금':>11}{'중앙%제외':>11}{'승률지금':>10}{'승률제외':>10}")
for rid in ALL5:
    x, y = S_ALL[S_ALL.rid == rid], S_EX[S_EX.rid == rid]
    print(f"  {rid:<5}{len(x):>11,}{len(y):>11,}{x.ret.mean():>11.2f}{y.ret.mean():>11.2f}"
          f"{x.ret.median():>11.2f}{y.ret.median():>11.2f}{(x.ret>0).mean():>9.0%}{(y.ret>0).mean():>10.0%}")
print(f"\n총 {time.time()-t0:.0f}초")

# ══════════════════════════════════════════════════════════════════════════
# ⑥ 부분 제외 — ⑤ 에서 **좋아진 규칙에만** 걸어 본다
#
# ⚠ 이건 결과를 보고 나서 고른 조합이다(사후 선택). 좋게 나와도 그건 '유망' 이지
#    채택 근거가 아니다 — 같은 함정으로 이 프로젝트는 여러 번 속았다. 판정은
#    ①~④ 의 전면 제외이고, 여기는 다음에 따로 검증할 거리를 남기는 자리다.
sec("⑥ [참고·사후선택] 낙폭 계열에만 걸면 — N2·N3·N4 에만 제외 적용")
HIT = {"N2", "N3", "N4"}
mask = ~(S_ALL.rid.isin(HIT) & isH)
S_PART = S_ALL[mask].reset_index(drop=True)
print(f"  신호 {len(S_ALL):,} → {len(S_PART):,}건 (전면 제외는 {len(S_EX):,})")
nav, mdd, ex = sim(S_PART, DS, 1.0)
print(f"  거래대금 큰 순: {nav:>6.2f}배 · 낙폭 {mdd:>6.1f}% · 노출 {ex*100:>3.0f}%"
      f"   (지금 {OUT[('지금 그대로',1.0)][1]:.2f}배 / {OUT[('지금 그대로',1.0)][2]:.1f}%)")
P = pd.DataFrame([sim(S_PART, DS, 1.0, seed=k) for k in range(NS)], columns=["nav", "mdd", "expo"])
dn = P.nav.values - a.nav.values; dm = P.mdd.values - a.mdd.values
print(f"  중앙 {P.nav.median():.2f}배 · 낙폭 중앙 {P.mdd.median():.1f}% · 노출 {P.expo.mean()*100:.0f}%")
print(f"  같은 시드에서 자산 큼 {int((dn>0).sum())}/{NS} (차이 중앙 {np.median(dn):+.2f}배)"
      f" · 낙폭 얕음 {int((dm>0).sum())}/{NS} (차이 중앙 {np.median(dm):+.1f}%p)")
