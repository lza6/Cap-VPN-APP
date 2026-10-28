"""对存活端点做「目标站点可达性矩阵」测试 —— 判断这批节点能不能给 new-api 渠道用
每个目标用一个能区分「网络不通」和「服务可达」的 URL:
  401/403/404/405/400 = 出口能到达该服务 (只是没凭证/方法不对)
  000/timeout         = 该节点到目标不通 (可能被目标风控或链路问题)
"""
import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import wait_port  # noqa: E402

TARGETS = [
    ("openai", "https://api.openai.com/v1/models"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/models"),
    ("anthropic", "https://api.anthropic.com/v1/messages"),
    ("claude-ai", "https://claude.ai/api/organizations"),
    ("chatgpt-web", "https://chatgpt.com/cdn-cgi/trace"),
    ("netflix", "https://www.netflix.com/title/80100172"),
    ("spotify", "https://open.spotify.com/"),
    ("cf-trace", "https://www.cloudflare.com/cdn-cgi/trace"),
]


def probe(item: dict, name: str, url: str) -> dict:
    p = subprocess.run(
        ["curl", "-sS", "-o", os.devnull, "--max-time", "20",
         "--socks5-hostname", f"127.0.0.1:{item['port']}",
         "-w", "%{http_code}", url], capture_output=True)
    code = int(p.stdout.strip() or 0) if p.returncode in (0, 22) else 0
    return {"target": name, "status": code, "reachable": code != 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="e2e_result.json")
    ap.add_argument("--config", default="e2e/sb_all.json")
    ap.add_argument("--mapfile", default="e2e/sb_all.json.map.json")
    ap.add_argument("--bin", default="./sing-box")
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--out", default="e2e_reach.json")
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 个存活端点")
    args = ap.parse_args()

    bench = json.load(open(args.bench, encoding="utf-8"))
    mapping = [m for m in json.load(open(args.mapfile, encoding="utf-8"))
               if m["port"] in {r["port"] for r in bench["results"] if r.get("alive")}]
    if args.limit:
        mapping = mapping[:args.limit]
    print(f"{len(mapping)} 个存活端点 × {len(TARGETS)} 个目标")

    log = open("singbox_reach.log", "wb")
    proc = subprocess.Popen([args.bin, "run", "-c", args.config],
                            stdout=log, stderr=subprocess.STDOUT)
    rows = []
    try:
        with cf.ThreadPoolExecutor(max_workers=32) as ex:
            list(ex.map(lambda m: wait_port(m["port"], 60.0), mapping))
        jobs = [(m, n, u) for m in mapping for n, u in TARGETS]
        with cf.ThreadPoolExecutor(max_workers=args.conc) as ex:
            futs = {ex.submit(probe, m, n, u): (m, n) for m, n, u in jobs}
            got = {}
            for f in cf.as_completed(futs):
                m, n = futs[f]
                r = f.result()
                got.setdefault(m["port"], {})[n] = r
        for m in mapping:
            row = dict(m)
            row["targets"] = got.get(m["port"], {})
            rows.append(row)
            marks = " ".join(f"{k}={v['status']}" for k, v in row["targets"].items())
            print(f"  {m['proto']:9} {m['location']:18} {m['server']:24} {marks}")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    agg = {n: sum(1 for r in rows if r["targets"].get(n, {}).get("reachable")) for n, _ in TARGETS}
    summary = {"endpoints": len(rows), "reachable_counts": agg}
    json.dump({"summary": summary, "results": rows},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
