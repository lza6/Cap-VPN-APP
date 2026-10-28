"""Cap VPN 节点收割器
协议: HTTPS + 硬编码 JWT Bearer, 响应体 = base64(IV16 || "::" || base64(AES-CBC(JSON)))
用途: 拉取官方节点清单(免费/高级两套) → 解密 → 归一化为 nodes.json
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

from capcrypt import decrypt

API_BASE = "https://capvpn.site/api/"
TOKEN = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
         "eyJpc3MiOiJteS1hcGkiLCJpYXQiOjE3MzM3MTIwMDAsInJvbGUiOiJzeXN0ZW0ifQ."
         "4ZtYgBNkq6x9v6vG8v_fDP9BjoOcyFJ97v6j7g6kjr8")
UA = "okhttp/4.12.0"

ENDPOINTS = {
    "free": "get_locations_free_v2_android.php",
    "premium": "get_locations_premium_v2_android.php?ispremium=0",
}


def fetch(endpoint: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(API_BASE + endpoint, headers={
        "Authorization": "Bearer " + TOKEN,
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_uri(proto: str, uri: str) -> dict:
    u = urllib.parse.urlparse(uri)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    return {
        "proto": proto,
        "raw": uri,
        "scheme": u.scheme,
        "host": u.hostname,
        "port": u.port,
        "userinfo": urllib.parse.unquote(u.username or "") + (
            ":" + urllib.parse.unquote(u.password) if u.password else ""),
        "query": q,
    }


def build(nodes_dir: str) -> dict:
    out = {"generated_at": None, "source": API_BASE, "locations": [], "nodes": []}
    import datetime
    out["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    seen = set()
    for tier, ep in ENDPOINTS.items():
        raw = fetch(ep)
        open(os.path.join(nodes_dir, f"raw_{tier}.b64"), "wb").write(raw)
        payload = json.loads(decrypt(raw))
        for loc in payload.get("response") or []:
            out["locations"].append({
                "id": loc.get("id"), "name": loc.get("name"), "type": loc.get("type"),
                "country_flag": loc.get("flagUrl"), "brief": loc.get("briefName"),
                "best_server_score": loc.get("best_server_score"),
                "healthy_server_count": loc.get("healthy_server_count"),
                "auto_rotate": loc.get("is_auto_rotate"),
                "tier": tier,
            })
            for s in loc.get("servers") or []:
                protos = {}
                for proto, uri in (s.get("protocols") or {}).items():
                    if uri:
                        protos[proto] = parse_uri(proto, uri)
                node = {
                    "server_id": s.get("id"), "server_name": s.get("name"),
                    "location_id": loc.get("id"), "location_name": loc.get("name"),
                    "tier": tier, "country": s.get("country"), "ip": s.get("ip"),
                    "is_online": s.get("is_online"), "port_open": s.get("port_open"),
                    "health_score": s.get("health_score"),
                    "bandwidth_mbps": s.get("bandwidth_mbps"),
                    "cpu_pct": s.get("cpu_pct"), "ram_pct": s.get("ram_pct"),
                    "last_health_at": s.get("last_health_at"),
                    "protocol_type": s.get("protocol_type"),
                    "protocols": protos,
                }
                key = (node["server_id"], tuple(sorted(protos)))
                if key in seen:
                    continue
                seen.add(key)
                out["nodes"].append(node)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "nodes.json"))
    args = ap.parse_args()
    nodes_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(nodes_dir, exist_ok=True)
    data = build(nodes_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"locations={len(data['locations'])} nodes={len(data['nodes'])} -> {args.out}")
    for n in data["nodes"]:
        print(f"  [{n['tier']:7}] {n['location_name']:20} {n['ip']:16} "
              f"online={n['is_online']} protos={','.join(n['protocols'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
