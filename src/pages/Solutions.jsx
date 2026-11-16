import { useEffect, useId, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { ArrowIcon, LeafIcon, SignalIcon, SparkIcon } from '../components/Icons'
import { useLiveDetection } from '../hooks/useLiveDetection'
import {
  API_BASE_URL,
  getPestSolutions,
  getHighRiskSolutionHistory,
  getPests,
} from '../services/api'
import {
  buildPestDirectory,
  getCommonPestName,
  getDetectionRiskEstimate,
  normalizePestName,
} from '../utils/pestNames'
import { formatModelScore } from '../utils/insectPredictions'
import { buildPotentialHostDisplay } from '../utils/potentialHostProfile'
import solutionsField from '../assets/solutions-field.jpg'
import './Solutions.css'

const MANAGEMENT_CATEGORIES = [
  { key: 'cultural_control_methods', title: 'Cultural Control', safetyKey: null },
  { key: 'mechanical_control_methods', title: 'Mechanical Control', safetyKey: null },
  { key: 'biological_control_options', title: 'Biological Control', safetyKey: null },
  {
    key: 'chemical_control_options',
    title: 'Chemical Control',
    safetyKey: 'safety_precautions',
  },
]

function SourceList({ sources = [] }) {
  if (!sources.length) {
    return <p className="solution-unavailable">Supporting source unavailable.</p>
  }

  return (
    <ul className="solution-sources">
      {sources.map((source, index) => {
        const sourceUrl = typeof source === 'string' ? source : source.url
        const sourceTitle =
          typeof source === 'string'
            ? source
            : [source.title, source.organization].filter(Boolean).join(' — ')

        return (
          <li key={sourceUrl || `${sourceTitle}-${index}`}>
            {sourceUrl ? (
              <a href={sourceUrl} target="_blank" rel="noreferrer">
                {sourceTitle || sourceUrl}
              </a>
            ) : (
              sourceTitle
            )}
            {typeof source !== 'string' && source.authors && (
              <span>{source.authors}</span>
            )}
            {typeof source !== 'string' && source.published_on && (
              <span>Published {source.published_on}</span>
            )}
            {typeof source !== 'string' && source.reviewed_on && (
              <span>Reviewed {source.reviewed_on}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ChemicalControlOptions({ options, sources }) {
  const sourcesById = new Map(
    sources
      .filter((source) => source.source_id)
      .map((source) => [source.source_id, source]),
  )

  return (
    <div className="chemical-control-options">
      {options.map((option) => {
        const optionSources = (option.source_ids || [])
          .map((sourceId) => sourcesById.get(sourceId))
          .filter(Boolean)
        const details = [
          ['Product', option.product],
          ['Study formulation', option.study_formulation],
          ['Evidence type', option.evidence_type],
          ['Country / jurisdiction', option.country],
          ['Target pest', option.target_pest],
          ['Crop scope', option.crop_scope],
          ['Research result', option.research_result],
          ['Application method', option.application_method],
          ['Dosage', option.dosage],
          ['Pre-harvest interval', option.pre_harvest_interval],
          ['Crop registration status', option.crop_registration_status],
          ['Safety', option.safety_notes],
        ].filter(([, value]) => value)

        return (
          <section className="chemical-control-option" key={option.id}>
            <div className="chemical-control-option-heading">
              <h5>{option.active_ingredient}</h5>
              <span className="unverified-badge">{option.status_label}</span>
            </div>
            <dl>
              {details.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <SourceList sources={optionSources} />
          </section>
        )
      })}
    </div>
  )
}

function getSources(item) {
  return Array.isArray(item.source_refs)
    ? item.source_refs
    : Array.isArray(item.source_references)
      ? item.source_references
      : item.source
        ? Array.isArray(item.source)
          ? item.source
          : [item.source]
        : []
}

function PestSolutionDetails({ label, value }) {
  if (!value) return null

  if (Array.isArray(value)) {
    if (!value.length) return null
    return (
      <section>
        <h4>{label}</h4>
        <ul>
          {value.map((entry, index) => (
            <li key={`${label}-${index}`}>{String(entry)}</li>
          ))}
        </ul>
      </section>
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([, entry]) => Boolean(entry))
    if (!entries.length) return null
    return (
      <section>
        <h4>{label}</h4>
        {entries.map(([key, entry]) => (
          <div className="pest-solution-subsection" key={key}>
            <h5>{key.replaceAll('_', ' ')}</h5>
            {Array.isArray(entry) ? (
              <ul>
                {entry.map((line, index) => (
                  <li key={`${key}-${index}`}>{String(line)}</li>
                ))}
              </ul>
            ) : (
              <p>{String(entry)}</p>
            )}
          </div>
        ))}
      </section>
    )
  }

  return (
    <section>
      <h4>{label}</h4>
      <p>{String(value)}</p>
    </section>
  )
}

function resolveHistoryPestId(item, pestDirectory) {
  for (const candidate of [item.pest_id, item.pest, item.common_name]) {
    const pestId = pestDirectory[normalizePestName(candidate)]?.pestId
    if (pestId) return pestId
  }

  return String(item.pest_id || '').trim()
}

function HistorySolutionModal({ item, onClose, pestDirectory }) {
  const pestId = resolveHistoryPestId(item, pestDirectory)
  const cropId = String(item.crop_id || '').trim()
  const requestKey = `${pestId}\u0000${cropId}`
  const [solutionResult, setSolutionResult] = useState({
    requestKey: '',
    solutions: [],
    error: '',
  })
  const isCurrentResult = solutionResult.requestKey === requestKey
  const historyPestSolutions = isCurrentResult
    ? solutionResult.solutions
    : []
  const solutionLoading = Boolean(pestId) && !isCurrentResult
  const solutionError = isCurrentResult ? solutionResult.error : ''

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  useEffect(() => {
    let active = true

    async function loadPestSolutions() {
      try {
        const result = await getPestSolutions(pestId)
        const verifiedSolutions = Array.isArray(result.solutions)
          ? result.solutions.filter(
              (solution) => solution.status === 'VERIFIED',
            )
          : []
        const cropSolutions = cropId
          ? verifiedSolutions.filter((solution) => solution.crop_id === cropId)
          : verifiedSolutions

        if (active) {
          setSolutionResult({
            requestKey,
            solutions: cropSolutions,
            error: '',
          })
        }
      } catch (loadError) {
        if (active) {
          setSolutionResult({
            requestKey,
            solutions: [],
            error:
              loadError.message || 'Unable to load crop-specific solutions.',
          })
        }
      }
    }

    if (pestId) loadPestSolutions()

    return () => {
      active = false
    }
  }, [cropId, pestId, requestKey])

  return (
    <div
      className="history-modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section
        className="history-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-modal-title"
      >
        <div className="history-modal-heading">
          <div>
            <p className="card-eyebrow">Saved detection</p>
            <h2 id="history-modal-title">
              {item.common_name || item.pest}
            </h2>
          </div>
          <button
            type="button"
            className="secondary-button history-modal-close"
            onClick={onClose}
            autoFocus
          >
            Close
          </button>
        </div>
        <div className="history-modal-content">
          {solutionError ? (
            <p className="inline-error" role="alert">{solutionError}</p>
          ) : solutionLoading ? (
            <p className="solution-loading">Loading pest solutions…</p>
          ) : historyPestSolutions.length > 0 ? (
            <VerifiedSolutionGroups
              items={historyPestSolutions}
              isLiveMatch={false}
            />
          ) : !pestId ? (
            <p className="solution-unavailable">
              The saved pest identity could not be matched to the pest catalogue.
            </p>
          ) : (
            <p className="solution-unavailable">
              {item.crop_id
                ? `No verified solution is currently available for crop ${item.crop_id} for this pest.`
                : 'No verified solution is currently available for this pest.'}
            </p>
          )}
        </div>
      </section>
    </div>
  )
}

function PestSolutionCard({ item }) {
  const sources = getSources(item)
  const details = [
    ['Description', item.description],
    ['Habitat', item.habitat],
    ['Crop context', item.crop_context],
    ['Crop damage', item.crop_damage || item.damage_notes],
    ['Affected plant parts', item.affected_plant_parts || item.affected_parts],
    ['Identification', item.identification_signs],
    ['Recommended treatment', item.recommended_treatment],
    ['Immediate control measures', item.immediate_control_measures],
    ['Management', item.management || item.recommendations],
    ['Biological control', item.biological_control_options || item.biological_control],
    ['Cultural control', item.cultural_control_methods || item.cultural_control],
    ['Mechanical control', item.mechanical_control_methods || item.mechanical_control],
    ['Chemical control', item.chemical_control_options],
    ['Monitoring', item.monitoring],
    ['Prevention', item.prevention],
    ['Safety', item.safety_precautions],
    ['Expert advice', item.expert_advice],
    ['Geographic qualification', item.geographic_qualification || item.geographic_limitation],
    ['Economic threshold', item.economic_threshold || item.action_threshold],
    ['Notes', item.notes],
  ]

  return (
    <article className="potential-host-profile pest-solution-card">
      <div className="potential-host-heading">
        <div>
          <p className="card-eyebrow">
            Pest-specific solution · {item.risk_level || item.risk} risk
          </p>
          <h3>{item.title || item.pest_name}</h3>
          {item.scientific_name && (
            <p className="solution-scientific-name">{item.scientific_name}</p>
          )}
          {(item.geographic_scope || item.region) && (
            <p className="solution-meta">{item.geographic_scope || item.region}</p>
          )}
          {item.crop_id && (
            <p className="solution-meta">
              Crop: {item.crop_name || item.crop_id}
            </p>
          )}
        </div>
      </div>
      <div className="potential-host-detail-grid pest-solution-details">
        {details.map(([label, value]) => (
          <PestSolutionDetails key={label} label={label} value={value} />
        ))}
      </div>
      <SourceList sources={sources} />
    </article>
  )
}

function EvidenceCard({ title, children, className = '' }) {
  return (
    <article className={`solution-panel ${className}`.trim()}>
      <p className="card-eyebrow">Evidence and guidance</p>
      <h3>{title}</h3>
      {children}
    </article>
  )
}

function PotentialHostProfile({ profile }) {
  const display = buildPotentialHostDisplay(profile)
  if (!display) return null

  return (
    <article className="potential-host-profile" aria-label={`${display.pestName} potential host profile`}>
      <div className="potential-host-heading">
        <div>
          <p className="card-eyebrow">Candidate pest profile</p>
          <h3>{display.pestName}</h3>
          {display.scientificName && (
            <p className="solution-scientific-name">
              Candidate scientific name: {display.scientificName}
            </p>
          )}
          <p className="solution-meta">
            {display.riskLevel} risk <span aria-hidden="true">·</span> {display.region}
          </p>
        </div>
        <span className="unverified-badge">{display.verificationLabel}</span>
      </div>

      <section className="potential-host-list" aria-labelledby="potential-hosts-title">
        <h4 id="potential-hosts-title">{display.hostHeading}</h4>
        <ul>
          {display.hosts.map((host) => (
            <li key={host.cropId}>
              <span>{host.cropName}</span>
              <small>Candidate</small>
            </li>
          ))}
        </ul>
      </section>

      {display.sections.length > 0 && (
        <div className="potential-host-detail-grid">
          {display.sections.map((section) => (
            <section key={section.title}>
              <h4>{section.title}</h4>
              <p>{section.content}</p>
            </section>
          ))}
        </div>
      )}
    </article>
  )
}

function RecommendationCard({ item, category }) {
  const recommendation = item[category.key]
  const sources = getSources(item)
  const recommendationSources = sources.filter((source) =>
    source.supports?.includes(category.key),
  )
  const isUserApproved =
    item.user_approved === true ||
    (item.status === 'VERIFIED' && sources.length === 0)
  const isVerified = Boolean(
    recommendation && (recommendationSources.length || isUserApproved),
  )
  const safetySources = sources.filter((source) =>
    source.supports?.includes('safety_precautions'),
  )

  return (
    <article className="recommendation-card">
      <div className="recommendation-heading">
        <h4>{category.title}</h4>
        <span className={isVerified ? 'verification-badge' : 'unverified-badge'}>
          {isVerified
            ? recommendationSources.length
              ? 'Sources available'
              : 'User approved'
            : 'Sources unavailable'}
        </span>
      </div>
      {isVerified ? (
        Array.isArray(recommendation) ? (
          <ChemicalControlOptions options={recommendation} sources={sources} />
        ) : (
          <p>{recommendation}</p>
        )
      ) : (
        <p className="solution-unavailable">Solution details are not available.</p>
      )}
      {isVerified && category.safetyKey && item[category.safetyKey] && safetySources.length > 0 && (
        <p className="safety-note">
          <strong>Safety:</strong> {item[category.safetyKey]}
        </p>
      )}
      {isVerified && !Array.isArray(recommendation) && (
        <SourceList sources={recommendationSources} />
      )}
      {isVerified && category.safetyKey && item[category.safetyKey] && safetySources.length > 0 && (
        <SourceList sources={safetySources} />
      )}
    </article>
  )
}

function VerifiedSolution({ item, isLiveMatch }) {
  const sources = Array.isArray(item.source_references) ? item.source_references : []
  const isUserApproved =
    item.user_approved === true ||
    (item.status === 'VERIFIED' && sources.length === 0)
  const hasEvidence = (key) => sources.some((source) => source.supports?.includes(key))
  const renderEvidence = (title, value, evidenceKey, className = '') => {
    const verified = Boolean(value && (hasEvidence(evidenceKey) || isUserApproved))

    return (
      <EvidenceCard title={title} className={className}>
        {verified ? (
          <p>{value}</p>
        ) : (
          <p className="solution-unavailable">
            Information is not available for this pest-crop record.
          </p>
        )}
        <p className="evidence-label">Supporting evidence</p>
        <SourceList
          sources={
            verified
              ? sources.filter((source) => source.supports?.includes(evidenceKey))
              : []
          }
        />
      </EvidenceCard>
    )
  }

  const preventionSources = (item.source_references || []).filter(
    (source) => source.supports?.includes('prevention'),
  )
  const preventionIsVerified = Boolean(
    item.prevention && (preventionSources.length || isUserApproved),
  )

  return (
    <article className="verified-solution">
      <div className="verified-solution-heading">
        <div>
          <p className="card-eyebrow">{item.crop_name}</p>
          <h3>{item.pest_name}</h3>
          {item.scientific_name && (
            <p className="solution-scientific-name">
              {item.scientific_name}
            </p>
          )}
          <p className="solution-meta">
            {item.insect_group} <span aria-hidden="true">·</span> {item.risk} risk
          </p>
        </div>
        <span className="verification-badge">
          {isUserApproved ? 'User approved' : 'Sources available'}
        </span>
      </div>
      {isLiveMatch && (
        <p className="match-note">Matches the current pest identification.</p>
      )}
      <div className="solution-detail-grid">
        {renderEvidence(
          'Crop Damage & Symptoms',
          item.crop_damage,
          'crop_damage',
        )}
        {renderEvidence(
          'Affected Plant Parts',
          item.affected_plant_parts,
          'affected_plant_parts',
        )}
        {renderEvidence(
          'Immediate Control Measures',
          item.immediate_control_measures,
          'immediate_control_measures',
        )}
        {renderEvidence(
          'Monitoring & Early Detection',
          item.monitoring,
          'monitoring',
        )}
        {renderEvidence(
          'Safety Precautions',
          item.safety_precautions,
          'safety_precautions',
        )}
        {renderEvidence(
          'Expert Advice',
          item.expert_advice,
          'expert_advice',
        )}
        <EvidenceCard title="Recommended Management Solutions">
          <div className="recommendation-list">
            {MANAGEMENT_CATEGORIES.map((category) => (
              <RecommendationCard
                key={category.key}
                item={item}
                category={category}
              />
            ))}
          </div>
        </EvidenceCard>
        <EvidenceCard title="Prevention" className="prevention-panel">
          <span className={preventionIsVerified ? 'verification-badge' : 'unverified-badge'}>
            {preventionIsVerified
              ? isUserApproved
                ? 'User approved'
                : 'Sources available'
              : 'Sources unavailable'}
          </span>
          {preventionIsVerified ? (
            <p>{item.prevention}</p>
          ) : (
            <p className="solution-unavailable">Solution details are not available.</p>
          )}
          {preventionIsVerified && <SourceList sources={preventionSources} />}
        </EvidenceCard>
      </div>
    </article>
  )
}

function CropSolutionAccordion({ item, isLiveMatch }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const panelId = useId()
  const cropName = item.crop_name || item.crop_id || 'Crop-specific solution'

  return (
    <section
      className={`crop-solution-accordion${isExpanded ? ' is-expanded' : ''}`}
    >
      <h4 className="crop-solution-accordion-title">
        <button
          type="button"
          className="crop-solution-accordion-toggle"
          aria-expanded={isExpanded}
          aria-controls={panelId}
          onClick={() => setIsExpanded((expanded) => !expanded)}
        >
          <span>{cropName}</span>
          <span className="crop-solution-accordion-icon" aria-hidden="true">
            {isExpanded ? '−' : '+'}
          </span>
        </button>
      </h4>
      <div
        id={panelId}
        className="crop-solution-accordion-panel"
        aria-hidden={!isExpanded}
        inert={!isExpanded}
      >
        <div className="crop-solution-accordion-panel-inner">
          <VerifiedSolution item={item} isLiveMatch={isLiveMatch} />
        </div>
      </div>
    </section>
  )
}

function PestCropSolutionGroup({ items, isLiveMatch }) {
  const headingId = useId()
  const pest = items[0]

  return (
    <section
      className="verified-solution-group"
      aria-labelledby={headingId}
    >
      <div className="verified-solution-group-heading">
        <p className="card-eyebrow">Crop-specific solutions</p>
        <h3 id={headingId}>
          {pest.pest_name || pest.pest_id || 'Pest solutions'}
        </h3>
        {pest.scientific_name && (
          <p className="solution-scientific-name">{pest.scientific_name}</p>
        )}
      </div>
      <div className="crop-solution-accordion-list">
        {items.map((item) => (
          <CropSolutionAccordion
            key={item.solution_id}
            item={item}
            isLiveMatch={isLiveMatch && item.pest_id === pest.pest_id}
          />
        ))}
      </div>
    </section>
  )
}

function VerifiedSolutionGroups({ items, isLiveMatch }) {
  const groups = new Map()

  items.forEach((item, index) => {
    const key =
      item.pest_id || item.pest_name || item.solution_id || `solution-${index}`
    const group = groups.get(key)
    if (group) {
      group.push(item)
    } else {
      groups.set(key, [item])
    }
  })

  return (
    <div className="verified-solution-list">
      {Array.from(groups, ([key, group]) =>
        group.length > 1 ? (
          <PestCropSolutionGroup
            key={key}
            items={group}
            isLiveMatch={isLiveMatch}
          />
        ) : (
          <VerifiedSolution
            key={group[0].solution_id || key}
            item={group[0]}
            isLiveMatch={isLiveMatch && group[0].pest_id === key}
          />
        ),
      )}
    </div>
  )
}

function Solutions() {
  const location = useLocation()
  const { detection, loading: detectionLoading } = useLiveDetection()

  const [pestDirectory, setPestDirectory] = useState({})
  const [pestDirectoryLoaded, setPestDirectoryLoaded] = useState(false)
  const [pestSolutionData, setPestSolutionData] = useState(null)
  const [pestSolutionsError, setPestSolutionsError] = useState('')
  const [pestDirectoryError, setPestDirectoryError] = useState('')
  const [highRiskHistory, setHighRiskHistory] = useState([])
  const [selectedHistoryItem, setSelectedHistoryItem] = useState(null)
  const [highRiskHistoryTotal, setHighRiskHistoryTotal] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const [clearingHistory, setClearingHistory] = useState(false)
  const [confirmClearHistory, setConfirmClearHistory] = useState(false)
  const [clearHistoryError, setClearHistoryError] = useState('')
  const [retryKey, setRetryKey] = useState(0)
  const [pestSolutionsRetryKey, setPestSolutionsRetryKey] = useState(0)

  const queryPest = new URLSearchParams(location.search).get('pest')?.trim()
  const status = String(detection?.status || '').toUpperCase()

  const detectionPest = pestDirectory[normalizePestName(detection?.pest_id)]
  const catalogRisk = String(detectionPest?.risk || '').trim().toUpperCase()
  const supportedRisk = ['HIGH', 'MEDIUM', 'LOW', 'NO_RISK'].includes(catalogRisk)

  const hasVerifiedCatalogMatch =
    detection?.pest_verified === true &&
    Boolean(detection?.pest_id) &&
    detection.pest_id === detectionPest?.pestId &&
    supportedRisk

  const normalizedQueryPest = normalizePestName(queryPest)
  const queryPestId =
    pestDirectory[normalizedQueryPest]?.pestId || queryPest
  const normalizedDetectionPestId = normalizePestName(detection?.pest_id)
  const normalizedDetectionName = normalizePestName(detection?.pest)
  const isPineWeevilProfileRequested =
    detection?.pest_id === 'pine_weevil' ||
    normalizedQueryPest === normalizePestName('pine_weevil')

  const queryMatchesDetection =
    !queryPest ||
    normalizedQueryPest === normalizedDetectionName ||
    normalizedQueryPest === normalizedDetectionPestId

  const hasVerifiedLiveDetection =
    hasVerifiedCatalogMatch &&
    status === 'HARMFUL_PEST' &&
    queryMatchesDetection

  const hasActionableLiveDetection =
    hasVerifiedLiveDetection &&
    ['HIGH', 'MEDIUM'].includes(catalogRisk)

  const isNonPest = status === 'NON_PEST'

  const hasLiveDetection =
    Boolean(detection) &&
    (
      Boolean(detection.pest_id) ||
      Boolean(detection.pest) ||
      Boolean(status)
    )
  const detectionConfidence =
    detection?.confidence === null ||
    detection?.confidence === undefined ||
    detection?.confidence === ''
      ? Number.NaN
      : Number(detection.confidence)
  const confidenceLabel = Number.isFinite(detectionConfidence)
    ? formatModelScore(detectionConfidence)
    : 'N/A'
  const activePotentialHostProfile =
    isPineWeevilProfileRequested &&
    pestSolutionData?.potential_host_profile?.pest_id === 'pine_weevil'
      ? pestSolutionData.potential_host_profile
      : null

  const storedSolutions = Array.isArray(pestSolutionData?.solutions)
    ? pestSolutionData.solutions
    : []
  const pestSolutions = Array.isArray(pestSolutionData?.advisories)
    ? pestSolutionData.advisories
    : []

  const verifiedSolutions = storedSolutions.filter((item) => {
    if (queryPestId) return item.pest_id === queryPestId

    if (hasLiveDetection) {
      return (
        hasActionableLiveDetection &&
        item.pest_id === detection?.pest_id
      )
    }

    return true
  })

  const pestName = hasVerifiedLiveDetection
    ? String(
        detection.common_name ||
          detectionPest?.commonName ||
          detection.pest ||
          'Unknown pest',
      ).trim()
    : 'Unknown pest'
  const riskLabel = hasVerifiedLiveDetection ? catalogRisk : 'Not available'
  const insectGroup = String(detection?.insect_group || '').trim()
  useEffect(() => {
    let active = true

    async function loadPestDirectory() {
      try {
        const pests = await getPests()

        if (!active) return

        setPestDirectory(buildPestDirectory(pests))
      } catch (loadError) {
        if (!active) return

        setPestDirectoryError(
          loadError.message || 'Unable to load pest information.',
        )
      } finally {
        if (active) setPestDirectoryLoaded(true)
      }
    }

    loadPestDirectory()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true

    async function loadPestSpecificData() {
      setPestSolutionsError('')
      setPestSolutionData(null)

      const pestIdToLoad = queryPestId
        ? queryPestId
        : hasVerifiedLiveDetection
          ? detection.pest_id
          : isPineWeevilProfileRequested
            ? 'pine_weevil'
            : null

      if (pestIdToLoad) {
        try {
          const result = await getPestSolutions(pestIdToLoad)
          if (!active) return
          setPestSolutionData(result)
        } catch (loadError) {
          if (!active) return
          setPestSolutionsError(
            loadError.message || 'Unable to load pest solution data.',
          )
        }
      }
    }

    if (pestDirectoryLoaded) loadPestSpecificData()

    return () => {
      active = false
    }
  }, [
    pestDirectoryLoaded,
    queryPestId,
    hasVerifiedLiveDetection,
    isPineWeevilProfileRequested,
    detection?.pest_id,
    pestSolutionsRetryKey,
  ])

  useEffect(() => {
    let active = true

    async function loadHighRiskHistory() {
      setHistoryLoading(true)
      setHistoryError('')
      try {
        const result = await getHighRiskSolutionHistory({ limit: 100 })
        if (!active) return
        setHighRiskHistory(Array.isArray(result.history) ? result.history : [])
        setHighRiskHistoryTotal(
          Number.isInteger(result.total) ? result.total : null,
        )
      } catch (loadError) {
        if (!active) return
        setHighRiskHistory([])
        setHighRiskHistoryTotal(null)
        setHistoryError(loadError.message || 'Unable to load HIGH-risk solution history.')
      } finally {
        if (active) setHistoryLoading(false)
      }
    }

    loadHighRiskHistory()
    return () => {
      active = false
    }
  }, [retryKey])

  const handleClearHistory = async () => {
    if (!confirmClearHistory) {
      setConfirmClearHistory(true)
      setClearHistoryError('')
      return
    }

    setClearingHistory(true)
    setClearHistoryError('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/solutions/history/high-risk`,
        { method: 'DELETE' },
      )
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(
          data?.detail || `Clear history failed with status ${response.status}.`,
        )
      }
      setHighRiskHistory([])
      setHighRiskHistoryTotal(0)
      setSelectedHistoryItem(null)
      setConfirmClearHistory(false)
    } catch (clearError) {
      setClearHistoryError(
        clearError.message || 'Unable to clear HIGH-risk solution history.',
      )
      setConfirmClearHistory(false)
    } finally {
      setClearingHistory(false)
    }
  }

  return (
    <main className="solutions-page">
      <section className="solutions-hero">
        <div className="solutions-hero-copy">
          <p className="solutions-eyebrow">Pest Guard · Evidence-led crop protection</p>
          <h1>Action Today,<br /><em>Healthier Tomorrow</em></h1>
          <p className="solutions-intro">
            Explore evidence-based crop protection. Recommendations are tied
            to their pest, crop, risk and sources; candidate profiles are
            shown separately.
          </p>
          <div className="solution-benefits" aria-label="Solution principles">
            <span><LeafIcon size={18} />Evidence-led</span>
            <span><SparkIcon size={18} />Crop-specific</span>
            <span><SignalIcon size={18} />Field-focused</span>
          </div>
        </div>
        <div className="solutions-hero-visual">
          <img src={solutionsField} alt="Farmer inspecting a crop in the field" />
          <div className="hero-image-caption">
            <span className="caption-dot" />
            <span><strong>Grounded in evidence</strong><small>Support for informed field decisions</small></span>
          </div>
        </div>
      </section>

      <div className="solutions-content">
        <section className="page-section live-detection-section" aria-labelledby="latest-detection-title">
          <div className="section-intro">
            <p className="card-eyebrow">Live field result</p>
            <h2 id="latest-detection-title">Latest Live Detection</h2>
            <p>Detection identity, group, risk and model score are shown as separate values.</p>
            {pestDirectoryError && (
              <p className="inline-error" role="alert">{pestDirectoryError}</p>
            )}
          </div>
          {detectionLoading ? (
            <div className="solution-loading">Loading latest detection…</div>
          ) : hasVerifiedLiveDetection ? (
            <article className="detection-summary">
              <div className="detection-summary-identity">
                <span className="status-indicator" aria-hidden="true" />
                <div>
                  <p className="card-eyebrow">Detected pest · {insectGroup || 'Group unavailable'}</p>
                  <h3>{pestName}</h3>
                  <span className="verification-badge">Pest identified</span>
                </div>
              </div>
              <dl className="detection-metrics">
                <div>
                  <dt>Risk level</dt>
                  <dd className={`risk-${riskLabel.toLowerCase()}`}>{riskLabel}</dd>
                </div>
                <div>
                  <dt>Model score</dt>
                  <dd>{confidenceLabel}</dd>
                  <small>Species prediction score</small>
                </div>
                <div>
                  <dt>Identification</dt>
                  <dd>Identified</dd>
                </div>
              </dl>
              <Link className="text-link" to="/live-monitoring">Open Live Monitoring <ArrowIcon size={15} /></Link>
            </article>
          ) : (
            <article className="detection-summary detection-summary-unconfirmed">
              <div>
                <p className="card-eyebrow">{isNonPest ? 'Non-pest result' : 'Identification unavailable'}</p>
                <h3>{isNonPest ? 'No pest-specific guidance' : hasLiveDetection ? 'Pest identity unavailable' : 'No live detection available'}</h3>
                <p>
                  {isNonPest
                    ? 'The latest result is classified as a non-pest sound.'
                    : 'Pest-specific risk and guidance are shown when an identification is available.'}
                </p>
                {detection?.pest && (
                  <span className="unconfirmed-label">
                    Possible match: {detection.common_name || detection.pest}
                  </span>
                )}
              </div>
              <dl className="detection-metrics unconfirmed-metrics">
                <div>
                  <dt>Main group</dt>
                  <dd>{insectGroup || 'Unavailable'}</dd>
                </div>
                <div>
                  <dt>Risk</dt>
                  <dd className="risk-unconfirmed">Not available</dd>
                </div>
                <div>
                  <dt>Model score</dt>
                  <dd>{Number.isFinite(detectionConfidence) ? confidenceLabel : 'N/A'}</dd>
                </div>
                <div>
                  <dt>Pest match</dt>
                  <dd>Unavailable</dd>
                </div>
              </dl>
              <Link className="text-link" to="/live-monitoring">Open Live Monitoring <ArrowIcon size={15} /></Link>
            </article>
          )}
        </section>

        {pestSolutions.length > 0 && (
          <section
            className="pest-solutions-list"
            aria-labelledby="pest-solutions-title"
          >
            <h2 id="pest-solutions-title">Pest Solutions</h2>
            {pestSolutions.map((item, index) => (
              <PestSolutionCard
                key={item.id || `${item.pest_id}-${index}`}
                item={item}
              />
            ))}
          </section>
        )}

        {pestSolutionsError && (
          <div className="inline-error" role="alert">
            <p>{pestSolutionsError}</p>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setPestSolutionsRetryKey((value) => value + 1)}
            >
              Try again
            </button>
          </div>
        )}
        <PotentialHostProfile profile={activePotentialHostProfile} />
        {verifiedSolutions.length > 0 && (
          <section className="page-section solutions-results-section" aria-labelledby="crop-guidance-title" aria-live="polite">
            <div className="section-intro">
              <p className="card-eyebrow">Crop-specific guidance and candidate profiles</p>
              <h2 id="crop-guidance-title">Crop Damage &amp; Management</h2>
              <p>Recommendations are tied to their pest, crop, risk and sources. Candidate profiles are clearly separated.</p>
            </div>
            <VerifiedSolutionGroups
              items={verifiedSolutions}
              isLiveMatch={hasVerifiedLiveDetection}
            />
          </section>
        )}

        <section className="page-section history-section" aria-labelledby="solution-history-title">
          <div className="history-heading">
            <div className="section-intro">
              <p className="card-eyebrow">Persisted field records</p>
              <h2 id="solution-history-title">Solution History</h2>
              <p>Saved HIGH- and MEDIUM-risk alerts from the backend. No sample records are displayed.</p>
            </div>
            <div className="history-actions">
              <div className="history-count">
                <span>Saved alerts</span>
                <strong>
                  {historyLoading || historyError || highRiskHistoryTotal === null
                    ? '—'
                    : highRiskHistoryTotal}
                </strong>
              </div>
              <button
                type="button"
                className={confirmClearHistory ? 'clear-button is-confirming' : 'clear-button'}
                onClick={handleClearHistory}
                disabled={clearingHistory}
              >
                {clearingHistory ? 'Clearing…' : confirmClearHistory ? 'Confirm clear' : 'Clear history'}
              </button>
              {confirmClearHistory && !clearingHistory && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setConfirmClearHistory(false)
                    setClearHistoryError('')
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
          {clearHistoryError && <p className="inline-error" role="alert">{clearHistoryError}</p>}
          {historyLoading ? (
            <div className="solution-loading">Loading saved alerts…</div>
          ) : historyError ? (
            <div className="inline-error" role="alert">
              <p>{historyError}</p>
              <button type="button" className="secondary-button" onClick={() => setRetryKey((value) => value + 1)}>Try again</button>
            </div>
          ) : highRiskHistory.length === 0 ? (
            <div className="empty-guidance history-empty">
              <LeafIcon size={22} />
              <h3>No HIGH- or MEDIUM-risk solution history yet</h3>
              <p>Saved alerts will appear here when they are returned by the backend.</p>
            </div>
          ) : (
            <div className="history-grid">
              {highRiskHistory.map((item) => {
                const historyKey = item.pest || item.pest_id || ''
                const historyPestRecord = pestDirectory[normalizePestName(item.pest_id)]
                const verifiedHistoryPest =
                  item.pest_verified === true &&
                  Boolean(item.pest_id) &&
                  item.pest_id === historyPestRecord?.pestId
                const savedRisk = String(item.risk || '').toUpperCase()
                const historyRisk = ['HIGH', 'MEDIUM'].includes(savedRisk)
                  ? savedRisk
                  : getDetectionRiskEstimate(item, pestDirectory).risk
                const historyConfidence =
                  item.confidence === null || item.confidence === undefined || item.confidence === ''
                    ? Number.NaN
                    : Number(item.confidence)
                const detectedAt = item.detected_at
                  ? new Date(item.detected_at).toLocaleString()
                  : 'Time not available'

                return (
                  <article key={item.id} className="history-card">
                    <button
                      type="button"
                      className="history-card-trigger"
                      aria-haspopup="dialog"
                      onClick={() => setSelectedHistoryItem(item)}
                    >
                      <div>
                        <p className="card-eyebrow">Saved field detection</p>
                        <h3>{getCommonPestName(historyKey, pestDirectory, item)}</h3>
                      </div>
                      <span className={`history-risk risk-${historyRisk.toLowerCase()}`}>
                        {historyRisk}
                      </span>
                      <div className="history-card-meta">
                        <span><small>Model score</small><strong>{verifiedHistoryPest && Number.isFinite(historyConfidence) ? formatModelScore(historyConfidence) : 'N/A'}</strong></span>
                        <span><small>Detected</small><strong>{detectedAt}</strong></span>
                        <span><small>Device</small><strong>{item.device_id || 'Unavailable'}</strong></span>
                      </div>
                      <span className="history-card-toggle">View saved solution details</span>
                    </button>
                  </article>
                )
              })}
            </div>
          )}
          {selectedHistoryItem && (
            <HistorySolutionModal
              item={selectedHistoryItem}
              pestDirectory={pestDirectory}
              onClose={() => setSelectedHistoryItem(null)}
            />
          )}
        </section>
      </div>
    </main>
  )
}

export default Solutions
