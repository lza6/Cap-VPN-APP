#!/usr/bin/env python3
"""Cap VPN → new-api 代理池落地脚本（服务器端 / 任意 Linux 主机）

做四件事：
  1. 读 nodes.json（tools/harvest.py 的产物），把 hysteria2 / vless-REALITY 节点展开成 mihomo proxies
  2. 每个节点一个独立 socks5 listener（默认从 42000 起，绑 172.18.0.1 供 Docker 内 new-api 访问）
  3. 起 mihomo，逐端口真实拨测（拉 cdn-cgi/trace 拿出口 IP）
  4. 只把「当场测通」的写成 proxies.txt —— new-api 的 TRYINGOPEN_PROXY_FILE 原生吃 socks5://host:port

用法：
    MIHOMO_BIN=/opt/capvpn/mihomo python3 deploy_pool.py --gen-config
    MIHOMO_BIN=/opt/capvpn/mihomo python3 deploy_pool.py            # 起池 + 测活 + 写 proxies.txt
    python3 deploy_pool.py --restart                                # 先杀已有 mihomo 再来

环境变量：
    CP_LISTEN_HOST   socks 监听地址，默认 172.18.0.1（Docker 网桥网关）
    CP_SOCKS_BASE    socks 起始端口，默认 42000
    CP_OUT           输出代理清单，默认 /opt/new-api/data/capvpn_proxies.txt
    MIHOMO_BIN       mihomo 可执行文件
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

WORK = os.path.dirname(os.path.abspath(__file__))
RUNDIR = os.path.join(WORK, "run")
NODES = os.environ.get("CP_NODES", os.path.join(WORK, "..", "..", "nodes.json"))
MIHOMO = os.environ.get("MIHOMO_BIN", "mihomo")
LISTEN_HOST = os.environ.get("CP_LISTEN_HOST", "172.18.0.1")
SOCKS_BASE = int(os.environ.get("CP_SOCKS_BASE", "42000"))
OUT_FILE = os.environ.get("CP_OUT", "/opt/new-api/data/capvpn_proxies.txt")
PROTO_ORDER = ("vless", "hysteria2")  # vless 端口固定，优先入池


def load_nodes(path: str) -> list:
    """nodes.json → 端点列表（同一 ip:port:cred 去重）"""
    data = json.load(open(path, encoding="utf-8"))
    out, seen = [], set()
    for node in data["nodes"]:
        for proto in PROTO_ORDER:
            p = node["protocols"].get(proto)
            if not p:
                continue
            sig = (proto, p["host"], p["port"], p["userinfo"])
            if sig in seen:
                continue
            seen.add(sig)
            out.append({
                "idx": len(out),
                "proto": proto,
                "location": node["location_name"],
                "tier": node["tier"],
                "server": p["host"],
                "port": int(p["port"]),
                "userinfo": p["userinfo"],
                "query": p["query"],
                "socks_port": SOCKS_BASE + len(out),
            })
    return out


def mihomo_proxy(n: dict) -> dict:
    q = n["query"]
    name = "capvpn-%d" % n["idx"]
    if n["proto"] == "hysteria2":
        return {
            "name": name, "type": "hysteria2", "server": n["server"], "port": n["port"],
            "password": n["userinfo"], "sni": q.get("sni", ""),
            "skip-cert-verify": q.get("insecure") == "1",
            "obfs": q.get("obfs"), "obfs-password": q.get("obfs-password"),
        }
    tls = {"enabled": True, "servername": q.get("sni", "")}
    if q.get("security") == "reality":
        tls["reality-opts"] = {"public-key": q.get("pbk", ""), "short-id": q.get("sid", "")}
    d = {
        "name": name, "type": "vless", "server": n["server"], "port": n["port"],
        "uuid": n["userinfo"], "network": q.get("type", "tcp"), "udp": True,
        "tls": True, "skip-cert-verify": False,
        "servername": q.get("sni", ""), "client-fingerprint": q.get("fp"),
        "flow": q.get("flow"), "reality-opts": tls.get("reality-opts"),
    }
    return {k: v for k, v in d.items() if v is not None}


def build_config(nodes: list, path: str) -> str:
    import yaml  # PyYAML 已在宿主 python3 环境，缺则 pip install pyyaml

    cfg = {
        "mixed-port": 0,
        "mode": "direct",
        "log-level": "warning",
        "proxies": [mihomo_proxy(n) for n in nodes],
        "listeners": [
            {"name": "li-%d" % n["idx"], "type": "socks", "listen": LISTEN_HOST,
             "port": n["socks_port"], "proxy": "capvpn-%d" % n["idx"], "udp": True}
            for n in nodes
        ],
        "rules": ["MATCH,DIRECT"],
    }
    yaml.safe_dump(cfg, open(path, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    return path


def wait_port(host: str, port: int, total: float = 30.0) -> bool:
    end = time.time() + total
    while time.time() < end:
        try:
            with socket.create_connection((host if host != "0.0.0.0" else "127.0.0.1", port), 0.4):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def probe(n: dict, timeout: int = 20) -> dict:
    port = n["socks_port"]
    host = "127.0.0.1" if LISTEN_HOST in ("0.0.0.0", "::") else LISTEN_HOST
    p = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout),
         "--socks5-hostname", "%s:%d" % (host, port),
         "https://www.cloudflare.com/cdn-cgi/trace"], capture_output=True)
    body = p.stdout.decode("utf-8", "ignore")
    kv = dict(line.split("=", 1) for line in body.splitlines() if "=" in line)
    return {**n, "alive": bool(kv.get("ip")), "exit_ip": kv.get("ip"),
            "exit_loc": kv.get("loc")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-config", action="store_true", help="只生成 mihomo 配置")
    ap.add_argument("--restart", action="store_true", help="先杀掉已有 mihomo")
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--no-probe", action="store_true", help="不测活，直接把全量端口写进清单")
    args = ap.parse_args()

    os.makedirs(RUNDIR, exist_ok=True)
    nodes = load_nodes(NODES)
    cfg_path = build_config(nodes, os.path.join(RUNDIR, "config.yaml"))
    print("配置已生成: %s (%d 个节点, socks %s:%d-%d)"
          % (cfg_path, len(nodes), LISTEN_HOST, SOCKS_BASE, SOCKS_BASE + len(nodes) - 1))
    if args.gen_config:
        return 0

    if args.restart:
        subprocess.run(["pkill", "-f", "mihomo"], check=False)
        time.sleep(1)
    log = open(os.path.join(RUNDIR, "mihomo.log"), "wb")
    subprocess.Popen([MIHOMO, "-d", RUNDIR, "-f", cfg_path],
                     stdout=log, stderr=subprocess.STDOUT)
    with ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(lambda n: wait_port(LISTEN_HOST, n["socks_port"], 60), nodes))

    if args.no_probe:
        alive = nodes
    else:
        with ThreadPoolExecutor(max_workers=args.conc) as ex:
            alive = [r for r in ex.map(probe, nodes) if r["alive"]]

    os.makedirs(os.path.dirname(OUT_FILE) or ".", exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("# capvpn pool generated %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        for r in alive:
            host = "127.0.0.1" if LISTEN_HOST in ("0.0.0.0", "::") else LISTEN_HOST
            f.write("socks5://%s:%d\n" % (host, r["socks_port"]))
    print("存活 %d/%d，已写 %s" % (len(alive), len(nodes), OUT_FILE))
    for r in alive:
        print("  %-20s %-9s %-16s -> %s" % (r["location"], r["proto"], r["server"],
                                            r["exit_ip"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
