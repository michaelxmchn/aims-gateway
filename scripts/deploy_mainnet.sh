#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# AIMS 2.0  —  Base Mainnet Production Deployment
# ═══════════════════════════════════════════════════════════════════════════════
#
# Interactive点火脚本，具备：
#   1. 基础镜像离线导入阻断检查
#   2. 交互式主网参数采集（RPC / 网关密钥 / DeepSeek API Key）
#   3. 自动 docker-compose 点火 + 5 次 ChainListener 健康轮询
#
# 使用方法:
#   chmod +x scripts/deploy_mainnet.sh
#   bash scripts/deploy_mainnet.sh
#
# 前置条件:
#   - docker 已安装且守护进程运行中
#   - redis:7-alpine 与 python:3.11-slim 已通过 docker load 离线导入
#   - docker-compose 插件可用（或 docker-compose 独立命令）
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Color constants ───────────────────────────────────────────────────────────
C_RED='\033[91m'
C_GREEN='\033[92m'
C_YELLOW='\033[93m'
C_CYAN='\033[96m'
C_BOLD='\033[1m'
C_RESET='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────

info()  { echo -e "  ${C_CYAN}INFO ${C_RESET} $1"; }
ok()    { echo -e "  ${C_GREEN}OK   ${C_RESET} $1"; }
warn()  { echo -e "  ${C_YELLOW}WARN ${C_RESET} $1"; }
fail()  { echo -e "  ${C_RED}FAIL ${C_RESET} $1"; }
banner(){
  echo
  echo -e "${C_BOLD}${C_CYAN}══════════════════════════════════════════════════════════════════${C_RESET}"
  echo -e "${C_BOLD}${C_CYAN}  $1${C_RESET}"
  echo -e "${C_BOLD}${C_CYAN}══════════════════════════════════════════════════════════════════${C_RESET}"
}

die() {
  echo -e "\n  ${C_RED}${C_BOLD}✖ FATAL:${C_RESET} $1" >&2
  exit 1
}

# ── Step 1: 基础镜像阻断检查 ─────────────────────────────────────────────────
banner "STEP 1/4  —  Offline Image Check"

REQUIRED_IMAGES=("redis:7-alpine" "python:3.11-slim")
MISSING=()

for img in "${REQUIRED_IMAGES[@]}"; do
  if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${img}$"; then
    ok "Found ${img}"
  else
    fail "MISSING  ${img}"
    MISSING+=("${img}")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo
  die "基础镜像缺失 — 请先离线导入:\n$(printf "  docker load -i %s.tar\n" "${MISSING[@]}")"
fi

echo
ok "All base images present — proceeding to configuration"
echo

# ── Step 2: 交互式环境变量采集 ─────────────────────────────────────────────
banner "STEP 2/4  —  Mainnet Configuration (interactive)"

echo "  ${C_YELLOW}Please enter the following parameters one by one.${C_RESET}"
echo "  ${C_YELLOW}Input is exported to your shell environment — nothing is written to disk.${C_RESET}"
echo

# ── 2a. Base Mainnet RPC URL ─────────────────────────────────────────────
while true; do
  read -r -p "  $(echo -e ${C_BOLD})▶$(echo -e ${C_RESET}) 请输入您的 Base 主网独享 RPC 链接 (BASE_MAINNET_RPC_URL): " BASE_MAINNET_RPC_URL
  BASE_MAINNET_RPC_URL="${BASE_MAINNET_RPC_URL%% }"  # trim trailing space
  if [[ -z "${BASE_MAINNET_RPC_URL}" ]]; then
    warn "RPC URL cannot be empty — try again"
    continue
  fi
  if [[ "${BASE_MAINNET_RPC_URL}" != https://* ]] && [[ "${BASE_MAINNET_RPC_URL}" != http://* ]]; then
    warn "Must start with https:// or http:// — try again"
    continue
  fi
  break
done
export BASE_MAINNET_RPC_URL
ok "BASE_MAINNET_RPC_URL set"
echo

# ── 2b. Gateway Hot Wallet Private Key ─────────────────────────────────────
while true; do
  read -r -s -p "  $(echo -e ${C_BOLD})▶$(echo -e ${C_RESET}) 请输入您的主网网关热钱包私钥 (GATEWAY_PRIVATE_KEY, 64 hex chars): " GATEWAY_PRIVATE_KEY
  echo  # newline after silent input
  GATEWAY_PRIVATE_KEY="${GATEWAY_PRIVATE_KEY##0x}"  # strip 0x prefix
  if [[ ${#GATEWAY_PRIVATE_KEY} -ne 64 ]]; then
    warn "Private key must be exactly 64 hex characters (got ${#GATEWAY_PRIVATE_KEY}) — try again"
    continue
  fi
  if ! [[ "${GATEWAY_PRIVATE_KEY}" =~ ^[0-9a-fA-F]{64}$ ]]; then
    warn "Private key contains invalid hex characters — try again"
    continue
  fi
  break
done
export GATEWAY_PRIVATE_KEY
ok "GATEWAY_PRIVATE_KEY set (${GATEWAY_PRIVATE_KEY:0:8}…${GATEWAY_PRIVATE_KEY: -6})"
echo

# ── 2c. DeepSeek API Key ───────────────────────────────────────────────────
while true; do
  read -r -p "  $(echo -e ${C_BOLD})▶$(echo -e ${C_RESET}) 请输入您的 DeepSeek 官方生产 API Key (OPENAI_API_KEY, sk-...): " OPENAI_API_KEY
  OPENAI_API_KEY="${OPENAI_API_KEY%% }"
  if [[ -z "${OPENAI_API_KEY}" ]]; then
    warn "API Key cannot be empty — try again"
    continue
  fi
  break
done
export OPENAI_API_KEY
ok "OPENAI_API_KEY set (${OPENAI_API_KEY:0:12}…)"
echo

# ── 2d. Redis Password ─────────────────────────────────────────────────────
while true; do
  read -r -s -p "  $(echo -e ${C_BOLD})▶$(echo -e ${C_RESET}) 请输入 Redis 高强度密码 (至少 32 字符, 建议 openssl rand -hex 32): " REDIS_PASSWORD
  echo
  if [[ ${#REDIS_PASSWORD} -lt 32 ]]; then
    warn "Redis password must be at least 32 characters (got ${#REDIS_PASSWORD}) — try again"
    continue
  fi
  break
done
export REDIS_PASSWORD
ok "REDIS_PASSWORD set (${REDIS_PASSWORD:0:8}…)"
echo

# ── 2e. Contract Address ──────────────────────────────────────────────────
while true; do
  read -r -p "  $(echo -e ${C_BOLD})▶$(echo -e ${C_RESET}) 请输入已部署的 AIMSAgentGateway 合约地址 (0x + 40 hex): " AIMS_CONTRACT_ADDRESS
  AIMS_CONTRACT_ADDRESS="${AIMS_CONTRACT_ADDRESS%% }"
  if ! [[ "${AIMS_CONTRACT_ADDRESS}" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
    warn "Must be 0x + 40 hex characters — try again"
    continue
  fi
  break
done
export AIMS_CONTRACT_ADDRESS
ok "AIMS_CONTRACT_ADDRESS set"
echo

# ── 2f. Signing Secret ────────────────────────────────────────────────────
while true; do
  read -r -s -p "  $(echo -e ${C_BOLD})▶$(echo -e ${C_RESET}) 请输入网关签名密钥 (AIMS_SIGNING_SECRET, openssl rand -hex 32 = 64 hex chars): " AIMS_SIGNING_SECRET
  echo
  AIMS_SIGNING_SECRET="${AIMS_SIGNING_SECRET##0x}"
  if [[ ${#AIMS_SIGNING_SECRET} -ne 64 ]]; then
    warn "Signing secret must be exactly 64 hex characters (got ${#AIMS_SIGNING_SECRET}) — try again"
    continue
  fi
  if ! [[ "${AIMS_SIGNING_SECRET}" =~ ^[0-9a-fA-F]{64}$ ]]; then
    warn "Contains invalid hex characters — try again"
    continue
  fi
  break
done
export AIMS_SIGNING_SECRET
ok "AIMS_SIGNING_SECRET set (${AIMS_SIGNING_SECRET:0:8}…${AIMS_SIGNING_SECRET: -6})"
echo

# ── Hardcoded DeepSeek endpoint (OpenAI-compatible) ──────────────────────
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL_NAME="deepseek-chat"
ok "OPENAI_BASE_URL= https://api.deepseek.com/v1 (hardcoded)"
ok "LLM_MODEL_NAME= deepseek-chat (hardcoded)"
echo

# ── Step 3: Summary & Confirmation ─────────────────────────────────────────
banner "STEP 3/4  —  Configuration Summary"

echo "  ${C_BOLD}Parameter                Value${C_RESET}"
echo "  ────────────────────────────────────────────────────────"
echo "  BASE_MAINNET_RPC_URL     ${BASE_MAINNET_RPC_URL}"
echo "  GATEWAY_PRIVATE_KEY      ${GATEWAY_PRIVATE_KEY:0:8}…${GATEWAY_PRIVATE_KEY: -6}"
echo "  OPENAI_API_KEY           ${OPENAI_API_KEY:0:12}…"
echo "  OPENAI_BASE_URL          https://api.deepseek.com/v1"
echo "  LLM_MODEL_NAME           deepseek-chat"
echo "  AIMS_CONTRACT_ADDRESS    ${AIMS_CONTRACT_ADDRESS}"
echo "  REDIS_PASSWORD           ${REDIS_PASSWORD:0:8}…"
echo "  AIMS_SIGNING_SECRET      ${AIMS_SIGNING_SECRET:0:8}…${AIMS_SIGNING_SECRET: -6}"
echo

read -r -p "  $(echo -e ${C_YELLOW})Proceed with deployment? [Y/n]$(echo -e ${C_RESET}) " confirm
confirm="${confirm:-Y}"
if [[ "${confirm}" != "Y" && "${confirm}" != "y" ]]; then
  die "Deployment aborted by user."
fi

# ── Step 4: Ignition & Health Check ───────────────────────────────────────
banner "STEP 4/4  —  Cluster Ignition"

# Detect docker compose command
COMPOSE_CMD=""
if command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
elif docker compose version &>/dev/null; then
  COMPOSE_CMD="docker compose"
else
  die "No docker-compose or docker compose found — install Docker Compose plugin."
fi

info "Using: ${COMPOSE_CMD}"
info "Starting production cluster..."

${COMPOSE_CMD} -f docker-compose.prod.yml up -d --build

echo
info "Waiting for gateway to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/health &>/dev/null; then
    ok "Gateway health check PASSED (attempt ${i})"
    break
  fi
  if [[ "${i}" -eq 30 ]]; then
    die "Gateway failed to start within 30 attempts — check logs: ${COMPOSE_CMD} -f docker-compose.prod.yml logs gateway-server"
  fi
  sleep 2
done

echo
banner "ChainListener Health Poll (5 rounds)"

LISTENER_OK=0
for round in $(seq 1 5); do
  sleep 3
  resp=$(curl -sf http://localhost:8000/api/admin/listener 2>/dev/null || true)
  if [[ -z "${resp}" ]]; then
    warn "[${round}/5]  /api/admin/listener not reachable yet"
    continue
  fi

  # Extract fields from JSON response
  listener_status=$(echo "${resp}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "parse-error")
  breaker_state=$(echo "${resp}" | python3 -c "import sys,json; d=json.load(sys.stdin); cb=d.get('circuit_breaker',{}); print(cb.get('state','unknown'))" 2>/dev/null || echo "parse-error")

  if [[ "${listener_status}" == "running" ]] && [[ "${breaker_state}" == "CLOSED" ]]; then
    ok "[${round}/5]  ChainListener=running  CircuitBreaker=CLOSED  ✓"
    LISTENER_OK=$((LISTENER_OK + 1))
  elif [[ "${listener_status}" == "running" ]]; then
    warn "[${round}/5]  ChainListener=running  CircuitBreaker=${breaker_state} (not yet CLOSED)"
  else
    warn "[${round}/5]  ChainListener=${listener_status}"
  fi
done

echo
if [[ "${LISTENER_OK}" -ge 3 ]]; then
  ok "Health: ${LISTENER_OK}/5 polls healthy — cluster is operational"
else
  warn "Health: only ${LISTENER_OK}/5 polls passed — check logs for details"
  warn "Logs: ${COMPOSE_CMD} -f docker-compose.prod.yml logs --tail=50 gateway-server"
fi

# ── Final Summary ──────────────────────────────────────────────────────────
banner "DEPLOYMENT COMPLETE"

echo "  ${C_BOLD}Service       Status${C_RESET}"
echo "  ──────────────────────────────────"
echo -e "  Gateway       ${C_GREEN}http://localhost:8000${C_RESET}"
echo -e "  Redis         ${C_GREEN}AOF persistence active${C_RESET}"
echo -e "  Workers       ${C_GREEN}3 × DePIN nodes (isolated)${C_RESET}"
echo -e "  AI Judge      ${C_GREEN}DeepSeek via OpenAI SDK${C_RESET}"
echo -e "  Chain mode    ${C_GREEN}Base Mainnet (chain 8453)${C_RESET}"
echo
echo "  Useful commands:"
echo "    Logs:       ${COMPOSE_CMD} -f docker-compose.prod.yml logs -f"
echo "    Gateway:    ${COMPOSE_CMD} -f docker-compose.prod.yml logs -f gateway-server"
echo "    Worker 1:   ${COMPOSE_CMD} -f docker-compose.prod.yml logs -f worker-node-1"
echo "    CB status:  curl -s http://localhost:8000/api/admin/circuit-breaker | jq ."
echo "    Stop:       ${COMPOSE_CMD} -f docker-compose.prod.yml down"
echo "    Wipe:       ${COMPOSE_CMD} -f docker-compose.prod.yml down -v"
echo
