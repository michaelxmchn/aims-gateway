#!/usr/bin/env node

const { copySkills } = require('./install');

console.log('Updating Claude Code skills...');
copySkills();
