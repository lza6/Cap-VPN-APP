# Cap VPN 节点池 → new-api 代理池 对接指南

> 面向：负责把本批节点接进 new-api 的另一个会话 / 运维同学。
> 前提：new-api 侧已有代理池实现（`relay/channel/tryingopen/proxy_pool.go`，环境变量 `TRYINGOPEN_PROXY_FILE` / `TRYINGOPEN_PROXIES`，渠道类型 `64 TryingOpen`）。
> 本仓库**不含可用凭证**：先用 `tools/harvest.py` 拉真实节点生成 `nodes.json`，再往下走。

---

## 0. 一页速查

| 项 | 值 |
|---|---|
| 上游清单 API | `GET https://capvpn.site/api/get_locations_free_v2_android.php` 和 `..._premium_v2_android.php?ispremium=0` |
| 鉴权 | `Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJteS1hcGkiLCJpYXQiOjE3MzM3MTIwMDAsInJvbGUiOiJzeXN0ZW0ifQ.4ZtYgBNkq6x9v6vG8v_fDP9BjoOcyFJ97v6j7g6kjr8` |
| 响应解密 | `base64( IV16 ∥ "::" ∥ base64(AES-256-CBC/ PKCS5, key="ChangeThisToA32CharRandomString!" ) )` → `tools/capcrypt.py` |
| 可用协议 | **vless + REALITY**（端口固定，首选）、**hysteria2**（端口 8444–8447 轮换） |
| 不可用协议 | wireguard（URI 是 `{WG_PRIVATE_KEY}` / `{WG_IP}` 模板，无真实密钥） |
| 实测存活 | 33/50 端点（hysteria2 20/30、vless 13/20），两次独立运行一致 |
| 唯一出口 IP | 15 个，覆盖 CA GB NL FR ES IT PL CH KR SG IN FI TR |
| 吞吐 | 5 MB 下载：29/33 成功，中位 26.1 Mbps，最高 74.6 Mbps（Canada） |
| 延迟 | 306–2143 ms（含验证机→节点 RTT），中位 ~640 ms |
| 有效期 | 凭证（uuid/密码）跨请求稳定；**hysteria2 端口随请求轮换**，`8444` 恒可用 |

---

## 1. 落地架构（推荐）

```
tools/harvest.py  ──(6h 定时)──>  nodes.json
                                      │
                    deploy_pool.py ───┴──> mihomo（每节点一个 socks5 listener, 172.18.0.1:42000+）
                                      │
                             拨测存活 → capvpn_proxies.txt（只写当场测通的）
                                      │
        new-api: TRYINGOPEN_PROXY_FILE=/opt/new-api/data/capvpn_proxies.txt  （渠道类型 64）
```

为什么不让 new-api 直接吃 URI：
1. new-api 代理池只认 `http(s)://` / `socks5://`，不认 `vless://` / `hysteria2://`；
2. hysteria2 是 QUIC/UDP，必须由本地内核落地成 socks5 才能被 new-api 复用；
3. Docker 里 new-api 的 `127.0.0.1` 是容器自己的命名空间 → **socks 必须绑 Docker 网桥网关**（默认 `172.18.0.1`），这点和仓库里 `deploy/supervpn/deploy_pool.py` 的既有做法一致。

---

## 2. 操作步骤（服务器端）

```bash
# 1) 准备目录与二进制
mkdir -p /opt/capvpn && cd /opt/capvpn
# mihomo 直接放进来（可用 release 包，或复用 deploy/supervpn/mihomo）
cp /path/to/mihomo /opt/capvpn/mihomo && chmod +x /opt/capvpn/mihomo

# 2) 代码 + 节点清单
cp -r <本仓库>/* /opt/capvpn/
python3 tools/harvest.py                # 需要能访问 capvpn.site；产物 nodes.json（含真实凭证，勿外传）

# 3) 起池（首次前台跑一遍，确认存活与出口 IP）
MIHOMO_BIN=/opt/capvpn/mihomo \
CP_LISTEN_HOST=172.18.0.1 CP_SOCKS_BASE=42000 \
CP_OUT=/opt/new-api/data/capvpn_proxies.txt \
python3 deploy/capvpn/deploy_pool.py --restart
#   → 输出形如：存活 33/50，已写 /opt/new-api/data/capvpn_proxies.txt

# 4) 交给 systemd 常驻
cp deploy/capvpn/capvpn-pool.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now capvpn-pool
```

### 2.1 new-api 侧

```bash
# docker-compose.yml / .env 里追加（多个清单文件用逗号分隔，面板会各成一张卡片）
TRYINGOPEN_PROXY_FILE=/opt/new-api/data/capvpn_proxies.txt
```

重启 new-api 后：后台「TwoAPI 面板 → 代理池」应出现一张以文件名 `capvpn_proxies.txt` 为 origin 的卡片；
渠道类型选 `TryingOpen`（`ChannelTypeTryingOpen = 64`）。代理池每轮的拨测/熔断逻辑由 new-api 自己负责，
本池只需保证 `proxies.txt` 里的端口**当场是通的**。

清单文件格式（new-api 原生支持）：

```
# capvpn pool generated 2026-10-29 05:40:00
socks5://172.18.0.1:42000
socks5://172.18.0.1:42001
...
```

### 2.2 定时刷新（重要）

hysteria2 端口会轮换、节点会掉线，建议 6 小时一轮：

```bash
# /etc/systemd/system/capvpn-refresh.service  +  capvpn-refresh.timer
# ExecStart=/usr/bin/python3 /opt/capvpn/deploy/capvpn/deploy_pool.py
# （脚本内部会重新读 nodes.json，先重跑 harvest.py 再 generate）
```

或直接用 cron：

```cron
17 */6 * * * cd /opt/capvpn && python3 tools/harvest.py && MIHOMO_BIN=/opt/capvpn/mihomo python3 deploy/capvpn/deploy_pool.py --restart >/var/log/capvpn-refresh.log 2>&1
```

> `--restart` 会 `pkill -f mihomo`。如果同一台机器还跑着别的 mihomo（例如 `deploy/supervpn` 那套），
> **不要用 `--restart`**，改成重启对应 systemd 单元，或者给两套池子用不同的进程名/端口段。

---

## 3. 其他接入方式

### 3.1 mihomo / clash 直接导入（临时验证用）

`dist/clash_proxies.yaml` 是本仓库导出的 proxies 片段（凭证字段为 `REDACTED`，需先跑 harvest + export_links 得到真实值）：

```bash
python tools/export_links.py     # → dist/clash_proxies.yaml（71 条 proxy）
# 把那一段 proxies: 合并进你的 mihomo config，proxy-groups 里选 CAPVPN
```

### 3.2 sing-box 直接导入

`dist/singbox_outbounds.json` 是 71 条 outbound（已按节点命名 `capvpn-<地区>-<server_id>-<协议>`），
直接贴进 `outbounds` 并配 `route.rules` 即可。

### 3.3 URI 直导（人工调试）

`dist/links.txt`（脱敏版为空，需自己生成真实值）可直接导入 v2rayN / NekoBox / Shadowrocket。

### 3.4 单节点单次测活（排障）

```bash
python tools/sbconfig.py                      # 生成 50 个 socks inbound（34500+）
python tools/bench.py --config sb_config.json --mapfile sb_config.json.map.json \
       --bin ./sing-box --conc 8 --timeout 12 --out bench.json
python tools/speed.py --bench bench.json --config sb_config.json \
       --mapfile sb_config.json.map.json --bin ./sing-box --out speed.json
python tools/reach.py --bench bench.json --config sb_config.json \
       --mapfile sb_config.json.map.json --bin ./sing-box --out reach.json
```

---

## 4. 选池策略建议

| 需求 | 选择 |
|---|---|
| 长期稳定（不频繁换端口） | **只用 vless 端点**（13 个，端口 2053/8443/443 固定） |
| 地区覆盖优先 | 按实测出口归属选：CA GB NL FR ES IT PL CH KR SG IN FI TR |
| 大带宽 | Canada `66.70.179.198`（vless 74.6 Mbps / hy2 66–74 Mbps） |
| 低延迟 | Canada（306 ms）> UK/NL/FR（590–650 ms）> 亚洲（SG 1.4–2.1 s） |
| 不要用的 | DE `162.55.242.208`、US `74.208.55.79`、AU `46.250.240.80`、JP `46.250.250.149`、SE `83.147.254.160`、CH `66.163.116.238` / `208.69.78.142`、BR `213.159.66.59`（实测全不通） |

注意：`premium/United States` 与 `free/Spain A41` 是同一个 IP（`212.227.235.66`），实际出口在 **ES** —— 选地区请以 `bench.json` 里的 `exit_ip` / `exit_loc` 为准，别信上游标签。

---

## 5. 已知风险与红线

1. **凭证稳定性**：uuid / hysteria2 密码在两次采样中 100% 一致（96/107 完全相同，差异全是端口轮换），
   但上游随时可以改。**不要把这批凭证写进代码常量**，一律走 `nodes.json` 文件 + 定时刷新。
2. **可用率**：本批 66%（33/50）。代理池调度必须做失败切换，不能假设全活。
3. **上游是商业付费服务**（capvpn.site，$周/月/年订阅）。把它接进对外服务的代理池属于未授权使用：
   - 仅自用、内部测试、技术演练可以；
   - 对公售卖 / 大规模转售请自行评估合规风险，出了问题不要怪节点。
4. **IP 类型**：出口全部是数据中心 IP（OVH / Hetzner / Contabo / DigitalOcean 系），
   OpenAI / Anthropic / Google 这类服务的数据中心 IP 风控较重，实际可用性需按渠道单独验证（`tools/reach.py` 已给矩阵）。
5. **速率**：单节点 `bandwidth_mbps` 字段是厂商自报（如 193 Mbps），实测共享带宽中位 26 Mbps，
   并发上去会互相踩。建议单节点并发 ≤ 3~5。

---

## 6. 排障清单

| 现象 | 原因 | 处理 |
|---|---|---|
| `proxies.txt` 生成后 new-api 全部拨测失败 | socks 绑了 `127.0.0.1`，容器内不可达 | `CP_LISTEN_HOST=172.18.0.1`（`docker network inspect bridge` 确认网关） |
| mihomo 启动即 FATAL `bind: address already in use` | 端口段被占（本机就踩过：残留 mihomo 占了 24000 段） | 换 `CP_SOCKS_BASE`，或先 `netstat -tlnp | grep 4200` 排查 |
| 存活率突然从 33 掉到个位数 | 上游改了端口/凭证，或 IP 被目标地区风控 | 重跑 `harvest.py` 再拨测；对比 `bench.json` 的 `exit_ip` |
| hysteria2 端口连不上 | 端口在 8444–8447 间轮换 | 用最新 harvest 结果里的端口；或只用 8444 |
| wireguard 一直握手失败 | URI 里是 `{WG_PRIVATE_KEY}` 占位符，无真实私钥 | 放弃 WG，用 vless/hysteria2 |

---

## 7. 验证过的事实（避免重复踩坑）

- 两次独立 GitHub Actions 运行（Azure US 出口）：`hysteria2 20/30`、`vless 13/20`，**计数完全一致**
- 出口 IP = 节点自身 IP（说明无中间链路，是直出），部分节点走 IPv6（`2001:41d0::/32` OVH）
- 本机（出口 IT）到全部节点 TCP 0/50 可达，但同机访问 github/cloudflare 正常 → **别在本机判节点死活**
- `get_best_server.php` 已下线（404），`is_online` 字段不可信（US 标在线实测死）
