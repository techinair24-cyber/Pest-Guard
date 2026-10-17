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
      ['LOW', 'MEDIUM', 'HIGH', 'UNKNOWN'].includes(entry.risk),
      entry.model_class,
    )
    assert.ok(entry.source_name.trim(), entry.model_class)
    assert.ok(entry.source_url.startsWith('https://'), entry.model_class)
    assert.ok(entry.risk_rationale.trim(), entry.model_class)
    assert.ok(Array.isArray(entry.affected_crops), entry.model_class)

    if (entry.risk !== 'UNKNOWN') {
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

test('API-resolved risk metadata is retained on unverified detections', () => {
  const detection = {
    pest: 'Desert locust',
    identification_status: 'UNCONFIRMED',
    risk: 'HIGH',
    risk_rationale: 'FAO documents severe swarm impacts.',
    metadata_source_name: 'FAO Locust Watch',
    metadata_source_url: 'https://www.fao.org/locusts/en/',
  }

  assert.deepEqual(getDetectionRiskEstimate(detection), {
    risk: 'HIGH',
    source: 'FAO Locust Watch',
    sourceUrl: 'https://www.fao.org/locusts/en/',
    rationale: 'FAO documents severe swarm impacts.',
  })
})

test('unrated metadata preserves its explanation without claiming LOW risk', () => {
  const estimate = getDetectionRiskEstimate({
    pest: 'Grasshopper',
    risk: 'UNKNOWN',
    risk_rationale: 'The model label is too broad to assign a risk tier.',
  })

  assert.equal(estimate.risk, 'UNKNOWN')
  assert.match(estimate.rationale, /too broad/)
})

test('catalogue risk remains available for independently verified records', () => {
  const directory = buildPestDirectory([
    { pest_id: 'fall-armyworm', name: 'Fall Armyworm', risk: 'HIGH' },
  ])

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
  assert.equal(
    getPestRiskEstimate('Armyworm', directory).risk,
    'UNKNOWN',
  )
})

test('unknown species do not fail name or risk display', () => {
  assert.equal(getDisplayPestName('Unrecognized insect'), 'Unrecognized insect')
  assert.equal(
    getDetectionRiskEstimate({ pest: 'Unrecognized insect' }).risk,
    'UNKNOWN',
  )
})
