import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPotentialHostDisplay } from './potentialHostProfile.js'

const profile = {
  pest_name: 'Pine weevil',
  scientific_name: 'Hylobius abietis',
  risk_level: 'HIGH',
  status: 'NEEDS_REVIEW',
  region: 'Palearctic forestry; not established in India',
  potential_host_crops: [
    { crop_id: 'pine', crop_name: 'Pine', review_status: 'NEEDS_REVIEW' },
    { crop_id: 'spruce', crop_name: 'Spruce', review_status: 'NEEDS_REVIEW' },
    { crop_id: 'fir', crop_name: 'Fir', review_status: 'NEEDS_REVIEW' },
    { crop_id: 'douglas_fir', crop_name: 'Douglas Fir', review_status: 'NEEDS_REVIEW' },
    { crop_id: 'hemlock', crop_name: 'Hemlock', review_status: 'NEEDS_REVIEW' },
  ],
  description: 'Candidate profile description.',
  identification_signs: 'Candidate identification signs.',
  crop_damage: 'Candidate crop damage.',
  affected_plant_parts: 'Candidate affected plant parts.',
  recommended_treatment: 'Candidate recommended treatment.',
  immediate_control_measures: 'Candidate immediate control measures.',
  biological_control_options: 'Candidate biological control options.',
  cultural_control_methods: 'Candidate cultural control methods.',
  mechanical_control_methods: 'Candidate mechanical control methods.',
  chemical_control_options: 'Candidate chemical control options.',
  prevention: 'Candidate prevention.',
  monitoring: 'Candidate monitoring.',
  safety_precautions: 'Candidate safety precautions.',
  expert_advice: 'Candidate expert advice.',
}

test('builds one unverified profile with all potential hosts together', () => {
  const display = buildPotentialHostDisplay(profile)

  assert.equal(display.pestName, 'Pine weevil')
  assert.equal(display.hostHeading, 'Potential hosts')
  assert.equal(display.verificationLabel, 'Unverified · verification pending')
  assert.deepEqual(
    display.hosts.map((host) => host.cropName),
    ['Pine', 'Spruce', 'Fir', 'Douglas Fir', 'Hemlock'],
  )
  assert.ok(display.hosts.every((host) => host.reviewStatus === 'NEEDS_REVIEW'))
  assert.deepEqual(
    display.sections.map((section) => section.title),
    [
      'Description',
      'Identification signs',
      'Crop damage',
      'Affected plant parts',
      'Recommended treatment',
      'Immediate control measures',
      'Biological control options',
      'Cultural control methods',
      'Mechanical control methods',
      'Chemical control options',
      'Prevention',
      'Monitoring',
      'Safety precautions',
      'Expert advice',
    ],
  )
  assert.equal(display.sections[0].content, 'Candidate profile description.')
})

test('does not present verified or hostless data as a potential-host profile', () => {
  assert.equal(
    buildPotentialHostDisplay({ ...profile, status: 'VERIFIED' }),
    null,
  )
  assert.equal(
    buildPotentialHostDisplay({ ...profile, potential_host_crops: [] }),
    null,
  )
})
