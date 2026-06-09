<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-09 | Hermes-Verified -->

# Buggy Skill (Test-Only) — Operation Rules

## Purpose
**⚠️ TEST-ONLY SKILL — DO NOT USE IN PRODUCTION**

This skill exists solely to test the AIMS Cool-down Jail mechanism. It intentionally fails every time it is executed. Do not route real user requests to this skill.

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input` | string | **YES** | Any input (will be ignored — this skill always fails) |

## Output

This skill never produces valid output. It always throws a `RuntimeError`.

## Behavior
- **Always fails** with: `RuntimeError: Intentional failure for testing cooldown jail`
- Designed to accumulate consecutive failures in the registry
- After 3 consecutive failures, the skill is sent to Cool-down Jail (24h frozen)
- When frozen, `load_all()` filters it out and it will not be injected into any LLM context

## Testing Rules
- Use this skill ONLY for integration testing of the jail mechanism.
- Route 3 prompts to this skill → verify it gets jailed → verify 4th prompt does NOT include it.
- Do NOT set `staked_points` higher than necessary for testing (5.0 is sufficient).

## Notes for the AI Agent
- If you see this skill in the active list, it means the jail timer has expired.
- You should generally prefer other skills over this one.
