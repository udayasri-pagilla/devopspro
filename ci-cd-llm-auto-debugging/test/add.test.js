import assert from 'assert';
import test from 'node:test';
import { add } from '../src/add.js';

test('adds two numbers', () => {
  assert.strictEqual(add(1, 2), 3);
});

test('works with negatives', () => {
  assert.strictEqual(add(-1, -2), -3);
});
