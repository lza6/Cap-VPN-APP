"""Cap VPN 节点池 Demo 服务 (只读 + 手动刷新)
启动: python demo_server.py [--port 8971]
接口:
  GET  /               演示页
  GET  /api/summary    概览
  GET  /api/nodes      节点全量表
  GET  /api/links      订阅链接 (text/plain)
  GET  /api/bench      最近一次压测结果
  POST /api/refresh    重新拉取上游节点清单 (解密后落盘 nodes.json)
"""
import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import harvest  # noqa: E402

NODES = os.path.join(ROOT, "nodes.json")
_lock = threading.Lock()


def load_nodes() -> dict:
    with open(NODES, encoding="utf-8") as f:
        return json.load(f)


def summary(data: dict) -> dict:
    by_proto, by_tier, countries = {}, {}, set()
    online = 0
    for n in data["nodes"]:
        for p in n["protocols"]:
            by_proto[p] = by_proto.get(p, 0) + 1
        by_tier[n["tier"]] = by_tier.get(n["tier"], 0) + 1
        countries.add(n["country"])
        online += 1 if n["is_online"] == "1" else 0
    def _bench(*names):
        for name in names:
            for base in (ROOT, os.path.join(ROOT, "results")):
                p = os.path.join(base, name)
                if os.path.exists(p):
                    return json.load(open(p, encoding="utf-8"))["summary"]
        return None

    bench = _bench("bench_local_r1.json")
    bench_remote = _bench("bench_remote_e2e.json", "bench_remote_e2e_r2.json")
    return {
        "generated_at": data["generated_at"], "source": data["source"],
        "locations": len(data["locations"]), "servers": len(data["nodes"]),
        "vendor_online": online, "protocols": by_proto, "tiers": by_tier,
        "countries": sorted(c for c in countries if c),
        "bench": bench,
        "bench_remote": bench_remote,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "capvpn-demo/0.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            html = open(os.path.join(ROOT, "demo.html"), "rb").read()
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/api/summary":
            return self._json(summary(load_nodes()))
        if path == "/api/nodes":
            data = load_nodes()
            return self._json({"generated_at": data["generated_at"], "nodes": data["nodes"]})
        if path == "/api/links":
            p = os.path.join(ROOT, "dist", "links.txt")
            body = open(p, "rb").read() if os.path.exists(p) else b""
            return self._send(200, body, "text/plain; charset=utf-8")
        if path == "/api/bench":
            for name in ("bench_local_r1.json", "bench_remote_e2e.json"):
                for base in (ROOT, os.path.join(ROOT, "results")):
                    p = os.path.join(base, name)
                    if os.path.exists(p):
                        return self._json(json.load(open(p, encoding="utf-8")))
            return self._json({"error": "no bench result yet"}, 404)
        return self._json({"error": "not found", "path": path}, 404)

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/api/refresh":
            return self._json({"error": "not found"}, 404)
        if not _lock.acquire(blocking=False):
            return self._json({"error": "refresh in progress"}, 429)
        try:
            data = harvest.build(ROOT)
            with open(NODES, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return self._json({"ok": True, "locations": len(data["locations"]),
                               "servers": len(data["nodes"])})
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "error": str(e)}, 502)
        finally:
            _lock.release()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8971)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"demo: http://{args.host}:{args.port}/")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
