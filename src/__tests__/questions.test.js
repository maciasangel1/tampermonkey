'use strict';

const { questions } = require('../questions');

describe('questions', () => {
  test('questions is a non-empty array', () => {
    expect(Array.isArray(questions)).toBe(true);
    expect(questions.length).toBeGreaterThan(0);
  });

  test('every question has id, prompt, type, and required fields', () => {
    for (const q of questions) {
      expect(typeof q.id).toBe('string');
      expect(q.id.length).toBeGreaterThan(0);
      expect(typeof q.prompt).toBe('string');
      expect(q.prompt.length).toBeGreaterThan(0);
      expect(['text', 'boolean', 'choice']).toContain(q.type);
      expect(typeof q.required).toBe('boolean');
    }
  });

  test('choice questions have a non-empty choices array', () => {
    const choiceQuestions = questions.filter((q) => q.type === 'choice');
    expect(choiceQuestions.length).toBeGreaterThan(0);
    for (const q of choiceQuestions) {
      expect(Array.isArray(q.choices)).toBe(true);
      expect(q.choices.length).toBeGreaterThan(0);
    }
  });

  test('all question ids are unique', () => {
    const ids = questions.map((q) => q.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  test('required questions include modelName and modelDescription', () => {
    const requiredIds = questions.filter((q) => q.required).map((q) => q.id);
    expect(requiredIds).toContain('modelName');
    expect(requiredIds).toContain('modelDescription');
  });
});
