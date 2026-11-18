import test from 'node:test';
import assert from 'node:assert/strict';
import {
  findActiveSentenceIndex,
  formatClock,
  formatTimestamp,
  isSupportedYouTubeUrl,
} from './transcript';

test('formatTimestamp formats mm:ss.t accurately', () => {
  assert.equal(formatTimestamp(0), '00:00.0');
  assert.equal(formatTimestamp(5.42), '00:05.4');
  assert.equal(formatTimestamp(65.9), '01:05.9');
  assert.equal(formatTimestamp(-3), '00:00.0');
});

test('formatClock formats mm:ss accurately', () => {
  assert.equal(formatClock(0), '00:00');
  assert.equal(formatClock(75.8), '01:15');
});

test('findActiveSentenceIndex matches active time ranges', () => {
  const sentences = [
    { id: 'seg_0001', start: 0.5, end: 2.1, text: 'Hello world' },
    { id: 'seg_0002', start: 3.0, end: 5.2, text: 'How are you' },
  ];
  assert.equal(findActiveSentenceIndex(sentences, 0.1), -1);
  assert.equal(findActiveSentenceIndex(sentences, 1.2), 0);
  assert.equal(findActiveSentenceIndex(sentences, 4.5), 1);
  assert.equal(findActiveSentenceIndex(sentences, 7.0), -1);
});

test('isSupportedYouTubeUrl validates YouTube hosts and rejects invalid URLs', () => {
  assert.equal(isSupportedYouTubeUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), true);
  assert.equal(isSupportedYouTubeUrl('https://youtu.be/dQw4w9WgXcQ'), true);
  assert.equal(isSupportedYouTubeUrl('https://vimeo.com/123456'), false);
  assert.equal(isSupportedYouTubeUrl('not a url'), false);
});
