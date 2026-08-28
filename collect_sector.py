"""업종·테마 구성 수집 (스냅샷)
- 업종: 79개 · 종목당 1개 (분기 1회 갱신이면 충분)
- 테마: 수백 개 · 종목당 여러 개 (주 1회 갱신 — 변화 이력 축적)
저장: DB 테이블 sector(스냅샷 날짜별)
사용: python collect_sector.py            업종+테마 모두
      python collect_sector.py --upjong   업종만
      python collect_sector.py --theme    테마만
"""
import re, sqlite3, sys, time
from datetime import datetime
import requests
import collect

log = collect.log
H = {"User-Agent": "Mozilla/5.0"}
TODAY = datetime.today().strftime("%Y%m%d")
con = sqlite3.connect(collect.DB, timeout=180)
con.execute("""CREATE TABLE IF NOT EXISTS sector(
    snap TEXT, kind TEXT, gid TEXT, gname TEXT, ticker TEXT,
    PRIMARY KEY(snap, kind, gid, ticker))""")
con.execute("CREATE INDEX IF NOT EXISTS ix_sector_t ON sector(ticker, kind)")
con.commit()

def fetch(url):
    for _ in range(3):
        try:
            r = requests.get(url, headers=H, timeout=15); r.encoding = "euc-kr"
            if r.status_code == 200: return r.text
        except Exception as e: log.warning(f"{url}: {str(e)[:50]}")
        time.sleep(1)
    return ""

def members(kind, gid):
    t = fetch(f"https://finance.naver.com/sise/sise_group_detail.naver?type={kind}&no={gid}")
    return sorted({c for c, _ in re.findall(r'item/main\.naver\?code=(\d{6})"[^>]*>([^<]+)<', t)})

def collect_groups(kind, list_url, pat):
    """kind: 'upjong' | 'theme'"""
    groups = []
    if kind == "upjong":
        t = fetch(list_url)
        groups = [(g, n.strip()) for g, n in re.findall(pat, t)]
    else:
        seen = {}
        page = 1
        while page <= 12:
            t = fetch(f"{list_url}?&page={page}")
            found = re.findall(pat, t)
            if not found: break
            for g, n in found: seen.setdefault(g, n.strip())
            page += 1; time.sleep(0.3)
        groups = sorted(seen.items())
    log.info(f"{kind}: {len(groups)}개 그룹")
    rows = []
    for i, (gid, gname) in enumerate(groups):
        for c in members(kind, gid):
            rows.append((TODAY, kind, gid, gname, c))
        if i % 30 == 0: log.info(f"  {kind} {i}/{len(groups)} · {len(rows)}행")
        time.sleep(0.3)
    con.executemany("INSERT OR REPLACE INTO sector VALUES (?,?,?,?,?)", rows)
    con.commit()
    log.info(f"{kind} 저장: {len(rows)}행 ({len({r[4] for r in rows})}종목)")
    return len(rows)

do_up = "--theme" not in sys.argv
do_th = "--upjong" not in sys.argv
if do_up:
    collect_groups("upjong", "https://finance.naver.com/sise/sise_group.naver?type=upjong",
                   r'sise_group_detail\.naver\?type=upjong&no=(\d+)"[^>]*>([^<]+)<')
if do_th:
    collect_groups("theme", "https://finance.naver.com/sise/theme.naver",
                   r'sise_group_detail\.naver\?type=theme&no=(\d+)"[^>]*>([^<]+)<')

for kind in ("upjong", "theme"):
    r = con.execute("SELECT count(DISTINCT gid), count(DISTINCT ticker), count(*) FROM sector WHERE snap=? AND kind=?", (TODAY, kind)).fetchone()
    print(f"{kind}: 그룹 {r[0]} · 종목 {r[1]} · 매핑 {r[2]}행")
snaps = [r[0] for r in con.execute("SELECT DISTINCT snap FROM sector ORDER BY snap")]
print("스냅샷 이력:", snaps)
con.close()
