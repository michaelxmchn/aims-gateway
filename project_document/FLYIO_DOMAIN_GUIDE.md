# Fly.io 域名绑定指南 — www.aimsgateway.com

> AIMS Gateway | 2026-06-16  
> 将 `www.aimsgateway.com` 绑定至 `aims-gateway.fly.dev`

---

## 当前状态

| 项目 | 值 |
|---|---|
| 生产 URL | `https://aims-gateway.fly.dev` |
| 目标域名 | `www.aimsgateway.com` |
| Fly.io App | `aims-gateway` |
| DNS 托管 | 外部 DNS 服务商（需登录管理后台） |

---

## 操作步骤

### 1. 添加 DNS A 记录（或 CNAME）

在 `aimsgateway.com` 的 DNS 管理后台（如 Cloudflare / Namecheap / GoDaddy）添加以下记录：

| 类型 | 名称 | 值 |
|---|---|---|
| `CNAME` | `www` | `aims-gateway.fly.dev` |

**备用方案**（如 DNS 服务商不支持 CNAME 到根域，使用 A 记录指向 Fly.io 边缘 IP）：
| 类型 | 名称 | 值 |
|---|---|---|
| `A` | `www` | `66.241.125.80` |
| `A` | `www` | `66.241.125.144` |

> Fly.io 边缘 IP 可能会变更，建议优先使用 CNAME。可运行 `dig aims-gateway.fly.dev +short` 获取当前 IP 列表。

### 2. 在 Fly.io 上添加证书

```bash
# 安装 flyctl（如未安装）
curl -L https://fly.io/install.sh | sh

# 登录
flyctl auth login

# 为应用添加域名和证书
flyctl certs create www.aimsgateway.com --app aims-gateway

# 验证证书状态
flyctl certs list --app aims-gateway
```

### 3. 验证 DNS 传播

```bash
# 检查 CNAME 解析
dig www.aimsgateway.com CNAME +short
# 预期输出: aims-gateway.fly.dev

# 检查证书颁发状态
flyctl certs show www.aimsgateway.com --app aims-gateway
# 预期: "Certificate Authority: Let's Encrypt", "Status: Ready"
```

### 4. 验证 HTTPS 访问

```bash
# 等待 DNS 传播（通常 1-10 分钟，视 TTL 而定）
curl -I https://www.aimsgateway.com/api/health
# 预期: HTTP/2 200
```

---

## 常用运维命令

```bash
# 查看证书状态
flyctl certs list --app aims-gateway

# 查看部署状态
flyctl status --app aims-gateway

# 查看最新部署日志
flyctl logs --app aims-gateway

# 重新部署
flyctl deploy --app aims-gateway

# 扩缩容（默认 1 实例）
flyctl scale count 2 --app aims-gateway
```

---

## 故障排除

| 现象 | 原因 | 解决 |
|---|---|---|
| `curl: Could not resolve host` | DNS 未传播 | 检查 DNS 记录是否生效，等待 TTL 过期 |
| `curl: SSL certificate problem` | 证书未颁发 | 运行 `flyctl certs create` 触发 Let's Encrypt |
| `HTTP 404` | 路径错误 | 确认请求路径以 `/api/` 开头 |
| `HTTP 403` | 缺少认证头部 | 添加 `X-Wallet-Address`, `X-Signature`, `X-Timestamp` |
| 证书状态 `Pending` | Let's Encrypt 验证中 | 通常 1-5 分钟自动完成，最长 30 分钟 |

---

## 参考

- [Fly.io Custom Domains 官方文档](https://fly.io/docs/app-guides/custom-domains/)
- [Fly.io SSL/TLS Certificates](https://fly.io/docs/app-guides/custom-domains/#custom-domains-with-fly-certificates)
- 现有生产端点: `https://aims-gateway.fly.dev/api/health`
