# AIMS aims-cli 8 步 DRM 加壳发布指南

> **适用网络**: Base Sepolia（测试网）→ Base Mainnet（正式发布）  
> **技能示例**: `tiktok_competitive_intel` — 马来西亚/东南亚 TikTok Shop 竞品情报智能体  
> **前置依赖**: Python 3.10+、pip、Node.js（仅 PyArmor 需要）、**EVM 钱包私钥（带 Base Sepolia 测试网 USDC）**

---

## 概述

本指南演示如何将一个 **AIMS Skill Python 脚本**通过 aims-cli 工具链执行 **8 步 DRM 加壳发布流程**，最终在 Base Sepolia 测试网上注册为可调用去中心化技能。

8 步流程：

| # | 步骤 | 产出 | 安全层级 |
|---|------|------|----------|
| 1 | `aims-cli init` | `aims.config.json` | Schema 强校验 |
| 2 | `aims-cli login` | `~/.aims/credentials` (Keystore v3) | AES-128-CTR 加密 |
| 3 | PyArmor 二进制加壳 | `wrapper.so` / `.pyd` | C 扩展层源码保护 |
| 4 | Cython 回退编译 | `logic.cpython-*.so` | CPython ABI 级闭源 |
| 5 | AES-256-GCM 核心加密 | `logic.enc` | 军事级对称加密 |
| 6 | EIP-191 版权签名 | 链上签名证明 | 钱包身份绑定 |
| 7 | ZIP 打包 + 网关上传 | `dist.zip` → IPFS/Arweave | 内容寻址持久化 |
| 8 | 链上元数据注册 | Base Sepolia 合约记录 | 不可篡改存证 |

---

## Step 0 — 准备工作

```bash
# 1. 克隆或创建技能项目（以 tiktok_competitive_intel 为例）
mkdir -p ~/tiktok-intel && cd ~/tiktok-intel

# 2. 安装 aims-cli
pip install aims-cli  # 或从源码安装
# 验证
aims-cli --help

# 3. 安装可选加壳工具（推荐至少安装一个）
pip install pyarmor      # 首选 — 商业级加壳保护
# 或
pip install cython       # 回退方案 — C 扩展编译

# 4. 安装加密依赖
pip install cryptography eth-account

# 5. 准备技能源文件
cat > main.py << 'PYEOF'
"""TikTok Shop 竞品情报入口 — DRM 加壳验证"""
from tiktok_competitive_intel import execute

def main(params: dict) -> dict:
    return execute(params)
PYEOF

# 6. 复制技能模块
cp /path/to/tiktok_competitive_intel.py .
```

---

## Step 1 — `aims-cli init`：交互式配置向导

生成项目的 `aims.config.json`——这是后续所有步骤的单一事实来源。

```bash
aims-cli init
```

### 交互过程

```
✦ AIMS Config Initialization
✦ Revenue Matrix (2×3)

Revenue Split Matrix
  Q1  worker_collab + pay_per_task    →  70% Developer / 25% Worker /  5% Platform
  Q2  worker_collab + subscription     →  95% Developer /  0% Worker /  5% Platform
  Q3  direct_skill   + pay_per_task    →  95% Developer /  0% Worker /  5% Platform
  Q4  direct_skill   + subscription    →  95% Developer /  0% Worker /  5% Platform
  Q5  direct_skill   + buyout          →  95% Developer /  0% Worker /  5% Platform

Function type [worker_collab/direct_skill]: direct_skill
Billing mode [pay_per_task/subscription/buyout]: pay_per_task

  ✓ Q3: 95% Developer / 0% Worker / 5% Platform

skill_id: tiktok_competitive_intel
version [1.0.0]:
developer_wallet (EIP-55 0x... address): 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18
price_per_task_usdc: 0.05
entry_point [main.py]:
gateway_url: https://aims-gateway-xxxx.fly.dev

output_schema — JSON object describing the return shape
output_schema (JSON): {"type": "object"}
```

### 产出：`aims.config.json`

```json
{
  "skill_id": "tiktok_competitive_intel",
  "version": "1.0.0",
  "developer_wallet": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
  "price_per_task_usdc": 0.05,
  "monetization": {
    "function_type": "direct_skill",
    "billing_mode": "pay_per_task",
    "rate_limit_per_day": null
  },
  "entry_point": "main.py",
  "output_schema": {"type": "object"},
  "gateway_url": "https://aims-gateway-xxxx.fly.dev",
  "enable_universal_free_trial": true
}
```

> **注意**: 如果你选择 **Subscription** 模式（Q4），`rate_limit_per_day` 必须设置（如 500）。选择 **Buyout** 买断制（Q5），系统会自动设为永久许可证，`rate_limit_per_day` 必须为 null。`worker_collab + buyout` 组合会被**风控熔断电路**拒绝。

---

## Step 2 — `aims-cli login`：Web3 私钥托管

将开发者 ECDSA 私钥加密存储为 **Ethereum Keystore v3 格式**（兼容 MetaMask/Geth 导入）。

```bash
aims-cli login
```

### 交互过程

```
Private key (hex):
Encryption password:
Confirm password:
✔ Private key encrypted and stored at ~/.aims/credentials
```

### 安全架构

```
┌─ 私钥输入 ──────────────────────────────────────┐
│  0xabcd...1234                                   │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌─ eth_account.Account.encrypt() ──────────────────┐
│  AES-128-CTR + scrypt KDF                       │
│  → Keystore v3 JSON                              │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌─ ~/.aims/credentials ────────────────────────────┐
│  chmod 0o600 │ 仅当前用户可读                     │
└───────────────────────────────────────────────────┘
```

验证：
```bash
ls -la ~/.aims/
# -rw-------  1 user  group  687 Jun 12 10:00 credentials
```

> **恢复**: Keystore 文件和密码同时存在才能解密。丢失密码则无可挽回——请离线备份密码。

---

## Step 3 — PyArmor 二进制加壳（首选）

将 `main.py` 编译为 C 扩展，源码变为不可读的二进制 `wrapper.so`。

```bash
pyarmor obfuscate --output dist/wrapper.py main.py
```

### 产出

```
dist/
└── wrapper.py          # PyArmor-obfuscated bytecode
```

PyArmor 的加壳保护：
- **控制流平坦化** — 源码控制流被随机化重排
- **字符串加密** — 所有字符串字面量在运行时解密
- **边界混淆** — 函数调用通过间接跳转表路由
- **反调试检测** — 检测 `ptrace()` / 调试器附加

验证加壳效果：
```bash
cat dist/wrapper.py  # 应输出乱码混淆代码，而非原始源码
```

> **许可证**: PyArmor 需要许可证文件（`pyarmor register`）。首次运行会自动申请 30 天试用。生产环境请购买商业许可证。

---

## Step 4 — Cython 回退编译（可选）

当 PyArmor 不可用时，使用 Cython 将 Python 编译为原生 `.so` 扩展。

```bash
# 生成 C 代码
cythonize -3 -i main.py

# 编译为共享库
gcc -shared -fPIC -O3 \
    -I$(python3 -c "import sysconfig; print(sysconfig.get_config_var('INCLUDEPY'))") \
    -o dist/wrapper.so main.c
```

### 产出

```
dist/
└── wrapper.so          # Cython-compiled native binary
```

验证：
```bash
nm -D dist/wrapper.so | grep PyInit  # 应导出 Python 初始化符号
file dist/wrapper.so                  # 应显示 ELF 64-bit LSB shared object
```

> **限制**: Cython 编译仅隐藏算法逻辑，字符串常量可能仍可通过 `.rodata` 段逆向。搭配 Step 5 的 AES-256-GCM 加密实现纵深防御。

---

## Step 5 — AES-256-GCM 核心加密（publisher 自动执行）

`publish` 命令自动调用 `encrypt_directory()`——将整个技能源码目录打包为 tar 后使用 **AES-256-GCM** 加密输出 `logic.enc`。

```
┌─ 源码目录 ─────────────────────────┐
│  main.py                           │
│  tiktok_competitive_intel.py       │
│  requirements.txt                  │
└───────────┬─── tar ────────────────┘
            ▼
┌─ tar bytes ────────────────────────┐
│  <所有文件 + 目录结构>               │
└───────────┬─── AES-256-GCM ────────┘
            ▼
┌─ logic.enc ────────────────────────┐
│  [12-byte nonce][AES-GCM ciphertext]│
└────────────────────────────────────┘
```

加密参数：
| 参数 | 值 |
|------|-----|
| 算法 | AES-256-GCM (AEAD) |
| 密钥 | `os.urandom(32)` ← 临时生成，仅存在于内存 |
| Nonce | 12 字节随机 |
| 认证标签 | 16 字节 (GCM 内置) |

### 密钥哈希

加密后生成 `key_hash`（SHA-256 摘要的前 16 hex chars），传递给 Step 6 签名：

```
key_hash = sha256(key).hex()[:16]
```

> **安全注意**: AES 密钥在 Step 5 生成后仅存在于内存中。`logic.enc` 一旦写入磁盘，原始密钥**不会**被持久化。网关通过签名中的 `key_hash` 在运行时获取正确密钥。如果密钥丢失，即使拥有 `logic.enc` 也无法解密。

---

## Step 6 — EIP-191 版权签名（publisher 自动执行）

`publish` 命令自动调用 `sign_skill()`——构建签名消息并调用 `Account.sign_message()`。

### 签名消息格式

```
AIMS-SKILL:{skill_id}:{key_hash}:{price_usdc}
```

示例：
```
AIMS-SKILL:tiktok_competitive_intel:a1b2c3d4e5f6g7h8:0.05
```

### 签名流程

```python
from eth_account import Account
from eth_account.messages import encode_defunct

message = f"AIMS-SKILL:{skill_id}:{key_hash}:{price_usdc}"
signable = encode_defunct(primitive=message.encode())
signed = Account.sign_message(signable, private_key)
```

### 产出（签名结果 JSON）

```json
{
  "signature": "0x...130 hex chars...",
  "message": "AIMS-SKILL:tiktok_competitive_intel:a1b2c3d4e5f6g7h8:0.05",
  "signer": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"
}
```

> **EIP-191 优势**: 不需要 Nonce、Deadline、TypedData 等复杂结构。`personal_sign` 格式在所有 EVM 钱包（MetaMask、Rabby、OKX Wallet）中通用。验签时网关通过 `Account.recover_message()` 恢复签名者地址并与 `developer_wallet` 比对。

---

## Step 7 — `aims-cli publish`：一键 3→8 步流水线

`publish` 命令自动聚合 **Step 3→8**（obfuscate → encrypt → sign → package → upload → register）。

```bash
aims-cli publish --gateway-url https://aims-gateway-xxxx.fly.dev
```

### 完整执行日志

```
✦ AIMS Skill Publish Pipeline
──────────────────────────────────────────────────
Step 1/8: Validating config...
✔ Config valid: tiktok_competitive_intel v1.0.0
Step 2/8: Loading developer key...
Keystore password:
✔ Developer key loaded
Step 3/8: Obfuscating entry point...
  → pyarmor obfuscate --output dist/wrapper.py main.py
✔ Obfuscated → wrapper.py
Step 4/8: Encrypting source (AES-256-GCM)...
  → encrypt_directory(./, key) → logic.enc
✔ Encrypted → logic.enc  key_hash=a1b2c3d4e5f6g7h8
Step 5/8: Signing provenance (EIP-191)...
  → AIMS-SKILL:tiktok_competitive_intel:a1b2c3d4e5f6g7h8:0.05
✔ Signed by 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18
Step 6/8: Packaging dist.zip...
✔ dist.zip created (12.3 KB)
Step 7/8: Uploading dist.zip...
  → POST /api/skills/upload (multipart)
✔ Uploaded → https://ipfs.aims.network/skills/tiktok_competitive_intel/logic
Step 8/8: Registering metadata...
  → POST /api/skills/register-metadata (EIP-191 signed)
✔ Publish complete! Your skill is live on the AIMS network.
```

### ASCII 审计表

`publish` 命令完成后打印完整的结算审计表：

```
╔═══════════════════════════════════════════════════════════╗
║              AIMS Settlement Audit Summary               ║
╚═══════════════════════════════════════════════════════════╝

  Skill:            tiktok_competitive_intel v1.0.0
  Quadrant:         Q3  (direct_skill + pay_per_task)
  Developer Wallet:  0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18
  EIP-191 Signer:    0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18
  Signature:         0xabcd...1234

  ┌──────────────────────┬──────────┬────────────┐
  │ Party                │    Share │     Amount  │
  ├──────────────────────┼──────────┼────────────┤
  │ Developer (95%)      │   95.0%  │ $0.0475    │
  │ Worker Node (0%)     │   0.0%   │    —       │
  │ AIMS Platform Treasury │   5.0%  │ $0.0025    │
  └──────────────────────┴──────────┴────────────┘

  Price per task:   $0.0500 USDC
  Total fees (5%):  $0.0025 USDC
  Net to developer: $0.0475 USDC

  ┌─────────────────────────────────────────────────────┐
  │  Delivery Summary                                   │
  ├─────────────────────────────────────────────────────┤
  │  Artifact:     dist.zip                             │
  │  Storage:      https://ipfs.aims.network/skills/... │
  │  Gateway:      https://aims-gateway-xxxx.fly.dev    │
  │  Rate Limit:   1000 tasks/day (trial-exempt)        │
  └─────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────┐
  │  Universal First-Task-Free Routing                  │
  ├─────────────────────────────────────────────────────┤
  │  Every wallet → 1 free call per Skill ID            │
  │  ─────────────────────────────────────────────      │
  │  Mode:         pay_per_task                          │
  │  Routing:                                           │
  │  1st call  → FREE (trial)                           │
  │  2nd+ call → PAY_PER_TASK (balance check enforced)  │
  └─────────────────────────────────────────────────────┘

✔ Publish complete! Your skill is live on the AIMS network.
```

---

## Step 8 — 链上验证（手工确认）

确认上链是否成功。

### 查看网关元数据

```bash
curl -X GET https://aims-gateway-xxxx.fly.dev/api/skills/tiktok_competitive_intel \
  -H "Content-Type: application/json"
```

### 检查注册状态

```bash
curl -X POST https://aims-gateway-xxxx.fly.dev/api/skills/register-metadata \
  -H "Content-Type: application/json" \
  -d '{"skill_id":"tiktok_competitive_intel","contributor_address":"0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"}'
# HTTP 409 → "already registered" → 成功！
```

### Base Sepolia 合约验证（请适配实际合约地址）

```bash
# 确认链上注册（使用 cast 或 ethers-rs）
cast call --rpc-url https://sepolia.base.org \
  0xYourAIMSCoreContract \
  "getSkill(bytes32)(string,address)" \
  $(cast keccak $(echo -n "tiktok_competitive_intel" | xxd -p -c 256))
# → 应返回技能名称 + 开发者地址
```

---

## 全局使用场景

### 场景 A：Metered 按次付费（Q3）

```
定价: $0.05/次  |  开发者抽成 95% ($0.0475)  |  平台 5% ($0.0025)
消费者: 预充值 USDC → 每次调用消耗余额 → 余额不足时 402 回退
推荐: 低频竞品快照、按需分析
```

### 场景 B：Subscription 订阅模式（Q4）

```
定价: $19.99/月  |  限速: 500 次/天  |  无限调用
订阅池按月分账 → 开发者按月获取 $18.99
推荐: 高频监控、连续 7×24 扫描
```

### 场景 C：Buyout 买断制（Q5）

```
定价: $199.00 一次性  |  永久许可证  |  无速率限制
买断池一次性分账 → 开发者净得 $189.05
推荐: 企业白标集成、OEM 嵌入
```

---

## 常见问题

### Q：`publish` 时报 `No credentials found. Run aims-cli login first.`

→ 开发者尚未执行 `aims-cli login`。运行后再试。

### Q：`Wrong password or corrupt keystore`

→ `~/.aims/credentials` 的密码不匹配。Keystore v3 无法暴力破解——请回忆正确密码。如果彻底忘记，删除 `~/.aims/credentials` 重新 `login`。

### Q：`Upload failed` 且提示 `dist.zip preserved`

→ 网络或网关临时故障。`dist.zip` 保留在本地，重新运行 `publish` 会重试上传，已有加密包无需重新构建。

### Q：`HTTP 409 — Already registered`

→ 该 `skill_id` 已经在网关注册。如需更新版本，请修改 `aims.config.json` 中的 `version` 字段（如 `1.0.1`），然后重新 publish。

### Q：`FileNotFoundError: pyarmor not found`

→ PyArmor 未安装。publisher 会自动回退到 Cython 编译。如需 PyArmor 保护：`pip install pyarmor`。

### Q：如何选择计费模式？

| 场景 | 推荐模式 | 理由 |
|------|----------|------|
| 竞品快照（每周 3-5 次） | Metered $0.05 | 按需付费，无月费负担 |
| 连续监控（每天 200+ 次） | Subscription $19.99 | 月费封顶，无限调用 |
| 企业集成（白标嵌入） | Buyout $199.00 | 一次性付费，永久使用 |

---

## 附录 A：`dist.zip` 包内容

```bash
unzip -l dist.zip

Archive:  dist.zip
  Length      Date    Time    Name
---------  ---------- -----   ----
    12345  2026-06-12 10:00   wrapper.so          # 加壳后的二进制入口
    67890  2026-06-12 10:00   logic.enc           # AES-256-GCM 加密的核心逻辑
---------                     -------
    80235                     2 files
```

## 附录 B：迁移到 Base Mainnet

```bash
# 1. 更新 aims.config.json
gateway_url: https://aims-gateway.mainnet.aims.network

# 2. 确保主网钱包有足够的 ETH gas
# 3. 重新 publish
aims-cli publish --gateway-url https://aims-gateway.mainnet.aims.network
```

> **⚠ 重要**: Mainnet 发布不可逆。请在 Base Sepolia 完成全部测试后再迁移。主网上的 `register-metadata` 将产生实际 Gas 费用和永久上链记录。
