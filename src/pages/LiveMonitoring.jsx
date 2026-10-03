import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useLiveDetection } from '../hooks/useLiveDetection'
import { ArrowIcon, LeafIcon, SparkIcon } from '../components/Icons'
import { getDetectionHistory, getPests } from '../services/api'
import './LiveMonitoring.css'

const HISTORY_CLEAR_KEY = 'pest_guard_history_cleared_at'
const WEATHER_CACHE_KEY = 'pest_guard_online_weather'

const FALLBACK_COMMON_PEST_NAMES = {
  Popplepsaltanotialis: 'Cicada',
  Yoyettarepetens: 'Cicada',
  Yoyettacelis: 'Cicada',
  Neotibicenpruinosus: 'Cicada',
  Atrapsaltaencaustica: 'Cicada',
  Achetadomesticus: 'House Cricket',
  Grylluscampestris: 'Field Cricket',
  Gryllusbimaculatus: 'Two-spotted Cricket',
  Chorthippusvagans: 'Heath Grasshopper',
  Pseudochorthippusparallelus: 'Meadow Grasshopper',
  Oecanthuspellucens: 'European Tree Cricket',
  Roeselianaroeselii: "Roesel's Bush-cricket",
}

function normalizePestKey(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

function buildPestDirectory(items) {
  const directory = {}

  if (!Array.isArray(items)) {
    return directory
  }

  items.forEach((item) => {
    const commonName = String(item?.name || '').trim()
    const scientificName = String(item?.scientific_name || '').trim()
    const pestId = String(item?.pest_id || '').trim()

    const entry = {
      commonName:
        commonName &&
        normalizePestKey(commonName) !== normalizePestKey(scientificName)
          ? commonName
          : '',
      scientificName,
    }

    ;[commonName, scientificName, pestId].forEach((candidate) => {
      const key = normalizePestKey(candidate)
      if (key) {
        directory[key] = entry
      }
    })
  })

  return directory
}

function getFallbackPestName(pest) {
  const key = normalizePestKey(pest)
  if (!key) {
    return ''
  }

  const fallbackEntry = Object.entries(FALLBACK_COMMON_PEST_NAMES).find(
    ([scientificName]) => normalizePestKey(scientificName) === key,
  )

  return fallbackEntry?.[1] || ''
}


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

function getDetectionTime(item) {
  return item?.detected_at || item?.timestamp || item?.created_at || null
}

function parseServerTimestamp(value) {
  if (!value) {
    return NaN
  }

  const text = String(value).trim()

  if (!text) {
    return NaN
  }

  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text)
  const normalized = hasTimezone ? text : `${text}Z`
  const timestamp = new Date(normalized).getTime()

  return Number.isFinite(timestamp) ? timestamp : NaN
}

function isAfterHistoryClear(item, clearedAt) {
  if (!clearedAt) {
    return true
  }

  const clearedAtMs = parseServerTimestamp(clearedAt)
  const detectionTimeMs = parseServerTimestamp(getDetectionTime(item))

  if (!Number.isFinite(clearedAtMs)) {
    return true
  }

  return Number.isFinite(detectionTimeMs) && detectionTimeMs > clearedAtMs
}

function sameDetection(first, second) {
  if (first?.id != null && second?.id != null) {
    return String(first.id) === String(second.id)
  }

  const firstTime = parseServerTimestamp(getDetectionTime(first))
  const secondTime = parseServerTimestamp(getDetectionTime(second))

  return Number.isFinite(firstTime) && firstTime === secondTime
}

function sortNewestFirst(detections) {
  return detections.sort((first, second) => {
    const firstTime = parseServerTimestamp(getDetectionTime(first))
    const secondTime = parseServerTimestamp(getDetectionTime(second))

    if (!Number.isFinite(firstTime) && !Number.isFinite(secondTime)) return 0
    if (!Number.isFinite(firstTime)) return 1
    if (!Number.isFinite(secondTime)) return -1
    return secondTime - firstTime
  })
}

function mergeDetections(...groups) {
  const merged = []

  groups.flat().forEach((detection) => {
    if (!merged.some((existing) => sameDetection(existing, detection))) {
      merged.push(detection)
    }
  })

  return sortNewestFirst(merged)
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

function formatDate(value) {
  if (!value) {
    return '—'
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

function displayStatus(status, pest) {
  if (status === 'HARMFUL_PEST') return 'HARMFUL PEST'
  if (status === 'NON_PEST') return 'NON-PEST'
  if (status === 'UNKNOWN' && pest) return 'AI PREDICTION'
  if (status === 'UNKNOWN') return 'UNKNOWN SOUND'
  return 'NO DETECTION'
}

function getDetectionMessage(status, pest) {
  if (status === 'HARMFUL_PEST') return 'Harmful pest activity detected in the field.'
  if (status === 'NON_PEST') return 'No harmful pest detected.'
  if (status === 'UNKNOWN' && pest) return 'The AI predicted this insect sound, but confidence is below the harmful-pest alert threshold.'
  if (status === 'UNKNOWN') return 'Waiting for a confident pest prediction.'
  return 'Waiting for an event from the field unit.'
}

function getConnectionState(device, loading) {
  if (loading) return 'Connecting'
  if (!device) return 'Offline'

  const value = String(device.connection || device.status || '').toUpperCase()
  return value === 'CONNECTED' || value === 'ONLINE' ? 'Online' : 'Offline'
}

function getConfidenceTone(value) {
  if (value === null || value === undefined || value === '') {
    return 'empty'
  }

  const number = Number(value)

  if (!Number.isFinite(number)) {
    return 'empty'
  }

  if (number >= 0.7) return 'high'
  if (number >= 0.4) return 'medium'
  return 'low'
}

function LiveMonitoring() {
  const navigate = useNavigate()
  const { detection, newDetection, device, loading, error } = useLiveDetection()
  const [history, setHistory] = useState([])
  const [historyFilter, setHistoryFilter] = useState('ALL')
  const [historyLimit, setHistoryLimit] = useState(8)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyClearedAt, setHistoryClearedAt] = useState(() => getStoredClearTime())
  const [popup, setPopup] = useState(null)
  const [pestDirectory, setPestDirectory] = useState({})
  const alertedKeysRef = useRef(new Set())

  const liveDetection = detection || history[0] || null
  const liveDevice = device || (liveDetection ? {
    device_id: liveDetection.device_id || 'FIELD-UNIT-01',
    status: 'ONLINE',
    connection: 'CONNECTED',
    last_seen: liveDetection.detected_at || liveDetection.timestamp || null,
    temperature: liveDetection.temperature ?? null,
    humidity: liveDetection.humidity ?? null,
  } : null)

  const connectionState = getConnectionState(liveDevice, loading)
  const detectionStatus = liveDetection?.status || ''
  const statusClass = detectionStatus === 'HARMFUL_PEST'
    ? 'harmful'
    : detectionStatus === 'NON_PEST'
      ? 'normal'
      : detectionStatus === 'UNKNOWN'
        ? 'unknown'
        : 'empty'
  const deviceId = liveDevice?.device_id || liveDetection?.device_id || 'FIELD-UNIT-01'
  const deviceTimestamp = liveDevice?.last_seen || liveDevice?.lastSeen
  const confidenceValue = Number(liveDetection?.confidence)
  const confidencePercent = Number.isFinite(confidenceValue)
    ? confidenceValue * 100
    : null
  const healthTone = connectionState === 'Online' ? 'online' : 'offline'

  function getDisplayPestName(pest) {
    const rawName = String(pest || '').trim()

    if (!rawName) {
      return 'Unknown pest'
    }

    const entry = pestDirectory[normalizePestKey(rawName)]
    const entryCommonName = String(entry?.commonName || '').trim()
    const fallbackName = getFallbackPestName(rawName)
    const scientificName = String(entry?.scientificName || rawName).trim()

    const commonName =
      entryCommonName &&
      normalizePestKey(entryCommonName) !== normalizePestKey(rawName)
        ? entryCommonName
        : fallbackName

    if (commonName && normalizePestKey(commonName) !== normalizePestKey(scientificName)) {
      return `${commonName} (${scientificName})`
    }

    return rawName
  }

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
  const [onlineWeather, setOnlineWeather] = useState(() => {
    try {
      const cached = JSON.parse(window.localStorage.getItem(WEATHER_CACHE_KEY) || 'null')
      if (cached && Number.isFinite(Number(cached.temperature)) && Number.isFinite(Number(cached.humidity))) {
        return {
          temperature: Number(cached.temperature),
          humidity: Number(cached.humidity),
          loading: false,
        }
      }
    } catch {
      // Ignore invalid cached weather.
    }

    return { temperature: null, humidity: null, loading: true }
  })

  useEffect(() => {
    let active = true

    async function loadOnlineWeather() {
      try {
        const response = await fetch(
          'https://api.open-meteo.com/v1/forecast?latitude=12.9716&longitude=77.5946&current=temperature_2m,relative_humidity_2m&timezone=auto',
        )

        if (!response.ok) {
          throw new Error(`Weather request failed: ${response.status}`)
        }

        const data = await response.json()
        const current = data?.current || {}

        const temperature = Number(current.temperature_2m)
        const humidity = Number(current.relative_humidity_2m)

        if (!Number.isFinite(temperature) || !Number.isFinite(humidity)) {
          throw new Error('Weather response did not contain temperature and humidity.')
        }

        const nextWeather = {
          temperature,
          humidity,
          loading: false,
        }

        try {
          window.localStorage.setItem(
            WEATHER_CACHE_KEY,
            JSON.stringify({ temperature, humidity, updatedAt: new Date().toISOString() }),
          )
        } catch {
          // Ignore storage failures.
        }

        if (active) {
          setOnlineWeather(nextWeather)
        }
      } catch (weatherError) {
        console.error('Unable to load online weather:', weatherError)
        if (active) {
          setOnlineWeather((current) => ({
            temperature: current.temperature ?? null,
            humidity: current.humidity ?? null,
            loading: false,
          }))
        }
      }
    }

    loadOnlineWeather()
    const refreshTimer = window.setInterval(loadOnlineWeather, 10 * 60 * 1000)

    return () => {
      active = false
      window.clearInterval(refreshTimer)
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
  }, [historyFilter, historyLimit, historyClearedAt])

  useEffect(() => {
    if (!newDetection || newDetection.status !== 'HARMFUL_PEST') {
      return
    }

    const popupKey =
      newDetection.id ??
      parseServerTimestamp(getDetectionTime(newDetection))

    if (popupKey == null || String(popupKey) === '' || alertedKeysRef.current.has(String(popupKey))) {
      return
    }

    alertedKeysRef.current.add(String(popupKey))
    setPopup({
      pest: newDetection.pest || 'Unknown pest',
      confidence: newDetection.confidence,
      risk: newDetection.risk || '—',
      time: getDetectionTime(newDetection),
      deviceId: newDetection.device_id || deviceId,
    })
  }, [newDetection, deviceId])

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

  const filters = ['ALL', 'HARMFUL_PEST', 'NON_PEST', 'UNKNOWN']

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

            <h3>{getDisplayPestName(popup.pest)}</h3>
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
          <small>{error ? 'Backend connection unavailable' : onlineWeather.loading ? 'Loading online weather' : 'REST + WebSocket + online weather'}</small>
        </div>
      </section>

      <section className="monitoring-grid">
        <article className={`monitoring-card latest-card latest-card-${statusClass}`}>
          <div className="monitoring-card-heading">
            <div>
              <p className="monitoring-card-eyebrow">AI classification</p>
              <h2>Latest Detection</h2>
            </div>
            <span className="detection-status-pill">{displayStatus(detectionStatus, liveDetection?.pest)}</span>
          </div>

          {liveDetection ? (
            <>
              <div className="latest-detection-main">
                <span className="detection-indicator" />
                <div>
                  <strong>{getDisplayPestName(liveDetection.pest)}</strong>
                  <p>{getDetectionMessage(detectionStatus, liveDetection.pest)}</p>
                </div>
              </div>

              <div className="confidence-visual">
                <div className="confidence-header">
                  <span>AI Confidence</span>
                  <strong>{confidencePercent === null ? 'Confidence —' : `${confidencePercent.toFixed(1)}%`}</strong>
                </div>

                {confidencePercent === null ? (
                  <p className="confidence-empty">No confidence value available.</p>
                ) : (
                  <div className="confidence-bar-wrap">
                    <div
                      className={`confidence-bar-fill ${getConfidenceTone(liveDetection.confidence)}`}
                      style={{ width: `${Math.min(Math.max(confidencePercent, 0), 100)}%` }}
                    />
                  </div>
                )}
              </div>

              <div className="detection-details">
                <div><span>Pest</span><strong>{getDisplayPestName(liveDetection.pest)}</strong></div>
                <div><span>Status</span><strong>{displayStatus(detectionStatus, liveDetection.pest)}</strong></div>
                <div><span>Confidence</span><strong>{formatConfidence(liveDetection.confidence)}</strong></div>
                <div><span>Risk</span><strong>{liveDetection.risk || '—'}</strong></div>
                <div><span>Date / time</span><strong>{formatDate(liveDetection.detected_at || liveDetection.timestamp)}</strong></div>
                <div><span>Device ID</span><strong>{liveDetection.device_id || deviceId}</strong></div>
                <div><span>Temperature</span><strong>{formatOnlineTemperature(displayTemperature)}</strong></div>
                <div><span>Humidity</span><strong>{formatOnlineHumidity(displayHumidity)}</strong></div>
              </div>
            </>
          ) : (
            <div className="no-detection-state">
              <div className="no-detection-icon"><LeafIcon size={23} /></div>
              <strong>No Detection Yet</strong>
              <p>Waiting for the field unit to send an AI detection.</p>
            </div>
          )}
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
              <span>Temperature (Online)</span>
              <strong>{formatOnlineTemperature(displayTemperature)}</strong>
            </div>
            <div className="device-health-row">
              <span>Humidity (Online)</span>
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
                {filter === 'ALL' ? 'All' : filter === 'HARMFUL_PEST' ? 'Harmful Pest' : filter === 'NON_PEST' ? 'Non-Pest' : 'Unknown'}
              </button>
            ))}
          </div>

          {historyLoading && <p className="inline-loading">Loading detection history...</p>}

          {!historyLoading && filteredHistory.length === 0 && (
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
                    <strong>{getDisplayPestName(item.pest)}</strong>
                  </div>

                  <div className="history-meta">
                    <span>{item.status || 'UNKNOWN'}</span>
                    <strong>{formatConfidence(item.confidence)}</strong>
                    <strong>{item.risk || '—'}</strong>
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
