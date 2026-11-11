import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  buildPestDirectory,
  getDetectionRiskEstimate,
  getDisplayPestName,
  getPestRiskEstimate,
  normalizePestName,
} from './pestNames.js'

const classNames = JSON.parse(
  await readFile(
    new URL(
      '../../backend/ai_model/pest_yamnet_updated_candidate/class_names.json',
      import.meta.url,
    ),
    'utf8',
  ),
)

const metadata = JSON.parse(
  await readFile(
    new URL(
      '../../backend/ai_model/pest_yamnet_updated_candidate/class_metadata.json',
      import.meta.url,
    ),
    'utf8',
  ),
)

const metadataByClass = new Map(
  metadata.map((entry) => [
    normalizePestName(entry.model_class),
    entry,
  ]),
)

test('metadata covers every exact active YAMNet model class', () => {
  assert.equal(classNames.length, 20)
  assert.equal(metadata.length, classNames.length)

  for (const label of classNames) {
    assert.ok(metadataByClass.has(normalizePestName(label)), label)
  }
})

test('every class has a readable common name and sourced risk assessment', () => {
  for (const entry of metadata) {
    assert.ok(entry.common_name.trim(), entry.model_class)
    assert.ok(
      ['HIGH', 'MEDIUM', 'LOW', 'NO_RISK'].includes(entry.risk),
      entry.model_class,
    )
    assert.ok(entry.source_name.trim(), entry.model_class)
    assert.ok(entry.source_url.startsWith('https://'), entry.model_class)
    assert.ok(entry.risk_rationale.trim(), entry.model_class)
    assert.ok(Array.isArray(entry.affected_crops), entry.model_class)

    if (entry.risk !== 'NO_RISK') {
      assert.ok(entry.affected_crops.length > 0, entry.model_class)
    }
  }
})

test('metadata matching ignores capitalization, spaces, and underscores', () => {
  const entry = metadataByClass.get('commonfieldgrasshopper')

  assert.equal(
    getDisplayPestName(
      'COMMON_field__grasshopper',
      {},
      entry,
    ),
    'Common field grasshopper (Chorthippus brunneus)',
  )
})

test('unverified detections do not present candidate risk as confirmed', () => {
  const detection = {
    status: 'UNKNOWN',
    pest: 'Desert locust',
    risk: 'HIGH',
    risk_rationale: 'FAO documents severe swarm impacts.',
    metadata_source_name: 'FAO Locust Watch',
    metadata_source_url: 'https://www.fao.org/locusts/en/',
  }

  assert.deepEqual(getDetectionRiskEstimate(detection), {
    risk: 'UNCONFIRMED',
    source: null,
    sourceUrl: null,
    rationale: 'Risk is not assigned to an unverified species candidate.',
  })
})

test('unrated metadata uses precautionary LOW', () => {
  const estimate = getDetectionRiskEstimate({
    status: 'UNKNOWN',
    pest: 'Grasshopper',
    risk: 'LOW',
    risk_rationale: 'The model label is too broad to assign a risk tier.',
  })
  assert.equal(estimate.risk, 'UNCONFIRMED')
  assert.match(estimate.rationale, /unverified species candidate/)
})

test('catalogue risk remains available for independently verified records', () => {
  const directory = buildPestDirectory([
    { pest_id: 'fall-armyworm', name: 'Fall Armyworm', risk: 'HIGH' },
  ])

  assert.equal(
    getDetectionRiskEstimate(
      {
        status: 'HARMFUL_PEST',
        pest: 'Fall Armyworm',
        pest_id: 'fall-armyworm',
        pest_verified: true,
      },
      directory,
    ).risk,
    'HIGH',
  )
  assert.equal(
    getPestRiskEstimate('Armyworm', directory).risk,
    'LOW',
  )
})

test('unknown species do not fail name or risk display', () => {
  assert.equal(getDisplayPestName('Unrecognized insect'), 'Unrecognized insect')
  assert.equal(
    getDetectionRiskEstimate({
      status: 'UNKNOWN',
      pest: 'Unrecognized insect',
    }).risk,
    'UNCONFIRMED',
  )
})
