import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatDeviceHumidity,
  formatDeviceTemperature,
  getDetectionControlPresentation,
  getIdentificationLabel,
  getLeadingSpeciesLabel,
  getLeadingSpeciesPrediction,
} from './liveMonitoringStatus.js'

test('latest detection highlights the highest-scoring returned species, not only its group', () => {
  const detection = {
    pest: 'Chorthippus mollis',
    insect_group: 'Grasshopper',
    confidence: 0.341,
    group_score: 0.916,
    top_predictions: [
      { pest: 'Chorthippus mollis', common_name: 'Chorthippus mollis', score: 0.341 },
      { pest: 'Gomphocerippus rufus', common_name: 'Rufous Grasshopper', score: 0.23 },
    ],
  }

  assert.equal(getLeadingSpeciesPrediction(detection).score, 0.341)
  assert.equal(
    getLeadingSpeciesLabel(detection),
    'Chorthippus mollis',
  )
})

test('confirmation is shown only for the explicit backend CONFIRMED status', () => {
  assert.equal(
    getIdentificationLabel({ identification_status: 'CONFIRMED' }),
    'CONFIRMED IDENTIFICATION',
  )
  for (const status of ['UNCONFIRMED', 'confirmed', 'ERROR', undefined]) {
    assert.equal(
      getIdentificationLabel({
        identification_status: status,
        group_score: 0.999,
      }),
      'SPECIES PREDICTION',
    )
  }
})

test('missing, invalid, or offline device sensor values are unavailable, not zero', () => {
  assert.equal(formatDeviceTemperature(null, true), 'Unavailable')
  assert.equal(formatDeviceTemperature('invalid', true), 'Unavailable')
  assert.equal(formatDeviceTemperature(0, true), '0.0 °C')
  assert.equal(formatDeviceTemperature(22.5, false), 'Unavailable')
  assert.equal(formatDeviceHumidity(undefined, true), 'Unavailable')
  assert.equal(formatDeviceHumidity(101, true), 'Unavailable')
  assert.equal(formatDeviceHumidity(0, true), '0%')
})

test('control presentation distinguishes command requests from device acknowledgements', () => {
  assert.equal(
    getDetectionControlPresentation({
      enabled: true,
      device_enabled: null,
      status: 'UNKNOWN',
    }).label,
    'CONTROL UNKNOWN',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: true,
      device_enabled: false,
      status: 'REQUESTED',
    }).label,
    'DETECT REQUESTED',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: true,
      device_enabled: true,
      status: 'RUNNING',
    }).label,
    'RUNNING',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: false,
      device_enabled: false,
      status: 'STOPPED',
    }).label,
    'STOPPED',
  )
})
