---
name: apk-vpn-node-harvest
description: 从 Android VPN APK 收割节点/代理池的完整方法论——静态定位 API 与硬编码密钥、破除响应加密、批量测活、代理池落地。适用于 sing-box / v2rayNG 系、Flutter AOT、自建 PHP 后端等各类 VPN 客户端。
---

# Skill: APK VPN 节点收割（代理池）

## 何时用

- 拿到一个 VPN/加速器 APK，目标是把里面的节点变成**可调度代理池**
- 判断某 App 的节点是静态内嵌还是动态下发
- 需要「真活」证据（出口 IP / 吞吐 / 目标站点可达性），而不是厂商自报的 `is_online`

## 五步法

### 1. 先判架构（10 分钟内定路线）

```bash
unzip -l app.apk | head -40                 # 看 dex 数量、lib/、assets/
ls apk/lib/*/                               # libbox.so=sing-box / libv2ray*=v2ray / libgojni=Go(gomobile)
python - <<'P'                              # dex 字符串提取（Windows 没有 strings 时）
import re,glob
o=open('dexstr.txt','w',encoding='utf-8',errors='ignore')
for f in sorted(glob.glob('apk/classes*.dex')):
    for m in re.finditer(rb'[ -~]{5,300}',open(f,'rb').read()):
        o.write(m.group().decode('utf-8','ignore')+'\n')
P
rg -o 'https?://[A-Za-z0-9._~:/?#@!&*+,;=%-]{4,90}' dexstr.txt | sort | uniq -c | sort -rn | head -40
```

判据：
| 信号 | 结论 |
|---|---|
| `libbox.so` + `assets/v2ray_config.json` | sing-box 内核、v2rayNG 系 UI；节点一定由后端下发 |
| `libgojni.so` (Go) | 逻辑在 Go 层，静态只能提字符串，需 frida 动态 hook |
| Flutter（`libapp.so`） | AOT，用 `strings libapp.so` + 找 API 域名 |
| assets 里出现 `wireguard://{WG_...}` | 服务端给的是模板，客户端拿不到私钥 → WG 不可用 |

### 2. 定位网络层（jadx，10 分钟）

```bash
jadx -d out --no-res app.apk
find out/sources -ipath '*<apppkg>*' -name '*.java' | rg -i 'api|service|retrofit|interceptor|auth|token'
```

重点看三处：
1. `AppConstant` / `Constants` —— BASE_URL、JWT、广告位、产品 ID
2. `*Interceptor` —— 响应解密/签名（如 `AesDecryptingInterceptor(decryptPaths=...)`）
3. `RetrofitClient` —— 超时、UA、证书固定（有 pinning 才需要上 frida）

### 3. 破响应加密

常见套路与解法：
- **`base64(IV ‖ "::" ‖ base64(cipher))` + AES-CBC 硬编码 key** → 直接 python 复刻（本仓库 `tools/capcrypt.py`）
- **AES-GCM + PBKDF2(salt 来自 Firebase RemoteConfig)** → 先解 RC，注意 salt 是 ASCII 还是 hex 解码（踩过坑）
- **XOR + 二次 AES**（NoobCrypt 类）→ 逐层剥
- 判定方法：看解密前后的 `Base64.decode(...,2)` 常量、`Cipher.getInstance("AES/...")` 参数、key 字面量长度（长度不对说明你抄漏了字符——本仓库就踩过 31 vs 32）

### 4. 收割 + 归一化

产出统一结构（本仓库 `nodes.json`）：`locations[] → servers[] → protocols{proto: {host,port,userinfo,query,raw}}`，
并**去重成唯一端点**（同 IP 多地区标签、同节点多协议都会重复）。

必查项：
- 凭证是否轮换（连拉两次对比 `userinfo`）
- 端口是否轮换（本样本 hysteria2 在 8444–8447 间随请求变，vless 固定 2053）
- 哪些协议是模板占位符（`{WG_PRIVATE_KEY}`）

### 5. 真活验证（关键，别自欺）

| 手段 | 适用 | 结论强度 |
|---|---|---|
| 本机 `curl --socks5-hostname` + `cdn-cgi/trace` | 任意 | ★★★ 拿到出口 IP 即真活 |
| check-host.net 分布式 TCP | 仅 TCP 协议 | ★★ 只能证明端口开放；**QUIC/UDP（hysteria2）会误判全死** |
| GitHub Actions（自建 workflow + sing-box） | 本机被墙/被限制时 | ★★★ 多地区外部视角，可重复，产物可下载 |

**判定标准**：`exit_ip` 必须等于节点自身 IP 或至少地理与标签一致；只看 `curl` 退出码不算活。

压测必备三件套：
1. `bench`：存活 + 延迟 + 出口 IP/地区
2. `speed`：5 MB 下载算 Mbps
3. `reach`：目标站点可达性矩阵（401/403/404 = 可达；000 = 不可达）

### 6. 代理池落地

new-api 系（`TRYINGOPEN_PROXY_FILE`）只吃 `socks5://host:port`：
`nodes.json → mihomo（每节点一个 socks listener，绑 Docker 网桥 172.18.0.1）→ 拨测 → proxies.txt`。
见 `deploy/capvpn/deploy_pool.py` + `docs/new-api对接指南.md`。

## 踩过的坑（照抄别再踩）

1. **端口段被占用 → 假阳性**：sing-box FATAL 后进程仍在，探针打到别人（mihomo）的 socks 上，
   得到「20/50 存活、出口全是 DigitalOcean」的假数据。**测活前 `netstat -ano | grep :345`**。
2. **Python 相对路径 Popen → WinError 2**：Windows 上 `subprocess` 一律用绝对路径。
3. **`python x.py > out.json` 在 Windows 写成 GBK** → `UnicodeDecodeError`。用 `open(...,'wb')` 写字节。
4. **check-host 判 hysteria2 死** → QUIC 是 UDP，TCP 探测无意义。
5. **GitHub Actions workflow 不注册**：`workflow_dispatch.inputs` 里出现中文 `description` 会导致
   `actions/workflows` 查不到该文件（total_count=0）。inputs 只用 ASCII。
6. **凭证抄漏字符**：`ChangeThisToA32CharRandomString!` 少一个 `A` 就 31 字节，AES 直接不成立。
7. **厂商 `is_online` 不可信**：标在线的节点实测可能是死的，反之亦然；地区标签也可能错标（US 节点出口在 ES）。
8. **本机被判死的节点不一定是死的**：先验证本机到任意外网端口的通行性，必要时换外部 vantage（Actions）。

## 合规

节点是第三方商业资源。研究/自用/内部演练可以；对外售卖或大规模转售属未授权使用。
公开仓库一律脱敏（`tools/mask.py`），凭证不进代码常量，走文件 + 定时刷新。
