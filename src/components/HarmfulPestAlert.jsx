import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './HarmfulPestAlert.css'

function formatPercent(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '—'
  }

  return `${(number * 100).toFixed(1)}%`
}

function formatTemperature(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)} °C` : '—'
}

function formatHumidity(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)} %` : '—'
}

function HarmfulPestAlert({ detection, onDismiss }) {
  const navigate = useNavigate()
  const [isVisible, setIsVisible] = useState(false)
  const previousKeyRef = useRef('')

  useEffect(() => {
    if (!detection || detection.status !== 'HARMFUL_PEST') {
      setIsVisible(false)
      previousKeyRef.current = ''
      return undefined
    }

    const eventKey = detection.id ?? detection.detected_at ?? detection.timestamp ?? ''

    if (!eventKey || eventKey === previousKeyRef.current) {
      return undefined
    }

    previousKeyRef.current = eventKey
    setIsVisible(false)

    const enterTimer = window.setTimeout(() => setIsVisible(true), 20)
    return () => window.clearTimeout(enterTimer)
  }, [detection])

  if (!detection || detection.status !== 'HARMFUL_PEST') {
    return null
  }

  const handleDismiss = () => {
    setIsVisible(false)
    onDismiss?.()
  }

  return (
    <div className={`harmful-alert-backdrop ${isVisible ? 'is-visible' : ''}`} onClick={handleDismiss} aria-hidden="true">
      <div className={`harmful-alert-popup ${isVisible ? 'is-visible' : ''}`} onClick={(event) => event.stopPropagation()} role="dialog" aria-live="assertive">
        <div className="alert-warning-pulse" aria-hidden="true" />
        <div className="alert-header">
          <span className="alert-badge">Field Alert</span>
          <button type="button" className="alert-close" onClick={handleDismiss} aria-label="Dismiss alert">
            ×
          </button>
        </div>

        <div className="alert-body">
          <div className="alert-title-wrap">
            <p className="alert-kicker">Harmful Pest Detected</p>
            <h3>{detection.pest || 'Unknown pest'}</h3>
          </div>

          <dl className="alert-stats">
            <div>
              <dt>AI Confidence</dt>
              <dd>{formatPercent(detection.confidence)}</dd>
            </div>
            <div>
              <dt>Risk</dt>
              <dd>{detection.risk || '—'}</dd>
            </div>
            <div>
              <dt>Temperature</dt>
              <dd>{formatTemperature(detection.temperature)}</dd>
            </div>
            <div>
              <dt>Humidity</dt>
              <dd>{formatHumidity(detection.humidity)}</dd>
            </div>
            <div className="alert-device-row">
              <dt>Device</dt>
              <dd>{detection.device_id || 'FIELD-UNIT-01'}</dd>
            </div>
          </dl>
        </div>

        <div className="alert-actions">
          <button type="button" className="alert-primary" onClick={() => { handleDismiss(); navigate('/solutions') }}>
            View Solution →
          </button>
          <button type="button" className="alert-secondary" onClick={handleDismiss}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  )
}

export default HarmfulPestAlert
