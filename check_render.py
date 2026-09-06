# -*- coding: utf-8 -*-
"""고친 index.html 을 로컬에서 띄워 실제 브라우저로 렌더까지 확인한다(배포 전 점검)."""
import io, sys, threading, http.server, functools, socketserver
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright
ROOT = r"G:\vscode\kospi-volume"
POS = [
 {"id":1788413199196,"qty":7,"code":"329180","date":"20260903","name":"HD현대중공업","price":419500,"filters":["P4"]},
 {"id":1788736735935,"qty":57,"code":"007810","date":"20260907","name":"코리아써키트","price":52600,"filters":["P4"]}]
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        # data/* 는 배포본에서 끌어온다(로컬엔 site/ 아래에만 있다)
        if self.path.startswith("/data/"):
            self.send_response(302)
            self.send_header("Location", "https://bamhobak.github.io/kospi-volume"+self.path); self.end_headers(); return
        return super().do_GET()
srv = socketserver.TCPServer(("127.0.0.1", 8899), functools.partial(H, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_context(viewport={"width":390,"height":840}).new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8899/index.html", wait_until="domcontentloaded", timeout=90000)
    pg.evaluate("p => localStorage.setItem('positions', JSON.stringify(p))", POS)
    pg.reload(wait_until="domcontentloaded", timeout=90000); pg.wait_for_timeout(12000)
    print("페이지 오류:", errs or "없음")
    print("#status:", pg.eval_on_selector("#status","e=>e.textContent.trim()")[:150])
    print("보유표 행수:", pg.eval_on_selector("#tbl tbody","e=>e.children.length"))
    row0 = pg.evaluate("() => { const r = document.querySelector('#tbl tbody').children[0]; return r ? r.innerText : '(none)' }")
    print("첫 행:", row0.replace(chr(10), " | ")[:220])
    print("규칙 매치:", pg.evaluate("()=>FILTERS.map(f=>[f.id, view.rows.filter(r=>{try{return f.fn(r)}catch(e){return false}}).length]).filter(x=>x[1])"))
    b.close()
srv.shutdown()
