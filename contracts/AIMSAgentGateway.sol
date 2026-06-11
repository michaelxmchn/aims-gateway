// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AIMS Agent Gateway — On-Chain Settlement & Proof-of-Task
/// @notice Production-grade settlement contract for the AIMS DePIN mesh.
///
/// **Multi-party streaming split**: 70 % Developer / 25 % Worker / 5 % Treasury.
///
/// **Escrow safety**: User deposits USDC into this contract. On task submission,
/// the gateway calls ``settleTask`` with an ECDSA authorization. The contract
/// atomically deducts from the user's balance, credits the three parties, and
/// emits a ``TaskSettled`` event. On timeout / failure, the escrow is returned
/// to the user via ``refundTask``.
///
/// **Proof-of-Task (PoT)**: Workers receive a gateway-signed ECDSA receipt.
/// They call ``claimReward`` on-chain to collect their 25 % share. Developers
/// call ``claimDeveloperReward`` for their 70 %. The treasury accumulates the
/// 5 % platform tax until the owner claims it.
///
/// **Replay protection**: Compound nonce guard — ``keccak256(nonce, taskId)``
/// prevents double-settle even if a nonce or taskId appears in a second call.
///
/// Security:
///   - Gateway ECDSA signature binds (taskId, worker, amount) — settlement
///     and claims must present a valid gateway signature.
///   - ``onlyGateway`` modifier for owner-sensitive operations.
///   - ``settled`` / ``refunded`` / ``claimed`` task status state machine.
///   - No re-entrancy: balances are updated before transfers (checks-effects-interactions).
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

contract AIMSAgentGateway {
    using SafeERC20 for IERC20;

    // ════════════════════════════════════════════════════════════════════
    // Constants
    // ════════════════════════════════════════════════════════════════════

    /// @notice Basis points denominator: 10 000 = 100 %.
    uint256 public constant BPS_DENOM = 10_000;

    /// @notice Developer receives 70 % of each settlement.
    uint256 public constant DEVELOPER_BPS = 7_000;

    /// @notice Worker (executor / bandwidth provider) receives 25 %.
    uint256 public constant WORKER_BPS = 2_500;

    /// @notice Treasury (protocol sustainability) receives 5 %.
    uint256 public constant TREASURY_BPS = 500;

    /// @notice Maximum timeout window for a task (in seconds).
    uint256 public constant MAX_TIMEOUT = 300; // 5 minutes

    // ════════════════════════════════════════════════════════════════════
    // Storage
    // ════════════════════════════════════════════════════════════════════

    /// @notice The USDC token contract.
    IERC20 public immutable usdc;

    /// @notice Gateway oracle address — the signer of settlement authorizations.
    address public gateway;

    /// @notice Platform treasury address — recipient of the 5 % protocol tax.
    address public immutable treasury;

    /// @notice Per-address deposit balances (user → USDC amount, 6 decimals).
    mapping(address => uint256) public balances;

    /// @notice Developer registry: skill_id hash → developer wallet address.
    ///         Set by the gateway when a skill is uploaded.
    mapping(bytes32 => address) public developers;

    // ── Task lifecycle ─────────────────────────────────────────────────

    enum TaskStatus { None, Settled, Refunded, Claimed }

    /// @notice Task lifecycle state.
    mapping(bytes32 => TaskStatus) public taskStatus;

    /// @notice Compound nonce guard: keccak256(nonce, taskId) → used.
    mapping(bytes32 => bool) public usedCompoundNonces;

    /// @notice Pending payouts awaiting claim (worker/developer → amount).
    mapping(address => uint256) public pendingPayouts;

    /// @notice Accumulated treasury fees (claimed by owner).
    uint256 public accumulatedTreasuryFees;

    /// @notice Task settlement snapshot — stores the worker address and amounts
    ///         so claimReward / claimDeveloperReward can verify without re-argument.
    struct TaskSettlement {
        address worker;
        address developer;
        uint256 totalAmount;    // full settlement amount
        uint256 workerShare;
        uint256 developerShare;
        uint256 treasuryShare;
        uint256 settledAt;      // block.timestamp
    }

    /// @notice Settlement snapshot per taskId.
    mapping(bytes32 => TaskSettlement) public taskSettlements;

    /// @notice Per-party claim tracking — worker and developer claim independently
    ///         so the first claim does not block the second.
    mapping(bytes32 => bool) public hasClaimedWorker;
    mapping(bytes32 => bool) public hasClaimedDeveloper;

    // ════════════════════════════════════════════════════════════════════
    // Events
    // ════════════════════════════════════════════════════════════════════

    /// @notice Emitted when a user deposits USDC into the contract.
    event Deposited(address indexed user, uint256 amount);

    /// @notice Emitted when a user withdraws their deposited USDC.
    event Withdrawn(address indexed user, uint256 amount);

    /// @notice Emitted when the gateway oracle records a settlement.
    event TaskSettled(
        bytes32 indexed taskId,
        address indexed user,
        address indexed worker,
        address developer,
        uint256 totalAmount,
        uint256 workerShare,
        uint256 developerShare,
        uint256 treasuryShare,
        uint256 nonce
    );

    /// @notice Emitted when a task is refunded due to timeout / failure.
    event TaskRefunded(
        bytes32 indexed taskId,
        address indexed user,
        uint256 amount,
        string reason
    );

    /// @notice Emitted when a worker claims their reward.
    event WorkerRewardClaimed(
        bytes32 indexed taskId,
        address indexed worker,
        uint256 amount
    );

    /// @notice Emitted when a developer claims their reward.
    event DeveloperRewardClaimed(
        bytes32 indexed taskId,
        address indexed developer,
        uint256 amount
    );

    /// @notice Emitted when treasury fees are claimed.
    event TreasuryClaimed(address indexed owner, uint256 amount);

    /// @notice Emitted when the developer registry is updated.
    event DeveloperRegistered(bytes32 indexed skillIdHash, address indexed developer);

    /// @notice Emitted when the gateway address is rotated.
    event GatewayUpdated(address indexed oldGateway, address indexed newGateway);

    // ════════════════════════════════════════════════════════════════════
    // Modifiers
    // ════════════════════════════════════════════════════════════════════

    modifier onlyGateway() {
        require(msg.sender == gateway, "AIMSAgentGateway: caller is not the gateway");
        _;
    }

    // ════════════════════════════════════════════════════════════════════
    // Constructor
    // ════════════════════════════════════════════════════════════════════

    /// @param _usdc     Address of the USDC token contract on Base.
    /// @param _gateway  Initial gateway oracle address.
    /// @param _treasury Address that receives the 5 % protocol treasury.
    constructor(address _usdc, address _gateway, address _treasury) {
        require(_usdc != address(0), "AIMSAgentGateway: invalid USDC address");
        require(_gateway != address(0), "AIMSAgentGateway: invalid gateway");
        require(_treasury != address(0), "AIMSAgentGateway: invalid treasury");
        usdc = IERC20(_usdc);
        gateway = _gateway;
        treasury = _treasury;
    }

    // ════════════════════════════════════════════════════════════════════
    // Deposit / Withdraw
    // ════════════════════════════════════════════════════════════════════

    /// @notice Deposit USDC into the contract.  User must have called
    ///         ``USDC.approve(address(this), amount)`` first.
    /// @param amount Amount of USDC to deposit (6 decimal atomic units).
    function deposit(uint256 amount) external {
        require(amount > 0, "AIMSAgentGateway: amount must be > 0");
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        balances[msg.sender] += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Withdraw previously deposited USDC back to the user.
    /// @param amount Amount of USDC to withdraw.
    function withdraw(uint256 amount) external {
        require(amount > 0, "AIMSAgentGateway: amount must be > 0");
        require(balances[msg.sender] >= amount, "AIMSAgentGateway: insufficient balance");
        balances[msg.sender] -= amount;
        usdc.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Check a user's spendable balance.
    /// @param user The user's EVM address.
    /// @return The deposited USDC balance (atomic units, 6 decimals).
    function balanceOf(address user) external view returns (uint256) {
        return balances[user];
    }

    // ════════════════════════════════════════════════════════════════════
    // Developer Registry
    // ════════════════════════════════════════════════════════════════════

    /// @notice Register or update the developer wallet for a skill.
    /// @param skillIdHash keccak256(skill_id_string).
    /// @param developer   The developer's EVM wallet address.
    function registerDeveloper(bytes32 skillIdHash, address developer) external onlyGateway {
        require(developer != address(0), "AIMSAgentGateway: invalid developer address");
        developers[skillIdHash] = developer;
        emit DeveloperRegistered(skillIdHash, developer);
    }

    /// @notice Look up the developer for a skill.
    /// @param skillIdHash keccak256(skill_id_string).
    /// @return The developer's EVM address, or address(0) if unregistered.
    function getDeveloper(bytes32 skillIdHash) external view returns (address) {
        return developers[skillIdHash];
    }

    // ════════════════════════════════════════════════════════════════════
    // Settlement (Gateway-Signed)
    // ════════════════════════════════════════════════════════════════════

    /// @notice Settle a completed task.  The gateway signs an ECDSA authorization
    ///         binding ``(taskId, worker, totalAmount)``.  Anyone can submit it.
    ///
    ///         On success:
    ///           - Deducts ``totalAmount`` from the user's deposit balance.
    ///           - Credits 70/25/5 to developer / worker / treasury.
    ///           - Stores a settlement snapshot so the three parties can claim.
    ///
    /// @param taskId           Unique task identifier (bytes32 = keccak256(task_uuid)).
    /// @param user             The user whose deposit is charged.
    /// @param worker           The worker that executed the task.
    /// @param skillIdHash      keccak256(skill_id) — used to look up the developer.
    /// @param totalAmount      Total settlement amount in USDC (6 decimals).
    /// @param nonce            Monotonic nonce for replay protection.
    /// @param deadline         UNIX timestamp; revert if block.timestamp > deadline.
    /// @param gatewaySignature Gateway's ECDSA signature (65 bytes, r/s/v).
    function settleTask(
        bytes32 taskId,
        address user,
        address worker,
        bytes32 skillIdHash,
        uint256 totalAmount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata gatewaySignature
    ) external {
        // ── Guard: deadline ────────────────────────────────────────────
        require(block.timestamp <= deadline, "AIMSAgentGateway: deadline passed");

        // ── Guard: amount ────────────────────────────────────────────
        require(totalAmount > 0, "AIMSAgentGateway: amount must be > 0");

        // ── Guard: compound nonce (nonce + taskId) ────────────────────
        bytes32 compoundNonce = keccak256(abi.encodePacked(nonce, taskId));
        require(!usedCompoundNonces[compoundNonce], "AIMSAgentGateway: nonce already used");

        // ── Guard: task lifecycle ─────────────────────────────────────
        require(
            taskStatus[taskId] == TaskStatus.None,
            "AIMSAgentGateway: task already settled or refunded"
        );

        // ── Guard: user balance ──────────────────────────────────────
        require(balances[user] >= totalAmount, "AIMSAgentGateway: insufficient user balance");

        // ── Verify gateway ECDSA signature ────────────────────────────
        // The gateway signs: keccak256(abi.encodePacked(taskId, worker, totalAmount))
        _verifyGatewaySignature(taskId, worker, totalAmount, gatewaySignature);

        // ── Look up developer ─────────────────────────────────────────
        address developer = developers[skillIdHash];
        // If no developer is registered, the developer share goes to treasury.
        bool hasDeveloper = developer != address(0);

        // ── Calculate splits ──────────────────────────────────────────
        uint256 developerShare = hasDeveloper
            ? (totalAmount * DEVELOPER_BPS) / BPS_DENOM
            : 0;
        uint256 workerShare = (totalAmount * WORKER_BPS) / BPS_DENOM;
        uint256 treasuryShare = totalAmount - developerShare - workerShare;

        // ── Record compound nonce used ────────────────────────────────
        usedCompoundNonces[compoundNonce] = true;

        // ── Mark task as settled ───────────────────────────────────────
        taskStatus[taskId] = TaskStatus.Settled;

        // ── Deduct from user ──────────────────────────────────────────
        balances[user] -= totalAmount;

        // ── Store settlement snapshot ─────────────────────────────────
        taskSettlements[taskId] = TaskSettlement({
            worker: worker,
            developer: developer,
            totalAmount: totalAmount,
            workerShare: workerShare,
            developerShare: developerShare,
            treasuryShare: treasuryShare,
            settledAt: block.timestamp
        });

        // ── Credit pending payouts ────────────────────────────────────
        pendingPayouts[worker] += workerShare;
        if (hasDeveloper) {
            pendingPayouts[developer] += developerShare;
        } else {
            // Unregistered developer → treasury claims it
            accumulatedTreasuryFees += developerShare;
        }
        accumulatedTreasuryFees += treasuryShare;

        emit TaskSettled(
            taskId, user, worker, developer,
            totalAmount, workerShare, developerShare, treasuryShare, nonce
        );
    }

    // ════════════════════════════════════════════════════════════════════
    // Timeout Refund
    // ════════════════════════════════════════════════════════════════════

    /// @notice Refund a task that has timed out.  Only the gateway can trigger
    ///         a refund (to prevent griefing).  The full ``totalAmount`` is
    ///         returned to the user's deposit balance.
    ///
    /// @param taskId  The task identifier.
    /// @param user    The user to refund.
    /// @param amount  The amount to refund.
    /// @param reason  Human-readable reason for the refund.
    function refundTask(
        bytes32 taskId,
        address user,
        uint256 amount,
        string calldata reason
    ) external onlyGateway {
        require(
            taskStatus[taskId] == TaskStatus.Settled,
            "AIMSAgentGateway: task not settled"
        );
        require(
            !hasClaimedWorker[taskId] && !hasClaimedDeveloper[taskId],
            "AIMSAgentGateway: cannot refund after claim"
        );
        require(amount > 0, "AIMSAgentGateway: amount must be > 0");

        TaskSettlement memory settlement = taskSettlements[taskId];

        // Must be within timeout window
        require(
            block.timestamp <= settlement.settledAt + MAX_TIMEOUT,
            "AIMSAgentGateway: refund window expired"
        );

        // Unwind the settlement:
        // 1. Revert pending payouts
        // 2. Return the amount to the user
        // 3. Mark task as refunded

        // Deduct from pending payouts (they may have been partially claimed)
        uint256 remainingWorker = pendingPayouts[settlement.worker];
        uint256 remainingDev = pendingPayouts[settlement.developer];

        if (remainingWorker >= settlement.workerShare) {
            pendingPayouts[settlement.worker] = remainingWorker - settlement.workerShare;
        } else {
            pendingPayouts[settlement.worker] = 0;
        }

        if (settlement.developer != address(0) && remainingDev >= settlement.developerShare) {
            pendingPayouts[settlement.developer] = remainingDev - settlement.developerShare;
        } else if (settlement.developer != address(0)) {
            pendingPayouts[settlement.developer] = 0;
        }

        // Reduce accumulated treasury fees
        if (accumulatedTreasuryFees >= settlement.treasuryShare) {
            accumulatedTreasuryFees -= settlement.treasuryShare;
        } else {
            accumulatedTreasuryFees = 0;
        }

        // Return to user
        taskStatus[taskId] = TaskStatus.Refunded;
        balances[user] += amount;

        emit TaskRefunded(taskId, user, amount, reason);
    }

    // ════════════════════════════════════════════════════════════════════
    // Claim: Worker (25 %)
    // ════════════════════════════════════════════════════════════════════

    /// @notice Claim the worker's 25 % reward for a settled task.
    ///         The worker presents a PoT — an ECDSA signature from the
    ///         gateway over ``keccak256(abi.encodePacked(taskId, worker, amount))``.
    ///
    /// @param taskId           The task identifier.
    /// @param gatewaySignature Gateway's PoT signature (65 bytes, r/s/v).
    function claimReward(
        bytes32 taskId,
        bytes calldata gatewaySignature
    ) external {
        require(
            !hasClaimedWorker[taskId],
            "AIMSAgentGateway: worker already claimed"
        );
        require(
            taskStatus[taskId] != TaskStatus.Refunded,
            "AIMSAgentGateway: task was refunded"
        );

        TaskSettlement storage settlement = taskSettlements[taskId];
        require(settlement.worker == msg.sender, "AIMSAgentGateway: not the assigned worker");

        uint256 workerAmount = settlement.workerShare;
        require(workerAmount > 0, "AIMSAgentGateway: worker share is zero");
        require(
            pendingPayouts[msg.sender] >= workerAmount,
            "AIMSAgentGateway: insufficient pending payout"
        );

        // Verify the PoT signature — gateway signs
        // keccak256(abi.encodePacked(taskId, worker, amount))
        _verifyGatewaySignature(taskId, msg.sender, workerAmount, gatewaySignature);

        // Mark worker as claimed (independent of developer claim)
        hasClaimedWorker[taskId] = true;

        // Transition to Claimed only when both parties have claimed
        if (hasClaimedDeveloper[taskId]) {
            taskStatus[taskId] = TaskStatus.Claimed;
        }

        // Deduct from pending payouts (protect against re-entrancy)
        pendingPayouts[msg.sender] -= workerAmount;

        // Transfer
        usdc.safeTransfer(msg.sender, workerAmount);

        emit WorkerRewardClaimed(taskId, msg.sender, workerAmount);
    }

    // ════════════════════════════════════════════════════════════════════
    // Claim: Developer (70 %)
    // ════════════════════════════════════════════════════════════════════

    /// @notice Claim the developer's 70 % share for a settled task.
    ///         The developer must be the registered developer for the skill
    ///         and present a valid gateway PoT signature.
    ///
    /// @param taskId           The task identifier.
    /// @param gatewaySignature Gateway's PoT signature over
    ///                         ``keccak256(abi.encodePacked(taskId, developer, amount))``.
    function claimDeveloperReward(
        bytes32 taskId,
        bytes calldata gatewaySignature
    ) external {
        require(
            !hasClaimedDeveloper[taskId],
            "AIMSAgentGateway: developer already claimed"
        );
        require(
            taskStatus[taskId] != TaskStatus.Refunded,
            "AIMSAgentGateway: task was refunded"
        );

        TaskSettlement storage settlement = taskSettlements[taskId];
        require(
            settlement.developer == msg.sender,
            "AIMSAgentGateway: not the assigned developer"
        );

        uint256 developerAmount = settlement.developerShare;
        require(developerAmount > 0, "AIMSAgentGateway: developer share is zero");
        require(
            pendingPayouts[msg.sender] >= developerAmount,
            "AIMSAgentGateway: insufficient pending payout"
        );

        // Verify gateway PoT signature
        _verifyGatewaySignature(taskId, msg.sender, developerAmount, gatewaySignature);

        // Mark developer as claimed (independent of worker claim)
        hasClaimedDeveloper[taskId] = true;

        // Transition to Claimed only when both parties have claimed
        if (hasClaimedWorker[taskId]) {
            taskStatus[taskId] = TaskStatus.Claimed;
        }

        pendingPayouts[msg.sender] -= developerAmount;
        usdc.safeTransfer(msg.sender, developerAmount);

        emit DeveloperRewardClaimed(taskId, msg.sender, developerAmount);
    }

    // ════════════════════════════════════════════════════════════════════
    // Claim: Treasury (5 %)
    // ════════════════════════════════════════════════════════════════════

    /// @notice Claim the accumulated 5 % treasury fees.
    function claimTreasuryFees() external {
        require(msg.sender == treasury, "AIMSAgentGateway: only treasury");
        uint256 amount = accumulatedTreasuryFees;
        require(amount > 0, "AIMSAgentGateway: no accumulated fees");
        accumulatedTreasuryFees = 0;
        usdc.safeTransfer(msg.sender, amount);
        emit TreasuryClaimed(msg.sender, amount);
    }

    // ════════════════════════════════════════════════════════════════════
    // View Functions
    // ════════════════════════════════════════════════════════════════════

    /// @notice Get the full settlement snapshot for a task.
    function getTaskSettlement(bytes32 taskId) external view returns (
        address worker,
        address developer,
        uint256 totalAmount,
        uint256 workerShare,
        uint256 developerShare,
        uint256 treasuryShare,
        uint256 settledAt,
        TaskStatus status
    ) {
        TaskSettlement memory s = taskSettlements[taskId];
        return (
            s.worker, s.developer, s.totalAmount,
            s.workerShare, s.developerShare, s.treasuryShare,
            s.settledAt, taskStatus[taskId]
        );
    }

    /// @notice Check if a compound nonce has been used.
    function isCompoundNonceUsed(uint256 nonce, bytes32 taskId) external view returns (bool) {
        return usedCompoundNonces[keccak256(abi.encodePacked(nonce, taskId))];
    }

    /// @notice View a party's pending payout.
    function getPendingPayout(address party) external view returns (uint256) {
        return pendingPayouts[party];
    }

    /// @notice View accumulated treasury fees.
    function getTreasuryFees() external view returns (uint256) {
        return accumulatedTreasuryFees;
    }

    // ════════════════════════════════════════════════════════════════════
    // ECDSA Verification
    // ════════════════════════════════════════════════════════════════════

    /// @notice Verify a gateway ECDSA signature over
    ///         ``keccak256(abi.encodePacked(taskId, party, amount))``.
    ///
    /// @param taskId    The task identifier (bytes32).
    /// @param party     The bound party address (worker or developer).
    /// @param amount    The amount bound to this signature.
    /// @param signature The ECDSA signature (65 bytes, r/s/v).
    function _verifyGatewaySignature(
        bytes32 taskId,
        address party,
        uint256 amount,
        bytes calldata signature
    ) internal view {
        bytes32 message = keccak256(abi.encodePacked(taskId, party, amount));
        (address recovered, ECDSA.RecoverError err, ) = ECDSA.tryRecover(message, signature);
        require(
            err == ECDSA.RecoverError.NoError && recovered == gateway,
            "AIMSAgentGateway: invalid gateway signature"
        );
    }

    // ════════════════════════════════════════════════════════════════════
    // Admin
    // ════════════════════════════════════════════════════════════════════

    /// @notice Update the gateway oracle address (key rotation).
    function setGateway(address newGateway) external onlyGateway {
        require(newGateway != address(0), "AIMSAgentGateway: invalid address");
        emit GatewayUpdated(gateway, newGateway);
        gateway = newGateway;
    }
}
