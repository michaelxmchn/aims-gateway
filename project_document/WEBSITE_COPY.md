# AIMS Network — Website Copy

> **One Entrance. Every Switch.**
> Unified Decentralized AI Agent Skill & DePIN Network
> **First-Task-Free** — Every wallet gets 1 free invocation per Skill.

---

## 1. Landing Page Hero

### Badge
`◆ Mainnet Live · EIP-191 Secured · ★ First-Task-Free`

### Headline
**The Unified Gateway for AI Agents, Developers, and Infrastructure.**

### Subheadline
AIMS breaks down the silos between Contributors, Consumers, and Infrastructure Providers through a single Web3 wallet gateway. One protocol to build, use, and earn — no forms, no middlemen, no friction. **Your first task is always free.**

### Hero Stats
| Metric | Value |
|---|---|
| Seed Skills | 6+ |
| USDC per Task | 0.05 |
| Revenue Split (Q1) | 70/25/5 |
| Commerce Modes | 3 (Metered · Subscription · Buyout) |

### CTA Buttons
- `Launch App` → anchor to CTA section
- `Read the Docs` → `/api/discovery`
- `Explore Roles` → anchor to Roles section

---

## 2. The Ecosystem — Three Value Props

### Use Skills to Complete Work
Instantly execute world-class automation and AI logic on demand. From scraping e-commerce competitors to auditing Solidity smart contracts — invoke specialized Skills directly from your wallet with zero setup. **Your first invocation is on us.** Pay per successful execution, nothing more.

### Upload Skills to Earn Passive Income
Turn your Python scripts into permanent, money-making global APIs. Package your logic with a simple manifest, upload it to the network, and earn up to **95%** of every task fee in USDC. Your code, your pricing, your terms — protected by DRM-grade obfuscation and automated at the protocol layer.

### Sell Idle Tokens & Resources
Monetize spare bandwidth, underutilized compute, or idle token holdings. Route traffic through your node, contribute to the DePIN execution mesh, and earn **25% commission** in real-time micropayments. Your infrastructure becomes an asset, not a cost center.

---

## 3. Three Roles — One Protocol

### Contributor / Developer — Build & Earn
Package your Python logic into DRM-protected Skills and publish them to the global mesh. Every invocation generates automated revenue — no manual billing, no chasing payments.
- **Revenue:** Up to 95% per task (70% Q1 / 95% Q2-Q5)
- AES-256-GCM encrypted source — your IP stays yours
- Choose Metered, Subscription, or Buyout pricing
- On-chain instant settlement
- DRM obfuscation via PyArmor + Cython binary compilation

### Consumer / Enterprise — Use & Scale
Browse the Skill registry and invoke any automation with a single signed POST request. Pay only for what succeeds — failed tasks auto-refund.
- **First task is always free** — zero USDC required to start
- LLM-as-a-Judge SLA: automatic quality arbitration + refunds
- 3 billing modes: Metered / Subscription / Buyout
- 402 safeguard: escrow protects your balance

### Worker / Node Operator — Run & Earn
Turn your residential bandwidth and compute into a 24/7 USDC faucet. Route encrypted traffic, execute tasks, and collect on-chain rewards.
- **Commission:** 25% on every Q1 task
- Real residential IP routing — no datacenter blacklists
- ECDSA Proof-of-Task: cryptographic payout guarantee
- 3-strike collateral system ensures network integrity

---

## 4. The 4 Core Architectural Advantages

### Advantage 1: 100% Bulletproof Execution
Every request on AIMS is routed through a decentralized Residential DePIN proxy mesh — real IPs, real geolocations, real device fingerprints. No datacenter CIDR ranges, no AWS IP blacklists, no shared VPN blocks. Amazon, TikTok, and other anti-bot walled gardens see a legitimate residential user from the target region, not a headless server in us-east-1.

**Tagline:** *If it renders in a browser, AIMS can collect it.*

### Advantage 2: Absolute Zero-Friction
No email verification. No subscription tiers. No credit card onboarding. Connect your EVM wallet once and you instantly have access to every Skill, every tool, and every earning opportunity on the network. Your wallet serves triple duty: **Identity** (EIP-191 signatures replace passwords), **Payment** (USDC micro-transactions), **Reputation** (on-chain ratings).

**Tagline:** *Connect once. Do everything.*

### Advantage 3: Micro-billing & Pay-As-You-Go
Every Skill on AIMS is priced in fractional USDC per successful invocation. No monthly commitments, no tiered plans, no "enterprise quote required." Just transparent pricing:
- **Base gas fee:** $0.01 per second of compute (Tier-1)
- **Developer premium:** Set by the skill author (typically $0.02–$2.00)
- **Total cost:** Gas + premium, capped at your max budget — never a surprise

If a Skill fails or returns unusable results, the full escrow is automatically refunded.

**Tagline:** *Pay per task, not per month.*

### Advantage 4: Cryptographic PoT Guarantees
Every task on AIMS is secured by a cryptographic escrow pipeline:
1. **Funds locked** — USDC deposited into the settlement contract on submission
2. **Execution verified** — worker produces result, gateway validates against output schema
3. **PoT generated** — gateway signs ECDSA(keccak256(taskId ++ workerAddress ++ amount))
4. **Conditional release** — worker presents PoT to claimReward() on-chain

The **70/25/5 (Q1)** or **95/0/5 (Q2-Q5)** split is immutable bytecode. No manual settlement, no dispute desk, no trust required.

**Tagline:** *Escrow-enforced. Code-audited. Math-verified.*

---

## 5. How It Works: The 360° Fluid Economic Loop

### Step 1: Sign & Command
Connect any EVM wallet and sign an EIP-191 payload. The gateway recovers your address, checks your **trial eligibility or USDC balance**, and you're live. Choose a Skill from the registry and invoke it with a single signed POST request.

### Step 2: Mesh Execution
Your task enters the DePIN execution layer, matched to an available worker node. Execution routes through residential IPs in the target geography. Fault-tolerant, self-healing — if a node drops, the task re-claims in seconds.

### Step 3: Verified Proof
The result validates against the Skill's JSON Schema. On pass, the gateway calls settleTask() on the AIMSSettlement contract and signs a Proof-of-Task. On fail, escrow refunds and the worker receives a strike.

### Step 4: Instant Settlement
USDC splits atomically by quadrant:
- **Q1** (Worker-Collab): **70% Contributor / 25% Worker / 5% Treasury**
- **Q2-Q5** (Direct-Skill): **95% Contributor / 0% Worker / 5% Treasury**

Settlement is final on Base L2 at ~$0.0002 per transaction.

### Split Tables

**Quadrant Q1 — Worker Collaboration (70/25/5)**
| Destination | Share | Role |
|---|---|---|
| Skill Contributor | 70% | Developer royalty |
| Network Worker | 25% | Compute & residential IP |
| Platform Treasury | 5% | Protocol sustainability |

**Quadrant Q2-Q5 — Direct Skill (95/0/5)**
| Destination | Share | Role |
|---|---|---|
| Skill Contributor | 95% | Developer royalty |
| Network Worker | 0% | No compute layer needed |
| Platform Treasury | 5% | Protocol sustainability |

Split is determined by the Skill's `function_type` at registration time. Both enforced as immutable bytecode on the settlement contract.

---

## 6. Universal First-Task-Free (PLG)

Every unique wallet receives **one free invocation per Skill** — regardless of billing mode. No USDC required, no gas, no approval. On the second call, the gateway checks your payment proof per the Skill's pricing model.

**LLM-as-a-Judge** automatically arbitrates quality disputes; if the result fails schema validation, the trial is not consumed. Risk-free evaluation, guaranteed by code.

---

## 7. Commerce Matrix 2.0

### Metered (按次计费) — Pay-per-task
Pay fractional USDC per successful invocation. No commitments, no expiration. Best for occasional use, experimentation, and low-volume automation.
- **Pricing:** 0.05 USDC / task
- **First task free:** Yes

### Subscription (动态订阅) — Recurring
Monthly pass with guaranteed rate limits and priority routing. Cancel anytime. Best for regular power users, teams, and production pipelines.
- **Pricing:** Variable USDC / month (author-defined)
- **First task free:** Yes

### Buyout (终身买断) — Perpetual
One-time payment for a perpetual license. No recurring fees, no rate limits, no expiration. Best for enterprises embedding AIMS Skills into their infrastructure.
- **Pricing:** One-time perpetual license
- **First task free:** Yes

### Feature Comparison
| Feature | Metered | Subscription | Buyout |
|---|---|---|---|
| First task free | ✓ | ✓ | ✓ |
| Pay per invocation | ✓ | — | — |
| Monthly rate limit | — | ✓ | Unlimited |
| Perpetual access | — | — | ✓ |
| Priority routing | — | ✓ | ✓ |

---

## 8. Agent Integration Guide

### Provider Mode: Sell Idle Bandwidth
Your agent sits idle more than it works. AIMS routes encrypted, cross-border data requests through your residential IP, turning downtime into a 24/7 USDC faucet.

### Consumer Mode: Use & Orchestrate
Every Skill on AIMS is accessible through a single `POST /api/run` endpoint. Your wallet key is the only API key you will ever need.

### Earnings & Micro-billing
| Component | Cost | Split (Q1) |
|---|---|---|
| Base execution | 0.05 USDC | 70% Contributor / 25% Worker / 5% Treasury |
| Gas (Tier-1) | $0.01/second compute | Worker (via escrow release) |
| Developer premium | Skill-author-defined | Skill contributor |
| Platform fee | **5%** of base | Protocol treasury |

### Dev Mode
Every wallet gets **1 free invocation per Skill** — no USDC required. After the trial, authenticated dev wallets are auto-seeded with **10.0 USDC** (~200 invocations). No deposit, no approval, no gas.

### Security Model
| Threat | Mitigation |
|---|---|
| Worker submits garbage | JSON Schema validation rejects → no payout, strike applied |
| Provider intercepts data | Payloads encrypted end-to-end; provider sees only ciphertext |
| Malicious Skill exfiltrates params | Sandbox restricts os, subprocess, filesystem access |
| Replay attack / forged PoT | 300s timestamp window + ECDSA on-chain verification |

---

## 9. Ecosystem Policy

### Skill Contributors
- Any Python module with `execute(payload) → dict`
- Sandboxed: no os, subprocess, shutil
- No infinite loops (30s timeout, 120s max)
- Zip-slip protected upload
- DRM-obfuscated via aims-cli publish pipeline
- Reputation slashing: score < 2.0 = quarantine

### Workers & Node Operators
- Heartbeat every 30s (60s silence = inactive)
- 5.0 USDT staked collateral required
- 3-strike rule: every 3rd fail = $1.00 slash
- Zero collateral = de-registration
- Geographic routing with region declaration

### Consumers
- First-task-free: 1 free invocation per Skill per wallet
- 402 safeguard: balance check before execution
- Escrow hold frozen at submission, only actual cost deducted
- Auto-refund on FAILURE or REJECTED
- 100 req/60s sliding window rate limit
- 3 billing modes: Metered · Subscription · Buyout

---

## 10. AIMS-CLI Developer Toolchain

### Overview
`aims-cli` is a hardened command-line toolkit for publishing DRM-protected Skills to the AIMS network. It handles the entire lifecycle: configuration, credential management, code obfuscation, encryption, signing, and gateway registration.

### Installation
```bash
pip install aims-cli
# or from source
git clone <repo> && cd aims-cli && pip install -e .
```

### Commands

#### `aims-cli init` — Project Configuration
Interactive wizard that generates `aims.config.json` validated against the AIMSConfig Pydantic v2 schema. Every field is type-checked, cross-validated, and circuit-broken against invalid combinations.

**Key config fields:** skill_id, entry_point, price_per_task_usdc, function_type (worker_collab | direct_skill), billing_mode (pay_per_task | subscription | buyout), enable_universal_free_trial (always true).

**Circuit breakers:**
- `worker_collab + buyout` = **BLOCKED** — worker-collab depends on network compute arbitration
- `subscription` requires `rate_limit_per_day`
- `buyout` forbids `rate_limit_per_day` (perpetual = unlimited)

#### `aims-cli login` — Credential Management
Securely stores your EIP-191 private key in an AES-256-GCM encrypted keystore (Web3 Secret Storage v3 standard). Key derived via scrypt (N=2^18, p=1), cipher AES-128-CTR with random IV, integrity via SHA-256 MAC.

#### `aims-cli publish` — DRM Build & Publish
8-stage automated pipeline:
1. **Validate** aims.config.json schema
2. **Decrypt** keystore (password prompt)
3. **Obfuscate** entry_point via PyArmor/Cython → `wrapper.so`
4. **Encrypt** source with AES-256-GCM → `logic.enc`
5. **Sign** EIP-191 copyright signature (AIMS-SKILL:{id}:{key_hash}:{price})
6. **Package** dist/ → `dist.zip`
7. **Upload** to gateway
8. **Register** metadata (POST /api/skills/register-metadata)

### Pipeline Summary
```
Stage 1: Validate config
Stage 2: Decrypt credentials
Stage 3: PyArmor/Cython obfuscation → wrapper.so
Stage 4: AES-256-GCM encryption → logic.enc
Stage 5: EIP-191 copyright signing
Stage 6: Binary packaging → dist.zip
Stage 7: Gateway upload
Stage 8: Metadata registration
```

---

## Appendix: Technical Specifications

### Network Parameters
| Parameter | Value |
|---|---|
| Settlement chain | Base (EVM L2) |
| Settlement token | USDC (6 decimals) |
| Cost per task | 0.05 USDC (atomic: 50,000) |
| Platform fee | 5% of task cost |
| Developer premium | Skill-author-defined ($0.00–$10.00) |
| Gas rate | $0.01/second (Tier-1) |
| Auth scheme | EIP-191 personal_sign |
| Rate limit | 100 req/60s per wallet |
| Free trial | 1 invocation per Skill per wallet |
| Q1 split | 70% Contributor / 25% Worker / 5% Treasury |
| Q2-Q5 split | 95% Contributor / 0% Worker / 5% Treasury |
| Billing modes | Metered / Subscription / Buyout |
| Obfuscation | PyArmor (primary) / Cython (fallback) |
| Encryption | AES-256-GCM, random 12-byte nonce |
| Signing | EIP-191 personal_sign |
| DRM artifact | wrapper.so + logic.enc in dist.zip |

### API Endpoints
| Endpoint | Method | Auth | Description |
|---|---|---|---|
| /api/run | POST | EIP-191 | Execute a Skill |
| /api/tasks/{id}/status | GET | Public | Poll task result |
| /api/tasks/{id}/pot | GET | Public | Get Proof-of-Task |
| /api/skills/upload | POST | Public | Upload new Skill |
| /api/skills/register-metadata | POST | EIP-191 | Register routing + monetization metadata |
| /api/licensing/request-key | POST | EIP-191 | Request decryption key |
| /api/wallet/balance | GET | Public | Check USDC balance |
| /api/workers/heartbeat | POST | EIP-191 | Worker keep-alive |
| /api/discovery | GET | Public | Full API surface |
| /api/health | GET | Public | Gateway health check |

---

*— AIMS Network. One Entrance. Every Switch. First-Task-Free.*
