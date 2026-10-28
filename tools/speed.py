"""对 bench 结果里存活的端点做吞吐测试 (下载 5MB, 计算 Mbps)
用法: python speed.py --bench e2e_result.json --bytes 5000000
"""
import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import wait_port  # noqa: E402

URL = "https://speed.cloudflare.com/__down?bytes={n}"


def measure(item: dict, nbytes: int) -> dict:
    port, url = item["port"], URL.format(n=nbytes)
    t0 = time.time()
    p = subprocess.run(["curl", "-sS", "--max-time", "60", "--socks5-hostname",
                        f"127.0.0.1:{port}", "-o", os.devnull, "-w", "%{size_download}",
                        url], capture_output=True)
    dt = time.time() - t0
    got = int(p.stdout.strip() or 0) if p.returncode == 0 else 0
    out = dict(item)
    out.update(bytes=got, seconds=round(dt, 2),
               mbps=round(got * 8 / dt / 1e6, 2) if got else 0.0,
               ok=got > 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="e2e_result.json")
    ap.add_argument("--config", default="e2e/sb_all.json")
    ap.add_argument("--mapfile", default="e2e/sb_all.json.map.json")
    ap.add_argument("--bin", default="./sing-box")
    ap.add_argument("--bytes", type=int, default=5_000_000)
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--out", default="e2e_speed.json")
    args = ap.parse_args()

    bench = json.load(open(args.bench, encoding="utf-8"))
    alive_ports = {r["port"] for r in bench["results"] if r.get("alive")}
    mapping = [m for m in json.load(open(args.mapfile, encoding="utf-8"))
               if m["port"] in alive_ports]
    print(f"对 {len(mapping)} 个存活端点做吞吐测试 ({args.bytes} bytes each)")

    log = open("singbox_speed.log", "wb")
    proc = subprocess.Popen([args.bin, "run", "-c", args.config],
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        with cf.ThreadPoolExecutor(max_workers=32) as ex:
            list(ex.map(lambda m: wait_port(m["port"], 60.0), mapping))
        results = []
        with cf.ThreadPoolExecutor(max_workers=args.conc) as ex:
            for i, r in enumerate(ex.map(lambda m: measure(m, args.bytes), mapping), 1):
                results.append(r)
                print(f"[{i:2}/{len(mapping)}] {r['proto']:9} {r['location']:18} "
                      f"{r['server']:24} {r['mbps']:>7} Mbps")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    ok = [r for r in results if r.get("ok")]
    summary = {
        "tested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoints": len(results), "ok": len(ok),
        "median_mbps": round(sorted(r["mbps"] for r in ok)[len(ok) // 2], 2) if ok else 0,
        "max_mbps": max((r["mbps"] for r in ok), default=0),
    }
    json.dump({"summary": summary, "results": results},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
