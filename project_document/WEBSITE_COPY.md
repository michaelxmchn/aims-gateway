# AIMS Network — Website Copy

> **One Entrance. Every Switch.**
> Unified Decentralized AI Agent Skill & DePIN Network

---

## 1. Landing Page Hero

### Headline
**The Unified Gateway for AI Agents, Developers, and Infrastructure.**

### Subheadline
AIMS breaks down the silos between Users, Developers, and Hardware Providers through a single Web3 wallet gateway. One protocol to consume, create, and earn — no forms, no middlemen, no friction.

### Value Propositions (3-column)

#### Use Skills to Complete Work
Instantly execute world-class automation and AI logic on demand. From scraping e-commerce competitors to auditing Solidity smart contracts — invoke specialized Skills directly from your wallet with zero setup. Pay per successful execution, nothing more.

#### Upload Skills to Earn Passive Income
Turn your Python scripts into permanent, money-making global APIs. Package your logic with a simple manifest, upload it to the network, and earn USDC every time a user invokes it. Your code, your pricing, your terms — automated at the protocol layer.

#### Sell Idle Tokens & Resources
Monetize spare bandwidth, underutilized compute, or idle token holdings. Route traffic through your node, contribute to the DePIN execution mesh, and get paid in real-time micropayments. Your infrastructure becomes an asset, not a cost center.

### CTA Buttons
- `Launch App` → (links to api.aimsgateway.com)
- `Read the Docs` → (links to docs)
- `Become a Developer` → (links to developer onboarding)

---

## 2. The 4 Core User-Centric Advantages

### Advantage 1: 100% Bulletproof Execution

**Headline:** Anti-Ban by Architecture.

**Body:** 
Every request on AIMS is routed through a decentralized Residential DePIN proxy mesh — real IPs, real geolocations, real device fingerprints. No datacenter CIDR ranges, no AWS IP blacklists, no shared VPN blocks. Amazon, TikTok, and other anti-bot walled gardens see a legitimate residential user from the target region, not a headless server in us-east-1.

The result: enterprise-grade scraping and data extraction with near-zero 403 rates. When you need accurate, unblockable data at scale — AIMS delivers what centralized proxies cannot.

**Tagline:** *If it renders in a browser, AIMS can collect it.*

---

### Advantage 2: Absolute Zero-Friction

**Headline:** Your Wallet is Your Account.

**Body:**
No email verification. No subscription tiers. No credit card onboarding. Connect your EVM wallet once and you instantly have access to every Skill, every tool, and every earning opportunity on the network.

Your wallet serves triple duty:
- **Identity** — EIP-191 personal_sign replaces passwords and API keys
- **Payment** — USDC micro-transactions replace subscription billing
- **Reputation** — on-chain ratings and stake-weighted scoring replace KYC

One connection unlocks consumption, hosting, and development simultaneously. The account model of Web3, not the labyrinth of Web2.

**Tagline:** *Connect once. Do everything.*

---

### Advantage 3: Micro-billing & Pure Pay-As-You-Go

**Headline:** You Consume, You Pay. Nothing More.

**Body:**
Every Skill on AIMS is priced in fractional USDC per successful invocation. No monthly commitments, no tiered plans, no "enterprise quote required." Just transparent, flat-rate pricing:

- **Base gas fee:** $0.01 per second of compute (Tier-1)
- **Developer premium:** Set by the skill author (typically $0.02–$2.00)
- **Total cost:** Gas + premium, capped at your max budget — never a surprise

If a Skill fails or returns unusable results, the full escrow is automatically refunded. You only pay for what works.

**Tagline:** *Pay per task, not per month.*

---

### Advantage 4: Cryptographic Proof-of-Task (PoT) Guarantees

**Headline:** Trust the Math, Not the Counterparty.

**Body:**
Every task on AIMS is secured by a cryptographic escrow pipeline:

1. **Funds locked** — USDC deposited into the settlement contract when the task is submitted
2. **Execution verified** — the worker produces a result and the gateway validates it against the Skill's output schema
3. **PoT generated** — upon validation, the gateway signs a Proof-of-Task: `ECDSA(keccak256(taskId ++ workerAddress ++ amount))`
4. **Conditional release** — the worker presents the PoT to `claimReward()` on-chain; funds only move when execution integrity is cryptographically proven

The 80/20 split is immutable bytecode: 80% to the worker, 20% to the protocol owner. No manual settlement, no dispute desk, no trust required.

**Tagline:** *Escrow-enforced. Code-audited. Math-verified.*

---

## 3. How It Works: The 360° Fluid Economic Loop

### Section Headline
**From Consumer to Creator in a Single Transaction.**

### Step 1: Sign & Command
You don't register — you authenticate. Connect any EVM wallet and sign an EIP-191 payload with your private key. The gateway recovers your address, checks your USDC balance, and you're live. Choose a Skill from the registry — `amazon_scraper`, `code_security_audit`, `data_analyzer`, or any community-uploaded Skill — and invoke it with a single signed POST request.

**The magic:** Your wallet simultaneously identifies you, authorizes the payment, and proves intent — all in one cryptographic operation that takes less than a second.

### Step 2: Mesh Execution
The request enters the DePIN execution layer. Your task is matched to an available worker node — which could be a dedicated server, a developer's laptop, or a community member contributing idle compute. The worker fetches the Skill's `logic.py` from the gateway, loads it into a sandboxed runtime, and executes your payload.

Behind the scenes, the DePIN mesh routes execution through residential IPs in the target geography, ensuring your request appears indistinguishable from organic user traffic. The mesh is redundant, fault-tolerant, and self-healing — if a node drops, the task is re-claimed within seconds.

**The magic:** The same network that executes your task may be powered by another user's spare bandwidth, and that user may be running a Skill you uploaded last week. Roles flow, they don't lock.

### Step 3: Verified Proof
Once execution completes, the result is validated against the Skill's `output_schema` (JSON Schema, strict mode). If validation passes, the gateway triggers the on-chain settlement flow:

1. `settleTask()` is called on the `AIMSSettlement` contract
2. The user's deposited USDC is debited by `COST_PER_TASK` (0.05 USDC)
3. A Proof-of-Task (PoT) is signed by the gateway's ECDSA key

If validation fails — missing fields, type mismatch, schema violation — the task is marked `REJECTED`, the escrow is refunded in full, and the worker receives a strike. The strike tracker implements a 3-strike slashing mechanism: three failed submissions within the active window deducts $1.00 from the worker's staked collateral.

**The magic:** You don't need to trust the worker, and the worker doesn't need to trust you. The code enforces the deal — automatically, instantly, provably.

### Step 4: Instant Cross-Flow Settlement
The final step is invisible to both parties but mathematically elegant. The 0.05 USDC fee flows through three channels automatically:

| Destination | Share | Purpose |
|---|---|---|
| **Worker (executor)** | 80% (0.04 USDC) | Reward for providing compute and IP resources |
| **Platform Owner** | 20% (0.01 USDC) | Protocol sustainability, development, and governance |
| **Skill Developer** | Variable (premium) | Per-invocation royalty set by the Skill author |

Settlement is instant and final. No waiting periods, no "pending" status that lasts 3-5 business days. The worker can immediately present their PoT to `claimReward()` on the Base chain and receive USDC in their wallet.

**The closing loop:** The user who was just a consumer can, in their next session, upload a Skill and become a developer. The worker who just executed a task can, when they submit a task, become a consumer. There are no separate "sides" of the marketplace — there is a single fluid economic loop where every participant can occupy every role.

---

## 4. Ecosystem Policy & Terms of Engagement

### Section Headline
**Protocol Integrity: The Rules of the Mesh.**

AIMS is a permissionless network, but permissionless does not mean lawless. The protocol enforces a set of automated, code-level policies that protect all participants. No lawyers, no moderators — just deterministic smart contract logic.

---

### Skill Developer Policy

#### What You Can Upload
Any Python module that exposes a single `execute(payload: dict) -> dict` function and is accompanied by a valid `manifest.json` (name, description, input_schema, output_schema, pricing). Skills are versioned — updates are additive only; removing parameters or changing output schemas requires a new version.

#### Safety Requirements
- **No filesystem access** — the sandbox restricts `os`, `subprocess`, and `shutil`
- **No raw network I/O** — use the provided `requests` wrapper with automatic proxy routing
- **No infinite loops** — execution is bounded by a configurable timeout (default 30s, max 120s)
- **Zip-slip protection** — upload extraction is hardened against path traversal attacks (CVE-2023-22809 style)

#### Pricing Guidelines
- Set your `developer_premium` in USDC (floating point, $0.00–$10.00 range)
- Premium is added to the base gas cost and capped by the user's `max_budget`
- You earn on every successful invocation, minus the 1% platform tax

#### Prohibited Behaviors
- **Exfiltrating user data** from the `params` payload to external endpoints
- **Mining cryptocurrency** or engaging in compute theft
- **Distributing malware** or phishing payloads
- **Price gouging** with unreasonable `developer_premium` values (the community can flag via reputation scoring)

Violations result in the Skill being removed from the registry and the developer's wallet being blacklisted. Reputation slashing is automated — a skill with a weighted score below 2.0 after 10+ ratings is quarantined.

---

### Worker / Node Operator Policy

#### Uptime & Reliability
- Heartbeat every 30 seconds — if silence exceeds 60 seconds, the node is marked inactive
- Claimed tasks must be submitted within the `CLAIM_TIMEOUT` window (default 30s)
- Target 99%+ uptime for consistent rewards; nodes below 90% receive fewer task assignments via reputation de-prioritization

#### Collateral & Slashing
- Registration requires a stake of 5.0 USDT as collateral (locked in the MockLedger escrow vault)
- **Strike accumulation:** each failed/substandard submission = 1 strike
- **3-strike rule:** every third strike triggers a $1.00 slashing event from collateral → founder treasury
- After slashing, the strike counter resets, allowing the worker to rebuild
- A worker with 0 collateral remaining is de-registered until they re-stake

#### Geographic Routing
- Workers can declare their residential region (e.g., `us-west`, `eu-central`, `ap-southeast`)
- Tasks are preferentially routed to workers in the target region for anti-bot residential IP benefits
- Misrepresenting region is a slashing offense (strikes accumulate per offense)

---

### Consumer (User) Policy

#### Billing & Refunds
- **402 safeguard:** the gateway checks your USDC balance before task submission; if insufficient, the request is rejected with HTTP 402 — no funds are ever at risk
- **Escrow holds:** the full `max_budget` is frozen at submission; only the actual cost consumed on SUCCESS is deducted
- **Auto-refund:** on FAILURE or REJECTED outcome, the entire escrow hold is instantly released — no claim needed
- **No-subscription model:** you cannot be billed for a period you didn't use; every charge is per-task

#### Rate Limiting
- 100 requests per 60-second sliding window per wallet address
- Burst tolerance of 5 additional requests within the window
- Rate limit resets after 60 seconds of inactivity

#### Dispute Resolution
AIMS does not have a customer support team. It has a cryptographic dispute framework:
- **Output schema mismatch:** detected automatically at submission time; refund is automatic
- **Worker timeout:** if a claimed task exceeds 30s without submission, the broker auto-releases and refunds
- **Invalid PoT:** the on-chain `claimReward()` function verifies the gateway ECDSA signature; a forged PoT is mathematically impossible within the EVM

---

## Appendix: Technical Specifications Reference

### Network Parameters
| Parameter | Value |
|---|---|
| Settlement chain | Base (EVM L2) |
| Settlement token | USDC (6 decimals) |
| Contract | `AIMSSettlement` |
| Cost per task | 0.05 USDC (atomic: 50,000) |
| Platform fee | 20% of task cost |
| Developer premium | Skill-author-defined ($0.00–$10.00) |
| Gas rate | $0.01/second (Tier-1) |
| Auth scheme | EIP-191 personal_sign |
| Rate limit | 100 req/60s per wallet |

### Contract Addresses *(mainnet)*
| Component | Address |
|---|---|
| AIMSSettlement | `0x0000000000000000000000000000000000000001` (dev/test) |
| USDC (Base) | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| Platform Owner | `0x08c9fd0a915f2b0856353850b8adea943f226bcf` |

---

*— AIMS Network. One Entrance. Every Switch.*
