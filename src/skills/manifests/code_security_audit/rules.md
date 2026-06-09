<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-09 | Hermes-Verified -->

# Code Security Audit — Operation Rules

## Purpose
Analyze Solidity source code for common smart contract vulnerabilities and return a severity-ranked security audit report. Use this skill when the user needs a security review of Ethereum/Base smart contracts.

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_code` | string | **YES** | The full Solidity source code to audit |
| `contract_name` | string | no | Name of the primary contract (auto-detected if omitted) |

## Output Format

The skill returns a markdown-formatted audit report with these sections:

```markdown
# Security Audit Report: [Contract Name]

## Summary
- **Files analyzed**: 1
- **Total issues**: N (Critical: X, High: Y, Medium: Z, Low: W)

## Findings

### [CRITICAL] Title of Issue
- **Line**: 42
- **Severity**: CRITICAL
- **Description**: Detailed explanation of the vulnerability
- **Impact**: What an attacker could do
- **Recommendation**: How to fix it

## Gas Optimizations
- ...

## Conclusion
Overall risk assessment and recommendations.
```

## Analysis Rules

### 1. Vulnerability Categories to Detect

| Severity | Patterns |
|----------|----------|
| **CRITICAL** | Reentrancy (external calls in state-changing functions), Unchecked low-level calls, Selfdestruct usage, Arbitrary storage writes |
| **HIGH** | Access control issues (missing `onlyOwner`), Integer overflow/underflow (pre-0.8), Oracle manipulation, Flash loan attacks |
| **MEDIUM** | Timestamp dependency, Gas griefing, Unhandled return values, Deprecated keywords (tx.origin) |
| **LOW** | Unused variables, Missing events, Naming conventions, Solidity version pragma too wide |

### 2. False Positive Rules
- Do NOT flag `require()` or `revert()` as "unchecked errors" — they are intentional.
- Do NOT flag OpenZeppelin's `ReentrancyGuard`-protected functions as reentrant.
- Do NOT flag `block.timestamp` in year-2038 context as a bug.

### 3. Severity Assignment
- **CRITICAL**: Direct loss of funds, contract destruction, or permanent lock of assets.
- **HIGH**: Significant fund loss under specific conditions, broken access control.
- **MEDIUM**: Unexpected behavior that could lead to limited fund loss or DoS.
- **LOW**: Best practice violations, code quality issues, gas inefficiencies.

### 4. Output Constraints
- Every finding MUST include a line number range or specific code reference.
- Every finding MUST include a concrete recommendation (not just "fix this").
- If the source code does not compile, note this in the Summary but still perform analysis on the available code.
- Use severity labels exactly as shown (CRITICAL/HIGH/MEDIUM/LOW).

## Notes for the AI Agent
- Focus on the most dangerous vulnerabilities first (reentrancy, access control).
- Provide specific code snippets in recommendations — show the fix, not just describe it.
- When presenting results, highlight the CRITICAL and HIGH findings in the summary.
