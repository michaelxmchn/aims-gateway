#!/usr/bin/env node
/* Deploy AIMSAgentGateway (70/25/5 split) + MockERC20 to local Hardhat.

 * Usage:
 *   npx hardhat run scripts/deploy_agent_gateway.cjs --network hardhat
 */

const { ethers } = require("hardhat");

const TREASURY = "0x08c9fd0a915f2b0856353850b8adea943f226bcf";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deployer:", deployer.address);
  console.log("Treasury:", TREASURY);

  // ── 1. Deploy MockERC20 ─────────────────────────────────────────
  const MockERC20 = await ethers.getContractFactory(
    "contracts/test/MockERC20.sol:MockERC20"
  );
  const mock = await MockERC20.deploy("USD Coin", "USDC", 6);
  await mock.waitForDeployment();
  const usdcAddress = await mock.getAddress();
  console.log("MockUSDC deployed at:", usdcAddress);

  // ── 2. Deploy AIMSAgentGateway ──────────────────────────────────
  const AIMSAgentGateway = await ethers.getContractFactory("AIMSAgentGateway");
  const gateway = await AIMSAgentGateway.deploy(
    usdcAddress,
    deployer.address,     // initial gateway oracle
    TREASURY,             // treasury address (5% recipient)
  );
  await gateway.waitForDeployment();
  const gatewayAddress = await gateway.getAddress();

  console.log("\n=== Deployment Summary ===");
  console.log("AIMSAgentGateway:", gatewayAddress);
  console.log("MockUSDC:        ", usdcAddress);
  console.log("Gateway oracle:  ", deployer.address);
  console.log("Treasury:        ", TREASURY);
  console.log("=======================\n");

  // ── 3. Mint 1M MockUSDC to deployer ─────────────────────────────
  const mintAmount = ethers.parseUnits("1000000", 6);
  await mock.mint(deployer.address, mintAmount);
  console.log("Minted 1,000,000 MockUSDC to deployer:", deployer.address);

  // ── 4. Print env vars ───────────────────────────────────────────
  console.log("\n=== Gateway Env Vars ===");
  console.log(`AIMS_RPC_URL=http://127.0.0.1:8545`);
  console.log(`AIMS_CONTRACT_ADDRESS=${gatewayAddress}`);
  console.log(`AIMS_USDC_ADDRESS=${usdcAddress}`);
  console.log(`AIMS_GATEWAY_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`);
  console.log(`AIMS_TREASURY_ADDRESS=${TREASURY}`);
  console.log("=======================\n");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
