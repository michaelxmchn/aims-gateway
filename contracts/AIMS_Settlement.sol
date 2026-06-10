// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AIMS Settlement Contract
/// @notice On-chain settlement for the AIMS Gateway credit & revenue system.
///         Users deposit USDC, the Gateway (oracle) authorises settlements via
///         settleTask(), and workers claim 80 % rewards via Proof-of-Task.
///
/// Security
/// --------
/// - **Nonce replay protection**: each settleTask call consumes a unique nonce.
///   Duplicate nonces are rejected, preventing replay attacks.
/// - **Gateway-only oracle**: settleTask can only be called by the registered
///   gateway address.
/// - **PoT claim verification**: claimReward() recovers the signer from the
///   gateway's ECDSA signature and verifies it matches the stored gateway.
/// - **Double-claim prevention**: each taskId can be claimed at most once.
///
/// Revenue split
/// -------------
/// - 80 % of the settlement amount goes to the Worker (claimant).
/// - 20 % goes to the Platform Owner (callable via claimOwnerFees()).

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract AIMSSettlement {
    using SafeERC20 for IERC20;

    // ── Constants ────────────────────────────────────────────────────────────

    /// @notice Basis points denominator: 10 000 = 100 %.
    uint256 public constant BPS_DENOM = 10_000;

    /// @notice Worker receives 80 % of each settlement.
    uint256 public constant WORKER_BPS = 8_000;

    /// @notice Platform owner receives 20 %.
    uint256 public constant OWNER_BPS = 2_000;

    // ── Storage ──────────────────────────────────────────────────────────────

    /// @notice The USDC token contract.
    IERC20 public immutable usdc;

    /// @notice Gateway oracle address — the only caller of settleTask().
    address public gateway;

    /// @notice Platform owner address — recipient of the 20 % platform fee.
    address public immutable platformOwner;

    /// @notice Per-address deposit balances (user → USDC amount).
    mapping(address => uint256) public balances;

    /// @notice Pending payouts awaiting claim (worker/owner → amount).
    mapping(address => uint256) public pendingPayouts;

    /// @notice Used nonces (nonce → used); prevents replay of settleTask calls.
    mapping(uint256 => bool) public usedNonces;

    /// @notice Settlement commitment for each taskId; prevents double-settle.
    mapping(bytes32 => bool) public settledTasks;

    /// @notice Tracks which taskIds have already been claimed (double-claim guard).
    mapping(bytes32 => bool) public claimedTasks;

    // ── Events ───────────────────────────────────────────────────────────────

    /// @notice Emitted when a user deposits USDC into the contract.
    event Deposited(address indexed user, uint256 amount);

    /// @notice Emitted when a user withdraws their deposited USDC.
    event Withdrawn(address indexed user, uint256 amount);

    /// @notice Emitted when the gateway oracle records a settlement.
    event TaskSettled(
        bytes32 indexed taskId,
        address indexed user,
        address indexed worker,
        uint256 amount,
        uint256 nonce
    );

    /// @notice Emitted when a worker successfully claims their reward.
    event RewardClaimed(
        bytes32 indexed taskId,
        address indexed claimant,
        uint256 workerAmount,
        uint256 ownerAmount
    );

    /// @notice Emitted when the platform owner claims accumulated fees.
    event OwnerFeesClaimed(address indexed owner, uint256 amount);

    // ── Modifiers ────────────────────────────────────────────────────────────

    modifier onlyGateway() {
        require(msg.sender == gateway, "AIMSSettlement: caller is not the gateway");
        _;
    }

    // ── Constructor ──────────────────────────────────────────────────────────

    /// @param _usdc           Address of the USDC token contract.
    /// @param _gateway        Initial gateway oracle address.
    /// @param _platformOwner  Address that receives the 20 % platform fee.
    constructor(address _usdc, address _gateway, address _platformOwner) {
        require(_usdc != address(0), "AIMSSettlement: invalid USDC address");
        require(_gateway != address(0), "AIMSSettlement: invalid gateway");
        require(_platformOwner != address(0), "AIMSSettlement: invalid owner");
        usdc = IERC20(_usdc);
        gateway = _gateway;
        platformOwner = _platformOwner;
    }

    // ── Deposit / Withdraw ───────────────────────────────────────────────────

    /// @notice Deposit USDC into the contract.  User must have called
    ///         `USDC.approve(address(this), amount)` first.
    function deposit(uint256 amount) external {
        require(amount > 0, "AIMSSettlement: amount must be > 0");
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        balances[msg.sender] += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Withdraw previously deposited USDC back to the user.
    function withdraw(uint256 amount) external {
        require(amount > 0, "AIMSSettlement: amount must be > 0");
        require(balances[msg.sender] >= amount, "AIMSSettlement: insufficient balance");
        balances[msg.sender] -= amount;
        usdc.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    // ── Oracle: settleTask ───────────────────────────────────────────────────

    /// @notice Record a settlement (gateway oracle function).
    ///         Deducts *amount* from *user*'s deposit balance and credits
    ///         80 % to the worker and 20 % to the platform owner as pending payouts.
    ///
    /// @param taskId   Unique task identifier (keccak256 of off-chain task ID).
    /// @param user     The user whose deposit is being settled.
    /// @param worker   The worker who executed the task.
    /// @param amount   Total settlement amount in USDC (6 decimals).
    /// @param nonce    Unique nonce for replay protection.
    function settleTask(
        bytes32 taskId,
        address user,
        address worker,
        uint256 amount,
        uint256 nonce
    ) external onlyGateway {
        require(amount > 0, "AIMSSettlement: amount must be > 0");
        require(!usedNonces[nonce], "AIMSSettlement: nonce already used");
        require(!settledTasks[taskId], "AIMSSettlement: task already settled");
        require(balances[user] >= amount, "AIMSSettlement: insufficient user balance");

        usedNonces[nonce] = true;
        settledTasks[taskId] = true;

        // Deduct from user's deposit balance
        balances[user] -= amount;

        // Split 80/20
        uint256 workerAmount = (amount * WORKER_BPS) / BPS_DENOM;
        uint256 ownerAmount = amount - workerAmount;

        pendingPayouts[worker] += workerAmount;
        pendingPayouts[platformOwner] += ownerAmount;

        emit TaskSettled(taskId, user, worker, amount, nonce);
    }

    // ── Claim: Worker ────────────────────────────────────────────────────────

    /// @notice Claim reward for a settled task using a Proof-of-Task.
    ///
    ///         The PoT is an ECDSA signature produced by the gateway over
    ///         `keccak256(abi.encodePacked(taskId, msg.sender))`.
    ///
    /// @param taskId            The task identifier.
    /// @param gatewaySignature  The gateway's ECDSA signature (r, s, v — 65 bytes).
    function claimReward(
        bytes32 taskId,
        bytes calldata gatewaySignature
    ) external {
        require(!claimedTasks[taskId], "AIMSSettlement: reward already claimed");

        // Recover the signer from the PoT
        bytes32 message = keccak256(abi.encodePacked(taskId, msg.sender));
        bytes32 ethSignedMessage = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", message)
        );
        address recovered = _recoverSigner(ethSignedMessage, gatewaySignature);
        require(recovered == gateway, "AIMSSettlement: invalid PoT signature");

        claimedTasks[taskId] = true;

        uint256 workerAmount = pendingPayouts[msg.sender];
        require(workerAmount > 0, "AIMSSettlement: no pending payout for caller");

        // Reset before transfer to prevent re-entrancy
        pendingPayouts[msg.sender] = 0;

        // The owner's share was already credited in settleTask. We only
        // transfer the worker's portion here.
        usdc.safeTransfer(msg.sender, workerAmount);

        emit RewardClaimed(taskId, msg.sender, workerAmount, 0);
    }

    // ── Claim: Platform Owner ────────────────────────────────────────────────

    /// @notice Claim the accumulated 20 % platform fees.
    function claimOwnerFees() external {
        uint256 amount = pendingPayouts[msg.sender];
        require(amount > 0, "AIMSSettlement: no pending payout");
        require(msg.sender == platformOwner, "AIMSSettlement: only platform owner");
        pendingPayouts[msg.sender] = 0;
        usdc.safeTransfer(msg.sender, amount);
        emit OwnerFeesClaimed(msg.sender, amount);
    }

    // ── Admin ────────────────────────────────────────────────────────────────

    /// @notice Update the gateway oracle address (key rotation).
    function setGateway(address _newGateway) external onlyGateway {
        require(_newGateway != address(0), "AIMSSettlement: invalid address");
        gateway = _newGateway;
    }

    // ── Internal helpers ─────────────────────────────────────────────────────

    /// @notice Recover signer address from a hash and ECDSA signature.
    function _recoverSigner(
        bytes32 hash,
        bytes calldata signature
    ) internal pure returns (address) {
        require(signature.length == 65, "AIMSSettlement: invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        // solhint-disable-next-line no-inline-assembly
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 0x20))
            v := byte(0, calldataload(add(signature.offset, 0x40)))
        }
        // EIP-155: if v is 0 or 1, adjust to 27/28
        if (v < 27) {
            v += 27;
        }
        return ecrecover(hash, v, r, s);
    }
}
