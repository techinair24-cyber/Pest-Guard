import { Link } from 'react-router-dom'
import { ArrowIcon } from './Icons'
import StatusBadge from './StatusBadge'
import {
  getDetectionDisplayStatus,
  isVerifiedPestDetection,
} from '../utils/detectionHistory'

function AlertCard({ detection }) {
  const harmful = isVerifiedPestDetection(detection)
  const displayStatus = getDetectionDisplayStatus(detection)
  const title = harmful
    ? 'Pest Detected'
    : displayStatus === 'Inference error'
      ? 'Inference error'
      : 'No pest detected'
  const confidence = `${(detection.confidence * 100).toFixed(1)}%`

  return (
    <article className={harmful ? 'alert-card' : 'alert-card alert-card-neutral'}>
      <div className="alert-card-heading"><div><p className="eyebrow">Detection result</p><h2>{title}</h2></div><StatusBadge tone={harmful ? 'high' : 'neutral'}>{harmful ? detection.risk : displayStatus}</StatusBadge></div>
      <div className="alert-pest-name">
        {harmful ? detection.pest : displayStatus}
      </div>
      <div className="alert-card-details"><span>{harmful ? 'Confidence' : 'Model score'} <strong>{confidence}</strong></span><span>Status <strong>{displayStatus}</strong></span></div>
      {harmful && <Link className="primary-button" to={`/solutions?pest=${encodeURIComponent(detection.pest || '')}`}>View Solution <ArrowIcon /></Link>}
    </article>
  )
}

export default AlertCard
