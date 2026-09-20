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

function displayStatus(status) {
  if (status === 'HARMFUL_PEST') return 'HARMFUL PEST'
  if (status === 'NON_PEST') return 'NON-PEST'
  if (status === 'UNKNOWN') return 'UNKNOWN SOUND'
  return 'NO DETECTION'
}

function getDetectionMessage(status) {
  if (status === 'HARMFUL_PEST') return 'Harmful pest activity detected in the field.'
  if (status === 'NON_PEST') return 'No harmful pest detected.'
  if (status === 'UNKNOWN') return 'The sound could not be confidently classified.'
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

  const connectionState = getConnectionState(device, loading)
  const detectionStatus = detection?.status || ''
  const statusClass = detectionStatus === 'HARMFUL_PEST'
    ? 'harmful'
    : detectionStatus === 'NON_PEST'
      ? 'normal'
      : detectionStatus === 'UNKNOWN'
        ? 'unknown'
        : 'empty'
  const deviceId = device?.device_id || detection?.device_id || 'FIELD-UNIT-01'
  const deviceTimestamp = device?.last_seen || device?.lastSeen
  const latestTemperature = detection?.temperature ?? device?.temperature ?? null
  const latestHumidity = detection?.humidity ?? device?.humidity ?? null
  const confidenceValue = Number(detection?.confidence)
  const confidencePercent = Number.isFinite(confidenceValue)
    ? confidenceValue * 100
    : null
  const healthTone = connectionState === 'Online' ? 'online' : 'offline'

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
    if (!detection) {
      return
    }

    if (!initialLoadRef.current) {
      initialLoadRef.current = true
      return
    }

    if (detection.status !== 'HARMFUL_PEST') {
      return
    }

    const popupKey = detection.id ?? detection.detected_at ?? detection.timestamp

    if (!popupKey || popupKey === alertedKeyRef.current) {
      return
    }

    alertedKeyRef.current = popupKey
    setPopup({
      pest: detection.pest || 'Unknown pest',
      confidence: detection.confidence,
      risk: detection.risk || '—',
      time: detection.detected_at || detection.timestamp,
      deviceId: detection.device_id || deviceId,
    })
  }, [detection, deviceId])

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
            <span className="detection-status-pill">{displayStatus(detectionStatus)}</span>
          </div>

          {detection ? (
            <>
              <div className="latest-detection-main">
                <span className="detection-indicator" />
                <div>
                  <strong>{detectionStatus === 'HARMFUL_PEST' ? detection.pest || 'Pest not identified' : displayStatus(detectionStatus)}</strong>
                  <p>{getDetectionMessage(detectionStatus)}</p>
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
                      className={`confidence-bar-fill ${getConfidenceTone(detection.confidence)}`}
                      style={{ width: `${Math.min(Math.max(confidencePercent, 0), 100)}%` }}
                    />
                  </div>
                )}
              </div>

              <div className="detection-details">
                <div><span>Pest</span><strong>{detection.pest || '—'}</strong></div>
                <div><span>Status</span><strong>{displayStatus(detectionStatus)}</strong></div>
                <div><span>Confidence</span><strong>{formatConfidence(detection.confidence)}</strong></div>
                <div><span>Risk</span><strong>{detection.risk || '—'}</strong></div>
                <div><span>Date / time</span><strong>{formatDate(detection.detected_at || detection.timestamp)}</strong></div>
                <div><span>Device ID</span><strong>{detection.device_id || deviceId}</strong></div>
                <div><span>Temperature</span><strong>{formatTemperature(detection.temperature ?? latestTemperature)}</strong></div>
                <div><span>Humidity</span><strong>{formatHumidity(detection.humidity ?? latestHumidity)}</strong></div>
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
              <strong>{device?.status || '—'}</strong>
            </div>
            <div className="device-health-row">
              <span>Last Seen</span>
              <strong>{formatDate(deviceTimestamp)}</strong>
            </div>
            <div className="device-health-row">
              <span>Temperature</span>
              <strong>{formatTemperature(latestTemperature)}</strong>
            </div>
            <div className="device-health-row">
              <span>Humidity</span>
              <strong>{formatHumidity(latestHumidity)}</strong>
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
            <SparkIcon size={21} />
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
                    <strong>{item.pest || '—'}</strong>
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
