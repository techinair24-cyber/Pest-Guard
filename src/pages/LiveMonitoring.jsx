import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useLiveDetection } from '../hooks/useLiveDetection'
import { ArrowIcon, LeafIcon, SparkIcon } from '../components/Icons'
import { formatTemperature, formatHumidity } from '../utils/formatters'
import { getDetectionHistory } from '../services/api'
import './LiveMonitoring.css'

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
  const { detection, device, loading, error } = useLiveDetection()
  const [history, setHistory] = useState([])
  const [historyFilter, setHistoryFilter] = useState('ALL')
  const [historyLimit, setHistoryLimit] = useState(8)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [popup, setPopup] = useState(null)
  const alertedKeyRef = useRef(null)
  const initialLoadRef = useRef(false)

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
  const [onlineWeather, setOnlineWeather] = useState({ temperature: null, humidity: null, loading: true })

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

        if (active) {
          setOnlineWeather({
            temperature: Number.isFinite(Number(current.temperature_2m)) ? Number(current.temperature_2m) : null,
            humidity: Number.isFinite(Number(current.relative_humidity_2m)) ? Number(current.relative_humidity_2m) : null,
            loading: false,
          })
        }
      } catch (weatherError) {
        console.error('Unable to load online weather:', weatherError)
        if (active) {
          setOnlineWeather({ temperature: null, humidity: null, loading: false })
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

  const displayTemperature = liveDetection?.temperature ?? liveDevice?.temperature ?? onlineWeather.temperature
  const displayHumidity = liveDetection?.humidity ?? liveDevice?.humidity ?? onlineWeather.humidity

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

        setHistory(response?.detections || [])
      } catch (historyFetchError) {
        if (!active) {
          return
        }

        console.error('Unable to load detection history:', historyFetchError)
        setHistory([])
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
  }, [historyFilter, historyLimit])

  useEffect(() => {
    if (!liveDetection) {
      return
    }

    if (!initialLoadRef.current) {
      initialLoadRef.current = true
      return
    }

    if (liveDetection.status !== 'HARMFUL_PEST') {
      return
    }

    const popupKey = liveDetection.id ?? liveDetection.detected_at ?? liveDetection.timestamp

    if (!popupKey || popupKey === alertedKeyRef.current) {
      return
    }

    alertedKeyRef.current = popupKey
    setPopup({
      pest: liveDetection.pest || 'Unknown pest',
      confidence: liveDetection.confidence,
      risk: liveDetection.risk || '—',
      time: liveDetection.detected_at || liveDetection.timestamp,
      deviceId: liveDetection.device_id || deviceId,
    })
  }, [liveDetection, deviceId])

  // Add each new WebSocket detection to the visible history immediately.
  // The existing Clear History button remains UI-only until a new detection arrives.
  useEffect(() => {
    if (!detection) {
      return
    }

    const detectionKey = detection.id ?? detection.detected_at ?? detection.timestamp

    if (!detectionKey) {
      return
    }

    setHistory((current) => {
      const alreadyExists = current.some(
        (item) => (item.id ?? item.detected_at ?? item.timestamp) === detectionKey,
      )

      if (alreadyExists) {
        return current
      }

      return [detection, ...current]
    })
  }, [detection])

  const filters = ['ALL', 'HARMFUL_PEST', 'NON_PEST', 'UNKNOWN']
  const filteredHistory = history.filter((item) => {
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

            <h3>{popup.pest}</h3>
            <div className="popup-details">
              <div><span>Confidence</span><strong>{formatConfidence(popup.confidence)}</strong></div>
              <div><span>Risk</span><strong>{popup.risk}</strong></div>
              <div><span>Time</span><strong>{formatDate(popup.time)}</strong></div>
              <div><span>Device</span><strong>{popup.deviceId}</strong></div>
            </div>

            <div className="popup-actions">
              <button type="button" className="popup-primary" onClick={() => { setPopup(null); navigate('/solutions') }}>
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
          <small>{error ? 'Backend connection unavailable' : 'REST + WebSocket monitoring'}</small>
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
                  <strong>{liveDetection.pest || displayStatus(detectionStatus, liveDetection.pest)}</strong>
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
                <div><span>Pest</span><strong>{liveDetection.pest || '—'}</strong></div>
                <div><span>Status</span><strong>{displayStatus(detectionStatus, liveDetection.pest)}</strong></div>
                <div><span>Confidence</span><strong>{formatConfidence(liveDetection.confidence)}</strong></div>
                <div><span>Risk</span><strong>{liveDetection.risk || '—'}</strong></div>
                <div><span>Date / time</span><strong>{formatDate(liveDetection.detected_at || liveDetection.timestamp)}</strong></div>
                <div><span>Device ID</span><strong>{liveDetection.device_id || deviceId}</strong></div>
                <div><span>Temperature</span><strong>{formatTemperature(displayTemperature)}</strong></div>
                <div><span>Humidity</span><strong>{formatHumidity(displayHumidity)}</strong></div>
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
              <strong>{formatTemperature(displayTemperature)}</strong>
            </div>
            <div className="device-health-row">
              <span>Humidity (Online)</span>
              <strong>{formatHumidity(displayHumidity)}</strong>
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
                  setHistory([])
                  setHistoryLimit(8)
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

          {!historyLoading && filteredHistory.length > 0 && (
            <div className="history-list">
              {filteredHistory.map((item) => (
                <div key={item.id ?? `${item.device_id}-${item.detected_at}`} className="history-row">
                  <div className="history-main">
                    <span className="history-time">{formatDate(item.detected_at)}</span>
                    <strong>{item.pest || displayStatus(item.status, item.pest)}</strong>
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
