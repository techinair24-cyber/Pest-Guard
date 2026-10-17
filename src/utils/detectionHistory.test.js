import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getDetectionDisplayStatus,
  isLatestDetectionCandidate,
  isNewerDetection,
  isAfterHistoryClear,
  mergeDetections,
  selectNewerDetection,
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

test('an older delayed REST response cannot replace a newer live detection', () => {
  const liveDetection = {
    id: 12,
    detected_at: '2025-01-01T12:01:00Z',
  }

  assert.equal(
    isNewerDetection(
      { id: 11, detected_at: '2025-01-01T12:00:00Z' },
      liveDetection,
    ),
    false,
  )
  assert.equal(
    isNewerDetection(
      { id: 13, detected_at: '2025-01-01T12:02:00Z' },
      liveDetection,
    ),
    true,
  )
  assert.equal(isNewerDetection(null, liveDetection), false)
})

test('a newer WebSocket detection replaces an older detection, but not vice versa', () => {
  const older = {
    id: 11,
    detected_at: '2025-01-01T12:00:00Z',
  }
  const newer = {
    id: 12,
    detected_at: '2025-01-01T12:01:00Z',
  }

  assert.equal(selectNewerDetection(older, newer), newer)
  assert.equal(selectNewerDetection(newer, older), newer)
})

test('latest detection selection includes unidentified results for the same device', () => {
  const unknown = {
    device_id: 'FIELD-UNIT-01',
    status: 'UNKNOWN',
    pest: null,
    confidence: 0.632,
    detected_at: '2025-01-01T12:00:00Z',
  }

  assert.equal(
    isLatestDetectionCandidate(
      unknown,
      'FIELD-UNIT-01',
      Date.parse('2025-01-01T12:00:05Z'),
    ),
    true,
  )
  assert.equal(
    isLatestDetectionCandidate(
      unknown,
      'FIELD-UNIT-02',
      Date.parse('2025-01-01T12:00:05Z'),
    ),
    false,
  )
})

test('classification display distinguishes confirmed, uncertain, non-pest, and inference error', () => {
  assert.equal(
    getDetectionDisplayStatus({
      pest: 'Acheta domesticus',
      identification_status: 'CONFIRMED',
    }),
    'Confirmed pest identification',
  )
  assert.equal(
    getDetectionDisplayStatus({
      pest: 'Acheta domesticus',
      identification_status: 'UNCONFIRMED',
    }),
    'Possible match - not confirmed',
  )
  assert.equal(
    getDetectionDisplayStatus({ status: 'UNKNOWN', pest: null }),
    'Rejected or uncertain classification',
  )
  assert.equal(
    getDetectionDisplayStatus({ status: 'NON_PEST' }),
    'Non-pest sound',
  )
  assert.equal(
    getDetectionDisplayStatus({ message: 'INFERENCE_ERROR: AI API HTTP 500' }),
    'Inference error',
  )
})
