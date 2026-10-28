# 压测产物说明（run 2026-10-29）

- `bench_remote_e2e.json` / `bench_remote_e2e_r2.json`：GitHub Actions（Azure US 出口）两轮独立测活，按真实出口 IP 判定
- `e2e_speed.json`：存活端点 5 MB 下载吞吐
- `e2e_reach.json`：存活端点对 openai/gemini/anthropic/claude.ai/chatgpt.com/netflix/spotify 的可达性（HTTP 状态码）
- `bench_local_r1.json`：本机（出口 IT）测活 0/50 —— 本地链路限制的对照证据
- `local_tcp_matrix.json`：本机 50 个 host:port 的 TCP 可达性矩阵
- `checkhost_tcp_partial.log`：check-host.net 分布式 TCP 探测（只跑完 7 条；QUIC 端口无意义故中止）
- `singbox_run1.log`：第一轮 sing-box 运行日志

## 两轮一致性

| 轮次 | 存活 | hysteria2 | vless |
|---|---|---|---|
| run1 | 33/50 | 20/30 | 13/20 |
| run2 | 33/50 | 20/30 | 13/20 |

## 存活端点明细（run1，按延迟排序）

| 延迟 ms | 协议 | 地区 | 等级 | 端点 | 出口 IP | 归属 | 吞吐 Mbps | openai | gemini |
|---|---|---|---|---|---|---|---|---|---|
| 306 | hysteria2 | Canada 1Gbps | premium | 66.70.179.198:8444 | 66.70.179.198 | CA | 66.38 | 401 | 403 |
| 329 | hysteria2 | Canada | free | 66.70.179.198:8447 | 66.70.179.198 | CA | 74.36 | 401 | 403 |
| 343 | vless | Canada | free | 66.70.179.198:2053 | 66.70.179.198 | CA | 74.61 | 401 | 403 |
| 592 | hysteria2 | United Kingdom A41 | premium | 51.89.194.151:8444 | 51.89.194.151 | GB | 29.52 | 401 | 403 |
| 599 | vless | United Kingdom A41 | free | 51.89.194.151:2053 | 51.89.194.151 | GB | 28.94 | 401 | 403 |
| 601 | vless | Netherlands | free | 51.15.16.68:2053 | 51.15.16.68 | NL | 27.75 | 401 | 403 |
| 611 | hysteria2 | France | premium | 51.77.217.70:8444 | 51.77.217.70 | FR | 31.21 | 401 | 403 |
| 616 | hysteria2 | Netherlands | premium | 51.15.16.68:8444 | 51.15.16.68 | NL | 27.74 | 401 | 403 |
| 617 | hysteria2 | United Kingdom A41 | free | 51.89.194.151:8446 | 51.89.194.151 | GB | 28.87 | 401 | 403 |
| 637 | hysteria2 | Netherlands | free | 51.15.16.68:8447 | 51.15.16.68 | NL | 27.91 | 401 | 403 |
| 642 | vless | Italy | premium | 57.131.38.163:2053 | 57.131.38.163 | IT | 26.52 | 401 | 403 |
| 647 | vless | France | free | 51.77.217.70:2053 | 51.77.217.70 | FR | 27.0 | 401 | 403 |
| 653 | hysteria2 | Italy | premium | 57.131.38.163:8444 | 57.131.38.163 | IT | 24.04 | 401 | 403 |
| 657 | hysteria2 | Spain A41 | free | 212.227.235.66:8447 | 212.227.235.66 | ES | 26.42 | 401 | 403 |
| 660 | hysteria2 | France | free | 51.77.217.70:8446 | 2001:41d0:303:9746::1 | FR | 28.12 | 401 | 403 |
| 675 | vless | Spain A41 | free | 212.227.235.66:2053 | 212.227.235.66 | ES | 26.13 | 401 | 403 |
| 680 | vless | Poland | premium | 54.37.136.194:2053 | 54.37.136.194 | PL | 12.71 | 401 | 403 |
| 682 | hysteria2 | United States | free | 212.227.235.66:8444 | 212.227.235.66 | ES | 25.93 | 401 | 403 |
| 695 | hysteria2 | Switzerland | premium | 208.69.78.217:8444 | 208.69.78.217 | CH | 25.49 | 401 | 403 |
| 709 | hysteria2 | South Korea | premium | 151.245.106.49:8444 | 151.245.106.49 | KR | 14.67 | 401 | 403 |
| 709 | vless | Switzerland | premium | 208.69.78.217:2053 | 208.69.78.217 | CH | 24.59 | 401 | 403 |
| 716 | hysteria2 | Poland | premium | 54.37.136.194:8444 | 2001:41d0:601:1100::59f9 | PL | 13.87 | 401 | 403 |
| 742 | vless | South Korea | premium | 151.245.106.49:2053 | 151.245.106.49 | KR | 15.55 | 401 | 403 |
| 852 | vless | Türkiye | premium | 151.241.226.201:2053 | 151.241.226.201 | TR | 18.06 | 401 | 403 |
| 858 | hysteria2 | Türkiye | premium | 151.241.226.201:8444 | 151.241.226.201 | TR | 17.5 | 401 | 403 |
| 897 | vless | India | free | 194.61.31.126:2053 | 194.61.31.126 | IN | 16.31 | 401 | 403 |
| 901 | hysteria2 | India | free | 194.61.31.126:8447 | 194.61.31.126 | IN | 14.63 | 401 | 403 |
| 934 | hysteria2 | India | premium | 194.61.31.126:8444 | 194.61.31.126 | IN | 16.31 | 401 | 403 |
| 935 | hysteria2 | Finland 1Gbps | premium | 95.216.27.15:8444 | 95.216.27.15 | FI | 0.0 | 401 | 403 |
| 1324 | hysteria2 | Finland A41 | free | 95.216.27.15:8445 | 95.216.27.15 | FI | 0.0 | 401 | 403 |
| 1451 | vless | Singapore A42 | premium | 45.132.75.213:2053 | 45.132.75.213 | SG | 0.0 | 401 | 0 |
| 2143 | hysteria2 | Singapore A42 | premium | 45.132.75.213:8444 | 45.132.75.213 | SG | 1.29 | 401 | 0 |
| 5067 | vless | Finland A41 | free | 95.216.27.15:2053 | 95.216.27.15 | FI | 0.0 | 401 | 403 |

## 死亡端点（17）

| 协议 | 地区 | 等级 | 端点 | 错误 |
|---|---|---|---|---|
| vless | Australia | free | 46.250.240.80:2053 | curl_rc=97 |
| hysteria2 | Australia | free | 46.250.240.80:8447 | curl_rc=28 |
| hysteria2 | Australia | premium | 46.250.240.80:8444 | curl_rc=28 |
| vless | Brazil | premium | 213.159.66.59:443 | curl_rc=28 |
| vless | Germany A41 | free | 162.55.242.208:2053 | curl_rc=97 |
| hysteria2 | Germany A41 | free | 162.55.242.208:8445 | curl_rc=35 |
| hysteria2 | Germany A42 | premium | 162.55.242.208:8444 | curl_rc=35 |
| hysteria2 | Germany A42 | free | 162.55.242.208:8447 | curl_rc=35 |
| vless | Japan | premium | 46.250.250.149:2053 | curl_rc=97 |
| hysteria2 | Japan | premium | 46.250.250.149:8444 | curl_rc=28 |
| hysteria2 | Sweden | premium | 83.147.254.160:443 | curl_rc=28 |
| vless | Switzerland | premium | 66.163.116.238:2053 | curl_rc=97 |
| vless | Switzerland | premium | 208.69.78.142:8443 | curl_rc=97 |
| hysteria2 | Switzerland | premium | 66.163.116.238:443 | curl_rc=28 |
| vless | United States | free | 74.208.55.79:2053 | curl_rc=97 |
| hysteria2 | United States | premium | 74.208.55.79:8444 | curl_rc=28 |
| hysteria2 | United States | free | 74.208.55.79:8445 | curl_rc=28 |

## 吞吐摘要

{"tested_at": "2026-10-28 21:35:23", "endpoints": 33, "ok": 29, "median_mbps": 26.13, "max_mbps": 74.61}

## 目标可达性摘要（33 个存活端点）

| 目标 | 可达 | 说明 |
|---|---|---|
| openai | 33/33 | 401 = 已到达（无 key） |
| anthropic | 33/33 | 405 |
| claude.ai | 33/33 | 403 |
| chatgpt.com | 33/33 | 200 |
| gemini | 31/33 | 403 |
| netflix | 32/33 | 301 |
| spotify | 33/33 | 200 |

## 本机对照

本机（出口 IT）存活 0/50，全部 curl_rc=7/28/97 —— 本地链路限制，不是节点死。
