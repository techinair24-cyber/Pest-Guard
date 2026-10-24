import {
  getCandidateDisplayName,
  getTopSpeciesPredictions,
} from './insectPredictions.js'

export function getLeadingSpeciesPrediction(detection) {
  const candidate = getTopSpeciesPredictions(detection?.top_predictions)[0]
  if (candidate) return candidate

  const pest = String(detection?.pest || '').trim()
  if (!pest) return null

  return {
    pest,
    common_name: detection?.common_name,
    score: detection?.confidence,
  }
}

export function getLeadingSpeciesLabel(detection) {
  const candidate = getLeadingSpeciesPrediction(detection)
  return candidate ? getCandidateDisplayName(candidate) : ''
}

export function getIdentificationLabel(detection) {
  return detection?.identification_status === 'CONFIRMED'
    ? 'CONFIRMED IDENTIFICATION'
    : 'SPECIES PREDICTION'
}

export function formatDeviceTemperature(value, isOnline) {
  if (!isOnline || value === null || value === undefined || value === '') {
    return 'Unavailable'
  }
  const temperature = Number(value)
  return Number.isFinite(temperature)
    ? `${temperature.toFixed(1)} °C`
    : 'Unavailable'
}

export function formatDeviceHumidity(value, isOnline) {
  if (!isOnline || value === null || value === undefined || value === '') {
    return 'Unavailable'
  }
  const humidity = Number(value)
  if (!Number.isFinite(humidity) || humidity < 0 || humidity > 100) {
    return 'Unavailable'
  }
  return `${Number(humidity.toFixed(1))}%`
}

export function getDetectionControlPresentation(response, { commandAccepted = false } = {}) {
  if (!response || typeof response.enabled !== 'boolean') {
    throw new Error('Backend returned an invalid control command.')
  }
  if (
    response.command_received !== undefined &&
    typeof response.command_received !== 'boolean'
  ) {
    throw new Error('Backend returned an invalid command acknowledgement state.')
  }
  if (
    response.device_enabled !== undefined &&
    response.device_enabled !== null &&
    typeof response.device_enabled !== 'boolean'
  ) {
    throw new Error('Backend returned an invalid device acknowledgement.')
  }
  if (
    response.device_online !== undefined &&
    typeof response.device_online !== 'boolean'
  ) {
    throw new Error('Backend returned an invalid device connection state.')
  }

  const knownStatuses = new Set([
    'UNKNOWN',
    'REQUESTED',
    'RUNNING',
    'STOPPED',
    'DEVICE_OFFLINE',
    'TIMEOUT',
  ])
  if (response.status && !knownStatuses.has(response.status)) {
    throw new Error('Backend returned an unknown control status.')
  }

  const hasDeviceAcknowledgement =
    response.device_enabled !== null &&
    response.device_enabled !== undefined
  const status = hasDeviceAcknowledgement
    ? response.device_enabled !== response.enabled
      ? 'REQUESTED'
      : response.device_enabled
        ? 'RUNNING'
        : 'STOPPED'
    : response.status === 'DEVICE_OFFLINE' || response.status === 'TIMEOUT'
      ? response.status
      : commandAccepted || response.command_received === true ||
          response.status === 'REQUESTED'
        ? 'REQUESTED'
        : 'UNKNOWN'
  if (
    response.status &&
    response.status !== status &&
    !(commandAccepted && response.status === 'UNKNOWN' && status === 'REQUESTED')
  ) {
    throw new Error('Backend control status does not match the device acknowledgement.')
  }

  const label = status === 'RUNNING'
    ? 'DETECTING'
    : status === 'STOPPED'
      ? 'DETECTION STOPPED'
      : status === 'REQUESTED'
        ? 'WAITING FOR DEVICE'
        : status === 'DEVICE_OFFLINE'
          ? 'DEVICE OFFLINE'
          : status === 'TIMEOUT'
            ? 'COMMAND TIMED OUT'
            : 'CONTROL UNKNOWN'
  const message = status === 'RUNNING'
    ? 'The field unit acknowledged Detect and is monitoring.'
    : status === 'STOPPED'
      ? 'The field unit acknowledged Stop.'
      : status === 'REQUESTED'
        ? 'The command is saved; waiting for the field unit to fetch and acknowledge it.'
        : status === 'DEVICE_OFFLINE'
          ? 'The command is saved, but the field unit has no recent heartbeat. No device acknowledgement is available.'
          : status === 'TIMEOUT'
            ? 'The command received no matching acknowledgement before it timed out. Check the field unit and firmware.'
            : 'No detection command or recent field-unit acknowledgement is available.'

  return {
    enabled: response.enabled,
    status,
    label,
    message,
    className: status === 'RUNNING'
      ? 'is-running'
      : status === 'STOPPED'
        ? 'is-stopped'
        : status === 'REQUESTED'
          ? 'is-requested'
          : 'is-unknown',
  }
}

export async function requestDetectionControl(deviceId, enabled, sendCommand) {
  const response = await sendCommand(deviceId, enabled)
  const control = getDetectionControlPresentation(response, {
    commandAccepted: true,
  })
  if (control.enabled !== enabled) {
    throw new Error('Backend did not confirm the requested control value.')
  }
  return {
    ...control,
    commandId: response.command_id ?? null,
    response,
  }
}

export function getRequestedDetectionControlPresentation(
  enabled,
  response,
  { requestPending = false, requestError = '' } = {},
) {
  const confirmed = response?.device_enabled === enabled &&
    response?.status === (enabled ? 'RUNNING' : 'STOPPED')
  const label = enabled ? 'DETECTING' : 'DETECTION STOPPED'
  const message = confirmed
    ? `The field unit confirmed ${enabled ? 'Detect' : 'Stop'}.`
    : requestError
      ? `${enabled ? 'Detect' : 'Stop'} was not accepted; the field-unit state is unconfirmed.`
      : response?.status === 'DEVICE_OFFLINE' || response?.device_online === false
        ? 'The requested state is shown; the field unit is offline and has not confirmed it.'
        : response?.status === 'TIMEOUT'
          ? 'The requested state is shown; no matching field-unit confirmation arrived before timeout.'
          : requestPending
            ? `Sending ${enabled ? 'Detect' : 'Stop'}; field-unit confirmation is pending.`
            : `The requested state is shown; waiting for the field unit to confirm ${enabled ? 'Detect' : 'Stop'}.`

  return {
    enabled,
    status: confirmed ? (enabled ? 'RUNNING' : 'STOPPED') : 'REQUESTED',
    label,
    message,
    className: enabled ? 'is-running' : 'is-stopped',
    confirmed,
  }
}

export function matchesDetectionControlAction(action, response) {
  if (!action?.accepted) return false
  return action.commandId
    ? response?.command_id === action.commandId
    : response?.enabled === action.enabled &&
      response?.command_received === true
}
