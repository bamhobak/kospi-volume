# -*- coding: utf-8 -*-
"""레이아웃 1개 × 색·타이포 컨셉 4개 → .dc.html 아트보드 생성
   레이아웃을 완전히 동일하게 유지해야 색상 비교가 정직해진다.
"""
import io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
OUT = Path(__file__).parent

# ── 컨셉: 토큰 + 폰트만 다르다 ────────────────────────────────
ALL = {
"Cobalt": dict(
  label="현행 코발트 (다듬음)",
  fonts="family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600",
  sans="'IBM Plex Sans KR'", mono="'IBM Plex Mono'", disp="'IBM Plex Sans KR'",
  dispw="700", tracking="-.4px", radius="13px", radius_s="9px",
  bg="#0f1218", panel="#171b24", panel2="#1e2330", rail="#141821", line="#2a3040",
  txt="#e6e9ef", mut="#8b93a5", dim="#5f677a", faint="#3f4759",
  kp="#4f8cff", kpS="#93b6ff", kpBg="#1d2942",
  kq="#f5a623", kqS="#f3c169", kqBg="#302713", kqInk="#0f1218",
  up="#ff8a8a", dn="#8ab4ff", ok="#38c98b", hotBg="#ff5b5b22"),

"ConceptEmber": dict(
  label="엠버 — 따뜻한 터미널",
  fonts="family=Gothic+A1:wght@400;500;700;900&family=JetBrains+Mono:wght@500;700",
  sans="'Gothic A1'", mono="'JetBrains Mono'", disp="'Gothic A1'",
  dispw="900", tracking="-.6px", radius="6px", radius_s="4px",
  bg="#12100d", panel="#1a1713", panel2="#221e18", rail="#161310", line="#332c22",
  txt="#f0e9dd", mut="#9c9384", dim="#6e675b", faint="#4a453c",
  kp="#ffb057", kpS="#ffca8f", kpBg="#33240f",
  kq="#7ad0c0", kqS="#a3e0d5", kqBg="#12302b", kqInk="#0d1a17",
  up="#ff7a63", dn="#5fa8d3", ok="#9fc46a", hotBg="#ff7a6322"),

"ConceptPaper": dict(
  label="페이퍼 — 리서치 리포트",
  fonts="family=Nanum+Myeongjo:wght@400;700;800&family=Noto+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500;600",
  sans="'Noto Sans KR'", mono="'IBM Plex Mono'", disp="'Nanum Myeongjo'",
  dispw="800", tracking="-.2px", radius="4px", radius_s="3px",
  bg="#f4f1ea", panel="#fffdf8", panel2="#eae7de", rail="#efece4", line="#d9d4c8",
  txt="#1c1a17", mut="#5f5a51", dim="#8a847a", faint="#b3ada1",
  kp="#1f4fa8", kpS="#1f4fa8", kpBg="#e3e9f5",
  kq="#a35a00", kqS="#a35a00", kqBg="#f6ead6", kqInk="#fffdf8",
  up="#b8332b", dn="#1f4fa8", ok="#256b46", hotBg="#b8332b18"),

"Main": dict(
  label="잉크 — 채택안",
  fonts="family=Gothic+A1:wght@400;500;700;900&family=IBM+Plex+Mono:wght@500;600",
  sans="'Gothic A1'", mono="'IBM Plex Mono'", disp="'Gothic A1'",
  dispw="900", tracking="-.8px", radius="0px", radius_s="0px",
  bg="#08090b", panel="#0e1013", panel2="#15181d", rail="#0b0d10", line="#23272e",
  txt="#f4f6f9", mut="#7d848f", dim="#565c66", faint="#3a3f47",
  kp="#5eead4", kpS="#5eead4", kpBg="#0d2b26",
  kq="#ffd60a", kqS="#ffd60a", kqBg="#2b2405", kqInk="#08090b",
  up="#fb7185", dn="#60a5fa", ok="#4ade80", hotBg="#fb718522"),
}

LAYOUT = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?{fonts}&display=swap">
  <style>
    body{{margin:0;font-family:{sans},Pretendard,-apple-system,'Malgun Gothic',sans-serif;
         font-size:13px;background:{bg};color:{txt};-webkit-font-smoothing:antialiased}}
    a{{color:{kp}}}a:hover{{color:{kpS}}}
    .n{{font-family:{mono},ui-monospace,monospace;font-variant-numeric:tabular-nums}}
    .k{{color:{dim};font-size:10px;font-weight:700;letter-spacing:.08em}}
  </style>
</helmet>

<div style="width:1440px;height:900px;display:flex;flex-direction:column;background:{bg};overflow:hidden">

  <!-- 상단 바 -->
  <div style="display:flex;align-items:center;gap:18px;padding:0 20px;height:52px;flex:none;
              background:{panel};border-bottom:1px solid {line}">
    <div style="font-family:{disp};font-weight:{dispw};font-size:16px;letter-spacing:{tracking}">
      밤호박 <span style="color:{kp}">종목 선별기</span></div>
    <div style="width:1px;height:18px;background:{line}"></div>
    <div style="display:flex;align-items:baseline;gap:7px">
      <span style="color:{dim};font-size:11px;font-weight:700">KOSPI</span>
      <span class="n" style="font-size:14px;font-weight:600;color:{up}">6,788.88</span>
      <span class="n" style="font-size:11px;color:{up};opacity:.75">+0.42%</span></div>
    <div style="display:flex;align-items:baseline;gap:7px">
      <span style="color:{dim};font-size:11px;font-weight:700">KOSDAQ</span>
      <span class="n" style="font-size:14px;font-weight:600;color:{up}">838.41</span>
      <span class="n" style="font-size:11px;color:{up};opacity:.75">+0.19%</span></div>
    <div style="display:flex;align-items:center;gap:7px;padding:4px 11px;border-radius:{radius_s};
                background:{panel2};border:1px solid {line}">
      <span style="width:6px;height:6px;border-radius:999px;background:{ok};display:inline-block"></span>
      <span style="color:{mut};font-size:11px">코스피 60일선 <b style="color:{txt}">아래</b> · P3·D1 활성</span></div>
    <div style="flex-grow:1"></div>
    <span class="n" style="color:{dim};font-size:11px">08-30 18:30 갱신</span>
  </div>

  <div style="display:flex;flex-grow:1;min-height:0">

    <!-- 좌측 레일 (A안) -->
    <div style="width:212px;flex:none;background:{rail};border-right:1px solid {line};
                display:flex;flex-direction:column;padding:14px 10px;gap:15px;overflow:hidden">

      <div style="display:flex;flex-direction:column;gap:4px">
        <div class="k" style="padding:0 8px 4px">오늘 할 일</div>
        <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:{radius_s};
                    background:{panel2};border:1px solid {up}55">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="{up}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 7h-9M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/></svg>
          <span style="font-weight:600">보유 종목</span><span style="flex-grow:1"></span>
          <span class="n" style="font-weight:700;color:{up}">8</span></div>
        <div style="display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:{radius_s};
                    background:{panel2};border:1px solid {line}">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="{mut}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/></svg>
          <span style="font-weight:600;color:{mut}">매수 대기</span><span style="flex-grow:1"></span>
          <span class="n" style="font-weight:700;color:{dim}">0</span></div>
        <div style="display:flex;align-items:center;gap:9px;padding:9px 10px">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="{dim}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
          <span style="color:{dim}">완료</span><span style="flex-grow:1"></span>
          <span class="n" style="color:{dim}">0</span></div>
      </div>

      <div style="display:flex;flex-direction:column;gap:4px">
        <div class="k" style="padding:0 8px 4px">규칙</div>
        {rules}
      </div>

      <div style="display:flex;flex-direction:column;gap:4px">
        <div class="k" style="padding:0 8px 4px">조회</div>
        <div style="display:flex;align-items:center;gap:9px;padding:8px 10px">
          <span style="width:5px;height:15px;border-radius:2px;background:{kp};opacity:.25"></span>
          <span style="color:{mut}">코스피 전체</span><span style="flex-grow:1"></span>
          <span class="n" style="color:{dim}">944</span></div>
        <div style="display:flex;align-items:center;gap:9px;padding:8px 10px">
          <span style="width:5px;height:15px;border-radius:2px;background:{kq};opacity:.25"></span>
          <span style="color:{mut}">코스닥 전체</span><span style="flex-grow:1"></span>
          <span class="n" style="color:{dim}">1,823</span></div>
      </div>

      <div style="flex-grow:1"></div>
      <div style="padding:11px;border-radius:{radius_s};background:{panel2};border:1px solid {line}">
        <div class="k" style="margin-bottom:7px">업종 60일 최약</div>
        <div style="display:flex;flex-direction:column;gap:5px;font-size:11px">
          <div style="display:flex;justify-content:space-between"><span style="color:{mut}">전자장비와기기</span><span class="n" style="color:{dn}">-26.1%</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:{mut}">복합기업</span><span class="n" style="color:{dn}">-23.5%</span></div>
          <div style="display:flex;justify-content:space-between"><span style="color:{mut}">자동차</span><span class="n" style="color:{dn}">-22.6%</span></div>
        </div>
      </div>
    </div>

    <!-- 본문: 규칙 헤더 + 신호 카드 (C안) -->
    <div style="flex-grow:1;min-width:0;display:flex;flex-direction:column;padding:18px 20px;gap:14px;overflow:hidden">

      <div style="display:flex;align-items:flex-start;gap:16px;flex:none">
        <div style="flex-grow:1;min-width:0">
          <div style="display:flex;align-items:center;gap:9px">
            <span class="n" style="font-size:11px;font-weight:700;color:{kqInk};background:{kq};
                                   border-radius:{radius_s};padding:2px 7px">D1</span>
            <span style="font-family:{disp};font-weight:{dispw};font-size:20px;letter-spacing:{tracking}">낙폭과대</span>
            <span style="color:{dim};font-size:12px">코스닥 · 20거래일 보유 · 손절 없음</span>
          </div>
          <div style="color:{mut};font-size:12px;margin-top:5px;line-height:1.55;text-wrap:pretty">
            20거래일 −20% 이상 폭락 · 당일 거래량 직전 20일 평균의 2배 · 외국인 60일 누적 순매수 1%↑ ·
            코스피 60일선 아래 · 소속 업종 60일 −15% 이하
          </div>
        </div>
        <div style="display:flex;gap:8px;flex:none">
          {stats}
        </div>
      </div>

      <!-- 신호 카드 -->
      <div style="background:{panel};border:1px solid {line};border-left:3px solid {kq};
                  border-radius:{radius};padding:19px 21px;display:flex;flex-direction:column;gap:17px;flex:none">

        <div style="display:flex;align-items:flex-start;gap:14px">
          <div style="flex-grow:1;min-width:0">
            <div style="display:flex;align-items:center;gap:9px;margin-bottom:4px">
              <span style="font-family:{disp};font-weight:{dispw};font-size:19px;letter-spacing:{tracking}">코이즈</span>
              <span class="n" style="color:{dim};font-size:12px">121850</span>
            </div>
            <div style="color:{mut};font-size:12px">코스닥 · 반도체 제조업 · 시총 812억</div>
          </div>
          <div style="text-align:right;flex:none">
            <div class="n" style="font-size:23px;font-weight:700;line-height:1.1">557<span style="font-size:13px;color:{mut};font-weight:500">원</span></div>
            <div class="n" style="color:{up};font-size:12px;margin-top:2px">+17 (+3.2%)</div>
          </div>
        </div>

        <div>
          <div class="k" style="margin-bottom:9px">왜 걸렸나</div>
          <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px">
            {why}
          </div>
        </div>

        <div style="display:flex;align-items:center;background:{panel2};border-radius:{radius_s};padding:14px 18px">
          <div style="flex-grow:1"><div class="k" style="margin-bottom:4px">매수</div>
            <div style="font-weight:600">8/31 시가</div></div>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="{faint}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin:0 16px"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          <div style="flex-grow:1"><div class="k" style="margin-bottom:4px">보유</div>
            <div style="font-weight:600">20거래일 · 손절 없음</div></div>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="{faint}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin:0 16px"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          <div style="flex-grow:1"><div class="k" style="margin-bottom:4px">매도</div>
            <div style="font-weight:600">9/26 종가</div></div>
          <div style="flex:none;margin-left:18px">
            <span style="background:{kp};color:{btnInk};border-radius:{radius_s};padding:10px 22px;
                         font-weight:700;display:inline-block">매수 기록</span></div>
        </div>

        <div style="display:flex;align-items:center;gap:9px;color:{dim};font-size:11px;line-height:1.5">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="{kq}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
          <span>D1은 손절이 없습니다. 20거래일 동안 −46%까지 내려간 적이 있고, 그걸 견뎠을 때의 성적이 위 숫자입니다.</span>
        </div>
      </div>

      <!-- 보유 요약 -->
      <div style="background:{panel};border:1px solid {line};border-radius:{radius};padding:15px 19px;flex:none">
        <div style="display:flex;align-items:center;margin-bottom:12px">
          <span class="k">보유 종목</span><span style="flex-grow:1"></span>
          <span class="n" style="color:{mut};font-size:11px">평가손익 <b style="color:{up}">+142만원</b></span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px">
          {holds}
        </div>
      </div>

      <div style="flex-grow:1"></div>
    </div>
  </div>
</div>
</x-dc>
</body>
</html>
"""

RULE = """<div style="display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:{radius_s};{sel}">
          <span style="width:5px;height:15px;border-radius:2px;background:{bar}"></span>
          <span class="n" style="font-weight:700;font-size:11px;color:{idc};width:20px">{rid}</span>
          <span style="color:{namec}{nameb}">{rname}</span><span style="flex-grow:1"></span>
          <span class="n" style="color:{cntc}{cntb}">{cnt}</span></div>"""

STAT = """<div style="background:{panel2};border:1px solid {line};border-radius:{radius_s};padding:8px 13px;text-align:center;min-width:74px">
            <div class="n" style="color:{c};font-size:17px;font-weight:700;line-height:1.15">{v}</div>
            <div style="color:{dim};font-size:10px;margin-top:2px">{l}</div></div>"""

WHY = """<div style="background:{panel2};border-radius:{radius_s};padding:11px 12px">
              <div style="color:{dim};font-size:10px;margin-bottom:5px">{l}</div>
              <div class="n" style="color:{c};font-size:16px;font-weight:700">{v}</div>
              <div style="color:{faint};font-size:10px;margin-top:3px">{s}</div></div>"""

HOLD = """<div style="background:{panel2};border-radius:{radius_s};padding:11px 12px;display:flex;align-items:center;gap:8px">
            <span style="width:4px;height:24px;border-radius:2px;background:{bar}"></span>
            <div style="min-width:0;flex-grow:1">
              <div style="font-weight:600;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{n}</div>
              <div style="color:{dim};font-size:10px;margin-top:1px">{s}</div></div>
            <span class="n" style="font-weight:700;color:{c}">{r}</span></div>"""

def build(name, t):
    t = dict(t)
    t["btnInk"] = "#ffffff" if name in ("Main", "ConceptPaper") else t["bg"]
    rules = []
    for rid, rname, cnt, active in (("P1", "상승초입", "0", False), ("P2", "조정매집", "0", False),
                                    ("P3", "폭락반등", "0", False), ("D1", "낙폭과대", "1", True)):
        kq = rid.startswith("D")
        rules.append(RULE.format(
            radius_s=t["radius_s"],
            sel=f"background:{t['kqBg']};border:1px solid {t['kq']}88" if active else "",
            bar=t["kq"] if kq else t["kp"] + (";opacity:.35" if not active else ""),
            idc=t["kqS"] if kq else t["kpS"], rid=rid,
            namec=t["txt"] if active else t["mut"], nameb=";font-weight:600" if active else "",
            cntc=t["kqS"] if active else t["dim"], cntb=";font-weight:700" if active else "", cnt=cnt,
            rname=rname))
    stats = "".join(STAT.format(**t, c=c, v=v, l=l) for c, v, l in (
        (t["ok"], "70%", "승률"), (t["txt"], "5.18", "PF"),
        (t["up"], "+13.4%", "건당 수익"), (t["mut"], "2.9", "월평균 건")))
    why = "".join(WHY.format(**t, l=l, c=c, v=v, s=s) for l, v, c, s in (
        ("20일 낙폭", "−31.4%", t["dn"], "기준 −20%↓"), ("당일 거래량", "4.1배", t["up"], "기준 2배↑"),
        ("외국인 60일", "+2.4%", t["up"], "기준 1%↑"), ("업종 60일", "−24.0%", t["dn"], "기준 −15%↓"),
        ("코스피 60일선", "아래", t["dn"], "시장 조건 충족")))
    holds = "".join(HOLD.format(**t, bar=bar, n=n, s=s, c=c, r=r) for n, s, r, c, bar in (
        ("일신석재", "P3 · 11일차", "+5.2%", t["up"], t["kp"]),
        ("디케이티", "D1 · 4일차", "−2.8%", t["dn"], t["kq"]),
        ("HL만도", "P1 · 매도 도래", "+8.4%", t["up"], t["kp"]),
        ("코이즈", "D1 · 2일차", "+1.4%", t["up"], t["kq"])))
    return LAYOUT.format(**t, rules="\n        ".join(rules), stats=stats, why=why, holds=holds)

CONCEPTS = {"Main": ALL["Main"]}      # 채택: 잉크
for name, t in CONCEPTS.items():
    (OUT / f"{name}.dc.html").write_text(build(name, t), encoding="utf-8")
    print(f"  {name}.dc.html  —  {t['label']}")
print(f"\n{len(CONCEPTS)}개 아트보드 생성 (레이아웃 동일, 토큰만 다름)")
