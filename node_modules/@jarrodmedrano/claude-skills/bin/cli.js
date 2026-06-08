#!/usr/bin/env node

const { copySkills } = require('../scripts/install');

const args = process.argv.slice(2);
const command = args[0];

switch (command) {
  case 'install':
    console.log('Installing Claude Code skills...');
    copySkills();
    break;

  case 'update':
    console.log('Updating Claude Code skills...');
    copySkills();
    break;

  case 'list':
    console.log('Available Claude Code Skills:\n');
    console.log('Web Development:');
    console.log('  /new-website    - Create frontend projects (React, Next.js, Vue, Vanilla)');
    console.log('  /new-backend    - Create backend APIs (Express, Fastify, NestJS, Hono)');
    console.log('  /new-fullstack  - Create full-stack apps (Next.js, T3, MERN, Monorepo)');
    console.log('  /project-setup  - Initialize any project with tooling\n');
    console.log('Code Quality:');
    console.log('  /code-review    - Code review workflows');
    console.log('  /design-review  - Design review workflows');
    console.log('  /security-review - Security review workflows\n');
    break;

  case 'help':
  default:
    console.log('Claude Code Skills CLI\n');
    console.log('Usage: claude-skills <command>\n');
    console.log('Commands:');
    console.log('  install  - Install skills to current project');
    console.log('  update   - Update skills to latest version');
    console.log('  list     - List all available skills');
    console.log('  help     - Show this help message\n');
    console.log('After installation, use skills in Claude Code:');
    console.log('  Example: /new-website my-app');
    break;
}
