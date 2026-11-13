import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildPestDirectory,
  getCandidateRiskEstimate,
  normalizePestName,
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

test('verified model aliases resolve to their canonical catalogue risk', () => {
  const aliases = [
    ['greater_dark_bush_cricket', 'large_dark_bush_cricket'],
    ['Floury Baker', 'floury_baker_cicada'],
    ['Razor Grinder', 'razor_grinder_cicada'],
    ['Red Squeaker', 'red_squeaker_cicada'],
    ['White Drummer', 'white_drummer_cicada'],
  ]
  const catalog = buildPestDirectory([
    {
      pest_id: 'large_dark_bush_cricket',
      name: 'Large Dark Bush-cricket',
      risk: 'LOW',
      aliases: ['greater_dark_bush_cricket'],
    },
    {
      pest_id: 'floury_baker_cicada',
      name: 'Floury Baker Cicada',
      risk: 'LOW',
      aliases: ['Floury Baker'],
    },
    {
      pest_id: 'razor_grinder_cicada',
      name: 'Razor Grinder Cicada',
      risk: 'LOW',
      aliases: ['Razor Grinder'],
    },
    {
      pest_id: 'red_squeaker_cicada',
      name: 'Red Squeaker Cicada',
      risk: 'LOW',
      aliases: ['Red Squeaker', 'Melampsalta rubea'],
    },
    {
      pest_id: 'white_drummer_cicada',
      name: 'White Drummer Cicada',
      risk: 'LOW',
      aliases: ['White Drummer'],
    },
  ])

  for (const [alias, pestId] of aliases) {
    const detection = {
      status: 'HARMFUL_PEST',
      pest: alias,
      pest_id: pestId,
      pest_verified: true,
    }

    assert.equal(
      getCandidateRiskEstimate({ pest: alias }, detection, catalog).risk,
      'LOW',
      alias,
    )
    assert.strictEqual(
      catalog[normalizePestName(alias)],
      catalog[normalizePestName(pestId)],
      alias,
    )
  }
})
