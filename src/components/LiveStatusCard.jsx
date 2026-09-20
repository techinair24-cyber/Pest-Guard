import { Link } from 'react-router-dom'
import { ArrowIcon, SignalIcon } from './Icons'
import { formatTemperature, formatHumidity } from '../utils/formatters'
import pestPreview from '../assets/pests/rice-planthopper.jpg'

function formatConfidence(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—'
  }

  return `${(value * 100).toFixed(1)}%`
}

function formatTime(timestamp) {
  if (!timestamp) {
    return '—'
  }

  const date = new Date(timestamp)

  if (Number.isNaN(date.getTime())) {
    return '—'
  }

  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getStatusLabel(status) {
  switch (status) {
    case 'HARMFUL_PEST':
      return 'HARMFUL PEST'
    case 'NON_PEST':
      return 'NON-PEST'
    case 'UNKNOWN':
      return 'UNKNOWN SOUND'
    default:
      return 'NO DETECTION'
  }
}

function getStatusClass(status) {
  switch (status) {
    case 'HARMFUL_PEST':
      return 'status-card-danger'
    case 'NON_PEST':
      return 'status-card-safe'
    case 'UNKNOWN':
      return 'status-card-unknown'
    default:
      return 'status-card-neutral'
  }
}

function getConnectionClass(connection) {
  return connection === 'ONLINE'
    ? 'online-dot'
    : 'offline-dot'
}

function LiveStatusCard({ detection, device, error }) {
  /*
    IMPORTANT:
    This component does not create fake detection data.

    Data comes from:
    useLiveDetection()
      ↓
    FastAPI backend
      ↓
    Database / AI result
  */

  const deviceAvailable = Boolean(device)
  const detectionAvailable = Boolean(detection)

  if (error) {
    return (
      <article className="status-card status-card-unavailable">
        <div className="status-card-top">
          <div>
            <p className="status-label">Live Status</p>

            <p className="status-device">
              <span className="offline-dot" />
              Live data unavailable
            </p>
          </div>

          <SignalIcon size={22} />
        </div>

        <div className="status-empty">
          <strong>Backend connection unavailable</strong>

          <p>
            Connect the Pest Guard backend to display real
            device and AI detection information here.
          </p>
        </div>

        <Link
          className="status-link"
          to="/live-monitoring"
        >
          Open Live Monitoring
          <ArrowIcon size={15} />
        </Link>
      </article>
    )
  }

  if (!deviceAvailable) {
    return (
      <article className="status-card status-card-unavailable">
        <div className="status-card-top">
          <div>
            <p className="status-label">Live Status</p>

            <p className="status-device">
              <span className="offline-dot" />
              Device unavailable
            </p>
          </div>

          <SignalIcon size={22} />
        </div>

        <div className="status-empty">
          <strong>Waiting for field signal</strong>

          <p>
            No AI detection has been received yet.
          </p>
        </div>

        <Link
          className="status-link"
          to="/live-monitoring"
        >
          Open Live Monitoring
          <ArrowIcon size={15} />
        </Link>
      </article>
    )
  }

  const status = detection?.status || 'NO_DETECTION'

  const connection =
    device?.connection ||
    device?.status ||
    'UNKNOWN'

  const pestName =
    detection?.pest ||
    detection?.pest_name ||
    null

  const confidence =
    detection?.confidence ?? null

  const risk =
    detection?.risk ||
    'UNKNOWN'

  const timestamp =
    detection?.detected_at ||
    detection?.timestamp ||
    detection?.created_at ||
    null

  const deviceName =
    device?.device_id ||
    device?.name ||
    'Field Unit'

  const temperature =
    device?.temperature ?? detection?.temperature

  const humidity =
    device?.humidity ?? detection?.humidity

  const statusLabel = getStatusLabel(status)
  const statusClass = getStatusClass(status)
  const connectionClass = getConnectionClass(connection)

  return (
    <article className={`status-card ${statusClass}`}>
      {/* HEADER */}
      <div className="status-card-top">
        <div>
          <p className="status-label">Live Status</p>

          <p className="status-device">
            <span className={connectionClass} />
            {connection}
          </p>
        </div>

        <SignalIcon size={22} />
      </div>

      {/* LATEST DETECTION */}
      {detectionAvailable ? (
        <>
          <div className="detection-name">
            {pestName ? (
              <img
                src={pestPreview}
                alt={`${pestName} crop pest`}
              />
            ) : (
              <div
                className="detection-placeholder"
                aria-hidden="true"
              >
                <SignalIcon size={20} />
              </div>
            )}

            <div>
              <span>Latest Detection</span>

              <strong>
                {pestName || statusLabel}
              </strong>
            </div>
          </div>

          {/* DETAILS */}
          <div className="status-details">
            <div>
              <span>Confidence</span>

              <strong>
                {formatConfidence(confidence)}
              </strong>
            </div>

            <div>
              <span>Risk</span>

              <strong
                className={
                  status === 'HARMFUL_PEST'
                    ? 'risk-high'
                    : ''
                }
              >
                {risk}
              </strong>
            </div>

            <div>
              <span>Time</span>

              <strong>
                {formatTime(timestamp)}
              </strong>
            </div>

            <div>
              <span>Temperature</span>

              <strong>
                {formatTemperature(temperature)}
              </strong>
            </div>

            <div>
              <span>Humidity</span>

              <strong>
                {formatHumidity(humidity)}
              </strong>
            </div>
          </div>

          <div className="status-extra">
            <span>Status</span>

            <strong>
              {statusLabel}
            </strong>
          </div>
        </>
      ) : (
        <div className="status-no-detection">
          <div className="detection-placeholder">
            <SignalIcon size={20} />
          </div>

          <div>
            <span>Latest Detection</span>

            <strong>
              Waiting for field signal
            </strong>

            <p>
              No AI detection has been received yet.
            </p>
          </div>
        </div>
      )}

      {/* DEVICE */}
      <p className="status-device-id">
        {deviceName}
      </p>

      {/* LINK */}
      <Link
        className="status-link"
        to="/live-monitoring"
      >
        View Live Monitoring
        <ArrowIcon size={15} />
      </Link>
    </article>
  )
}

export default LiveStatusCard