# -*- coding: utf-8 -*-
"""외국 기법 실측(H0092~) 보고서를 한 표로 모은다 (2026-09-25).

각 보고서(research/reports/Hxxxx.md)의 판정 줄과 **대표 보유기간(main_hold)** 원안 성적 표를 읽는다.
'근접' = 학습·검증 중앙이 둘 다 양수인데 떨어진 것 — 무엇에 막혔는지 보고 재료로 쓸지 가른다.

    python research/intl_summary.py            → research/reports/intl_summary_YYYYMMDD.md
"""
import json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry

MAP = json.loads((ROOT / "cache" / "intl_map.json").read_text(encoding="utf-8"))
ROW = re.compile(r"^\| (\d+)일 \| (홀드아웃 05~15|학습 16~22|검증 23~|전체 16~) \| ([\d,]+|표본 부족) \|(.*)$")


def parse(hid):
    rp = ROOT / "reports" / f"{hid}.md"
    if not rp.exists():
        return None
    txt = rp.read_text(encoding="utf-8")
    spec = json.loads((ROOT / "specs" / f"{hid}.json").read_text(encoding="utf-8"))
    mh = spec["main_hold"]
    st = {}
    for line in txt.splitlines():
        m = ROW.match(line)
        if m and int(m.group(1)) == mh and m.group(3) != "표본 부족":
            cells = [c.strip() for c in m.group(4).split("|")]
            st[m.group(2)] = dict(n=int(m.group(3).replace(",", "")), med=float(cells[0]), trim=float(cells[1]),
                                  mean=float(cells[2]), win=float(cells[3].rstrip("%")), pos=cells[4],
                                  ci=cells[5])
    v = re.search(r"\*\*판정: (.+?)\*\*", txt)
    why = re.search(r"\*\*❌ \d단계 탈락 — (.+?)\*\*", txt)
    nb = re.findall(r"^\| (.+?) \| [\d,]+ \|.*\| (✅|❌) \|$", txt, re.M)
    dsr = re.search(r"진짜일 확률 ([\d.]+|nan)", txt)
    ov = re.search(r"## 5 기존 규칙과 겹침.*?\n- (\d+)%", txt, re.S)
    return dict(mh=mh, st=st, verdict=v.group(1) if v else "?", why=why.group(1) if why else "",
                nb=f"{sum(1 for _, o in nb if o == '✅')}/{len(nb)}" if nb else "", dsr=dsr.group(1) if dsr else "",
                ov=ov.group(1) if ov else "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    reg = {x["id"]: x for x in registry.load()}
    rows = []
    for k, hid in sorted(MAP.items(), key=lambda kv: kv[1]):
        r = parse(hid)
        if r:
            rows.append((k, hid, reg[hid]["name"], r))
    f = lambda s, key: ("%+.2f" % s[key]) if s else "—"
    out = ["# 외국 기법 실측 요약 · %s" % time.strftime("%Y-%m-%d"), "",
           "대표 보유기간 원안 · 자금 무제한·다 산다 · 익일 시가 · 비용 차감. 중앙·절삭은 %. 통과 기준은 run_spec 0~5단계.", ""]
    stages = {}
    for _, _, _, r in rows:
        stages[r["verdict"]] = stages.get(r["verdict"], 0) + 1
    out += ["**판정 분포**: " + " · ".join("%s %d" % kv for kv in sorted(stages.items())), ""]
    for mk in ("KR", "US"):
        R = [x for x in rows if x[0].endswith("_" + mk)]
        R.sort(key=lambda x: -(x[3]["st"].get("전체 16~", {}).get("med", -99)))
        out += ["## %s (%d개)" % ("국내" if mk == "KR" else "미장", len(R)), "",
                "| 가설 | 기법 | 보유 | 전체 16~ n | 중앙 | 절삭 | 승률 | 학습 중앙 | 검증 중앙 | %s판정 | 이유 |" % ("홀드아웃 중앙 | " if mk == "KR" else ""),
                "|---|---|---|---|---|---|---|---|---|---|---|" + ("---|" if mk == "KR" else "")]
        for k, hid, name, r in R:
            s = r["st"]; a = s.get("전체 16~"); tr = s.get("학습 16~22"); va = s.get("검증 23~"); ho = s.get("홀드아웃 05~15")
            out.append("| %s | %s | %d일 | %s | %s | %s | %s | %s | %s | %s%s | %s |" % (
                hid, name.replace(" [%s]" % mk, "")[:60], r["mh"], f"{a['n']:,}" if a else "—", f(a, "med"), f(a, "trim"),
                ("%.0f%%" % a["win"]) if a else "—", f(tr, "med"), f(va, "med"),
                (f(ho, "med") + " | ") if mk == "KR" else "", r["verdict"], r["why"][:70]))
        out.append("")
        near = [x for x in R if x[3]["st"].get("학습 16~22", {}).get("med", -1) > 0 and x[3]["st"].get("검증 23~", {}).get("med", -1) > 0]
        out += ["**근접(학습·검증 중앙 모두 양수)**: " + (", ".join("%s %s(%s)" % (h, n.split(" ")[0], r["verdict"]) for _, h, n, r in near) or "없음"), ""]
    rp = ROOT / "reports" / ("intl_summary_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out)); print("\n보고서:", rp)


if __name__ == "__main__":
    main()
