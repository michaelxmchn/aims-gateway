# Git Changelog Generator — Operation Rules

## Purpose
Generate a formatted changelog from a git repository's commit history between two refs (tags, branches, or commit hashes). Supports conventional commits parsing and multiple output formats.

## Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `repo_path` | string | **YES** | — | Absolute path to the git repository on disk |
| `from_ref` | string | **YES** | — | Starting git ref (tag, branch, or commit hash) |
| `to_ref` | string | no | HEAD | Ending git ref |
| `format` | string | no | "markdown" | Output format: `markdown` or `json` |

## Output Format

### Markdown format
```markdown
# Changelog (v1.0.0 → v1.1.0)

## Features
- feat(auth): add OAuth2 login flow (abc1234)
- feat(api): implement rate limiting (def5678)

## Bug Fixes
- fix(ui): correct button alignment on mobile (ghi9012)

## Maintenance
- chore(deps): update dependencies (jkl3456)
```

### JSON format
```json
{
  "from_ref": "v1.0.0",
  "to_ref": "v1.1.0",
  "total_commits": 12,
  "sections": {
    "Features": [...],
    "Bug Fixes": [...],
    "Maintenance": [...]
  }
}
```

## Operating Rules

### 1. Conventional Commit Parsing
Parse commit messages using the Conventional Commits spec:
- `feat(scope):` → "Features" section
- `fix(scope):` → "Bug Fixes" section
- `docs:`, `refactor:`, `test:`, `chore:`, `style:` → "Maintenance" section
- `BREAKING CHANGE:` or `!` after type → append ⚠️ icon and add to "Breaking Changes" section

### 2. Commit Grouping
- Group commits by type (not by scope).
- Within each section, sort by scope alphabetically, then chronologically.
- Merge consecutive same-scope commits into one bullet where appropriate.

### 3. Edge Cases
- If `from_ref` does not exist in the repo, return error: "Ref 'X' not found in repository."
- If `repo_path` is not a valid git repository, return error: "Not a git repository: X"
- If there are zero commits between the refs, return: "No changes between X and Y."
- Do NOT include merge commits (they clutter the changelog).

### 4. Output Constraints
- Markdown output MUST be valid GitHub-Flavored Markdown.
- JSON output MUST be valid JSON parseable by `json.loads()`.
- Each commit entry MUST include its abbreviated hash (first 7 characters).
- Lines in markdown output should not exceed 100 characters.

## Notes for the AI Agent
- This skill reads the local git repository — ensure the path is accessible.
- Large ranges (1000+ commits) may take time; consider warning the user.
- When presenting, highlight breaking changes first.
