import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildPestDirectory,
  getDetectionRiskEstimate,
  getDisplayPestName,
  getPestRiskEstimate,
  normalizePestName,
} from './pestNames.js'

const catalogueFixture = [
  {
    pest_id: 'brown_bunyip_cicada',
    name: 'Brown Bunyip Cicada',
    scientific_name: 'Tamasa tristigma',
    aliases: ['Brown Bunyip'],
    risk: 'LOW',
  },
]
const directory = buildPestDirectory(catalogueFixture)

test('Brown Bunyip alias resolves to the existing canonical catalogue identity', () => {
  const alias = directory[normalizePestName('Brown Bunyip')]
  const canonical = directory[normalizePestName('Brown Bunyip Cicada')]

  assert.deepEqual(alias, canonical)
  assert.equal(alias.pestId, 'brown_bunyip_cicada')
  assert.equal(alias.scientificName, 'Tamasa tristigma')
  assert.equal(
    getDisplayPestName('BROWN_bunyip', directory),
    'Brown Bunyip Cicada (Tamasa tristigma)',
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
  assert.equal(
    getDetectionRiskEstimate(
      {
        status: 'HARMFUL_PEST',
        pest: 'Brown Bunyip',
        pest_id: 'brown_bunyip_cicada',
        pest_verified: true,
      },
      directory,
    ).risk,
    'LOW',
  )
  assert.equal(
    getPestRiskEstimate('Tamasa tristigma', directory).risk,
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
