# -*- coding: utf-8 -*-
"""2026-11-14 계좌 비교 2단계 — [반대매매](P9 갭-3%·7일) 거래 목록. crmap8_1112.run 그대로(보수: 체결 손해 + 체결률 1/(1+3p)).
결과 C:/temp/kp/mix_p9.pkl : {(종목당, 하루 상한): 거래표(date·sell·inv·pnl)}"""
import sys, re, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "crmap8_1112.py").read_text(encoding="utf-8").replace(chr(13), "")
KEY = "    z = z[z.inv > 0].copy()" + chr(10)
assert KEY in src
src = src.split("OUT = []; P = lambda")[0]
src = src.replace(KEY, KEY + "    if RET_Z: return z" + chr(10))
ns = {"__file__": str(ROOT / "crmap8_1112.py"), "__name__": "x", "RET_Z": True}
exec(compile(src, "crmap8", "exec"), ns)
R = {}
for amt, dc in ((200e4, 5e7), (200e4, 1e8), (300e4, 1e8)):
    z = ns["run"](-3, 7, amt, dc, False)
    R[(amt, dc)] = z[["date", "sell", "t", "inv", "net", "pnl"]].reset_index(drop=True)
    w = z[(z.date >= "20250401") & (z.date <= "20261008")]
    print(amt, dc, len(z), "창 안", len(w), "손익 %.0f만" % (w.pnl.sum() / 1e4))
pickle.dump(R, open(r"C:\temp\kp\mix_p9.pkl", "wb"))
