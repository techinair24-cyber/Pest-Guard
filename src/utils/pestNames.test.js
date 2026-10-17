import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  buildPestDirectory,
  getDisplayPestName,
  getDetectionRiskEstimate,
  getPestRiskEstimate,
  PEST_CLASS_RISK_ESTIMATES,
} from './pestNames.js'

const classNames = JSON.parse(
  await readFile(
    new URL('../../backend/ai_model/class_names.json', import.meta.url),
    'utf8',
  ),
)

test('desert locust has a documented general risk estimate', () => {
  const label = 'Desert locust'
  assert.ok(classNames.includes(label))
  const estimate = getPestRiskEstimate(label)

  assert.equal(estimate.risk, 'HIGH')
  assert.ok(estimate.source)
  assert.ok(estimate.sourceUrl.startsWith('https://'))
  assert.ok(estimate.rationale)

  assert.equal(
    PEST_CLASS_RISK_ESTIMATES.desertlocust.canonicalName,
    'Desert locust',
  )
})

test('Katydid has the documented general monitoring risk estimate', () => {
  assert.ok(classNames.includes('Katydid'))
  const estimate = getPestRiskEstimate('Katydid')

  assert.equal(estimate.canonicalName, 'Katydid')
  assert.equal(estimate.risk, 'MEDIUM')
  assert.equal(estimate.source, 'UC Statewide IPM Program')
  assert.equal(
    estimate.sourceUrl,
    'https://ipm.ucanr.edu/agriculture/citrus/katydids/',
  )
  assert.match(estimate.rationale, /varies by species and crop/)
})

test('unsupported model classes remain unknown instead of inheriting similar pest risk', () => {
  for (const label of [
    'Grasshopper',
    'Cicada',
    'termite',
    'Fruite Fly',
    'Migratory locust',
  ]) {
    assert.ok(classNames.includes(label))
    assert.equal(getPestRiskEstimate(label).risk, 'UNKNOWN')
  }
  assert.equal(getPestRiskEstimate('Desert cricket').risk, 'UNKNOWN')
})

test('every active model output label has an explicit supported or unknown risk result', () => {
  const supportedRisks = new Map([
    ['Desert locust', 'HIGH'],
    ['Katydid', 'MEDIUM'],
  ])

  assert.equal(classNames.length, 20)

  for (const label of classNames) {
    const estimate = getPestRiskEstimate(label)
    assert.equal(
      estimate.risk,
      supportedRisks.get(label) || 'UNKNOWN',
      label,
    )
  }
})

test('every active model label has a readable display name without inventing taxonomy', () => {
  const readableNames = new Map([
    ['Field Crickt', 'Field Cricket'],
    ['Fruite Fly', 'Fruit Fly'],
    ['termite', 'Termite'],
  ])

  for (const label of classNames) {
    const displayName = getDisplayPestName(label)
    assert.ok(displayName, label)
    assert.ok(!displayName.endsWith(`(${label})`), label)
    assert.equal(displayName, readableNames.get(label) || label, label)
  }
})

test('scientific names are displayed only when a matching catalog record provides one', () => {
  const directory = buildPestDirectory([
    {
      pest_id: 'aphid',
      name: 'Aphid',
      scientific_name: 'Aphididae',
    },
  ])

  assert.equal(getDisplayPestName('Aphid', directory), 'Aphid (Aphididae)')
  assert.equal(getDisplayPestName('Cicada'), 'Cicada')
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

test('detection risk stays unknown until its catalog identity is independently verified', () => {
  const directory = buildPestDirectory([
    { pest_id: 'fall-armyworm', name: 'Fall Armyworm', risk: 'HIGH' },
  ])

  assert.equal(
    getDetectionRiskEstimate(
      { pest: 'Fall Armyworm', pest_id: 'fall-armyworm' },
      directory,
    ).risk,
    'UNKNOWN',
  )
  assert.equal(
    getDetectionRiskEstimate(
      {
        pest: 'Fall Armyworm',
        pest_id: 'other-pest',
        pest_verified: true,
      },
      directory,
    ).risk,
    'UNKNOWN',
  )
  assert.equal(
    getDetectionRiskEstimate(
      {
        pest: 'Fall Armyworm',
        pest_id: 'fall-armyworm',
        pest_verified: true,
      },
      directory,
    ).risk,
    'HIGH',
  )
})
