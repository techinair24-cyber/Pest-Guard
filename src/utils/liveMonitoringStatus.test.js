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

test('control presentation distinguishes unknown, sent, and acknowledged commands', () => {
  assert.deepEqual(
    getDetectionControlPresentation({
      enabled: true,
      command_received: false,
      device_enabled: null,
      status: 'UNKNOWN',
    }).status,
    'UNKNOWN',
  )
  assert.deepEqual(
    getDetectionControlPresentation({
      enabled: true,
      command_received: true,
      device_enabled: null,
      status: 'REQUESTED',
    }),
    {
      enabled: true,
      status: 'REQUESTED',
      label: 'COMMAND SENT',
      message: 'The Detect command was accepted; waiting for the field-unit acknowledgement.',
      className: 'is-requested',
    },
  )
  assert.equal(
    getDetectionControlPresentation(
      {
        enabled: true,
        device_enabled: null,
        status: 'UNKNOWN',
      },
      { commandAccepted: true },
    ).label,
    'COMMAND SENT',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: true,
      device_enabled: false,
      status: 'REQUESTED',
    }).label,
    'COMMAND SENT',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: true,
      device_enabled: true,
      status: 'RUNNING',
    }).label,
    'DETECTING',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: false,
      device_enabled: false,
      status: 'STOPPED',
    }).label,
    'DETECTION STOPPED',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: false,
      command_received: true,
      device_enabled: true,
      status: 'REQUESTED',
    }).label,
    'COMMAND SENT',
  )
})
