"""把 nodes.json 导出成各种订阅/客户端格式:
- links.txt            : hysteria2:// / vless:// 原始链接 (可直接导入 v2rayN / NekoBox / sing-box)
- clash.yaml           : mihomo/clash 的 proxies 片段
- singbox_outbounds.json: sing-box outbounds 片段
- pool_plan.json       : 代理池落地计划 (每节点 → local socks5 端口)
"""
import argparse
import json
import os
import re
import sys

BASE_PORT = 34500


def safe(name: str) -> str:
    n = re.sub(r"[^0-9A-Za-z._-]+", "-", name).strip("-")
    return n or "node"


def proxy_name(node: dict, proto: str) -> str:
    return f"capvpn-{safe(node['location_name'])}-{node['server_id']}-{proto}"


def export(data: dict, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    links, clash, outbounds, plan = [], [], [], []
    port = BASE_PORT
    seen = set()
    for node in data["nodes"]:
        for proto, p in node["protocols"].items():
            if proto == "wireguard":
                continue  # URI 为 {WG_PRIVATE_KEY}/{WG_IP} 模板, 无可用凭证
            sig = (proto, p["host"], p["port"], p["userinfo"])
            name = proxy_name(node, proto)
            q = p["query"]
            if sig not in seen:
                seen.add(sig)
                links.append(p["raw"])
            if proto == "hysteria2":
                ob = {"type": "hysteria2", "tag": name, "server": p["host"],
                      "server_port": p["port"], "password": p["userinfo"],
                      "tls": {"enabled": True, "server_name": q.get("sni", ""),
                              "insecure": q.get("insecure") == "1"},
                      "up_mbps": 30, "down_mbps": 100}
                if q.get("obfs") == "salamander":
                    ob["obfs"] = {"type": "salamander", "password": q.get("obfs-password", "")}
                clash.append({"name": name, "type": "hysteria2", "server": p["host"],
                              "port": p["port"], "password": p["userinfo"],
                              "sni": q.get("sni", ""), "skip-cert-verify": True,
                              "obfs": q.get("obfs"), "obfs-password": q.get("obfs-password")})
            elif proto == "vless":
                tls = {"enabled": True, "server_name": q.get("sni", "")}
                if q.get("fp"):
                    tls["utls"] = {"enabled": True, "fingerprint": q["fp"]}
                if q.get("security") == "reality":
                    tls["reality"] = {"enabled": True, "public_key": q.get("pbk", ""),
                                      "short_id": q.get("sid", "")}
                ob = {"type": "vless", "tag": name, "server": p["host"],
                      "server_port": p["port"], "uuid": p["userinfo"], "tls": tls}
                if q.get("flow"):
                    ob["flow"] = q["flow"]
                clash.append({"name": name, "type": "vless", "server": p["host"],
                              "port": p["port"], "uuid": p["userinfo"], "network": q.get("type", "tcp"),
                              "tls": True, "servername": q.get("sni", ""),
                              "client-fingerprint": q.get("fp"), "flow": q.get("flow"),
                              "reality-opts": {"public-key": q.get("pbk"), "short-id": q.get("sid")}
                              if q.get("security") == "reality" else None,
                              "skip-cert-verify": False})
            else:
                continue
            outbounds.append(ob)
            plan.append({"name": name, "proto": proto, "location": node["location_name"],
                         "tier": node["tier"], "upstream": f'{p["host"]}:{p["port"]}',
                         "local_socks": f"127.0.0.1:{port}", "singbox_tag": name})
            port += 1

    open(os.path.join(outdir, "links.txt"), "w", encoding="utf-8").write("\n".join(links) + "\n")
    json.dump(outbounds, open(os.path.join(outdir, "singbox_outbounds.json"), "w",
                              encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(plan, open(os.path.join(outdir, "pool_plan.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(outdir, "clash_proxies.yaml"), "w", encoding="utf-8") as f:
        f.write("proxies:\n")
        for c in clash:
            f.write(f"  - name: \"{c['name']}\"\n")
            for k, v in c.items():
                if k == "name" or v is None:
                    continue
                f.write(f"    {k}: {json.dumps(v, ensure_ascii=False)}\n")
        f.write("\nproxy-groups:\n  - name: CAPVPN\n    type: select\n    proxies:\n")
        for c in clash:
            f.write(f"      - \"{c['name']}\"\n")
    return {"links": len(links), "outbounds": len(outbounds), "clash": len(clash)}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "dist")
    data = json.load(open(os.path.join(root, "nodes.json"), encoding="utf-8"))
    print(export(data, outdir))
