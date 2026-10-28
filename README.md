# Cap VPN v1.36 逆向 —— 节点池收割 & 代理池落地工具

> APK 静态逆向 + 上游 API 协议还原 + 节点全量收割 + 真实握手/吞吐/可达性压测 + new-api 代理池落地脚本。
> 样本：`Cap VPN v1.36 b38 (Premium by @ElaMods).apk`（`com.capproject.capvpn`）

**⚠️ 本仓库不含任何可用凭证**：所有 uuid / 密码 / obfs 密码 / REALITY 公钥 / short_id 均已替换为 `REDACTED`。
真实凭证需自行运行 `tools/harvest.py` 生成，且仅限研究与自用（详见 `docs/REVERSE_REPORT.md` 第 8 节）。

---

## 状态表

| 环节 | 状态 | 证据 |
|---|---|---|
| APK 结构分析 | ✅ 完成 | `docs/REVERSE_REPORT.md` |
| 上游 API 端点还原 | ✅ 完成 | 2 条 `get_locations_*` + JWT Bearer，现网 200 |
| 响应 AES 解密 | ✅ 完成 | `tools/capcrypt.py`，37 KB base64 → 19 KB JSON 实测 |
| 节点全量收割 | ✅ 完成 | 35 地区 / 39 服务器 / 107 协议条目 → 50 唯一端点 |
| 本机测活 | ✅ 已跑 | 0/50（**本地链路限制**，非节点死） |
| 真实握手 + 出网验证 | ✅ 完成 | GitHub Actions（US 出口）**33/50 存活**，两次运行一致 |
| 吞吐压测 | ✅ 完成 | 29/33 成功，中位 **26.1 Mbps**，峰值 **74.6 Mbps** |
| 目标站点可达性矩阵 | ✅ 完成 | 33 个存活端点：openai/anthropic/claude.ai/chatgpt/spotify **33/33 可达**，gemini 31/33，netflix 32/33 → `results/RESULTS.md` |
| Demo 页 | ✅ 完成 | `demo_server.py` → `http://127.0.0.1:8971/` |
| new-api 代理池落地 | ✅ 已备脚本 | `deploy/capvpn/` + `docs/new-api对接指南.md`（mihomo 配置已用 `mihomo -t` 校验通过） |
| wireguard 协议 | ❌ 不可用 | URI 为 `{WG_PRIVATE_KEY}` / `{WG_IP}` 模板，客户端拿不到私钥 |

---

## 协议速查

```text
基址   https://capvpn.site/api/
鉴权   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.
       eyJpc3MiOiJteS1hcGkiLCJpYXQiOjE3MzM3MTIwMDAsInJvbGUiOiJzeXN0ZW0ifQ.
       4ZtYgBNkq6x9v6vG8v_fDP9BjoOcyFJ97v6j7g6kjr8
清单   GET get_locations_free_v2_android.php
       GET get_locations_premium_v2_android.php?ispremium=0
解密   base64( IV[16] ‖ "::" ‖ base64(AES-256-CBC/PKCS5(JSON)) )
key    ChangeThisToA32CharRandomString!     (32B ASCII, 硬编码)
协议   vless+REALITY(端口固定，首选) / hysteria2(端口 8444-8447 轮换) / wireguard(不可用)
```

---

## 目录

```
tools/
  capcrypt.py       响应 AES 解密（IV+"::"+AES-CBC）
  harvest.py        拉清单 → 解密 → 归一化 nodes.json
  sbconfig.py       nodes.json → sing-box 配置（每端点一个 socks inbound）
  bench.py          并发测活（走 socks5h 拉 cdn-cgi/trace，拿真实出口 IP）
  speed.py          存活端点 5MB 下载吞吐
  reach.py          目标站点可达性矩阵（openai/gemini/…）
  checkhost.py      check-host.net 分布式 TCP 探测（仅 TCP 协议有意义）
  export_links.py   导出 links.txt / clash yaml / sing-box outbounds / pool_plan
  mask.py           生成脱敏版节点数据（仓库公开用）
deploy/capvpn/
  deploy_pool.py    nodes.json → mihomo 每节点 socks5 → 拨测 → proxies.txt
  capvpn-pool.service
demo_server.py      本地只读 Demo（概览/节点表/订阅链接/刷新）
demo.html
docs/
  REVERSE_REPORT.md       完整逆向报告（含全部工程坑）
  new-api对接指南.md      给集成会话的操作手册
results/                  真实压测产物（不含凭证）+ RESULTS.md 明细表
```

---

## 快速开始

```bash
pip install pycryptodome pyyaml

python tools/harvest.py           # 1. 收割 → nodes.json
python tools/sbconfig.py         # 2. 生成 sing-box 配置
python tools/bench.py --bin ./sing-box --out bench.json      # 3. 测活（需可直连节点的网络）
python tools/speed.py --bench bench.json --bin ./sing-box     # 4. 吞吐
python tools/export_links.py     # 5. 导出订阅/客户端格式
python demo_server.py --port 8971 # 6. Demo 页
```

代理池落地见 `docs/new-api对接指南.md`（mihomo 每节点 socks5 → `TRYINGOPEN_PROXY_FILE`）。

---

## 实测结论（两次独立运行，US 出口）

| 指标 | 结果 |
|---|---|
| 端点存活 | **33/50**（hysteria2 20/30、vless 13/20） |
| 唯一出口 IP | 15（= 节点自身 IP，直出无中间链路） |
| 覆盖地区 | CA GB NL FR ES IT PL CH KR SG IN FI TR |
| 延迟 | 306 – 2143 ms（中位 ~640 ms，含验证机 RTT） |
| 吞吐 | 中位 26.1 Mbps / 峰值 74.6 Mbps（Canada） |
| 不可用 | DE/US/AU/JP/SE/BR 及部分 CH 节点（17 个端点） |
| 目标可达性 | 存活节点对 OpenAI(401)/Anthropic(405)/claude.ai(403)/chatgpt.com(200)/Spotify 全通，Gemini 31/33、Netflix 32/33 |

> 本机（出口 IT）到全部节点 TCP 0/50 —— 本地链路限制，**不要在本机判节点死活**。

---

## 免责

仅供安全研究、协议分析与代理池技术验证。节点属第三方商业服务，未授权接入对外服务存在合规风险，后果自负。
