import { Link } from 'react-router-dom'
import { ArrowIcon } from './Icons'
import StatusBadge from './StatusBadge'

function PestCard({ pest }) {
  return (
    <article className="pest-card">
      <img src={pest.image} alt={`${pest.name} on a crop plant`} />
      <div className="pest-card-body">
        <div className="pest-card-meta"><span>{pest.affected_crop || pest.crop}</span><StatusBadge tone={pest.risk.toLowerCase()}>{pest.risk} risk</StatusBadge></div>
        <h2>{pest.name}</h2>
        <p className="scientific-name">{pest.scientific_name || pest.scientificName}</p>
        <p>{pest.description}</p>
        <Link className="text-link" to={`/solutions? pest=${pest.id}`.replace('? ', '?')}>View Details <ArrowIcon size={14} /></Link>
      </div>
    </article>
  )
}

export default PestCard
