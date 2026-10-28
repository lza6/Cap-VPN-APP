"""nodes.json -> sing-box 配置 (每个节点独立 socks inbound, 便于逐节点测活)"""
import json
import os
import sys

BASE_PORT = 34500


def outbound_for(node: dict, proto: str, tag: str) -> dict | None:
    p = node["protocols"][proto]
    q = p["query"]
    if proto == "hysteria2":
        ob = {"type": "hysteria2", "tag": tag, "server": p["host"], "server_port": p["port"],
              "password": p["userinfo"],
              "tls": {"enabled": True, "server_name": q.get("sni", ""),
                      "insecure": q.get("insecure") == "1"},
              "up_mbps": 30, "down_mbps": 100}
        if q.get("obfs") == "salamander" and q.get("obfs-password"):
            ob["obfs"] = {"type": "salamander", "password": q["obfs-password"]}
        return ob
    if proto == "vless":
        tls = {"enabled": True, "server_name": q.get("sni", "")}
        if q.get("fp"):
            tls["utls"] = {"enabled": True, "fingerprint": q["fp"]}
        if q.get("security") == "reality":
            tls["reality"] = {"enabled": True, "public_key": q.get("pbk", ""),
                              "short_id": q.get("sid", "")}
        ob = {"type": "vless", "tag": tag, "server": p["host"], "server_port": p["port"],
              "uuid": p["userinfo"], "tls": tls}
        if q.get("flow"):
            ob["flow"] = q["flow"]
        net = q.get("type", "tcp")
        if net == "ws":
            ob["transport"] = {"type": "ws", "path": q.get("path", "/"),
                               "headers": {"Host": q.get("host", p["host"])}}
        elif net == "grpc":
            ob["transport"] = {"type": "grpc", "service_name": q.get("serviceName", "")}
        elif net != "tcp":
            ob["transport"] = {"type": net}
        return ob
    return None  # wireguard: URI 里是 {WG_PRIVATE_KEY}/{WG_IP} 模板, 无可用凭证


def build(nodes_path: str, out_path: str, protos=("hysteria2", "vless")) -> dict:
    data = json.load(open(nodes_path, encoding="utf-8"))
    inbounds, outbounds, mapping = [], [], []
    port = BASE_PORT
    seen = set()
    for node in data["nodes"]:
        for proto in protos:
            if proto not in node["protocols"]:
                continue
            p = node["protocols"][proto]
            sig = (proto, p["host"], p["port"], p["userinfo"])
            if sig in seen:
                continue
            seen.add(sig)
            tag_in, tag_out = f"in{port}", f"n{port}"
            ob = outbound_for(node, proto, tag_out)
            if not ob:
                continue
            inbounds.append({"type": "socks", "tag": tag_in, "listen": "127.0.0.1",
                             "listen_port": port})
            outbounds.append(ob)
            mapping.append({"port": port, "node_id": node["server_id"],
                            "location": node["location_name"], "tier": node["tier"],
                            "proto": proto, "server": f'{p["host"]}:{p["port"]}',
                            "country": node["country"]})
            port += 1
    cfg = {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": inbounds,
        "outbounds": outbounds + [{"type": "direct", "tag": "direct"}],
        "route": {
            "rules": [{"inbound": [i["tag"]], "outbound": o["tag"]}
                      for i, o in zip(inbounds, outbounds)],
            "final": "direct",
        },
    }
    json.dump(cfg, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(mapping, open(out_path + ".map.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return {"nodes": len(mapping), "config": out_path}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    args = sys.argv[1:]
    protos = tuple(args[0].split(",")) if args else ("hysteria2", "vless")
    print(build(os.path.join(root, "nodes.json"),
                os.path.join(root, "sb_config.json"), protos))
