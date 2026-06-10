const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AIMSSettlement", function () {
  let usdc, settlement;
  let user, worker, owner;
  let userSigner, workerSigner, ownerSigner;
  let gatewayWallet; // ethers.Wallet with known private key for raw signing

  const BPS_DENOM = 10_000n;
  const WORKER_BPS = 8_000n;
  const AMOUNT = 1_000_000n; // 1 USDC (6 decimals)
  const DEPOSIT = 10_000_000n; // 10 USDC

  beforeEach(async function () {
    const [fundingSigner, _u, _w, _o] = await ethers.getSigners();
    userSigner = _u;
    workerSigner = _w;
    ownerSigner = _o;
    user = userSigner.address;
    worker = workerSigner.address;
    owner = ownerSigner.address;

    // Create a dedicated gateway wallet with known private key so we can
    // produce raw ECDSA signatures (without the Ethereum prefix) matching
    // the Solidity contract's ECDSA.recover() verification.
    gatewayWallet = ethers.Wallet.createRandom();
    // Fund it with ETH from the default signer
    await fundingSigner.sendTransaction({
      to: gatewayWallet.address,
      value: ethers.parseEther("1.0"),
    });

    // Deploy mock USDC
    const MockERC20 = await ethers.getContractFactory("contracts/test/MockERC20.sol:MockERC20");
    usdc = await MockERC20.deploy("USD Coin", "USDC", 6);
    await usdc.waitForDeployment();

    // Deploy settlement contract with gatewayWallet.address as the oracle
    const AIMSSettlement = await ethers.getContractFactory("AIMSSettlement");
    settlement = await AIMSSettlement.deploy(
      await usdc.getAddress(),
      gatewayWallet.address,
      owner
    );
    await settlement.waitForDeployment();

    // Seed user with USDC and approve settlement contract
    await usdc.mint(user, DEPOSIT);
    await usdc.connect(userSigner).approve(await settlement.getAddress(), DEPOSIT);
  });

  // ── Raw ECDSA signing helpers ──────────────────────────────────────────────

  /** Sign a raw hash (bytes32) with the gateway key — no Ethereum prefix. */
  function rawSign(hash) {
    const sigObj = gatewayWallet.signingKey.sign(ethers.getBytes(hash));
    return ethers.Signature.from(sigObj).serialized;
  }

  /** Build settleTask message hash matching Solidity ABI-encodePacked. */
  function buildSettleMsg(taskId, user, worker, amount, nonce) {
    return ethers.solidityPackedKeccak256(
      ["bytes32", "address", "address", "uint256", "uint256"],
      [taskId, user, worker, amount, nonce]
    );
  }

  /** Build PoT (claimReward) message hash matching Solidity. */
  function buildPotMsg(taskId, claimant, amount) {
    return ethers.solidityPackedKeccak256(
      ["bytes32", "address", "uint256"],
      [taskId, claimant, amount]
    );
  }

  // ── Deposits ──────────────────────────────────────────────────────────────

  describe("Deposits", function () {
    it("should accept USDC deposits", async function () {
      await settlement.connect(userSigner).deposit(DEPOSIT);
      expect(await settlement.balances(user)).to.equal(DEPOSIT);
    });

    it("should reject zero-amount deposits", async function () {
      await expect(
        settlement.connect(userSigner).deposit(0)
      ).to.be.revertedWith("AIMSSettlement: amount must be > 0");
    });

    it("should emit Deposited event", async function () {
      await expect(settlement.connect(userSigner).deposit(DEPOSIT))
        .to.emit(settlement, "Deposited")
        .withArgs(user, DEPOSIT);
    });
  });

  // ── Withdrawals ───────────────────────────────────────────────────────────

  describe("Withdrawals", function () {
    beforeEach(async function () {
      await settlement.connect(userSigner).deposit(DEPOSIT);
    });

    it("should allow withdrawal of deposited funds", async function () {
      await settlement.connect(userSigner).withdraw(DEPOSIT);
      expect(await settlement.balances(user)).to.equal(0);
    });

    it("should reject withdrawal exceeding balance", async function () {
      await expect(
        settlement.connect(userSigner).withdraw(DEPOSIT + 1n)
      ).to.be.revertedWith("AIMSSettlement: insufficient balance");
    });
  });

  // ── Settlement (gateway-signed) ───────────────────────────────────────────

  describe("Settlement (gateway-signed)", function () {
    let taskId, nonce;

    beforeEach(async function () {
      await settlement.connect(userSigner).deposit(DEPOSIT);
      taskId = ethers.solidityPackedKeccak256(["string"], ["task-0001"]);
      nonce = 1;
    });

    it("should settle a task and split 80/20", async function () {
      const hash = buildSettleMsg(taskId, user, worker, AMOUNT, nonce);
      const sig = rawSign(hash);

      await settlement
        .connect(workerSigner)
        .settleTask(taskId, user, worker, AMOUNT, nonce, sig);

      // 80% to worker
      const workerShare = (AMOUNT * WORKER_BPS) / BPS_DENOM;
      expect(await settlement.pendingPayouts(worker)).to.equal(workerShare);

      // 20% to owner
      const ownerShare = AMOUNT - workerShare;
      expect(await settlement.pendingPayouts(owner)).to.equal(ownerShare);

      // User balance deducted
      expect(await settlement.balances(user)).to.equal(DEPOSIT - AMOUNT);
    });

    it("should reject double-settle of the same task", async function () {
      const hash = buildSettleMsg(taskId, user, worker, AMOUNT, nonce);
      const sig = rawSign(hash);

      await settlement
        .connect(workerSigner)
        .settleTask(taskId, user, worker, AMOUNT, nonce, sig);

      // Use a different nonce so we pass the nonce check and hit the
      // task-already-settled check instead.
      const nonce2 = 2;
      const hash2 = buildSettleMsg(taskId, user, worker, AMOUNT, nonce2);
      const sig2 = rawSign(hash2);
      await expect(
        settlement
          .connect(workerSigner)
          .settleTask(taskId, user, worker, AMOUNT, nonce2, sig2)
      ).to.be.revertedWith("AIMSSettlement: task already settled");
    });

    it("should reject nonce reuse", async function () {
      const hash = buildSettleMsg(taskId, user, worker, AMOUNT, nonce);
      const sig = rawSign(hash);
      await settlement
        .connect(workerSigner)
        .settleTask(taskId, user, worker, AMOUNT, nonce, sig);

      const taskId2 = ethers.solidityPackedKeccak256(["string"], ["task-0002"]);
      const hash2 = buildSettleMsg(taskId2, user, worker, AMOUNT, nonce);
      const sig2 = rawSign(hash2);
      await expect(
        settlement
          .connect(workerSigner)
          .settleTask(taskId2, user, worker, AMOUNT, nonce, sig2)
      ).to.be.revertedWith("AIMSSettlement: nonce already used");
    });

    it("should reject settlement with invalid gateway signature", async function () {
      // Sign a different hash (not matching taskId) — produces a structurally
      // valid signature that won't recover to the gateway address.
      const wrongHash = buildSettleMsg(
        ethers.solidityPackedKeccak256(["string"], ["wrong-task"]),
        user, worker, AMOUNT, nonce
      );
      const badSig = rawSign(wrongHash);
      await expect(
        settlement
          .connect(workerSigner)
          .settleTask(taskId, user, worker, AMOUNT, nonce, badSig)
      ).to.be.revertedWith("AIMSSettlement: invalid gateway signature");
    });

    it("should reject when user has insufficient balance", async function () {
      const hash = buildSettleMsg(taskId, user, worker, DEPOSIT + 1n, nonce);
      const sig = rawSign(hash);
      await expect(
        settlement
          .connect(workerSigner)
          .settleTask(taskId, user, worker, DEPOSIT + 1n, nonce, sig)
      ).to.be.revertedWith("AIMSSettlement: insufficient user balance");
    });
  });

  // ── Claim (Proof-of-Task) ─────────────────────────────────────────────────

  describe("Claim (Proof-of-Task)", function () {
    let taskId, nonce, workerShare;

    beforeEach(async function () {
      await settlement.connect(userSigner).deposit(DEPOSIT);
      taskId = ethers.solidityPackedKeccak256(["string"], ["task-0001"]);
      nonce = 1;
      workerShare = (AMOUNT * WORKER_BPS) / BPS_DENOM;

      // Settle a task first
      const hash = buildSettleMsg(taskId, user, worker, AMOUNT, nonce);
      const sig = rawSign(hash);
      await settlement
        .connect(workerSigner)
        .settleTask(taskId, user, worker, AMOUNT, nonce, sig);
    });

    it("should allow worker to claim reward with valid PoT", async function () {
      const potHash = buildPotMsg(taskId, worker, workerShare);
      const potSig = rawSign(potHash);
      const before = await usdc.balanceOf(worker);

      await settlement.connect(workerSigner).claimReward(taskId, potSig);

      const after = await usdc.balanceOf(worker);
      expect(after - before).to.equal(workerShare);
      expect(await settlement.pendingPayouts(worker)).to.equal(0);
    });

    it("should reject double-claim", async function () {
      const potHash = buildPotMsg(taskId, worker, workerShare);
      const potSig = rawSign(potHash);
      await settlement.connect(workerSigner).claimReward(taskId, potSig);

      await expect(
        settlement.connect(workerSigner).claimReward(taskId, potSig)
      ).to.be.revertedWith("AIMSSettlement: reward already claimed");
    });

    it("should reject claim with invalid PoT signature", async function () {
      // Sign a wrong taskId so the signature won't recover to gateway
      const wrongTaskId = ethers.solidityPackedKeccak256(["string"], ["wrong-task"]);
      const wrongPotHash = buildPotMsg(wrongTaskId, worker, workerShare);
      const fakeSig = rawSign(wrongPotHash);
      await expect(
        settlement.connect(workerSigner).claimReward(taskId, fakeSig)
      ).to.be.revertedWith("AIMSSettlement: invalid PoT signature");
    });

    it("should reject claim with wrong-amount PoT signature", async function () {
      const wrongAmount = workerShare + 1n;
      const wrongPotHash = buildPotMsg(taskId, worker, wrongAmount);
      const wrongPotSig = rawSign(wrongPotHash);
      await expect(
        settlement.connect(workerSigner).claimReward(taskId, wrongPotSig)
      ).to.be.revertedWith("AIMSSettlement: invalid PoT signature");
    });
  });

  // ── Platform Owner Fees ───────────────────────────────────────────────────

  describe("Platform Owner Fees", function () {
    let taskId, nonce;

    beforeEach(async function () {
      await settlement.connect(userSigner).deposit(DEPOSIT);
      taskId = ethers.solidityPackedKeccak256(["string"], ["task-0001"]);
      nonce = 1;

      const hash = buildSettleMsg(taskId, user, worker, AMOUNT, nonce);
      const sig = rawSign(hash);
      await settlement
        .connect(workerSigner)
        .settleTask(taskId, user, worker, AMOUNT, nonce, sig);
    });

    it("should allow owner to claim accumulated fees", async function () {
      const ownerShare = AMOUNT - (AMOUNT * WORKER_BPS) / BPS_DENOM;
      const before = await usdc.balanceOf(owner);

      await settlement.connect(ownerSigner).claimOwnerFees();

      const after = await usdc.balanceOf(owner);
      expect(after - before).to.equal(ownerShare);
    });

    it("should reject non-owner claiming fees", async function () {
      await expect(
        settlement.connect(workerSigner).claimOwnerFees()
      ).to.be.revertedWith("AIMSSettlement: only platform owner");
    });
  });

  // ── Gateway key rotation ──────────────────────────────────────────────────

  describe("Gateway key rotation", function () {
    it("should allow gateway to update its address", async function () {
      const gwSigner = gatewayWallet.connect(ethers.provider);
      const newGateway = worker;
      await settlement.connect(gwSigner).setGateway(newGateway);
      expect(await settlement.gateway()).to.equal(newGateway);
    });

    it("should reject non-gateway from rotating key", async function () {
      await expect(
        settlement.connect(workerSigner).setGateway(worker)
      ).to.be.revertedWith("AIMSSettlement: caller is not the gateway");
    });
  });
});
