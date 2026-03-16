'use strict';

/**
 * Feedback questions used to configure an AI model chat for Open Web UI.
 * Each question has an id, prompt text, type, and optional choices.
 */
const questions = [
  {
    id: 'modelName',
    prompt: 'What is the name of this AI model configuration?',
    type: 'text',
    required: true,
    placeholder: 'e.g. Customer Support Agent',
  },
  {
    id: 'modelDescription',
    prompt: 'Describe the purpose of this AI model in one sentence.',
    type: 'text',
    required: true,
    placeholder: 'e.g. Helps customers resolve billing and account issues.',
  },
  {
    id: 'primaryUseCase',
    prompt: 'What is the primary use case?',
    type: 'choice',
    required: true,
    choices: [
      'General assistant',
      'Coding / development',
      'Writing / editing',
      'Data analysis',
      'Customer support',
      'Research',
      'Education / tutoring',
      'Creative / storytelling',
      'Other',
    ],
  },
  {
    id: 'tone',
    prompt: 'What tone should the AI use?',
    type: 'choice',
    required: true,
    choices: [
      'Professional',
      'Friendly and casual',
      'Technical and precise',
      'Empathetic and supportive',
      'Concise and direct',
    ],
  },
  {
    id: 'language',
    prompt: 'What language should the AI primarily respond in?',
    type: 'text',
    required: true,
    placeholder: 'e.g. English',
  },
  {
    id: 'expertiseAreas',
    prompt:
      'List specific expertise areas or topics (comma-separated, leave blank if none).',
    type: 'text',
    required: false,
    placeholder: 'e.g. Python, REST APIs, cloud infrastructure',
  },
  {
    id: 'constraints',
    prompt:
      'List any constraints or topics the AI should avoid (comma-separated, leave blank if none).',
    type: 'text',
    required: false,
    placeholder: 'e.g. political opinions, personal medical advice',
  },
  {
    id: 'askClarifyingQuestions',
    prompt: 'Should the AI ask clarifying questions when a request is ambiguous?',
    type: 'boolean',
    required: true,
  },
  {
    id: 'responseFormat',
    prompt: 'Preferred response format for detailed answers?',
    type: 'choice',
    required: true,
    choices: [
      'Prose paragraphs',
      'Bullet points',
      'Numbered lists',
      'Markdown with headers',
      'Code blocks where applicable',
    ],
  },
  {
    id: 'additionalInstructions',
    prompt:
      'Any additional instructions or personality traits? (leave blank if none)',
    type: 'text',
    required: false,
    placeholder:
      'e.g. Always cite sources, use analogies when explaining complex topics.',
  },
];

module.exports = { questions };
