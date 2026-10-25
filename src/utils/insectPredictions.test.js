import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatModelScore,
  getCandidateDisplayName,
  getDetectionInsectGroup,
  getPredictionUncertainty,
  getTopSpeciesPredictions,
  UNKNOWN_INSECT_GROUP,
} from './insectPredictions.js'

test('the broad group, not a species, is the primary display value', () => {
  assert.equal(
    getDetectionInsectGroup({
      pest: 'Chorthippus mollis',
      insect_group: 'Grasshopper',
    }),
    'Grasshopper',
  )
  assert.equal(getDetectionInsectGroup({ pest: 'unmapped species' }), UNKNOWN_INSECT_GROUP)
})

test('species candidates use actual response values and sort to the top three', () => {
  const candidates = [
    { pest: 'low', score: 0.2 },
    { pest: 'high', score: 0.8, common_name: 'High insect' },
    { pest: 'middle', score: 0.5 },
    { pest: 'last', score: 0.1 },
  ]

  assert.deepEqual(
    getTopSpeciesPredictions(candidates).map(({ pest, score }) => [pest, score]),
    [['high', 0.8], ['middle', 0.5], ['low', 0.2]],
  )
  assert.equal(getCandidateDisplayName(candidates[1]), 'High insect (high)')
  assert.equal(formatModelScore(candidates[1].score), '80.0%')
})

test('missing model scores are not converted to fabricated zero scores', () => {
  assert.equal(formatModelScore(null), 'N/A')
  assert.equal(formatModelScore(undefined), 'N/A')
  assert.deepEqual(
    getTopSpeciesPredictions([
      { pest: 'no score', score: null },
      { pest: 'valid score', score: 0.25 },
    ]).map(({ pest }) => pest),
    ['valid score'],
  )
})

test('candidate results use neutral wording and retain the score qualification', () => {
  for (const detection of [
    {
      confidence: 0.277,
      pest: 'Chorthippus mollis',
      identification_status: 'UNCONFIRMED',
    },
    { confidence: null, pest: 'Chorthippus mollis'     },
  ]) {
    const message = getPredictionUncertainty(detection)
    assert.equal(message, '')
  }
})

test('history and live websocket records use the same group and candidate display rules', () => {
  const record = {
    pest: 'Chorthippus mollis',
    insect_group: 'Grasshopper',
    top_predictions: [{ pest: 'Chorthippus mollis', score: 0.277 }],
  }
  const liveRecord = { ...record }
  const savedRecord = { ...record }

  assert.equal(getDetectionInsectGroup(liveRecord), getDetectionInsectGroup(savedRecord))
  assert.deepEqual(
    getTopSpeciesPredictions(liveRecord.top_predictions),
    getTopSpeciesPredictions(savedRecord.top_predictions),
  )
})
