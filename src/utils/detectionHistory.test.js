import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isAfterHistoryClear,
  mergeDetections,
} from './detectionHistory.js'

test('clear cutoff hides old and equal-time detections but keeps newer events', () => {
  const cutoff = '2025-01-01T12:00:00.000Z'

  assert.equal(
    isAfterHistoryClear(
      { detected_at: '2025-01-01T11:59:59.999Z' },
      cutoff,
    ),
    false,
  )
  assert.equal(
    isAfterHistoryClear(
      { detected_at: cutoff },
      cutoff,
    ),
    false,
  )
  assert.equal(
    isAfterHistoryClear(
      { detected_at: '2025-01-01T12:00:00.001Z' },
      cutoff,
    ),
    true,
  )
  assert.equal(
    isAfterHistoryClear(
      { detected_at: '2025-01-01T11:00:00Z' },
      '',
    ),
    true,
  )
})

test('history merges a saved event and its live WebSocket copy only once', () => {
  const liveEvent = {
    id: 7,
    device_id: 'FIELD-UNIT-01',
    detected_at: '2025-01-01T12:00:00Z',
  }
  const olderEvent = {
    id: 6,
    device_id: 'FIELD-UNIT-01',
    detected_at: '2025-01-01T11:59:00Z',
  }
  const merged = mergeDetections(
    [liveEvent],
    [{ ...liveEvent }, olderEvent],
  )

  assert.equal(merged.length, 2)
  assert.deepEqual(
    merged.map((item) => item.id),
    [7, 6],
  )
})
