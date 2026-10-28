# Cap VPN v1.36 (b38) 逆向报告 —— 节点池 / 代理池收割

> 样本：`Cap VPN v1.36 b38 (Premium by @ElaMods).apk`（83,084,130 字节，ElaMods 重打包）
> 包名：`com.capproject.capvpn`　版本：`Version 1.36`（versionCode 38）
> 结论：**已从上游 API 完整收割节点清单，含 hysteria2 / vless-REALITY 全套凭证；真实握手 + 出网验证 33/50 端点存活（GitHub Actions US 出口，两次运行结果完全一致）。**

---

## 1. APK 静态结构

| 项 | 内容 |
|---|---|
| dex | `classes.dex` ~ `classes10.dex`（共 10 个，约 37 MB） |
| native | `lib/arm64-v8a/libbox.so`（62 MB，**sing-box 核心**，Go/gomobile）、`libmmkv.so` |
| assets | `v2ray_config.json`（v2rayNG 模板残留，含 `v2ray.cool:10086` 示例节点，非真实节点）、`custom_routing_*`（v2rayNG 路由模板）、`ad-viewer/`、Lottie 动画 |
| 重打包痕迹 | `E_l_a_Mods.xml`、`assets/ads.txt`、`lib/arm64-v8a/El-a Mo-ds.so`（85 B 占位） |
| 完整性/风控 | `com.pairip.*`（Google Play Integrity license check）、Firebase Crashlytics、AdMob、UnityAds |
| 应用代码包 | `com.capvpn.capp.*`（413 个 Java 类，Retrofit + Hilt + MMKV） |

一句话架构：**v2rayNG 系 UI + sing-box 内核 + 自建 PHP 后端下发节点 URI**。

---

## 2. 网络层逆向（关键）

### 2.1 端点表

基址：`AppConstant.BASE_URL = "https://capvpn.site/api/"`（`com.capvpn.capp.app.AppConstant`）

| 方法 | 路径 | 说明 | 现网状态 |
|---|---|---|---|
| GET | `get_locations_free_v2_android.php` | 免费节点清单（AES 加密响应） | 200 |
| GET | `get_locations_premium_v2_android.php?ispremium=0` | 高级节点清单（AES 加密响应） | 200（`ispremium=0` 由破解版改写，等于白嫖全量） |
| GET | `get_best_server.php?type=&platform=android` | 最优节点（`MainActivity` 硬编码 URL） | **404，已下线** |
| POST | `send_email.php` | 联系表单 | 存在 |
| POST | `add_user` / `subscription` / GET `get_sub_status` | Google 登录与内购校验 | 存在，本任务未涉及 |

### 2.2 鉴权：硬编码 JWT（HS256）

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.
eyJpc3MiOiJteS1hcGkiLCJpYXQiOjE3MzM3MTIwMDAsInJvbGUiOiJzeXN0ZW0ifQ.
4ZtYgBNkq6x9v6vG8v_fDP9BjoOcyFJ97v6j7g6kjr8
```

- payload：`{"iss":"my-api","iat":1733712000,"role":"system"}`（iat = 2024-12-09 08:00 UTC）
- 无过期字段、无设备绑定、无签名校验交互 → **一个 token 全局通用**，客户端不做任何刷新
- 缺失时返回 `Auth missing`（HTTP 200 + 明文），不是 401

### 2.3 响应加密：AES-CBC + "::" 分隔（`a/AbstractC0241a.g()`）

```text
响应体 = Base64( IV[16字节] || "::" || Base64( AES-CBC-PKCS5Padding(JSON) ) )
AES key = "ChangeThisToA32CharRandomString!"   // 32 字节 ASCII，硬编码
```

- 仅两条路径走解密：`AesDecryptingInterceptor` 构造参数
  `setOf("get_locations_free_v2_android.php", "get_locations_premium_v2_android.php")`
- 其他路径直接返回明文；解密失败时静默回退原始字节（`Log.e("AES", ...)`）
- 实现：`tools/capcrypt.py`（已实测，37 KB base64 → 19 KB JSON）

### 2.4 请求层

`RetrofitClient`：HTTP/2 + HTTP/1.1、connect/read/write 均 15 s、`retryOnConnectionFailure(true)`、
`HttpLoggingInterceptor.LEVEL_NONE`；UA 未显式设置（OkHttp 默认 `okhttp/x.y.z`）。
无证书固定（no pinning）、无设备指纹、无 header 签名 → 纯 HTTP 客户端即可完整复刻。

---

## 3. 节点数据结构

`response[]` = Location，`Location.servers[]` = Server，`Server.protocols` = 协议 URI 字典：

```jsonc
{
  "id": "116", "name": "United Kingdom A41", "type": "free,premium",
  "is_auto_rotate": "1", "best_server_score": "82.610", "healthy_server_count": "3",
  "servers": [{
    "id": "1200", "name": "UK-1", "country": "UK", "ip": "51.89.194.151",
    "is_online": "1", "port_open": "1", "health_score": "82.610",
    "bandwidth_mbps": "193.44", "cpu_pct": "7.92", "ram_pct": "9.12",
    "last_health_at": "2026-10-28 21:05:03",       // 厂商每 5 分钟自探活
    "protocol_type": "wireguard|multi",
    "protocols": {
      "wireguard":  "wireguard://{WG_PRIVATE_KEY}@IP:51820?address={WG_IP}&peer_pubkey=...&dns=1.1.1.1",
      "hysteria2":  "hysteria2://用户:密码@IP:8447?mport=24000-24199,37000-37199&obfs=salamander&obfs-password=...&sni=vpn.local&insecure=1",
      "vless":      "vless://UUID@IP:2053?encryption=none&security=reality&sni=www.apple.com&fp=chrome&pbk=...&sid=...&type=tcp"
    }
  }]
}
```

### 3.1 三种协议的可利用性

| 协议 | 凭证完整性 | 端口稳定性 | 结论 |
|---|---|---|---|
| **vless + REALITY** | 完整（uuid / pbk / sid / sni / fp 全给） | **端口固定**（2053 / 8443 / 443） | ✅ **代理池首选** |
| **hysteria2** | 完整（user:pass / obfs 密码 / sni） | 端口在 **8444–8447 间随请求轮换**，`8444` 恒可用 | ✅ 可用，需每轮重新拉取或固定 8444 探测 |
| wireguard | **模板占位符** `{WG_PRIVATE_KEY}` / `{WG_IP}` | — | ❌ **不可用**。代码里 `buildSingBoxWireGuardEndpoint()` 直接 `private_key = profileItem.getSecretKey()`（即 URI 里的字面占位符），本地地址恒为 `V2rayConstants.WIREGUARD_LOCAL_ADDRESS_V4 = 172.16.0.2/32`，MTU 1420；服务端既然拿不到我们的公钥，握手必然失败。另 2 条带 `publickey/reserved` 的是 WARP 风格变体（同样无 key） |

> 破解版把 `ispremium` 置 0，因此免费/高级两套清单都能拉；高级清单多出 JP/KR/SG/CH/PL/TR/BR/SE 等地。

---

## 4. 收割规模

| 指标 | 数值 |
|---|---|
| Location（地区条目） | 35 |
| Server（服务器条目） | 39（free 13 / premium 26） |
| 协议条目合计 | 107（wireguard 36 / hysteria2 36 / vless 35） |
| **唯一协议端点（去重后）** | **50**（hysteria2 30 + vless 20） |
| 唯一出口 IP | 15 |
| 覆盖国家/地区 | CA GB NL FR ES IT PL CH KR SG IN FI TR（+US/DE/JP/AU/SE/BR 条目存在但当前不通） |

---

## 5. 实测验活（证据）

### 5.1 本机（出口 IT 80.174.118.51）：0/50 —— **本地链路限制，不是节点全死**

- 39 个节点 IP 的 50 个 host:port 全部 TCP 超时（4 s 超时并发 40 线程跑完）
- 同机可正常访问 github.com / cloudflare / 8.8.8.8:53，但 1.1.1.1:443、9.9.9.9:443 也超时 → 本机出口存在选择性阻断
- 交叉验证：check-host.net 分布式 TCP 探测显示 `51.89.194.151:2053` 在 **CA/NL/US** 视角开放（0.01–0.13 s）→ 节点本身活着

> ⚠️ 教训：本机 24000 端口段被残留的 `mihomo.exe`（fastvpn 会话遗留，PID 3920）占用，第一轮压测把 sing-box inbound 全绑定失败，探针打到 mihomo 上，得到「20/50 存活、出口全是 DigitalOcean US」的**假阳性**。换端口段 34500 后归零。压测前必须确认端口段未被占用（`netstat -ano | findstr :3450`）。

### 5.2 GitHub Actions（Azure US 出口）：**33/50 端点存活，两次独立运行结果完全一致**

（验证用的临时私有仓库 `lza6/capvpn-e2e` 已在使用后删除；workflow 内容见 `results/` 说明，结构为：
下载 sing-box → `sing-box check` → `bench.py` → `speed.py` → `reach.py` → 上传产物。）

- 方式：`.github/workflows/e2e.yml` → 下载 sing-box 1.14.4 → 50 个端点各绑一个 socks inbound（34500+）→ 并发 `curl --socks5-hostname` 拉 `https://www.cloudflare.com/cdn-cgi/trace`
- 判定：拿到**真实出口 IP** + `loc` 与节点声称国家一致 = 活
- 存活：hysteria2 **20/30**、vless **13/20**；合计 **33/50**
- 出口 IP **等于节点自身 IP**（如 66.70.179.198 → CA、51.89.194.151 → GB、208.69.78.217 → CH），部分走 IPv6（`2001:41d0:*` = OVH）
- 延迟（含 runner→节点 RTT）：**306 ms ~ 2143 ms**，中位约 640 ms
- 吞吐（5 MB 下载）：**存活 29/33 成功，中位 26.13 Mbps，最高 74.61 Mbps**（Canada 66.70.179.198）
- 两轮 `by_proto` 计数完全相同（20/30、13/20）→ **稳定性初步成立**
- 目标站点可达性矩阵（33 个存活端点 × 7 目标，见 `results/RESULTS.md`）：
  `openai` 33/33（401）、`anthropic` 33/33（405）、`claude.ai` 33/33（403）、`chatgpt.com` 33/33（200）、
  `spotify` 33/33（200）、`netflix` 32/33（301）、`gemini` 31/33（403）
  → 说明这些**数据中心出口对主流 AI 服务的网络层完全可达**（是否被风控拒绝需要真 key 才能验，本任务预算为 0 未做）

### 5.3 死亡端点（17 个）与原因

| 端点 | 错误 | 判断 |
|---|---|---|
| 162.55.242.208（DE A41/A42，3 条） | `curl_rc=35` / `rc=97` | 端口不通 / TLS 被重置，节点实际不可用 |
| 74.208.55.79（US，3 条） | `rc=97` / `rc=28` | 不可用 |
| 46.250.240.80（AU）、46.250.250.149（JP） | `rc=28/97` | 不可用 |
| 83.147.254.160（SE）、66.163.116.238（CH）、208.69.78.142（CH） | `rc=28/97` | 不可用 |
| 213.159.66.59（BR，仅 vless） | `rc=28` | 不可用 |

厂商自己的 `is_online` 标记与实测**不完全一致**（例如 DE A42 `is_online=0` 确实死；但 SE `is_online=0` 也死，吻合；而 US `is_online=1` 实测却死）→ **不能只信上游健康字段，必须自测**。

### 5.4 数据错标

`premium / United States / 212.227.235.66:8444` 实际出口在 **ES（西班牙）**，与 `free / Spain A41` 同一个 IP → 厂商地区标签有复用/错标，做地区选择时以**实测出口 IP 归属**为准。

---

## 6. 复现步骤

```bash
# 0) 依赖
pip install pycryptodome          # 仅解密需要
# sing-box 1.14.4 (Windows/Linux 均可)

# 1) 收割 + 解密 + 归一化
python tools/harvest.py            # → nodes.json（35 地区 / 39 服务器 / 107 协议条目）

# 2) 生成 sing-box 配置（每端点一个 socks inbound，34500 起）
python tools/sbconfig.py           # → sb_config.json + sb_config.json.map.json

# 3) 逐端点测活（需要能直连节点的网络环境）
python tools/bench.py --config sb_config.json --mapfile sb_config.json.map.json \
       --bin ./sing-box --conc 8 --timeout 12 --out bench_result.json

# 4) 进出口吞吐
python tools/speed.py --bench bench_result.json --config sb_config.json \
       --mapfile sb_config.json.map.json --bin ./sing-box --out speed.json

# 5) 目标站点可达性矩阵（判断能否给 new-api 渠道用）
python tools/reach.py --bench bench_result.json --config sb_config.json \
       --mapfile sb_config.json.map.json --bin ./sing-box --out reach.json

# 6) 导出订阅/客户端格式（脱敏演示数据仓库内为 nodes_public.json）
python tools/export_links.py       # → dist/links.txt, dist/clash_proxies.yaml, dist/singbox_outbounds.json, dist/pool_plan.json

# 7) Demo 页
python demo_server.py --port 8971  # → http://127.0.0.1:8971/
```

---

## 7. 采集工程坑（都踩过）

| 坑 | 现象 | 处理 |
|---|---|---|
| 端口段被占用 | sing-box `bind: Only one usage of each socket address`，FATAL 后进程存活但无 listener，探针打到别人的 mihomo 上 → 假阳性 | 压测前 `netstat -ano` 检查端口段；换 34500 段 |
| Python 相对路径启动 exe | `FileNotFoundError: [WinError 2]`（同目录 bash 可直接执行） | `subprocess` 一律用绝对路径 |
| Windows 控制台编码 | `python x.py > out.json` 把 JSON 写成 GBK 乱码 → `UnicodeDecodeError: 0xa8` | 用 `open(...,'wb')` 写字节，别依赖 stdout 重定向 |
| check-host TCP 探测 | hysteria2 是 **QUIC/UDP**，TCP 探测恒为 `refused`，会误判全死 | UDP 协议只能用真客户端握手验证 |
| GitHub Actions workflow 不注册 | `workflow_dispatch.inputs` 里放中文 `description` 后，`actions/workflows` 里查不到该文件（total_count=0） | inputs 里只用 ASCII，或去掉 inputs |
| 上游端口轮换 | hysteria2 端口每次请求在 8444–8447 之间变 | 固定 8444 或每轮重新 harvest |
| 上游 `get_best_server.php` | 404 | 已下线，不依赖 |

---

## 8. 合规边界（请遵守）

- 本仓库**不含可用凭证**：`nodes_public.json` 与 `dist/` 中所有 uuid / 密码 / obfs 密码 / reality pbk / short_id 均已替换为 `REDACTED`。
- 节点为第三方商业服务（capvpn.site）的付费资源。把它接入自有代理池用于**生产/转售**属于未授权使用，风险自负；建议仅作**研究、连通性验证与代理池技术演练**。
- 建议用途：验证自有代理池调度/健康检查/故障切换链路；若要长期稳定出口，请使用自有 VPS 或授权代理服务商。
