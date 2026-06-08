# Repository Guidelines

<!-- ADS:FILL AGENTS.md is the cross-vendor contributor guide (Claude, Codex, and others read it). Keep it in English by convention. It overlaps CLAUDE.md on purpose — this is the canonical version for non-Claude agents. -->

## Authority & Required Reading
Rules in `.project.agents/CLAUDE.md` apply to every agent working here. Direct user instructions still take precedence.

The canonical contributor guide is `.project.agents/AGENTS.md`. Do not create or maintain a root-level `AGENTS.md` unless the user explicitly asks for one.

Before any code-changing task, read `.project.agents/SELF_CONSTRAINTS.md` and `.project.agents/VIBECODING_GUIDE.md`, then run `git status --short`. For product work, also read the relevant sections of `PRD.md`, `ARCHITECTURE.md`, `ROADMAP.md`, and `CONVENTIONS.md` under `.project.agents/docs/context/`.

## Project Structure & Module Organization
<!-- ADS:FILL One paragraph: what the project is, where source/tests/assets live. -->
`AIMS` is a Decentralized AI Skill Network (Agent Protocol) built with Solidity (Base L2), TypeScript, Append-only Log, DAG Execution Engine. Source is in `src`; tests in `tests`.

Target architecture is documented in `ARCHITECTURE.md`: {{MODULE_LIST_ONE_LINE}}.

## Source-of-Truth Rules
`PRD.md` defines behavior and scope.
`UIUX.md` defines visual and interaction rules.
`ARCHITECTURE.md` is the authority for modules, dependencies, contracts, and directory layout. Derived documents (implementation spec, asset checklist) follow upstream changes, not the other way around.

Feature changes must update `PRD.md`. Module, dependency, entity, or invariant changes must update `ARCHITECTURE.md` in the same commit. Do not let code and architecture drift for more than 24 hours.

## Build, Test, and Development Commands

```sh
# Build
forge build

# Test
forge test
```

<!-- ADS:FILL Note any environment requirement that makes these commands fail (toolchain version, selected SDK, env vars). -->

## Architecture & Coding Style
<!-- ADS:FILL Language conventions, indentation, naming summary. -->
Use {{LANGUAGE_CONVENTIONS}}, {{INDENTATION}}. {{NAMING_SUMMARY}}. Name files after their primary type/unit.

Do not add modules that are not registered in `ARCHITECTURE.md`. Preserve the dependency DAG; no reverse dependencies, no cross-feature imports, and no direct access to another module's private implementation. Avoid empty names such as `Manager`, `Helper`, `Util`, or `Common`.

UI/presentation code should consume state and send intents only — put business logic in services/use cases, and keep data-model types thin. {{LAYERING_RULE}}

## Testing Guidelines
<!-- ADS:FILL Preferred framework + which modules MUST have tests + what requires real-environment validation. -->
Use {{TEST_FRAMEWORK}}. Required coverage areas from `ARCHITECTURE.md`: {{REQUIRED_TEST_MODULES}}. Test filenames should mirror the unit under test.

{{REAL_ENV_VALIDATION}} require real-environment validation; mock/simulator-only evidence is not enough for those claims.

## Git, Logs, and PRs
Do not pile new work onto unrelated dirty changes without calling it out. Prefer Conventional Commits such as `feat: ...`, `fix: ...`, `docs: ...`.

Each independently verifiable feature, milestone, non-trivial fix, or refactor needs an execution log in `.project.agents/log/YYYY-MM-DD-<slug>.md` unless it is only a minor documentation edit. Logs must include what changed, relevant commits (or "uncommitted" with reason), verification performed, and next steps.

Pull requests should include scope, linked issues, screenshots for UI changes, environment/device coverage, and any documentation updates.

## Security & Configuration
Do not commit secrets, credentials, build output, or personal IDE files. Agent configuration and generated agent notes belong under `.project.agents/`, not the repository root, `.claude/`, or a global home directory.
