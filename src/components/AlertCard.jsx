import { Link } from 'react-router-dom'
import { ArrowIcon } from './Icons'
import StatusBadge from './StatusBadge'

function AlertCard({ detection }) {
  const harmful = detection.status === 'HARMFUL_PEST'
  const title = harmful ? 'Pest Detected' : detection.status === 'NON_PEST' ? 'Non-pest sound' : 'Unknown sound'
  const confidence = `${(detection.confidence * 100).toFixed(1)}%`

  return (
    <article className={harmful ? 'alert-card' : 'alert-card alert-card-neutral'}>
      <div className="alert-card-heading"><div><p className="eyebrow">Detection result</p><h2>{title}</h2></div><StatusBadge tone={harmful ? 'high' : 'neutral'}>{detection.risk}</StatusBadge></div>
      <div className="alert-pest-name">{detection.pest || detection.status.replace('_', ' ')}</div>
      <div className="alert-card-details"><span>Confidence <strong>{confidence}</strong></span><span>Status <strong>{detection.status.replace('_', ' ')}</strong></span></div>
      {harmful && <Link className="primary-button" to={`/solutions?pest=${encodeURIComponent(detection.pest || '')}`}>View Solution <ArrowIcon /></Link>}
    </article>
  )
}

export default AlertCard
