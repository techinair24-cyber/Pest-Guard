import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildPestDirectory,
  getCandidateRiskEstimate,
} from './pestNames.js'

const directory = buildPestDirectory([
  {
    pest_id: 'european_field_cricket',
    name: 'European Field Cricket',
    risk: 'HIGH',
  },
  {
    pest_id: 'european_mole_cricket',
    name: 'European Mole Cricket',
    risk: 'HIGH',
  },
  {
    pest_id: 'low-risk-cricket',
    name: 'Low Risk Cricket',
    risk: 'LOW',
  },
])

test('high-risk candidate is unconfirmed beside unrelated low-risk detection', () => {
  const result = getCandidateRiskEstimate(
    { pest: 'European Field Cricket' },
    {
      status: 'HARMFUL_PEST',
      pest: 'Low Risk Cricket',
      pest_id: 'low-risk-cricket',
      pest_verified: true,
      risk: 'LOW',
    },
    directory,
  )

  assert.equal(result.risk, 'UNCONFIRMED')
})

test('group-only detection risk is not attributed to a species candidate', () => {
  const result = getCandidateRiskEstimate(
    { pest: 'European Mole Cricket' },
    {
      status: 'UNKNOWN',
      pest: 'Mole Crickets',
      pest_id: null,
      pest_verified: false,
      risk: 'LOW',
    },
    directory,
  )

  assert.equal(result.risk, 'UNCONFIRMED')
})

test('verified candidate risk comes from its exact catalogue id', () => {
  const detection = {
    status: 'HARMFUL_PEST',
    pest: 'European Field Cricket',
    pest_id: 'european_field_cricket',
    pest_verified: true,
    risk: 'LOW',
  }

  assert.equal(
    getCandidateRiskEstimate(
      { pest: 'European Field Cricket' },
      detection,
      directory,
    ).risk,
    'HIGH',
  )
})

test('verified catalogue risk preserves all four supported categories', () => {
  for (const risk of ['HIGH', 'MEDIUM', 'LOW', 'NO_RISK']) {
    const pestId = `risk-${risk.toLowerCase()}`
    const pestName = `Risk ${risk}`
    const catalog = buildPestDirectory([
      { pest_id: pestId, name: pestName, risk },
    ])
    const detection = {
      status: 'HARMFUL_PEST',
      pest: pestName,
      pest_id: pestId,
      pest_verified: true,
      risk: 'LOW',
    }

    assert.equal(
      getCandidateRiskEstimate(pestName, detection, catalog).risk,
      risk,
      risk,
    )
  }
})
