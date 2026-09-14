# -*- coding: utf-8 -*-
"""손으로 배포할 때 쓰는 자리. 바로 wrangler 를 부르지 말고 **이걸** 부른다.

왜 있나 (2026-09-14 사고):
  손으로 `pipeline.py` 를 돌리고 `wrangler pages deploy site` 를 그대로 쳤더니,
  로컬에 남아 있던 **사흘 묵은 site/data/table_us.json(20260910)** 이 배포본의
  최신본(20260911)을 덮어썼다. 미장 표 기준일 가드가 걸려 미장 규칙이 조용히 죽었고,
  화면에서 해외 종목이 사라졌다. 터지지 않고 조용히 틀리는, 이 프로젝트의 그 부류다.

  워크플로에는 '없으면 배포본에서 되살린다' 가 있지만 **있으면 그냥 쓴다**.
  Actions 는 체크아웃이 늘 깨끗해 그걸로 충분했는데, 내 PC 에는 묵은 파일이 남는다.

그래서 여기서는 '있나' 가 아니라 **'어느 쪽이 최신 거래일인가'** 로 고른다.
누가 만들었는지는 상관없다 — 뒤로 가는 배포만 막으면 된다.
"""
import json, os, pathlib, subprocess, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).resolve().parent
SITE_URL = os.environ.get("SITE_URL", "https://kospi-volume.pages.dev")
GUARDED = ["table.json", "table_us.json", "uscal.json"]   # 거래일이 뒤로 가면 안 되는 것들

for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

HDR = {"User-Agent": "Mozilla/5.0 (compatible; kospi-volume-bot)"}
if os.environ.get("CF_ACCESS_CLIENT_ID"):
    HDR["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
    HDR["CF-Access-Client-Secret"] = os.environ["CF_ACCESS_CLIENT_SECRET"]


def basedate(raw: bytes):
    """그 표가 **몇 일자까지** 담고 있나. 못 읽으면 None — 판단을 포기한다(덮지 않는다)."""
    try:
        d = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    for k in ("dates", "days"):
        v = d.get(k)
        if isinstance(v, list) and v:
            return str(v[-1])
    return None


def fetch(name):
    try:
        rq = urllib.request.Request(f"{SITE_URL}/data/{name}?cb={int(time.time())}", headers=HDR)
        raw = urllib.request.urlopen(rq, timeout=120).read()
        return (None, None) if raw.lstrip()[:1] == b"<" else (raw, basedate(raw))
    except Exception as e:
        print(f"  · {name}: 배포본을 못 읽었다 ({e!r})"[:110])
        return None, None


print("── 배포 전 점검: 표의 거래일이 뒤로 가지 않는가 ──")
for name in GUARDED:
    p = BASE / "site" / "data" / name
    mine = basedate(p.read_bytes()) if p.exists() else None
    raw, theirs = fetch(name)
    if raw is None:
        print(f"  · {name}: 배포본 없음 — 내 것을 그대로 올린다 (내 기준일 {mine})")
        continue
    if mine is None or (theirs or "") > mine:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        print(f"  ⚠ {name}: 내 것({mine})이 배포본({theirs})보다 낡았다 — **배포본을 지킨다**")
    else:
        print(f"  · {name}: 내 것 {mine} ≥ 배포본 {theirs} — 올린다")

print("\n── wrangler ──")
cmd = "npx --yes wrangler@4 pages deploy site --project-name kospi-volume --branch main --commit-dirty=true"
if subprocess.run(cmd, shell=True, cwd=str(BASE)).returncode:
    sys.exit("배포 실패")

want = json.loads((BASE / "site" / "data" / "ver.json").read_text(encoding="utf-8"))["v"]
print(f"\n── 확인: 배포본이 {want} 가 되는가 ──")
for i in range(10):
    try:
        rq = urllib.request.Request(f"{SITE_URL}/data/ver.json?cb={int(time.time())}{i}", headers=HDR)
        got = json.loads(urllib.request.urlopen(rq, timeout=30).read().decode())
        if got.get("v") == want:
            print(f"  ✅ v{want} 반영됨"); break
        print(f"  {i}회차: 아직 {got.get('v')}")
    except Exception as e:
        print(f"  {i}회차: {e!r}"[:90])
    time.sleep(10)
else:
    print(f"  ⚠ {want} 를 확인하지 못했다 — 캐시일 수 있으니 직접 볼 것")
