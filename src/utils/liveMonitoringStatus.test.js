import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatDeviceHumidity,
  formatDeviceTemperature,
  getDetectionControlPresentation,
  getRequestedDetectionControlPresentation,
  getIdentificationLabel,
  getLeadingSpeciesLabel,
  getLeadingSpeciesPrediction,
  matchesDetectionControlAction,
  requestDetectionControl,
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
      label: 'WAITING FOR DEVICE',
      message: 'The command is saved; waiting for the field unit to fetch and acknowledge it.',
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
    'WAITING FOR DEVICE',
  )
  assert.equal(
    getDetectionControlPresentation({
      enabled: true,
      device_enabled: false,
      status: 'REQUESTED',
    }).label,
    'WAITING FOR DEVICE',
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
    'WAITING FOR DEVICE',
  )
})

test('Detect is shown as sent until the field unit acknowledges it', async () => {
  const calls = []
  const control = await requestDetectionControl(
    'FIELD-UNIT-01',
    true,
    async (...args) => {
      calls.push(args)
      return {
        device_id: 'FIELD-UNIT-01',
        enabled: true,
        command_received: true,
        device_enabled: null,
        status: 'REQUESTED',
      }
    },
  )

  assert.deepEqual(calls, [['FIELD-UNIT-01', true]])
  assert.equal(control.label, 'WAITING FOR DEVICE')
  assert.match(control.message, /waiting for the field unit to fetch and acknowledge/)
})

test('Stop is shown as sent until the field unit acknowledges it', async () => {
  const control = await requestDetectionControl(
    'FIELD-UNIT-01',
    false,
    async () => ({
      device_id: 'FIELD-UNIT-01',
      enabled: false,
      command_received: true,
      device_enabled: true,
      status: 'REQUESTED',
    }),
  )

  assert.equal(control.label, 'WAITING FOR DEVICE')
  assert.match(control.message, /waiting for the field unit to fetch and acknowledge/)
})

test('accepted commands show confirmed labels only with matching device acknowledgement', async () => {
  const detect = await requestDetectionControl('FIELD-UNIT-01', true, async () => ({
    enabled: true,
    device_enabled: true,
    status: 'RUNNING',
  }))
  const stop = await requestDetectionControl('FIELD-UNIT-01', false, async () => ({
    enabled: false,
    device_enabled: false,
    status: 'STOPPED',
  }))

  assert.equal(detect.label, 'DETECTING')
  assert.equal(stop.label, 'DETECTION STOPPED')
})

test('failed control requests reject without producing a successful control state', async () => {
  await assert.rejects(
    requestDetectionControl(
      'FIELD-UNIT-01',
      true,
      async () => {
        throw new Error('backend unavailable')
      },
    ),
    /backend unavailable/,
  )
})

test('a response that does not accept the requested state is rejected', async () => {
  await assert.rejects(
    requestDetectionControl('FIELD-UNIT-01', true, async () => ({
      enabled: false,
      device_enabled: null,
      status: 'UNKNOWN',
    })),
    /Backend did not confirm the requested control value/,
  )
})

test('offline and timed-out devices are not presented as command acknowledgements', () => {
  const offline = getDetectionControlPresentation({
    enabled: false,
    command_received: true,
    command_id: 'control-1',
    device_online: false,
    device_enabled: null,
    status: 'DEVICE_OFFLINE',
  })
  const timedOut = getDetectionControlPresentation({
    enabled: true,
    command_received: true,
    command_id: 'control-2',
    device_online: true,
    device_enabled: null,
    status: 'TIMEOUT',
  })

  assert.equal(offline.label, 'DEVICE OFFLINE')
  assert.match(offline.message, /no recent heartbeat/)
  assert.equal(timedOut.label, 'COMMAND TIMED OUT')
  assert.match(timedOut.message, /Check the field unit and firmware/)
})

test('requested Detect and Stop labels remain visible while device confirmation is pending', () => {
  const detect = getRequestedDetectionControlPresentation(true, null, {
    requestPending: true,
  })
  const stop = getRequestedDetectionControlPresentation(false, {
    enabled: false,
    command_received: true,
    device_enabled: null,
    status: 'REQUESTED',
  })

  assert.equal(detect.label, 'DETECTING')
  assert.equal(detect.confirmed, false)
  assert.match(detect.message, /confirmation is pending/)
  assert.equal(stop.label, 'DETECTION STOPPED')
  assert.equal(stop.confirmed, false)
  assert.match(stop.message, /waiting for the field unit/)
})

test('requested UI states show hardware confirmation only for matching acknowledged state', () => {
  const confirmed = getRequestedDetectionControlPresentation(true, {
    enabled: true,
    device_enabled: true,
    status: 'RUNNING',
  })
  const notConfirmed = getRequestedDetectionControlPresentation(true, {
    enabled: true,
    device_enabled: false,
    status: 'REQUESTED',
  })

  assert.equal(confirmed.label, 'DETECTING')
  assert.equal(confirmed.confirmed, true)
  assert.match(confirmed.message, /field unit confirmed Detect/)
  assert.equal(notConfirmed.label, 'DETECTING')
  assert.equal(notConfirmed.confirmed, false)
})

test('a failed request keeps the selected label but clearly reports unconfirmed device state', () => {
  const presentation = getRequestedDetectionControlPresentation(false, null, {
    requestError: 'backend unavailable',
  })

  assert.equal(presentation.label, 'DETECTION STOPPED')
  assert.equal(presentation.confirmed, false)
  assert.match(presentation.message, /was not accepted/)
  assert.match(presentation.message, /state is unconfirmed/)
})

test('stale polls cannot reconcile over a newer or unaccepted button action', () => {
  const currentAction = {
    enabled: false,
    commandId: 'latest-command',
    accepted: true,
  }

  assert.equal(
    matchesDetectionControlAction(currentAction, {
      command_id: 'older-command',
      enabled: true,
      command_received: true,
    }),
    false,
  )
  assert.equal(
    matchesDetectionControlAction(
      { ...currentAction, accepted: false },
      { command_id: 'latest-command', enabled: false, command_received: true },
    ),
    false,
  )
  assert.equal(
    matchesDetectionControlAction(currentAction, {
      command_id: 'latest-command',
      enabled: false,
      command_received: true,
    }),
    true,
  )
})
