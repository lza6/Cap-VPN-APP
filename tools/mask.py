"""生成脱敏版节点数据 (仓库公开用): 保留结构/端口/SNI, 抹掉一切可用凭证"""
import json
import os
import sys

MASK = "REDACTED"


def mask_uri(proto: str, uri: str) -> str:
    import urllib.parse as up
    u = up.urlparse(uri)
    userinfo = MASK if u.username else ""
    q = up.parse_qs(u.query)
    for k in ("obfs-password", "pbk", "sid"):
        if k in q:
            q[k] = [MASK]
    query = up.urlencode([(k, v[0]) for k, v in q.items()])
    return up.urlunparse((u.scheme, f"{userinfo}@{u.hostname}:{u.port}" if userinfo else
                          f"{u.hostname}:{u.port}", u.path, "", query, u.fragment))


def main(src: str, dst: str) -> None:
    data = json.load(open(src, encoding="utf-8"))
    for n in data["nodes"]:
        for proto, p in n["protocols"].items():
            p["raw"] = mask_uri(proto, p["raw"])
            p["userinfo"] = MASK
            for k in ("obfs-password", "pbk", "sid"):
                if k in p["query"]:
                    p["query"][k] = MASK
    data["note"] = ("凭证已脱敏。真实凭证需自行运行 tools/harvest.py 从上游获取。"
                    "上游鉴权 JWT 见 docs/REVERSE_REPORT.md。")
    json.dump(data, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"脱敏完成 -> {dst} (节点 {len(data['nodes'])})")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main(os.path.join(root, "nodes.json"),
         sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "nodes_public.json"))
