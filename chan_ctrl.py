# -*- coding: utf-8 -*-
"""채널이 정말 보태는가 — 대조군 비교.

chan_test.py 에서 [코스피] 하락채널 하단이탈 + 업종 + 이격 하나가 살아남았다.
그런데 '업종 -10% + 25일선 -12%' 는 우리 [업종붕괴 이탈]·[깊은 이격] 이 이미 쓰는 재료다.
채널이 보탠 게 있는지, 아니면 우리 재료가 일하고 채널은 표본만 줄인 건지 갈라야 한다.
대조군: 같은 재료에서 **채널 조건만 뺀 것**.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
# ⚠ chan_test.py 를 그대로 exec 하면 그 안의 stdout 재감싸기가 우리 래퍼의 버퍼를 닫는다.
#   그 한 줄만 빼고 머리 부분을 가져온다(채널 계산·로딩·stat 재사용).
_src = open("chan_test.py", encoding="utf-8").read().split("NT, ROWS = 0, []")[0]
_src = _src.replace('sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")', "")
exec(_src)
import verdict, pandas as pd
NT, ROWS = 0, []
HDR = (f"    {'조건':<34}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
       f"{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")
def show(K, mk, nm, m):
    global NT
    for h in HS:
        NT += 1
        r = stat(K, mk, m, h, nm)
        if r is None: continue
        r["mk"] = mk; ROWS.append(r)
        print(f"    {nm:<34}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
              f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
              f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")
for K, mk in ((KP,"KOSPI"),(KQ,"KOSDAQ")):
    b = base(K) & K.pos.notna()
    dn = K.slope < -20
    out_lo = K.pos <= -1.5
    mat = (K.u <= -10) & (K.dev25 <= -12)          # 우리 재료(업종붕괴 + 이격)
    print("="*128); print(f"[{mk}] 채널이 보태는 게 있나 — 같은 재료에서 채널만 빼 본다"); print("="*128)
    print(HDR)
    show(K, mk, "재료만 (업종+이격)",              b & mat)
    show(K, mk, "재료 + 하락채널(위치무관)",        b & mat & dn)
    show(K, mk, "재료 + 하락채널 하단이탈",         b & mat & dn & out_lo)
    show(K, mk, "재료 + 채널 하단이탈(방향무관)",    b & mat & out_lo)
    show(K, mk, "채널 하단이탈만 (재료 없음)",      b & dn & out_lo)
    print()
verdict.log_trials("채널 대조군", NT)
print(f"시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
