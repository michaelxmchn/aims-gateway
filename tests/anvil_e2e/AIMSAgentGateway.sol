// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AIMS Agent Gateway — E2E Anvil Edition
/// @notice Simplified native-ETH settlement contract with worker-signed PoT.
///
/// **Worker-signed Proof-of-Task**: The worker ECDSA-signs `keccak256(taskId)`
/// with their own key.  `settleTask` verifies this via `ecrecover`.
///
/// **70/25/5 split**: Developer / Worker / Treasury (gateway owner).
///
/// **Reentrancy**: Custom nonReentrant guard using a state variable.
/// Checks-effects-interactions pattern strictly followed.
contract AIMSAgentGateway {
    // ── State ───────────────────────────────────────────────────────────
    address public gatewayOwner;

    mapping(address => uint256) public availableBalance;

    uint256 private _status;
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED    = 2;

    // ── Constants ───────────────────────────────────────────────────────
    uint256 public constant TASK_COST      = 0.05 ether;
    uint256 public constant DEVELOPER_BPS  = 7_000;
    uint256 public constant WORKER_BPS     = 2_500;
    uint256 public constant TREASURY_BPS   = 500;
    uint256 public constant BPS_DENOM      = 10_000;

    // ── Events ──────────────────────────────────────────────────────────
    event DepositSuccess(address indexed user, uint256 amount);
    event TaskSettled(
        bytes32 indexed taskId,
        address indexed consumer,
        address indexed worker,
        address developer,
        uint256 taskCost,
        uint256 developerShare,
        uint256 workerShare,
        uint256 treasuryShare
    );

    // ── Modifiers ───────────────────────────────────────────────────────
    modifier onlyGateway() {
        require(msg.sender == gatewayOwner, "AIMSAgentGateway: only gateway");
        _;
    }

    modifier nonReentrant() {
        require(_status != _ENTERED, "AIMSAgentGateway: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }

    // ── Constructor ─────────────────────────────────────────────────────
    constructor() {
        gatewayOwner = msg.sender;
        _status = _NOT_ENTERED;
    }

    // ── Deposit ─────────────────────────────────────────────────────────
    /// @notice Deposit ETH into the caller's programmatic balance.
    function deposit() external payable {
        require(msg.value > 0, "AIMSAgentGateway: zero deposit");
        availableBalance[msg.sender] += msg.value;
        emit DepositSuccess(msg.sender, msg.value);
    }

    // ── Settlement ──────────────────────────────────────────────────────
    /// @notice Settle a completed task.
    ///
    /// 1. Verifies the worker-signed PoT via `ecrecover`.
    /// 2. Deducts `TASK_COST` from the consumer's balance.
    /// 3. Splits 70 % / 25 % / 5 % to developer, worker, treasury.
    ///
    /// @param taskId       Unique task identifier (bytes32).
    /// @param potSignature Worker's ECDSA signature over `keccak256(taskId)`
    ///                     (65 bytes: r 32 + s 32 + v 1).
    /// @param developer    Recipient of the 70 % developer share.
    /// @param worker       Recipient of the 25 % worker share (and PoT signer).
    /// @param consumer     The user whose balance is debited.
    function settleTask(
        bytes32 taskId,
        bytes calldata potSignature,
        address developer,
        address worker,
        address consumer
    ) external onlyGateway nonReentrant {
        // ── Verify worker-signed PoT ────────────────────────────────────
        bytes32 messageHash = keccak256(abi.encodePacked(taskId));
        address signer = _recoverSigner(messageHash, potSignature);
        require(signer == worker, "AIMSAgentGateway: invalid PoT signature");

        // ── Check consumer balance ────────────────────────────────────
        uint256 balance = availableBalance[consumer];
        require(balance >= TASK_COST, "AIMSAgentGateway: insufficient balance");

        // ── Effects: deduct from consumer ─────────────────────────────
        availableBalance[consumer] = balance - TASK_COST;

        // ── Calculate splits ──────────────────────────────────────────
        uint256 devShare      = (TASK_COST * DEVELOPER_BPS) / BPS_DENOM;
        uint256 workerShare   = (TASK_COST * WORKER_BPS)   / BPS_DENOM;
        uint256 treasuryShare = TASK_COST - devShare - workerShare;

        // ── Interactions: transfer (CEI pattern) ──────────────────────
        (bool devOk, ) = payable(developer).call{value: devShare}("");
        require(devOk, "AIMSAgentGateway: developer transfer failed");

        (bool workerOk, ) = payable(worker).call{value: workerShare}("");
        require(workerOk, "AIMSAgentGateway: worker transfer failed");

        (bool treasuryOk, ) = payable(gatewayOwner).call{value: treasuryShare}("");
        require(treasuryOk, "AIMSAgentGateway: treasury transfer failed");

        emit TaskSettled(
            taskId, consumer, worker, developer,
            TASK_COST, devShare, workerShare, treasuryShare
        );
    }

    // ── ECDSA recovery ──────────────────────────────────────────────────
    /// @notice Recover the signer address from a 65-byte ECDSA signature.
    /// @param hash      The keccak256 hash that was signed.
    /// @param signature 65 bytes: r (32) + s (32) + v (1).
    /// @return signer   The address that signed `hash`.
    function _recoverSigner(
        bytes32 hash,
        bytes calldata signature
    ) internal pure returns (address) {
        require(signature.length == 65, "AIMSAgentGateway: invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 0x20))
            v := byte(0, calldataload(add(signature.offset, 0x40)))
        }
        return ecrecover(hash, v, r, s);
    }

    // ── View ────────────────────────────────────────────────────────────
    /// @notice Convenience view to read a user's deposit balance.
    function getBalance(address user) external view returns (uint256) {
        return availableBalance[user];
    }
}
