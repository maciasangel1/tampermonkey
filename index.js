#!/usr/bin/env node
'use strict';

const path = require('path');
const { runQuestionnaire } = require('./src/prompt');
const { writeConfigFile } = require('./src/generator');

const OUTPUT_DIR = path.join(process.cwd(), 'output');

function main() {
  try {
    const answers = runQuestionnaire();

    console.log('\nGenerating configuration file...\n');

    const filePath = writeConfigFile(answers, OUTPUT_DIR);

    console.log(`✅  Configuration file created successfully:`);
    console.log(`   ${filePath}`);
    console.log(
      '\nImport this file into Open Web UI by copying the System Prompt\n' +
      'section into the model system prompt field.\n'
    );
  } catch (err) {
    console.error('Error generating configuration:', err.message);
    process.exit(1);
  }
}

main();
