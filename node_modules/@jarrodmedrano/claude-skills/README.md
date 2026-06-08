# Claude Code Skills

Reusable Claude Code skills for web development projects. This package provides a collection of powerful skills for scaffolding and managing projects with Claude Code.

## Installation

### Install as npm package (recommended)

In any project where you want to use these skills:

```bash
npm install @jarrodmedrano/claude-skills
```

The skills will automatically be copied to your project's `.claude/skills/` and `.claude/commands/` directories during installation.

**If the automatic installation doesn't work** (e.g., if you used `npm install --ignore-scripts`), you can manually install the skills:

```bash
npx claude-skills install
```

This will copy all skills and commands to the appropriate directories in your project.

### Use as local directory

Alternatively, you can use this directory directly as your Claude Code projects hub.

## Quick Start

Once installed, you can use custom skills to quickly scaffold new projects:

### Available Skills

#### `/new-website [project-name]`
Create a new frontend web project with your choice of:
- Next.js (App Router + TypeScript + Tailwind)
- React + Vite
- Vue 3 + Vite
- Vanilla JS/TS

**Example:**
```
/new-website my-portfolio
```

#### `/new-backend [project-name]`
Create a new backend/API project with:
- Express.js + TypeScript
- Fastify + TypeScript
- NestJS
- Hono

**Example:**
```
/new-backend my-api
```

#### `/new-fullstack [project-name]`
Create a full-stack application with:
- Next.js (with API routes)
- T3 Stack (Next.js + tRPC + Prisma)
- MERN Stack
- Monorepo (separate frontend/backend)
- **Solito** (Expo + Next.js - Universal app for web + mobile)

**Example:**
```
/new-fullstack my-saas-app
```

#### `/project-setup [project-name]`
Initialize any type of project with tooling:
- Libraries
- CLI tools
- Static sites
- Browser extensions
- Electron apps
- Component libraries

**Example:**
```
/project-setup my-tool
```

## Directory Structure

```
jarrod-claude/
├── .claude/
│   └── skills/          # Custom Claude Code skills
├── project-1/           # Your projects will be created here
├── project-2/
└── README.md           # This file
```

## Usage Tips

1. **Starting a new project**: Use one of the skills above
2. **Working on existing project**: Navigate to the project directory or specify the path
3. **Custom skills**: Add new skills in `.claude/skills/` as markdown files

## What Gets Created

When you use these skills, Claude will:
- Create the project directory
- Initialize with the chosen framework/stack
- Install dependencies
- Set up TypeScript configuration
- Create basic project structure
- Initialize git repository
- Generate README with getting started instructions

## Next Steps

1. Navigate to this directory in your terminal
2. Run `claude` to start Claude Code
3. Use `/new-website my-first-site` (or any skill) to create your first project
4. Claude will guide you through setup options

## Updating Skills

To get the latest skills after updating the package:

```bash
npm update @jarrodmedrano/claude-skills
npm run update-skills
```

Or use the CLI:

```bash
npx claude-skills update
```

## CLI Commands

The package includes a CLI for managing skills:

```bash
npx claude-skills install   # Install/reinstall skills
npx claude-skills update    # Update skills to latest
npx claude-skills list      # List all available skills
npx claude-skills help      # Show help
```

## Publishing Your Own Version

If you want to publish your own version of these skills:

1. Update the package name in [package.json](package.json):
   ```json
   {
     "name": "@yourusername/claude-skills"
   }
   ```

2. Publish to npm:
   ```bash
   npm login
   npm publish --access public
   ```

3. Others can install with:
   ```bash
   npm install @yourusername/claude-skills
   ```

## Development

To add new skills:

1. Create a `.md` file in [.claude/skills/](.claude/skills/) or a directory for complex skills
2. Follow the existing skill format
3. Update the version in [package.json](package.json)
4. Publish the new version

## Customization

You can modify the skills in [.claude/skills/](.claude/skills/) to match your preferred setup, add new frameworks, or change default configurations.

## Requirements

- Node.js (v18+ recommended)
- npm or pnpm
- Git
- Claude Code CLI

## License

MIT

---

Happy coding!
