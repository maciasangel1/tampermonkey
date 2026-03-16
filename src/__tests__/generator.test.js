'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { generateMarkdown, writeConfigFile, toFileName, toBulletList } = require('../generator');

const sampleAnswers = {
  modelName: 'Customer Support Agent',
  modelDescription: 'Helps customers resolve billing and account issues.',
  primaryUseCase: 'Customer support',
  tone: 'Friendly and casual',
  language: 'English',
  expertiseAreas: 'billing, account management, refunds',
  constraints: 'political opinions, medical advice',
  askClarifyingQuestions: true,
  responseFormat: 'Bullet points',
  additionalInstructions: 'Always greet the user warmly.',
};

describe('toFileName', () => {
  test('converts spaces to hyphens and lowercases', () => {
    expect(toFileName('Customer Support Agent')).toBe('customer-support-agent');
  });

  test('removes leading and trailing hyphens', () => {
    expect(toFileName('  My Model  ')).toBe('my-model');
  });

  test('replaces special characters with hyphens', () => {
    expect(toFileName('Model #1 / Test!')).toBe('model-1-test');
  });

  test('handles already lowercase names', () => {
    expect(toFileName('coding-assistant')).toBe('coding-assistant');
  });
});

describe('toBulletList', () => {
  test('converts comma-separated string to bullet list', () => {
    const result = toBulletList('Python, REST APIs, cloud infrastructure');
    expect(result).toBe('- Python\n- REST APIs\n- cloud infrastructure');
  });

  test('returns empty string for blank input', () => {
    expect(toBulletList('')).toBe('');
    expect(toBulletList('   ')).toBe('');
    expect(toBulletList(null)).toBe('');
    expect(toBulletList(undefined)).toBe('');
  });

  test('trims whitespace from each item', () => {
    const result = toBulletList('  a  ,  b  ,  c  ');
    expect(result).toBe('- a\n- b\n- c');
  });

  test('filters out empty items', () => {
    const result = toBulletList('a,,b');
    expect(result).toBe('- a\n- b');
  });
});

describe('generateMarkdown', () => {
  let markdown;

  beforeAll(() => {
    markdown = generateMarkdown(sampleAnswers);
  });

  test('includes model name as H1 heading', () => {
    expect(markdown).toContain('# Customer Support Agent');
  });

  test('includes model description', () => {
    expect(markdown).toContain('Helps customers resolve billing and account issues.');
  });

  test('includes configuration table', () => {
    expect(markdown).toContain('| Primary Use Case | Customer support |');
    expect(markdown).toContain('| Tone | Friendly and casual |');
    expect(markdown).toContain('| Language | English |');
    expect(markdown).toContain('| Ask Clarifying Questions | Yes |');
    expect(markdown).toContain('| Response Format | Bullet points |');
  });

  test('includes expertise areas as bullet list', () => {
    expect(markdown).toContain('## Expertise Areas');
    expect(markdown).toContain('- billing');
    expect(markdown).toContain('- account management');
    expect(markdown).toContain('- refunds');
  });

  test('includes constraints as bullet list', () => {
    expect(markdown).toContain('## Constraints');
    expect(markdown).toContain('- political opinions');
    expect(markdown).toContain('- medical advice');
  });

  test('includes additional instructions', () => {
    expect(markdown).toContain('## Additional Instructions');
    expect(markdown).toContain('Always greet the user warmly.');
  });

  test('includes Open Web UI import instructions', () => {
    expect(markdown).toContain('## Open Web UI Import Instructions');
    expect(markdown).toContain('Open Web UI');
  });

  test('includes behaviour guidelines', () => {
    expect(markdown).toContain('## Behaviour Guidelines');
    expect(markdown).toContain('ask one focused clarifying question');
  });

  test('no clarifying questions when disabled', () => {
    const noClaryAnswers = { ...sampleAnswers, askClarifyingQuestions: false };
    const md = generateMarkdown(noClaryAnswers);
    expect(md).toContain('Do not ask clarifying questions');
    expect(md).toContain('| Ask Clarifying Questions | No |');
  });

  test('omits expertise section when blank', () => {
    const noExpertise = { ...sampleAnswers, expertiseAreas: '' };
    const md = generateMarkdown(noExpertise);
    expect(md).not.toContain('## Expertise Areas');
  });

  test('omits constraints section when blank', () => {
    const noConstraints = { ...sampleAnswers, constraints: '' };
    const md = generateMarkdown(noConstraints);
    expect(md).not.toContain('## Constraints');
  });

  test('omits additional instructions section when blank', () => {
    const noInstructions = { ...sampleAnswers, additionalInstructions: '' };
    const md = generateMarkdown(noInstructions);
    expect(md).not.toContain('## Additional Instructions');
  });
});

describe('writeConfigFile', () => {
  let tmpDir;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'md-gen-test-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  test('creates the output directory if it does not exist', () => {
    const subDir = path.join(tmpDir, 'nested', 'output');
    writeConfigFile(sampleAnswers, subDir);
    expect(fs.existsSync(subDir)).toBe(true);
  });

  test('creates a .md file with correct name', () => {
    const filePath = writeConfigFile(sampleAnswers, tmpDir);
    expect(path.basename(filePath)).toBe('customer-support-agent.md');
    expect(fs.existsSync(filePath)).toBe(true);
  });

  test('written file contains expected content', () => {
    const filePath = writeConfigFile(sampleAnswers, tmpDir);
    const content = fs.readFileSync(filePath, 'utf8');
    expect(content).toContain('# Customer Support Agent');
    expect(content).toContain('Open Web UI Import Instructions');
  });

  test('returns the absolute path of the created file', () => {
    const filePath = writeConfigFile(sampleAnswers, tmpDir);
    expect(path.isAbsolute(filePath)).toBe(true);
  });
});
