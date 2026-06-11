<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-11 | Hermes-Verified -->

# Test Skill — Sandbox Echo

## Purpose
Pure sandbox skill for DePIN bandwidth smoke tests and settlement pipeline verification. Accepts any input and echoes it back.

## When to invoke
- Network connectivity tests between gateway and worker nodes
- Settlement pipeline verification (test the 70/25/5 flow without real work)
- Schema validation bypass — no output schema restrictions

## Output
Returns whatever was passed in `params`, wrapped in a standard envelope:
```json
{"status": "accepted", "echo": <params>}
```

## Notes
- No billing deduction for test_skill tasks
- Always passes output validation regardless of result content
- Settlement always returns `ACCEPTED` outcome
