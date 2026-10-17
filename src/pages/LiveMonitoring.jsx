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
  normalizePestName,
} from '../utils/pestNames'
import {
  getDetectionTime,
  isAfterHistoryClear,
  mergeDetections,
  parseServerTimestamp,
} from '../utils/detectionHistory'
import './LiveMonitoring.css'

const HISTORY_CLEAR_KEY = 'pest_guard_history_cleared_at'
const ALERTED_DETECTIONS_KEY = 'pest_guard_alerted_detection_keys'

function formatOnlineTemperature(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)} °C` : '—'
}

function formatOnlineHumidity(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(0)}%` : '—'
}

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

function formatDetectionConfidence(value) {
  if (value === null || value === undefined || value === '') {
    return 'N/A'
  }

  const number = Number(value)
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : 'N/A'
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
  const { detection, device, loading, error } = useLiveDetection()
  const [history, setHistory] = useState([])
  const [historyFilter, setHistoryFilter] = useState('ALL')
  const [historyLimit, setHistoryLimit] = useState(8)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const [historyRetryCount, setHistoryRetryCount] = useState(0)
  const [historyClearedAt, setHistoryClearedAt] = useState(() => getStoredClearTime())
  const [popup, setPopup] = useState(null)
  const [detectionControlEnabled, setDetectionControlEnabled] = useState(false)
  const [detectionControlBusy, setDetectionControlBusy] = useState(false)
  const [detectionControlError, setDetectionControlError] = useState('')
  const [detectionControlMessage, setDetectionControlMessage] = useState('Detection is stopped.')
  const [pestDirectory, setPestDirectory] = useState({})
  const alertedKeysRef = useRef(getStoredAlertedKeys())

  const liveDetection = detection || history[0] || null

  const detectionCandidates = mergeDetections(
    history,
    detection ? [detection] : [],
  ).filter((item) => {
    const timestamp = parseServerTimestamp(getDetectionTime(item))
    const sameDevice = !device?.device_id || !item.device_id || item.device_id === device.device_id
    return Number.isFinite(timestamp) &&
      timestamp <= Date.now() + 5000 &&
      sameDevice &&
      typeof item.pest === 'string' && item.pest.trim() !== ''
  })

  // Keep the latest valid candidate visible until a newer candidate arrives.
  const displayDetection = detectionCandidates[0] || null
  const liveDevice = device || (liveDetection ? {
    device_id: liveDetection.device_id || 'FIELD-UNIT-01',
    status: 'OFFLINE',
    connection: 'DISCONNECTED',
    last_seen: liveDetection.detected_at || liveDetection.timestamp || null,
    temperature: liveDetection.temperature ?? null,
    humidity: liveDetection.humidity ?? null,
  } : null)

  const connectionState = getConnectionState(liveDevice, loading)
  const detectionStatus = displayDetection?.status || liveDetection?.status || ''
  const statusClass = detectionStatus === 'HARMFUL_PEST'
    ? 'harmful'
    : detectionStatus === 'NON_PEST'
      ? 'normal'
      : detectionStatus === 'UNKNOWN'
        ? 'unknown'
        : 'empty'
  const deviceId = liveDevice?.device_id || liveDetection?.device_id || 'FIELD-UNIT-01'


  // PEST_GUARD_DETECTION_CONTROL_HANDLERS
  useEffect(() => {
    let active = true

    getDetectionControl(deviceId)
      .then((result) => {
        if (!active) return
        const enabled = Boolean(result?.enabled)
        setDetectionControlEnabled(enabled)
        setDetectionControlMessage(
          enabled ? 'Detection is running.' : 'Detection is stopped.'
        )
        setDetectionControlError('')
      })
      .catch((controlError) => {
        if (!active) return
        setDetectionControlError(`Unable to read device control: ${controlError.message}`)
      })

    return () => {
      active = false
    }
  }, [deviceId])

  const handleDetectionControl = async (enabled) => {
    setDetectionControlBusy(true)
    setDetectionControlError('')

    try {
      const result = await setDetectionEnabled(deviceId, enabled)
      const accepted = Boolean(result?.enabled)
      setDetectionControlEnabled(accepted)
      setDetectionControlMessage(
        accepted
          ? 'Detect requested. The field unit will start at its next control check.'
          : 'Stop requested. A detection cycle already in progress may finish.'
      )
    } catch (controlError) {
      setDetectionControlError(`Control request failed: ${controlError.message}`)
    } finally {
      setDetectionControlBusy(false)
    }
  }
  const deviceTimestamp = liveDevice?.last_seen || liveDevice?.lastSeen
  const healthTone = connectionState === 'Online' ? 'online' : 'offline'
  const predictedPestName =
    typeof displayDetection?.pest === 'string' ? displayDetection.pest.trim() : ''
  const riskDetails = getDetectionRiskEstimate(displayDetection, pestDirectory)
  const riskEstimate = riskDetails.risk
  const matchingPestRecord =
    pestDirectory[normalizePestName(predictedPestName)]
  const predictedScientificName =
    displayDetection?.scientific_name ||
    matchingPestRecord?.scientificName ||
    ''
  const predictedPestDisplayName = predictedPestName
    ? getDisplayPestName(
        predictedPestName,
        pestDirectory,
        displayDetection,
      )
    : ''
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

  const displayTemperature = onlineWeather.temperature
  const displayHumidity = onlineWeather.humidity

  useEffect(() => {
    let active = true

    async function loadHistory() {
      setHistoryLoading(true)

      try {
        const response = await getDetectionHistory({
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
            (item) =>
              (historyFilter === 'ALL' || item.status === historyFilter) &&
              isAfterHistoryClear(item, historyClearedAt),
          )

          return mergeDetections(currentVisible, visibleDetections)
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
  }, [historyFilter, historyLimit, historyClearedAt, historyRetryCount])

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

  const filteredHistory = historyWithLiveDetection.filter((item) => {
    if (historyFilter === 'ALL') {
      return true
    }

    return item.status === historyFilter
  })

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
          <span className={`detection-control-state ${detectionControlEnabled ? 'is-running' : 'is-stopped'}`}>
            {detectionControlEnabled ? 'RUNNING' : 'STOPPED'}
          </span>
          <button
            type="button"
            className="detection-control-button detection-control-start"
            onClick={() => handleDetectionControl(true)}
            disabled={detectionControlBusy || detectionControlEnabled}
          >
            {detectionControlBusy ? 'Please wait…' : 'Detect'}
          </button>
          <button
            type="button"
            className="detection-control-button detection-control-stop"
            onClick={() => handleDetectionControl(false)}
            disabled={detectionControlBusy || !detectionControlEnabled}
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
              <strong>
                {predictedPestName
                  ? predictedPestDisplayName
                  : 'No pest detected yet'}
              </strong>
              {predictedPestName && (
                <small className="latest-identification-detail">
                  {predictedScientificName
                    ? `Scientific name: ${predictedScientificName}`
                    : `Scientific name unavailable; model class: ${predictedPestName}`}
                </small>
              )}
            </div>
          </div>

          {displayDetection && (
            <p className="latest-identification-status">
              Unverified model prediction · Detected {formatDate(getDetectionTime(displayDetection))}
            </p>
          )}

          {matchingPestRecord?.description || matchingPestRecord?.symptoms ? (
            <div className="latest-catalog-reference">
              <strong>Catalogue reference (not identification confirmation)</strong>
              {matchingPestRecord.description && <p>{matchingPestRecord.description}</p>}
              {matchingPestRecord.symptoms && (
                <p><b>Symptoms:</b> {matchingPestRecord.symptoms}</p>
              )}
            </div>
          ) : null}

          <div className="detection-details">
            <div>
              <span>Model score (not calibrated confidence)</span>
              <strong>{formatDetectionConfidence(displayDetection?.confidence)}</strong>
            </div>
            <div className={`latest-risk latest-risk-${riskEstimate.toLowerCase()}`}>
              <div className="latest-risk-heading">
                <span>Risk Level</span>
                <strong>{riskEstimate}</strong>
              </div>
              <small>
                {riskEstimate === 'UNKNOWN' ? (
                  'No evidence-backed risk tier is available; this is not evidence of low risk.'
                ) : (
                  <>
                    General estimate; not site-specific.
                    {riskDetails.sourceUrl ? (
                      <> Source: <a href={riskDetails.sourceUrl} target="_blank" rel="noreferrer">{riskDetails.source}</a></>
                    ) : riskDetails.source ? (
                      <> Source: {riskDetails.source}</>
                    ) : (
                      ' Classification source unavailable.'
                    )}
                  </>
                )}
              </small>
              {riskDetails.rationale && (
                <small>{riskDetails.rationale}</small>
              )}
              {Array.isArray(displayDetection?.affected_crops) &&
                displayDetection.affected_crops.length > 0 && (
                  <small>
                    Documented affected crops: {displayDetection.affected_crops.join(', ')}
                  </small>
                )}
              <div
                className="latest-risk-track"
                role="img"
                aria-label={`Risk level: ${riskEstimate}`}
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
              <strong>{formatOnlineTemperature(displayTemperature)}</strong>
            </div>
            <div className="device-health-row">
              <span>Humidity</span>
              <strong>{formatOnlineHumidity(displayHumidity)}</strong>
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
              {filteredHistory.map((item) => (
                <div key={item.id ?? `${item.device_id}-${item.detected_at}`} className="history-row">
                  <div className="history-main">
                    <span className="history-time">{formatDate(getDetectionTime(item))}</span>
                    <strong>
                      {getDisplayPestName(item.pest, pestDirectory)}
                    </strong>
                  </div>

                  <div className="history-meta">
                    {String(item.status || '').toUpperCase() !== 'UNKNOWN' && (
                      <span>{item.status}</span>
                    )}
                    <strong>{formatConfidence(item.confidence)}</strong>
                    <strong>{getDetectionRiskEstimate(item, pestDirectory).risk}</strong>
                    <strong>{item.device_id || deviceId}</strong>
                  </div>
                </div>
              ))}

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
