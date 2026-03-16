'use strict';

const readlineSync = require('readline-sync');
const { questions } = require('./questions');

/**
 * Asks a boolean question via CLI.
 * @param {string} prompt - The question prompt.
 * @returns {boolean}
 */
function askBoolean(prompt) {
  const answer = readlineSync.keyInYNStrict(prompt);
  return answer;
}

/**
 * Asks a multiple-choice question via CLI.
 * @param {string} prompt - The question prompt.
 * @param {string[]} choices - Available choices.
 * @returns {string} Selected choice text.
 */
function askChoice(prompt, choices) {
  console.log(`\n${prompt}`);
  const index = readlineSync.keyInSelect(choices, 'Choose one:', {
    cancel: false,
  });
  return choices[index];
}

/**
 * Asks a text question via CLI.
 * @param {string} prompt - The question prompt.
 * @param {boolean} required - Whether a non-empty answer is required.
 * @param {string} [placeholder] - Hint shown alongside the prompt.
 * @returns {string}
 */
function askText(prompt, required, placeholder) {
  const hint = placeholder ? ` (e.g. ${placeholder})` : '';
  let answer = '';
  do {
    answer = readlineSync.question(`\n${prompt}${hint}\n> `);
    if (required && !answer.trim()) {
      console.log('  This field is required. Please enter a value.');
    }
  } while (required && !answer.trim());
  return answer.trim();
}

/**
 * Runs the interactive questionnaire and returns a map of answers.
 * @returns {Object} Answers keyed by question id.
 */
function runQuestionnaire() {
  console.log('\n========================================');
  console.log('  AI Model Configuration Generator');
  console.log('  for Open Web UI');
  console.log('========================================\n');
  console.log(
    'Answer the following questions to generate a Markdown configuration\n' +
    'file that can be imported into Open Web UI as a system prompt.\n'
  );

  const answers = {};

  for (const question of questions) {
    switch (question.type) {
      case 'boolean':
        answers[question.id] = askBoolean(`\n${question.prompt}`);
        break;
      case 'choice':
        answers[question.id] = askChoice(question.prompt, question.choices);
        break;
      case 'text':
      default:
        answers[question.id] = askText(
          question.prompt,
          question.required,
          question.placeholder
        );
        break;
    }
  }

  return answers;
}

module.exports = { runQuestionnaire, askBoolean, askChoice, askText };
