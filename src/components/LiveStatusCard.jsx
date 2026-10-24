import { Link } from 'react-router-dom'
import { ArrowIcon, SignalIcon } from './Icons'
import { formatTemperature, formatHumidity } from '../utils/formatters'
import {
  formatModelScore,
  getCandidateDisplayName,
  getDetectionInsectGroup,
  getPredictionUncertainty,
  getTopSpeciesPredictions,
} from '../utils/insectPredictions'

function formatDateTime(timestamp) {
  if (!timestamp) {
    return '—'
  }

  const date = new Date(timestamp)

  if (Number.isNaN(date.getTime())) {
    return '—'
  }

  return date.toLocaleString()
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

  const insectGroup = getDetectionInsectGroup(detection)
  const topPredictions = getTopSpeciesPredictions(detection?.top_predictions)

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
    detection?.device_id ||
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
            <div
              className="detection-placeholder"
              aria-hidden="true"
            >
              <SignalIcon size={24} />
            </div>

            <div>
              <span>Broad insect group</span>

              <strong>
                {pestName ? insectGroup : statusLabel}
              </strong>
            </div>
          </div>

          {/* DETAILS */}
          <div className="status-details">
            <div>
              <span>Group model score</span>

              <strong>
                {formatModelScore(detection?.group_score)}
              </strong>
              <small>Uncalibrated ranking estimate</small>
            </div>

            <div>
              <span>Candidate risk · unverified</span>

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
              <span>Detection date &amp; time</span>

              <strong>
                {formatDateTime(timestamp)}
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

          {topPredictions.length > 0 && (
            <div className="top-predictions">
              <h4>Top Species Predictions</h4>

              <ol>
                {topPredictions.map((prediction, index) => (
                  <li key={`${prediction.pest}-${index}`}>
                    <span>
                      {getCandidateDisplayName(prediction)}
                      <small>Unverified candidate</small>
                    </span>
                    <strong>{formatModelScore(prediction.score)}</strong>
                  </li>
                ))}
              </ol>

              <small>
                Model scores are uncalibrated ranking estimates, not verified probabilities.
              </small>
            </div>
          )}

          {getPredictionUncertainty(detection) && (
            <p className="status-uncertainty">
              {getPredictionUncertainty(detection)}
            </p>
          )}

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
        Device ID: {deviceName}
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