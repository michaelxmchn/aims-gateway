#!/usr/bin/env node
/* Deployment script for AIMSSettlement on Base.
 *
 * Usage:
 *   DEPLOYER_PRIVATE_KEY=0x... npx hardhat run scripts/deploy_settlement.cjs --network base
 *   DEPLOYER_PRIVATE_KEY=0x... npx hardhat run scripts/deploy_settlement.cjs --network baseSepolia
 *
 * The PLATFORM_OWNER address is hard-coded below — it receives 20 %
 * of every settlement.  Because Solidity's `immutable` keyword embeds
 * the value in the deployed bytecode, NOTHING can change it after
 * deployment.  Not the deployer.  Not the gateway.  Not an upgrade.
 *
 * On mainnet, the canonical USDC address on Base is used as the
 * settlement token.  On testnets/sepolia a MockERC20 is deployed.
 */

import { ethers } from "hardhat";

// ── Immutable platform owner ──────────────────────────────────────────────
// This address receives the 20 % platform fee on EVERY settlement.
// Burned into the contract bytecode — cannot be changed after deploy.
const PLATFORM_OWNER = "0x08c9fd0a915f2b0856353850b8adea943f226bcf";

// ── Canonical USDC on Base mainnet ────────────────────────────────────────
const BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deployer:", deployer.address);
  console.log("Platform owner (immutable):", PLATFORM_OWNER);

  const network = await ethers.provider.getNetwork();
  const chainId = Number(network.chainId);
  const isMainnet = chainId === 8453;

  // ── 1. Determine USDC token address ─────────────────────────────────
  let usdcAddress;
  if (isMainnet) {
    usdcAddress = BASE_USDC;
    console.log("USDC (canonical Base):", usdcAddress);
  } else {
    // Deploy a mock ERC20 for testnet / local hardhat
    const MockERC20 = await ethers.getContractFactory(
      "contracts/test/MockERC20.sol:MockERC20"
    );
    const mock = await MockERC20.deploy("USD Coin", "USDC", 6);
    await mock.waitForDeployment();
    usdcAddress = await mock.getAddress();
    console.log("MockUSDC deployed at:", usdcAddress);
  }

  // ── 2. Deploy AIMSSettlement ────────────────────────────────────────
  const AIMSSettlement = await ethers.getContractFactory("AIMSSettlement");
  const settlement = await AIMSSettlement.deploy(
    usdcAddress,
    deployer.address,     // initial gateway oracle
    PLATFORM_OWNER,       // immutable platform owner
  );
  await settlement.waitForDeployment();
  const settlementAddress = await settlement.getAddress();

  console.log("\n=== Deployment Summary ===");
  console.log("AIMSSettlement:", settlementAddress);
  console.log("USDC token:    ", usdcAddress);
  console.log("Gateway:       ", deployer.address);
  console.log("Platform owner:", PLATFORM_OWNER);
  console.log("Chain ID:      ", chainId);
  console.log("==========================\n");

  // ── 3. Verify the immutable owner is correct ────────────────────────
  const onChainOwner = await settlement.platformOwner();
  if (onChainOwner.toLowerCase() !== PLATFORM_OWNER.toLowerCase()) {
    throw new Error(
      `Platform owner mismatch! Expected ${PLATFORM_OWNER}, got ${onChainOwner}`
    );
  }
  console.log("✓ Platform owner verified on-chain:", onChainOwner);

  // ── 4. Verify gateway was set correctly ─────────────────────────────
  const onChainGateway = await settlement.gateway();
  if (onChainGateway.toLowerCase() !== deployer.address.toLowerCase()) {
    throw new Error(
      `Gateway mismatch! Expected ${deployer.address}, got ${onChainGateway}`
    );
  }
  console.log("✓ Gateway verified on-chain:", onChainGateway);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
