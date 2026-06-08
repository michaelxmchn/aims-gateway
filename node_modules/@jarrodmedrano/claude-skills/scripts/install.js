#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

/**
 * Post-install script that copies Claude Code skills to the project's .claude directory
 */

function copySkills() {
  // Find the project root (where package.json is, going up from node_modules)
  let projectRoot = process.cwd();

  // If we're in node_modules, go up to find the project root
  if (projectRoot.includes('node_modules')) {
    const parts = projectRoot.split(path.sep);
    const nodeModulesIndex = parts.lastIndexOf('node_modules');
    projectRoot = parts.slice(0, nodeModulesIndex).join(path.sep);
  }

  // Determine package location (either in node_modules or current directory)
  let packageRoot;
  if (projectRoot.includes('node_modules')) {
    // During install, cwd might be the package itself in node_modules
    packageRoot = process.cwd();
  } else {
    // Try to find the package in node_modules
    const possiblePackagePath = path.join(projectRoot, 'node_modules', 'jarrod-claude-skills');
    if (fs.existsSync(possiblePackagePath)) {
      packageRoot = possiblePackagePath;
    } else {
      // Fallback: assume we're running from the package directory itself
      packageRoot = __dirname.includes('node_modules')
        ? path.join(__dirname, '..')
        : path.join(__dirname, '..');
    }
  }

  const skillsTargetDir = path.join(projectRoot, '.claude', 'skills');
  const commandsTargetDir = path.join(projectRoot, '.claude', 'commands');
  const agentsTargetDir = path.join(projectRoot, '.claude', 'agents');
  const skillsSourceDir = path.join(packageRoot, '.claude', 'skills');
  const commandsSourceDir = path.join(packageRoot, '.claude', 'commands');
  const agentsSourceDir = path.join(packageRoot, '.claude', 'agents');

  // Create .claude directories if they don't exist
  if (!fs.existsSync(skillsTargetDir)) {
    fs.mkdirSync(skillsTargetDir, { recursive: true });
    console.log('✓ Created .claude/skills directory');
  }

  if (!fs.existsSync(commandsTargetDir)) {
    fs.mkdirSync(commandsTargetDir, { recursive: true });
    console.log('✓ Created .claude/commands directory');
  }

  if (!fs.existsSync(agentsTargetDir)) {
    fs.mkdirSync(agentsTargetDir, { recursive: true });
    console.log('✓ Created .claude/agents directory');
  }

  // Copy skills, commands, and agents
  try {
    if (fs.existsSync(skillsSourceDir)) {
      copyRecursive(skillsSourceDir, skillsTargetDir);
      console.log(`✓ Skills copied to ${skillsTargetDir}`);
    }

    if (fs.existsSync(commandsSourceDir)) {
      copyRecursive(commandsSourceDir, commandsTargetDir);
      console.log(`✓ Commands copied to ${commandsTargetDir}`);
    }

    if (fs.existsSync(agentsSourceDir)) {
      copyRecursive(agentsSourceDir, agentsTargetDir);
      console.log(`✓ Agents copied to ${agentsTargetDir}`);
    }

    console.log('\n✓ Claude Code skills installed successfully!');
    console.log('\nAvailable skills:');
    console.log('  /new-website    - Create frontend projects');
    console.log('  /new-backend    - Create backend APIs');
    console.log('  /new-fullstack  - Create full-stack apps');
    console.log('  /project-setup  - Initialize any project');
    console.log('\nAvailable commands:');
    console.log('  /code-review    - Code review workflows');
    console.log('  /design-review  - Design review workflows');
    console.log('  /security-review - Security review workflows');
    console.log('\nAvailable agents:');
    console.log('  design-review        - Design review subagent');
    console.log('  pragmatic-code-review - Code review subagent');
    console.log('\nTo update later, run: npm run update-skills');
  } catch (error) {
    console.error('Error copying skills:', error.message);
    console.error('Package root:', packageRoot);
    console.error('Project root:', projectRoot);
    process.exit(1);
  }
}

function copyRecursive(src, dest) {
  const exists = fs.existsSync(src);
  const stats = exists && fs.statSync(src);
  const isDirectory = exists && stats.isDirectory();

  if (isDirectory) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    fs.readdirSync(src).forEach(childItem => {
      copyRecursive(
        path.join(src, childItem),
        path.join(dest, childItem)
      );
    });
  } else {
    fs.copyFileSync(src, dest);
  }
}

// Only run if this is being executed directly (not required as a module)
if (require.main === module) {
  copySkills();
}

module.exports = { copySkills };
