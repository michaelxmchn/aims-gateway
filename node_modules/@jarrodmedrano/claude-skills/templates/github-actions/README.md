# GitHub Actions Templates

This directory contains GitHub Actions workflow templates for automating Claude Code reviews in your CI/CD pipeline.

## Available Templates

### Code Review Workflows

- **`claude-code-review.yml`** - Basic Claude Code review workflow
- **`claude-code-review-custom.yml`** - Customizable Claude Code review workflow with advanced options

### Security Review Workflow

- **`security.yml`** - Automated security review workflow

## Usage

To use these templates in your project:

1. Copy the desired `.yml` file to your repository's `.github/workflows/` directory:
   ```bash
   cp templates/github-actions/claude-code-review.yml .github/workflows/
   ```

2. Set up required secrets in your GitHub repository settings:
   - `CLAUDE_CODE_OAUTH_TOKEN` or `CLAUDE_API_KEY`

3. Customize the workflow as needed for your project

4. The workflow will automatically run on pull requests

## Documentation

For more information about setting up Claude Code in GitHub Actions, see:
- [Code Review Documentation](../../.claude/commands/code-review/README.md)
- [Security Review Documentation](../../.claude/commands/security-review/README.md)
