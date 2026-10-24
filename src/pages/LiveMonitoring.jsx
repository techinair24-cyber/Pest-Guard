import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { getDetectionControl, setDetectionEnabled } from '../services/api'

import { useLiveDetection } from '../hooks/useLiveDetection'
import { ArrowIcon, SparkIcon } from '../components/Icons'
import { getDetectionHistory, getPests } from '../services/api'
import {
  buildPestDirectory,
  getDisplayPestName,
  getDetectionRiskEstimate,
} from '../utils/pestNames'
import {
  getDetectionTime,
  getDetectionDisplayStatus,
  getDetectionHistoryKey,
  filterDetectionHistory,
  isLatestDetectionCandidate,
  isAfterHistoryClear,
  mergeDetections,
  parseServerTimestamp,
} from '../utils/detectionHistory'
import {
  formatModelScore,
  getCandidateDisplayName,
  getDetectionInsectGroup,
  getPredictionUncertainty,
  getTopSpeciesPredictions,
} from '../utils/insectPredictions'
import {
  formatDeviceHumidity,
  formatDeviceTemperature,
  getDetectionControlPresentation,
  getIdentificationLabel,
  getLeadingSpeciesPrediction,
} from '../utils/liveMonitoringStatus'
import './LiveMonitoring.css'

const HISTORY_CLEAR_KEY = 'pest_guard_history_cleared_at'
const ALERTED_DETECTIONS_KEY = 'pest_guard_alerted_detection_keys'

function getStoredClearTime() {
  try {
    return window.localStorage.getItem(HISTORY_CLEAR_KEY) || ''
  } catch {
    return ''
  }
}

function getStoredAlertedKeys() {
  try {
    const storedKeys = JSON.parse(
      window.localStorage.getItem(ALERTED_DETECTIONS_KEY) || '[]',
    )
    return new Set(Array.isArray(storedKeys) ? storedKeys.map(String) : [])
  } catch {
    return new Set()
  }
}

function HealthIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 12.5A7 7 0 0 1 12 6a7 7 0 0 1 7 6.5A7 7 0 0 1 12 18a7 7 0 0 1-7-5.5Z" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 9.4v3.2l2.1 1.7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const number = Number(value)
  if (!Number.isFinite(number)) {
    return '—'
  }

  return `${(number * 100).toFixed(1)}%`
}

function isUnconfirmedMatchStatus(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '') ===
    'possiblematchnotconfirmed'
}

function formatDate(value) {
  const timestamp = parseServerTimestamp(value)

  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleString()
    : '—'
}

function getConnectionState(device, loading) {
  if (loading) return 'Connecting'
  if (!device) return 'Offline'
  const value = String(device.status || device.connection || '').toUpperCase()
  return value === 'CONNECTED' || value === 'ONLINE' ? 'Online' : 'Offline'
}
function LiveMonitoring() {
  const navigate = useNavigate()
  const {
    detection,
    device,
    loading,
    error,
    detectionError,
    detectionLoading,
  } = useLiveDetection()
  const [history, setHistory] = useState([])
  const [historyFilter, setHistoryFilter] = useState('ALL')
  const [historyLimit, setHistoryLimit] = useState(8)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const [historyRetryCount, setHistoryRetryCount] = useState(0)
  const [historyClearedAt, setHistoryClearedAt] = useState(() => getStoredClearTime())
  const [popup, setPopup] = useState(null)
  const [detectionControlKnown, setDetectionControlKnown] = useState(false)
  const [detectionControlView, setDetectionControlView] = useState(
    () => getDetectionControlPresentation({ enabled: false }),
  )
  const [detectionControlBusy, setDetectionControlBusy] = useState(false)
  const [detectionControlError, setDetectionControlError] = useState('')
  const [detectionControlMessage, setDetectionControlMessage] = useState(
    'Checking the backend control command.',
  )
  const [pestDirectory, setPestDirectory] = useState({})
  const alertedKeysRef = useRef(getStoredAlertedKeys())

  const liveDetection = detection || history[0] || null
  const liveDevice = device || (liveDetection ? {
    device_id: liveDetection.device_id || 'FIELD-UNIT-01',
    status: 'OFFLINE',
    connection: 'DISCONNECTED',
    last_seen: liveDetection.detected_at || liveDetection.timestamp || null,
    temperature: liveDetection.temperature ?? null,
    humidity: liveDetection.humidity ?? null,
  } : null)
  const deviceId = liveDevice?.device_id || liveDetection?.device_id || 'FIELD-UNIT-01'
  const detectionCandidates = mergeDetections(
    history,
    detection ? [detection] : [],
  ).filter((item) => isLatestDetectionCandidate(item, deviceId))

  // Keep the latest valid candidate visible until a newer candidate arrives.
  const displayDetection = detectionCandidates[0] || null
  const displayDetectionLabel = getDetectionDisplayStatus(displayDetection)

  const connectionState = getConnectionState(liveDevice, loading)
  const detectionStatus = displayDetection?.status || ''
  const statusClass = detectionStatus === 'HARMFUL_PEST'
    ? 'harmful'
    : detectionStatus === 'NON_PEST'
      ? 'normal'
      : detectionStatus === 'UNKNOWN'
        ? 'unknown'
        : 'empty'
  // PEST_GUARD_DETECTION_CONTROL_HANDLERS
  useEffect(() => {
    let active = true

    const refreshControlState = () => {
      getDetectionControl(deviceId)
        .then((result) => {
          if (!active) return
          const control = getDetectionControlPresentation(result)
          setDetectionControlView(control)
          setDetectionControlKnown(true)
          setDetectionControlMessage(control.message)
          setDetectionControlError('')
        })
        .catch((controlError) => {
          if (!active) return
          setDetectionControlKnown(false)
          setDetectionControlError(`Unable to read backend control command: ${controlError.message}`)
        })
    }

    refreshControlState()
    const refreshTimer = window.setInterval(refreshControlState, 5000)

    return () => {
      active = false
      window.clearInterval(refreshTimer)
    }
  }, [deviceId])

  const handleDetectionControl = async (enabled) => {
    setDetectionControlBusy(true)
    setDetectionControlError('')

    try {
      const result = await setDetectionEnabled(deviceId, enabled)
      const control = getDetectionControlPresentation(result)
      if (control.enabled !== enabled) {
        throw new Error('Backend did not confirm the requested control value.')
      }
      setDetectionControlView(control)
      setDetectionControlKnown(true)
      setDetectionControlMessage(control.message)
    } catch (controlError) {
      setDetectionControlKnown(false)
      setDetectionControlError(`Control request failed: ${controlError.message}`)
    } finally {
      setDetectionControlBusy(false)
    }
  }
  const deviceTimestamp = liveDevice?.last_seen || liveDevice?.lastSeen
  const healthTone = connectionState === 'Online' ? 'online' : 'offline'
  const leadingSpeciesPrediction = getLeadingSpeciesPrediction(displayDetection)
  const predictedPestName = leadingSpeciesPrediction?.pest || ''
  const insectGroup = getDetectionInsectGroup(displayDetection)
  const topSpeciesPredictions = getTopSpeciesPredictions(
    displayDetection?.top_predictions,
  )
  const riskDetails = getDetectionRiskEstimate(displayDetection, pestDirectory)
  const riskEstimate = riskDetails.risk
  const reportingDeviceId =
    displayDetection?.device_id || device?.device_id || 'N/A'

  useEffect(() => {
    let active = true

    async function loadPestDirectory() {
      try {
        const pests = await getPests()

        if (active) {
          setPestDirectory(buildPestDirectory(pests))
        }
      } catch (pestDirectoryError) {
        console.error('Unable to load pest directory:', pestDirectoryError)
      }
    }

    loadPestDirectory()

    return () => {
      active = false
    }
  }, [])
  const [onlineWeather, setOnlineWeather] = useState({
    temperature: null,
    humidity: null,
    loading: true,
    locationError: '',
  })

  useEffect(() => {
    let active = true
    let watchId = null
    let refreshTimer = null
    let lastCoords = null
    let lastWeatherCoords = null

    async function loadOnlineWeather(coords) {
      try {
        const params = new URLSearchParams({
          latitude: String(coords.latitude),
          longitude: String(coords.longitude),
          current: 'temperature_2m,relative_humidity_2m',
          timezone: 'auto',
        })

        const response = await fetch(
          `https://api.open-meteo.com/v1/forecast?${params.toString()}`
        )

        if (!response.ok) {
          throw new Error(`Weather request failed: ${response.status}`)
        }

        const data = await response.json()
        const temperature = Number(data?.current?.temperature_2m)
        const humidity = Number(data?.current?.relative_humidity_2m)

        if (!Number.isFinite(temperature) || !Number.isFinite(humidity)) {
          throw new Error('Weather data is incomplete.')
        }

        if (active) {
          setOnlineWeather({
            temperature,
            humidity,
            loading: false,
            locationError: '',
          })
        }
      } catch (weatherError) {
        console.error('Unable to load location weather:', weatherError)

        if (active) {
          setOnlineWeather((current) => ({
            ...current,
            loading: false,
            locationError: 'Weather unavailable for your location.',
          }))
        }
      }
    }

    if (!navigator.geolocation) {
      setOnlineWeather({
        temperature: null,
        humidity: null,
        loading: false,
        locationError: 'Browser location is not supported.',
      })

      return () => {
        active = false
      }
    }

    watchId = navigator.geolocation.watchPosition(
      (position) => {
        const coords = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        }

        lastCoords = coords

        const locationChanged =
          !lastWeatherCoords ||
          Math.abs(coords.latitude - lastWeatherCoords.latitude) >= 0.01 ||
          Math.abs(coords.longitude - lastWeatherCoords.longitude) >= 0.01

        if (locationChanged) {
          lastWeatherCoords = coords
          loadOnlineWeather(coords)
        }
      },
      (locationError) => {
        if (!active) return

        console.error('Browser geolocation error:', locationError)

        setOnlineWeather((current) => ({
          ...current,
          loading: false,
          locationError:
            locationError.code === 1
              ? 'Allow browser location access to load local weather.'
              : 'Unable to detect your location.',
        }))
      },
      {
        enableHighAccuracy: false,
        maximumAge: 300000,
        timeout: 15000,
      }
    )

    refreshTimer = window.setInterval(() => {
      if (lastCoords) {
        lastWeatherCoords = lastCoords
        loadOnlineWeather(lastCoords)
      }
    }, 10 * 60 * 1000)

    return () => {
      active = false

      if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId)
      }

      if (refreshTimer !== null) {
        window.clearInterval(refreshTimer)
      }
    }
  }, [])

  const displayTemperature = formatDeviceTemperature(
    liveDevice?.temperature,
    connectionState === 'Online',
  )
  const displayHumidity = formatDeviceHumidity(
    liveDevice?.humidity,
    connectionState === 'Online',
  )

  useEffect(() => {
    let active = true

    async function loadHistory() {
      setHistoryLoading(true)

      try {
        const response = await getDetectionHistory({
          deviceId,
          limit: historyLimit,
          status: historyFilter === 'ALL' ? undefined : historyFilter,
        })

        if (!active) {
          return
        }

        setHistoryError('')
        const detections = Array.isArray(response?.detections) ? response.detections : []

        const visibleDetections = historyClearedAt
          ? detections.filter((item) => isAfterHistoryClear(item, historyClearedAt))
          : detections

        setHistory((current) => {
          const currentVisible = current.filter(
            (item) => isAfterHistoryClear(item, historyClearedAt),
          )

          return filterDetectionHistory(
            mergeDetections(currentVisible, visibleDetections),
            historyFilter,
          )
        })
      } catch (historyFetchError) {
        if (!active) {
          return
        }

        console.error('Unable to load detection history:', historyFetchError)
        setHistoryError('Detection history is temporarily unavailable. Please retry.')
      } finally {
        if (active) {
          setHistoryLoading(false)
        }
      }
    }

    loadHistory()

    return () => {
      active = false
    }
  }, [deviceId, historyFilter, historyLimit, historyClearedAt, historyRetryCount])

  useEffect(() => {
    if (!detection || detection.status !== 'HARMFUL_PEST') {
      return
    }

    const popupKey =
      detection.id != null
        ? `id:${detection.id}`
        : Number.isFinite(parseServerTimestamp(getDetectionTime(detection)))
          ? `time:${parseServerTimestamp(getDetectionTime(detection))}`
          : ''

    if (!popupKey || alertedKeysRef.current.has(popupKey)) {
      return
    }

    alertedKeysRef.current.add(popupKey)
    try {
      window.localStorage.setItem(
        ALERTED_DETECTIONS_KEY,
        JSON.stringify(Array.from(alertedKeysRef.current).slice(-200)),
      )
    } catch {
      // Keep deduplication in memory if storage is unavailable.
    }

    setPopup({
      pest: detection.pest || 'Unknown pest',
      confidence: detection.confidence,
      risk: detection.risk || '—',
      time: getDetectionTime(detection),
      deviceId: detection.device_id || deviceId,
    })
  }, [detection, deviceId])

  // Keep the newest live WebSocket detection visible in the history immediately.
  // Clearing history does not remove the current live detection.
  useEffect(() => {
    if (!detection) {
      return
    }

    if (!isAfterHistoryClear(detection, historyClearedAt)) {
      return
    }

    setHistory((current) => mergeDetections([detection], current))
  }, [detection, historyClearedAt])

  const filters = ['ALL', 'HARMFUL_PEST', 'NON_PEST']

  const historyWithLiveDetection = mergeDetections(history, detection ? [detection] : [])
    .filter((item) => isAfterHistoryClear(item, historyClearedAt))

  const filteredHistory = filterDetectionHistory(
    historyWithLiveDetection,
    historyFilter,
  )

  const canLoadMore = filteredHistory.length >= historyLimit

  return (
    <main className="monitoring-page">
      {popup && (
        <div className="harmful-alert-backdrop" onClick={() => setPopup(null)} aria-hidden="true">
          <div className="harmful-alert-popup" onClick={(event) => event.stopPropagation()} role="dialog" aria-live="assertive">
            <div className="popup-header">
              <span className="popup-badge">HARMFUL PEST DETECTED</span>
              <button type="button" className="popup-close" onClick={() => setPopup(null)} aria-label="Dismiss alert">
                ×
              </button>
            </div>

            <h3>{getDisplayPestName(popup.pest, pestDirectory)}</h3>
            <div className="popup-details">
              <div><span>Confidence</span><strong>{formatConfidence(popup.confidence)}</strong></div>
              <div><span>Risk</span><strong>{popup.risk}</strong></div>
              <div><span>Time</span><strong>{formatDate(popup.time)}</strong></div>
              <div><span>Device</span><strong>{popup.deviceId}</strong></div>
            </div>

            <div className="popup-actions">
              <button type="button" className="popup-primary" onClick={() => { setPopup(null); navigate(`/solutions?pest=${encodeURIComponent(popup.pest || '')}`) }}>
                View Solution
              </button>
              <button type="button" className="popup-secondary" onClick={() => setPopup(null)}>
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      <section className="monitoring-hero">
        <div className="monitoring-hero-copy">
          <p className="monitoring-eyebrow">Live field monitoring</p>
          <h1>Listen to the Field.<br /><em>Protect the Crop.</em></h1>
          <p>
            Monitor sound-based pest activity from the connected Pest Guard field unit and view the latest AI detection in real time.
          </p>
        </div>

        <div className={`system-status-card system-status-${connectionState.toLowerCase()}`}>
          <div className="status-card-label"><span className="monitoring-status-dot" />Live system</div>
          <strong>{connectionState}</strong>
          <small>
            {error
              ? 'Backend connection unavailable'
              : onlineWeather.loading
                ? 'Detecting location and loading weather'
                : onlineWeather.locationError ||
                  'REST + WebSocket + current-location weather'}
          </small>
        </div>
      </section>

      <section className="detection-control-panel" aria-label="Manual detection controls">
        <div className="detection-control-copy">
          <p className="monitoring-card-eyebrow">FIELD UNIT CONTROL</p>
          <h2>Detection Control</h2>
          <p>{detectionControlMessage}</p>
          {detectionControlError && (
            <p className="detection-control-error" role="alert">{detectionControlError}</p>
          )}
        </div>
        <div className="detection-control-actions">
            <span
              className={`detection-control-state ${
                detectionControlKnown ? detectionControlView.className : 'is-unknown'
              }`}
            >
              {!detectionControlKnown
                ? 'CONTROL UNKNOWN'
                : detectionControlView.label}
          </span>
          <button
            type="button"
            className="detection-control-button detection-control-start"
            onClick={() => handleDetectionControl(true)}
            disabled={detectionControlBusy || (detectionControlKnown && detectionControlView.enabled)}
          >
            {detectionControlBusy ? 'Please wait…' : 'Detect'}
          </button>
          <button
            type="button"
            className="detection-control-button detection-control-stop"
            onClick={() => handleDetectionControl(false)}
            disabled={detectionControlBusy || (detectionControlKnown && !detectionControlView.enabled)}
          >
            {detectionControlBusy ? 'Please wait…' : 'Stop'}
          </button>
        </div>
      </section>

      <section className="monitoring-grid">
        <article className={`monitoring-card latest-card latest-card-${statusClass}`}>
          <div className="monitoring-card-heading">
            <div>
              <p className="monitoring-card-eyebrow">AI classification</p>
              <h2>Latest Detection</h2>
            </div>
          </div>

          <div className="latest-detection-main">
            <span className="detection-indicator" />
            <div>
              {predictedPestName && (
                <small
                  className="top-match-label"
                  style={{
                    display: 'block',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    marginBottom: '0.25rem',
                  }}
                >
                  {getIdentificationLabel(displayDetection)}
                </small>
              )}
              <strong>
                {predictedPestName
                  ? insectGroup
                  : displayDetection
                    ? displayDetectionLabel === 'Inference error'
                      ? displayDetectionLabel
                      : displayDetectionLabel === 'Non-pest sound'
                        ? displayDetectionLabel
                        : 'Unidentified sound'
                    : loading
                      ? 'Connecting to field unit…'
                      : connectionState !== 'Online'
                        ? 'Device offline'
                        : detectionError
                          ? 'Detection data unavailable'
                          : detectionLoading
                            ? 'Checking for detections…'
                            : 'No detection received'}
              </strong>
              {predictedPestName && (
                <small className="latest-species-candidate">
                  Leading species candidate:{' '}
                  {getCandidateDisplayName(leadingSpeciesPrediction)}
                  {' · '}
                  {formatModelScore(leadingSpeciesPrediction.score)}
                  {' (uncalibrated score)'}
                </small>
              )}
            </div>
          </div>

          {displayDetection && (
            <p className="latest-identification-status">
              {predictedPestName
                ? 'Model prediction · '
                : !isUnconfirmedMatchStatus(displayDetectionLabel)
                  ? `${displayDetectionLabel} · `
                  : ''}
              Detected{' '}
              {formatDate(getDetectionTime(displayDetection))}
            </p>
          )}
          {detectionError && displayDetection && (
            <p className="latest-identification-status" role="status">
              Latest refresh failed; showing the most recently received record.
            </p>
          )}
          {topSpeciesPredictions.length > 0 && (
            <div className="monitoring-top-species">
              <h3>Top Species Predictions</h3>
              <ol>
                {topSpeciesPredictions.map((candidate, index) => (
                  <li key={`${candidate.pest}-${index}`}>
                    <span>
                      {getCandidateDisplayName(candidate)}
                      <small>Species candidate</small>
                    </span>
                    <strong>{formatModelScore(candidate.score)}</strong>
                  </li>
                ))}
              </ol>
            </div>
          )}
          <div className="detection-details">
            <div>
              <span>Group-level model score (uncalibrated)</span>
              <strong>{formatModelScore(displayDetection?.group_score)}</strong>
            </div>
            <div className={`latest-risk latest-risk-${riskEstimate.toLowerCase()}`}>
              <div className="latest-risk-heading">
                <span>Candidate risk</span>
                <strong>{displayDetection ? riskEstimate : '—'}</strong>
              </div>
              <div
                className="latest-risk-track"
                role="img"
                aria-label={`Risk level: ${displayDetection ? riskEstimate : 'unavailable'}`}
              >
                <span className="latest-risk-fill" />
              </div>
            </div>
            <div className="latest-device-id">
              <span>Device ID</span>
              <strong>{reportingDeviceId}</strong>
            </div>
          </div>
        </article>

        <article className="monitoring-card device-health-card">
          <div className="monitoring-card-heading">
            <div>
              <p className="monitoring-card-eyebrow">Field health</p>
              <h2>Device Health</h2>
            </div>
            <HealthIcon size={22} />
          </div>

          {error && (
            <div className="backend-notice">
              <strong>Backend connection unavailable</strong>
              <span>The device health panel is waiting for live field data.</span>
            </div>
          )}

          <div className="device-health-list">
            <div className="device-health-row">
              <span>Device ID</span>
              <strong>{deviceId}</strong>
            </div>
            <div className="device-health-row">
              <span>Connection</span>
              <strong className={`health-status ${healthTone}`}>
                <span className="status-indicator" />
                {connectionState}
              </strong>
            </div>
            <div className="device-health-row">
              <span>Status</span>
              <strong>{liveDevice?.status || '—'}</strong>
            </div>
            <div className="device-health-row">
              <span>Last Seen</span>
              <strong>{formatDate(deviceTimestamp)}</strong>
            </div>
            <div className="device-health-row">
              <span>Temperature</span>
              <strong>{displayTemperature}</strong>
            </div>
            <div className="device-health-row">
              <span>Humidity</span>
              <strong>{displayHumidity}</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="monitoring-secondary-grid">
        <article className="monitoring-card history-card">
          <div className="monitoring-card-heading">
            <div>
              <p className="monitoring-card-eyebrow">Recent events</p>
              <h2>Detection History</h2>
            </div>
            <div className="history-header-actions">
              <button
                type="button"
                className="history-filter"
                onClick={() => {
                  const clearedAt = new Date().toISOString()
                  try {
                    window.localStorage.setItem(HISTORY_CLEAR_KEY, clearedAt)
                  } catch {
                    // Ignore storage failures.
                  }
                  setHistoryClearedAt(clearedAt)
                  setHistory([])
                  setHistoryError('')
                  setHistoryLimit(8)
                  setHistoryLoading(false)
                }}
                disabled={history.length === 0}
              >
                Clear History
              </button>
              <SparkIcon size={21} />
            </div>
          </div>

          <div className="history-filters" role="tablist" aria-label="Detection history filters">
            {filters.map((filter) => (
              <button
                key={filter}
                type="button"
                className={filter === historyFilter ? 'history-filter active' : 'history-filter'}
                onClick={() => {
                  setHistoryFilter(filter)
                  setHistoryLimit(8)
                }}
              >
                {filter === 'ALL' ? 'All' : filter === 'HARMFUL_PEST' ? 'Harmful Pest' : 'Non-Pest'}
              </button>
            ))}
          </div>

          {historyLoading && <p className="inline-loading">Loading detection history...</p>}

          {!historyLoading && historyError && filteredHistory.length === 0 && (
            <div className="empty-history" role="alert">
              <strong>Unable to Load History</strong>
              <p>{historyError}</p>
              <button
                type="button"
                className="history-filter"
                onClick={() => setHistoryRetryCount((count) => count + 1)}
              >
                Retry
              </button>
            </div>
          )}

          {!historyLoading && !historyError && filteredHistory.length === 0 && (
            <div className="empty-history">
              <strong>No Detection History</strong>
              <p>The field unit has not recorded any detection events yet.</p>
            </div>
          )}

          {filteredHistory.length > 0 && (
            <div className="history-list">
              {filteredHistory.map((item) => {
                const scientificName = String(item.pest || '').trim()
                const topCandidates = getTopSpeciesPredictions(item.top_predictions)

                return (
                  <div key={getDetectionHistoryKey(item)} className="history-row">
                    <div className="history-main">
                      <span className="history-time">{formatDate(getDetectionTime(item))}</span>
                      <strong>
                        {scientificName
                          ? getDetectionInsectGroup(item)
                          : getDetectionDisplayStatus(item) === 'Inference error'
                            ? 'Inference error'
                            : getDetectionDisplayStatus(item) === 'Non-pest sound'
                              ? 'Non-pest sound'
                              : 'Unidentified sound'}
                      </strong>
                      {scientificName && (
                        <small>
                          Top species candidate: {getCandidateDisplayName({
                            pest: scientificName,
                            common_name: item.common_name,
                          })}
                        </small>
                      )}
                      {topCandidates.length > 0 && (
                        <div className="history-top-species">
                          <strong>Top Species Predictions</strong>
                          <ol>
                            {topCandidates.map((candidate, index) => (
                              <li key={`${candidate.pest}-${index}`}>
                                {getCandidateDisplayName(candidate)}
                                {' · '}
                                {formatModelScore(candidate.score)}
                               
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}
                      {scientificName && (
                        <small className="history-uncertainty">
                          {getPredictionUncertainty(item)}
                        </small>
                      )}
                      {!isUnconfirmedMatchStatus(getDetectionDisplayStatus(item)) && (
                        <small>{getDetectionDisplayStatus(item)}</small>
                      )}
                    </div>

                    <div className="history-meta">
                      {String(item.status || '').toUpperCase() !== 'UNKNOWN' &&
                        !isUnconfirmedMatchStatus(item.status) && (
                        <span>{item.status}</span>
                      )}
                      <strong>{formatConfidence(item.confidence)}</strong>
                      <small>Species score</small>
                      <strong>{formatModelScore(item.group_score)}</strong>
                      <small>Group score</small>
                      <strong>{getDetectionRiskEstimate(item, pestDirectory).risk}</strong>
                      <strong>{item.device_id || deviceId}</strong>
                    </div>
                  </div>
                )
              })}

              {canLoadMore && (
                <button type="button" className="history-load-more" onClick={() => setHistoryLimit((value) => value + 8)}>
                  Load more
                </button>
              )}
            </div>
          )}
        </article>
      </section>

      <section className="monitoring-support-grid">
        <article className="sensor-summary monitoring-card">
          <div className="monitoring-card-heading"><div><p className="monitoring-card-eyebrow">Hardware stack</p><h2>Sensor Summary</h2></div><SparkIcon size={21} /></div>
          <div className="sensor-list">
            <div><span>Acoustic sensor</span><strong>INMP441</strong></div>
            <div><span>Vibration sensor</span><strong>Piezoelectric Vibration Module</strong></div>
            <div><span>Controller</span><strong>ESP32-S3 N16R8</strong></div>
            <div><span>Connection</span><strong>Wi-Fi</strong></div>
          </div>
        </article>

        <article className="flow-card monitoring-card">
          <div className="monitoring-card-heading"><div><p className="monitoring-card-eyebrow">System path</p><h2>Detection Flow</h2></div><ArrowIcon size={21} /></div>
          <div className="detection-flow"><span>Sound + Vibration</span><i>↓</i><span>ESP32-S3</span><i>↓</i><span>AI CNN</span><i>↓</i><span>FastAPI</span><i>↓</i><span>Pest Guard</span></div>
        </article>
      </section>

      <p className="monitoring-note">Pest Guard combines field sensing and AI classification to support earlier, more informed crop protection decisions.</p>
    </main>
  )
}

export default LiveMonitoring
