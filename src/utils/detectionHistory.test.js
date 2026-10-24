import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getDetectionDisplayStatus,
  filterDetectionHistory,
  getDetectionHistoryKey,
  isLatestDetectionCandidate,
  isNewerDetection,
  isAfterHistoryClear,
  mergeDetections,
  selectNewerDetection,
} from './detectionHistory.js'
import {
  getDetectionInsectGroup,
  getTopSpeciesPredictions,
} from './insectPredictions.js'

test('history preserves distinct classifications recorded at the same time', () => {
  const grasshopper = {
    device_id: 'FIELD-UNIT-01',
    status: 'UNKNOWN',
    pest: 'Chorthippus mollis',
    insect_group: 'Grasshopper',
    confidence: 0.341,
    top_predictions: [{ pest: 'Chorthippus mollis', score: 0.341 }],
    detected_at: '2025-01-01T12:00:00Z',
  }
  const cicada = {
    device_id: 'FIELD-UNIT-01',
    status: 'UNKNOWN',
    pest: 'Cicada species',
    insect_group: 'Cicada',
    confidence: 0.23,
    top_predictions: [{ pest: 'Cicada species', score: 0.23 }],
    detected_at: '2025-01-01T12:00:00Z',
  }

  const history = mergeDetections([grasshopper], [cicada])

  assert.equal(history.length, 2)
  assert.notEqual(getDetectionHistoryKey(grasshopper), getDetectionHistoryKey(cicada))
  assert.deepEqual(
    history.map((record) => [
      getDetectionInsectGroup(record),
      record.pest,
      getTopSpeciesPredictions(record.top_predictions)[0].pest,
      record.detected_at,
    ]),
    [
      ['Grasshopper', 'Chorthippus mollis', 'Chorthippus mollis', '2025-01-01T12:00:00Z'],
      ['Cicada', 'Cicada species', 'Cicada species', '2025-01-01T12:00:00Z'],
    ],
  )
})

test('history category filters use each record’s stored classification status', () => {
  const records = [
    { id: 1, status: 'HARMFUL_PEST', pest: 'Pest A', insect_group: 'Beetle' },
    { id: 2, status: 'NON_PEST', pest: null, insect_group: 'Unknown insect group' },
    { id: 3, status: 'UNKNOWN', pest: 'Possible pest', insect_group: 'Cricket' },
  ]

  assert.deepEqual(
    filterDetectionHistory(records, 'HARMFUL_PEST').map(({ id }) => id),
    [1],
  )
  assert.deepEqual(
    filterDetectionHistory(records, 'NON_PEST').map(({ id }) => id),
    [2],
  )
  assert.deepEqual(filterDetectionHistory(records, 'ALL'), records)
  assert.deepEqual(filterDetectionHistory(records, 'UNKNOWN').map(({ id }) => id), [3])
})

test('newer copies of the same history event refresh fields without changing its identity', () => {
  const oldRecord = {
    id: 8,
    device_id: 'FIELD-UNIT-01',
    status: 'UNKNOWN',
    pest: 'Old label',
    insect_group: 'Unknown insect group',
    detected_at: '2025-01-01T12:00:00Z',
  }
  const updatedRecord = {
    ...oldRecord,
    pest: 'Chorthippus mollis',
    insect_group: 'Grasshopper',
    top_predictions: [{ pest: 'Chorthippus mollis', score: 0.341 }],
  }

  const [merged] = mergeDetections([oldRecord], [updatedRecord])

  assert.equal(merged.pest, 'Chorthippus mollis')
  assert.equal(getDetectionInsectGroup(merged), 'Grasshopper')
  assert.equal(merged.top_predictions[0].score, 0.341)
})

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

test('history deduplicates matching records when only one copy has a database ID', () => {
  const savedRecord = {
    id: 7,
    device_id: 'FIELD-UNIT-01',
    status: 'UNKNOWN',
    pest: 'Chorthippus mollis',
    insect_group: 'Grasshopper',
    confidence: 0.341,
    detected_at: '2025-01-01T12:00:00Z',
  }

  const merged = mergeDetections(
    [savedRecord],
    [{ ...savedRecord, id: undefined, top_predictions: [{ pest: 'Chorthippus mollis', score: 0.341 }] }],
  )

  assert.equal(merged.length, 1)
  assert.equal(merged[0].id, 7)
  assert.equal(merged[0].top_predictions[0].pest, 'Chorthippus mollis')
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
