"""check-host.net 分布式 TCP 连通性探测 (本机无法直连节点时用于外部佐证)
用法: python checkhost.py [--nodes 4] [--delay 6] [--out checkhost_result.json]
"""
import argparse
import json
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def api(url: str, tries: int = 4) -> dict | None:
    for _ in range(tries):
        try:
            r = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
            return json.loads(urllib.request.urlopen(r, timeout=25).read())
        except Exception:
            time.sleep(4)
    return None


def probe(host: str, port: int, nodes: int, delay: float) -> dict:
    d = api(f"https://check-host.net/check-tcp?host={host}:{port}&max_nodes={nodes}")
    if not d:
        return {"target": f"{host}:{port}", "error": "request_failed"}
    rid = d["request_id"]
    time.sleep(delay + 12)
    res = api(f"https://check-host.net/check-result/{rid}")
    out = []
    for node, r in (res or {}).items():
        if not r:
            out.append({"node": node, "ok": None})
            continue
        first = r[0]
        if isinstance(first, dict):
            out.append({"node": node, "ok": first.get("error") is None,
                        "time": first.get("time"), "error": first.get("error"),
                        "vantage": (d.get("nodes", {}).get(node) or [None, None])[1]})
        else:
            out.append({"node": node, "ok": None, "raw": first})
    okc = sum(1 for x in out if x.get("ok") is True)
    return {"target": f"{host}:{port}", "reachable_nodes": okc, "total_nodes": len(out), "details": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default="nodes.json")
    ap.add_argument("--out", default="checkhost_result.json")
    ap.add_argument("--max-nodes", type=int, default=4)
    ap.add_argument("--delay", type=float, default=6)
    args = ap.parse_args()

    data = json.load(open(args.nodes, encoding="utf-8"))
    seen, targets = set(), []
    for n in data["nodes"]:
        for proto, p in n["protocols"].items():
            if proto == "wireguard":
                continue
            key = (p["host"], int(p["port"]))
            if key in seen:
                continue
            seen.add(key)
            targets.append({"host": p["host"], "port": int(p["port"]), "protos": [proto],
                            "location": n["location_name"], "tier": n["tier"]})
    print(f"共 {len(targets)} 个唯一 host:port")
    results = []
    for i, t in enumerate(targets, 1):
        r = probe(t["host"], t["port"], args.max_nodes, args.delay)
        r.update(location=t["location"], tier=t["tier"], protos=t["protos"])
        results.append(r)
        print(f"[{i:2}/{len(targets)}] {t['host']}:{t['port']:<5} "
              f"{r.get('reachable_nodes','?')}/{r.get('total_nodes','?')} 可连通  {t['location']}")
        time.sleep(args.delay)
    json.dump(results, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = [r for r in results if r.get("reachable_nodes", 0) > 0]
    print(f"\n外部可达端点: {len(ok)}/{len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
