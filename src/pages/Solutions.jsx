import { useEffect, useState } from 'react'
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
            {typeof source !== 'string' && source.reviewed_on && (
              <span>Reviewed {source.reviewed_on}</span>
            )}
          </li>
        )
      })}
    </ul>
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

function PestSolutionCard({ item }) {
  const sources = getSources(item)
  const details = [
    ['Description', item.description],
    ['Habitat', item.habitat],
    ['Crop context', item.crop_context],
    ['Crop damage', item.crop_damage || item.damage_notes],
    ['Affected plant parts', item.affected_plant_parts || item.affected_parts],
    ['Identification', item.identification_signs],
    ['Management', item.management || item.recommendations],
    ['Biological control', item.biological_control_options || item.biological_control],
    ['Cultural control', item.cultural_control_methods || item.cultural_control],
    ['Mechanical control', item.mechanical_control_methods || item.mechanical_control],
    ['Monitoring', item.monitoring],
    ['Prevention', item.prevention],
    ['Safety', item.safety_precautions],
    ['Geographic qualification', item.geographic_qualification || item.geographic_limitation],
    ['Economic threshold', item.economic_threshold || item.action_threshold],
    ['Notes', item.notes],
  ]

  return (
    <article className="potential-host-profile pest-solution-card">
      <div className="potential-host-heading">
        <div>
          <p className="card-eyebrow">
            Pest-specific solution · {item.risk_level} risk
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
        {item.chemical_control_options && (
          <PestSolutionDetails
            label="Chemical control"
            value={item.chemical_control_options}
          />
        )}
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
              <small>{host.reviewStatus}</small>
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
  const isVerified = Boolean(recommendation && recommendationSources.length)
  const safetySources = sources.filter((source) =>
    source.supports?.includes('safety_precautions'),
  )

  return (
    <article className="recommendation-card">
      <div className="recommendation-heading">
        <h4>{category.title}</h4>
        <span className={isVerified ? 'verification-badge' : 'unverified-badge'}>
          {isVerified ? 'Source verified' : 'Not verified'}
        </span>
      </div>
      {isVerified ? (
        <p>{recommendation}</p>
      ) : (
        <p className="solution-unavailable">Solution not verified yet.</p>
      )}
      {isVerified && category.safetyKey && item[category.safetyKey] && safetySources.length > 0 && (
        <p className="safety-note">
          <strong>Safety:</strong> {item[category.safetyKey]}
        </p>
      )}
      {isVerified && <SourceList sources={recommendationSources} />}
      {isVerified && category.safetyKey && item[category.safetyKey] && safetySources.length > 0 && (
        <SourceList sources={safetySources} />
      )}
    </article>
  )
}

function VerifiedSolution({ item, isLiveMatch }) {
  const sources = Array.isArray(item.source_references) ? item.source_references : []
  const hasEvidence = (key) => sources.some((source) => source.supports?.includes(key))
  const renderEvidence = (title, value, evidenceKey, className = '') => {
    const verified = Boolean(value && hasEvidence(evidenceKey))

    return (
      <EvidenceCard title={title} className={className}>
        {verified ? (
          <p>{value}</p>
        ) : (
          <p className="solution-unavailable">
            Information not verified or not available for this pest-crop record.
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
  const preventionIsVerified = Boolean(item.prevention && preventionSources.length)

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
        <span className="verification-badge">Source verified</span>
      </div>
      {isLiveMatch && (
        <p className="match-note">Matches the current verified detection.</p>
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
            {preventionIsVerified ? 'Source verified' : 'Not verified'}
          </span>
          {preventionIsVerified ? (
            <p>{item.prevention}</p>
          ) : (
            <p className="solution-unavailable">Solution not verified yet.</p>
          )}
          {preventionIsVerified && <SourceList sources={preventionSources} />}
        </EvidenceCard>
      </div>
    </article>
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
  const riskLabel = hasVerifiedLiveDetection ? catalogRisk : 'UNCONFIRMED'
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

      const pestIdToLoad = queryPest
        ? queryPest
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
    queryPest,
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
          <p className="solutions-eyebrow">Pest Guard · Verified crop protection</p>
          <h1>Action Today,<br /><em>Healthier Tomorrow</em></h1>
          <p className="solutions-intro">
            Explore evidence-based crop protection. Verified recommendations
            appear only when pest, crop, risk and source have been reviewed
            together; pending candidate profiles are labelled separately.
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
                  <span className="verification-badge">Verified catalogue match</span>
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
                  <dd>Verified</dd>
                </div>
              </dl>
              <Link className="text-link" to="/live-monitoring">Open Live Monitoring <ArrowIcon size={15} /></Link>
            </article>
          ) : (
            <article className="detection-summary detection-summary-unconfirmed">
              <div>
                <p className="card-eyebrow">{isNonPest ? 'Non-pest result' : 'Identification unconfirmed'}</p>
                <h3>{isNonPest ? 'No pest-specific guidance' : hasLiveDetection ? 'Unknown pest' : 'No live detection available'}</h3>
                <p>
                  {isNonPest
                    ? 'The latest result is classified as a non-pest sound.'
                    : 'A verified species identity and catalogue match are required before pest-specific risk or guidance can be confirmed.'}
                </p>
                {detection?.pest && (
                  <span className="unconfirmed-label">
                    Model candidate: {detection.common_name || detection.pest}
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
                  <dd className="risk-unconfirmed">UNCONFIRMED</dd>
                </div>
                <div>
                  <dt>Model score</dt>
                  <dd>{Number.isFinite(detectionConfidence) ? confidenceLabel : 'N/A'}</dd>
                </div>
                <div>
                  <dt>Catalogue status</dt>
                  <dd>Unverified</dd>
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

        <section className="page-section solutions-results-section" aria-labelledby="crop-guidance-title" aria-live="polite">
          <div className="section-intro">
            <p className="card-eyebrow">Verified guidance and review candidates</p>
            <h2 id="crop-guidance-title">Crop Damage &amp; Management</h2>
            <p>Verified recommendations are tied to their pest, crop, risk and sources. Pending profiles are clearly marked.</p>
          </div>
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
            <div className="verified-solution-list">
              {verifiedSolutions.map((item) => (
                <VerifiedSolution
                  key={item.solution_id}
                  item={item}
                  isLiveMatch={hasVerifiedLiveDetection && item.pest_id === detection.pest_id}
                />
              ))}
            </div>
          )}
        </section>

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
                const historyRisk = getDetectionRiskEstimate(item, pestDirectory)
                const historyConfidence =
                  item.confidence === null || item.confidence === undefined || item.confidence === ''
                    ? Number.NaN
                    : Number(item.confidence)
                const detectedAt = item.detected_at
                  ? new Date(item.detected_at).toLocaleString()
                  : 'Time not available'

                return (
                  <details key={item.id} className="history-card">
                    <summary>
                      <div>
                        <p className="card-eyebrow">{verifiedHistoryPest ? 'Verified catalogue match' : 'Unconfirmed model prediction'}</p>
                        <h3>{verifiedHistoryPest ? getCommonPestName(historyKey, pestDirectory, item) : 'Unconfirmed model prediction'}</h3>
                      </div>
                      <span className={`history-risk risk-${historyRisk.risk.toLowerCase()}`}>{historyRisk.risk}</span>
                      <div className="history-card-meta">
                        <span><small>Model score</small><strong>{verifiedHistoryPest && Number.isFinite(historyConfidence) ? formatModelScore(historyConfidence) : 'N/A'}</strong></span>
                        <span><small>Detected</small><strong>{detectedAt}</strong></span>
                        <span><small>Device</small><strong>{item.device_id || 'Unavailable'}</strong></span>
                      </div>
                      <span className="history-card-toggle">View persisted detection record</span>
                    </summary>
                    <div className="history-card-details">
                      <p className="solution-unavailable">No verified solution content is available for this saved detection.</p>
                    </div>
                  </details>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default Solutions
