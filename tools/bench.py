"""逐节点测活压测: 起 sing-box (每节点一个 socks inbound) -> 并发走 socks5h 拉 cdn-cgi/trace
判定标准: 真实出口 IP + 地理位置 + 延迟; 只有能拿到出口 IP 才算活。
"""
import argparse
import concurrent.futures as cf
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
PROBE = "http://cp.cloudflare.com/generate_204"


class SocksHTTP(urllib.request.HTTPSHandler):
    pass


def http_via_socks(port: int, url: str, timeout: float = 15.0) -> tuple[int, float, bytes]:
    """用 requests? 不: 手写 socks5 握手太啰嗦, 直接走 curl 保证行为可复现"""
    t0 = time.time()
    p = subprocess.run(
        ["curl", "-sS", "--max-time", str(int(timeout)),
         "--socks5-hostname", f"127.0.0.1:{port}", url],
        capture_output=True)
    return (p.returncode, time.time() - t0, p.stdout)


def wait_port(port: int, total: float = 20.0) -> bool:
    end = time.time() + total
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def parse_trace(body: bytes) -> dict:
    d = {}
    for line in body.decode("utf-8", "ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def probe(item: dict, timeout: float) -> dict:
    port, proto = item["port"], item["proto"]
    r = dict(item)
    rc, dt, body = http_via_socks(port, TRACE, timeout)
    if rc != 0 or b"ip=" not in body:
        r.update(alive=False, latency_ms=round(dt * 1000), error=(body[:120].decode("utf-8", "ignore") if body else f"curl_rc={rc}"))
        return r
    tr = parse_trace(body)
    rc2, dt2, _ = http_via_socks(port, PROBE, timeout)
    r.update(alive=True, latency_ms=round(dt * 1000), exit_ip=tr.get("ip"),
             exit_loc=tr.get("loc"), warp=tr.get("warp"),
             latency204_ms=round(dt2 * 1000) if rc2 == 0 else None,
             ok204=(rc2 == 0))
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="sb_config.json")
    ap.add_argument("--mapfile", default="sb_config.json.map.json")
    ap.add_argument("--bin", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "bin", "sing-box-1.14.4-windows-amd64", "sing-box.exe"))
    ap.add_argument("--conc", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=15)
    ap.add_argument("--out", default="bench_result.json")
    args = ap.parse_args()

    mapping = json.load(open(args.mapfile, encoding="utf-8"))
    log = open("singbox.log", "wb")
    proc = subprocess.Popen([args.bin, "run", "-c", args.config],
                            stdout=log, stderr=subprocess.STDOUT)
    t_start = time.time()
    try:
        with cf.ThreadPoolExecutor(max_workers=32) as ex:
            ready = [m for m, ok in zip(mapping, ex.map(lambda m: wait_port(m["port"], 60.0), mapping)) if ok]
        print(f"sing-box 启动, inbound 就绪 {len(ready)}/{len(mapping)} ({(time.time()-t_start):.1f}s)")
        if len(ready) < len(mapping):
            log.flush()
            print("  未就绪端口:", [m["port"] for m in mapping if m not in ready][:10])
        results = []
        with cf.ThreadPoolExecutor(max_workers=args.conc) as ex:
            futs = {ex.submit(probe, m, args.timeout): m for m in mapping}
            for i, f in enumerate(cf.as_completed(futs), 1):
                r = f.result()
                results.append(r)
                flag = "OK " if r.get("alive") else "-- "
                print(f"[{i:2}/{len(mapping)}] {flag}{r['proto']:9} {r['location']:18} "
                      f"{r['server']:24} {r['latency_ms']:>5}ms "
                      f"{r.get('exit_ip','') or r.get('error','')}")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    results.sort(key=lambda r: (not r.get("alive"), r.get("latency_ms", 9999)))
    summary = {
        "tested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_unique_endpoints": len(results),
        "alive": sum(1 for r in results if r.get("alive")),
        "alive_204": sum(1 for r in results if r.get("ok204")),
        "by_proto": {},
        "unique_exit_ips": sorted({r["exit_ip"] for r in results if r.get("exit_ip")}),
    }
    for r in results:
        b = summary["by_proto"].setdefault(r["proto"], {"total": 0, "alive": 0})
        b["total"] += 1
        b["alive"] += 1 if r.get("alive") else 0
    json.dump({"summary": summary, "results": results},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n存活 {summary['alive']}/{summary['total_unique_endpoints']} "
          f"| 204 通 {summary['alive_204']} | 唯一出口IP {len(summary['unique_exit_ips'])}")
    print(json.dumps(summary["by_proto"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
