# -*- coding: utf-8 -*-
"""규칙별 **최악 거래**가 어디서 나오나 (2026-09-12).

물음: "트레일링이 걸려 있으니 -90% 까지 갈 일은 없는 거지?"

  ① 트레일링이 걸린 규칙은 P1·P4·P6 **셋뿐**이다. 나머지 여섯은 스탑이 없다.
  ② 트레일링이 걸린 규칙에서도 -8% 아래로 뚫리는가 — 뚫린다면 왜인가.
  ③ 실제 계좌 체결(L)과 전체 신호(S)를 나눠 본다. 자리 제한이 최악을 걸러주기도 한다.

portfolio.py 를 그대로 실행해 같은 코드·같은 패널을 쓴다.

    python worst_trades.py
"""
import sys, io, warnings, contextlib
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

print("## portfolio.py 실행 중 — 아래는 그 출력")
exec(open("portfolio.py", encoding="utf-8").read(), globals())
print("\n## 여기서부터 최악 거래 분석")

W = 104
print("=" * W)
print("① 트레일링 설정")
print("=" * W)
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    t = TRAIL.get(rid)
    print(f"  {rid:<4} {'트레일 -8%' if t else '스탑 없음 — 정해진 날까지 그냥 보유'}")

# 전체 신호 기준 수익률
S2 = S.copy()
S2["ret"] = (S2.exit / S2.buy - 1) * 100 - S2.cost      # cost 는 이미 %p 단위(세금+슬리피지)
print(f"\n  비용(세금 0.15% + 슬리피지) 분포: 중앙 {S2.cost.median():.2f}%p · "
      f"최소 {S2.cost.min():.2f} · 최대 {S2.cost.max():.2f}")

print("\n" + "=" * W)
print("② 규칙별 최악 — 전체 신호(S) 기준 · 비용 차감")
print("=" * W)
print(f"  {'규칙':<5}{'트레일':>7}{'신호':>7}{'평균':>8}{'중앙':>8}{'승률':>7}{'하위5%':>9}{'최악':>9}{'-30%↓':>8}{'-50%↓':>8}")
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    z = S2[S2.rid == rid]
    if not len(z): continue
    t = "-8%" if TRAIL.get(rid) else "없음"
    print(f"  {rid:<5}{t:>7}{len(z):>7,}{z.ret.mean():>8.2f}{z.ret.median():>8.2f}"
          f"{(z.ret>0).mean()*100:>6.0f}%{z.ret.quantile(0.05):>9.1f}{z.ret.min():>9.1f}"
          f"{(z.ret<=-30).mean()*100:>7.2f}%{(z.ret<=-50).mean()*100:>7.2f}%")

print("\n" + "=" * W)
print("③ 트레일링이 걸린 규칙이 -8% 아래로 뚫린 비율 — 왜 스탑이 못 막나")
print("=" * W)
print("  트레일링은 **종가로 판정하고 그 가격에 체결된다고 가정**한다. 현실에서 뚫리는 길:")
print("    · 갭 — 종가 판정 뒤 다음 시가가 훨씬 아래")
print("    · 하한가 잠김 — 팔 상대가 없다")
print("    · 보유 마지막날 — 트레일이 안 걸린 채 만기 청산")
for rid in ["P1", "P4", "P6"]:
    z = S2[S2.rid == rid]
    if not len(z): continue
    # 가정대로면 손실은 -8% - 비용 근처가 바닥이어야 한다
    floor = -8 - z.cost.mean()
    thru = z[z.ret < floor - 0.5]
    print(f"\n  {rid}: 신호 {len(z):,}건 · 가정상 바닥 {floor:.2f}%")
    print(f"     그 아래로 뚫린 거래 {len(thru):,}건 ({len(thru)/len(z)*100:.1f}%)"
          f" · 그중 최악 {z.ret.min():.1f}%")
    if len(thru):
        print(f"     뚫린 거래 평균 {thru.ret.mean():.1f}% · 중앙 {thru.ret.median():.1f}%"
              f" · -30% 아래 {int((thru.ret<=-30).sum()):,}건")

print("\n" + "=" * W)
print("④ 실제 계좌가 체결한 거래(L) — 자리 제한을 통과한 것만")
print("=" * W)
print(f"  {'규칙':<5}{'체결':>7}{'평균':>8}{'중앙':>8}{'승률':>7}{'최악':>9}{'계좌 타격':>11}")
for rid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]:
    z = L[L.rid == rid]
    if not len(z): continue
    w = z.loc[z.ret.idxmin()]
    print(f"  {rid:<5}{len(z):>7,}{z.ret.mean():>8.2f}{z.ret.median():>8.2f}"
          f"{(z.ret>0).mean()*100:>6.0f}%{z.ret.min():>9.1f}{w.amt*w.ret:>10.2f}%p")
print("\n  '계좌 타격' = 그 한 건이 계좌 전체에 낸 손실. 종목당 비중이 3~15%라 -90% 라도")
print("  계좌로는 그만큼 안 아프다. 이게 비중 제한이 하는 일이다.")

print("\n" + "=" * W)
print("⑤ 최악 거래 열 건 — 어느 규칙·어느 날")
print("=" * W)
w = S2.nsmallest(10, "ret")[["date", "ticker", "name", "rid", "buy", "exit", "ret"]]
print(w.to_string(index=False))
