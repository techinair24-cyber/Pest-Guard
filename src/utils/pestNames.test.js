import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  buildPestDirectory,
  getPestRiskEstimate,
  PEST_CLASS_RISK_ESTIMATES,
} from './pestNames.js'

const classNames = JSON.parse(
  await readFile(
    new URL('../../backend/ai_model/class_names.json', import.meta.url),
    'utf8',
  ),
)

test('supported locust model classes have documented general risk estimates', () => {
  for (const label of ['Desert locust', 'Migratory locust']) {
    assert.ok(classNames.includes(label))
    const estimate = getPestRiskEstimate(label)

    assert.equal(estimate.risk, 'HIGH')
    assert.ok(estimate.source)
    assert.ok(estimate.sourceUrl.startsWith('https://'))
    assert.ok(estimate.rationale)
  }

  assert.equal(
    PEST_CLASS_RISK_ESTIMATES.desertlocust.canonicalName,
    'Desert locust',
  )
})

test('unsupported model classes remain unknown instead of inheriting similar pest risk', () => {
  for (const label of [
    'Grasshopper',
    'Cicada',
    'termite',
    'Fruite Fly',
  ]) {
    assert.ok(classNames.includes(label))
    assert.equal(getPestRiskEstimate(label).risk, 'UNKNOWN')
  }
  assert.equal(getPestRiskEstimate('Desert cricket').risk, 'UNKNOWN')
})

test('model scores do not participate in class risk lookup', () => {
  const estimates = [0.1, 0.99].map((confidence) => {
    const detection = { pest: 'Desert locust', confidence }
    return getPestRiskEstimate(detection.pest)
  })

  assert.deepEqual(
    estimates.map((estimate) => estimate.risk),
    ['HIGH', 'HIGH'],
  )
})

test('catalog risk metadata is used only for a matching catalog record', () => {
  const directory = buildPestDirectory([
    { pest_id: 'fall-armyworm', name: 'Fall Armyworm', risk: 'HIGH' },
  ])

  assert.equal(
    getPestRiskEstimate('Fall Armyworm', directory).risk,
    'HIGH',
  )
  assert.equal(
    getPestRiskEstimate('Armyworm', directory).risk,
    'UNKNOWN',
  )
})
