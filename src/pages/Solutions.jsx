import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { ArrowIcon, LeafIcon, SignalIcon, SparkIcon } from '../components/Icons'
import { useLiveDetection } from '../hooks/useLiveDetection'
import {
  API_BASE_URL,
  getCrops,
  getCropSolutions,
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
import solutionsField from '../assets/solutions-field.jpg'
import './Solutions.css'

const MANAGEMENT_CATEGORIES = [
  {
    key: 'cultural_control_methods',
    title: 'Cultural Control',
    safetyKey: null,
  },
  {
    key: 'biological_control_options',
    title: 'Biological Control',
    safetyKey: null,
  },
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
      {sources.map((source) => (
        <li key={source.url}>
          <a href={source.url} target="_blank" rel="noreferrer">
            {source.title} — {source.organization}
          </a>
          {source.reviewed_on && <span>Reviewed {source.reviewed_on}</span>}
        </li>
      ))}
    </ul>
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

function RecommendationCard({ item, category }) {
  const recommendation = item[category.key]
  const sources = item.source_references || []
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
        <EvidenceCard title="Crop Damage & Symptoms">
          {item.crop_damage && (item.source_references || []).some(
            (source) => source.supports?.includes('crop_damage'),
          ) ? (
            <p>{item.crop_damage}</p>
          ) : (
            <p className="solution-unavailable">Solution not verified yet.</p>
          )}
          <p className="evidence-label">Supporting evidence</p>
          <SourceList
            sources={(item.source_references || []).filter(
              (source) => source.supports?.includes('crop_damage'),
            )}
          />
        </EvidenceCard>

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

  const [solution, setSolution] = useState(null)
  const [crops, setCrops] = useState([])
  const [cropSearchResults, setCropSearchResults] = useState([])
  const [pestDirectory, setPestDirectory] = useState({})
  const [loadingSolution, setLoadingSolution] = useState(false)
  const [error, setError] = useState('')
  const [canRetry, setCanRetry] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const [cropDraft, setCropDraft] = useState('')
  const [selectedCrop, setSelectedCrop] = useState('')
  const [cropLoadError, setCropLoadError] = useState('')
  const [highRiskHistory, setHighRiskHistory] = useState([])
  const [highRiskHistoryTotal, setHighRiskHistoryTotal] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const [clearingHistory, setClearingHistory] = useState(false)
  const [confirmClearHistory, setConfirmClearHistory] = useState(false)
  const [clearHistoryError, setClearHistoryError] = useState('')

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
  const queryMatchesDetection =
    !queryPest ||
    normalizePestName(queryPest) === normalizePestName(detection?.pest)
  const hasVerifiedLiveDetection =
    hasVerifiedCatalogMatch &&
    status === 'HARMFUL_PEST' &&
    queryMatchesDetection
  const isNonPest = status === 'NON_PEST'
  const hasLiveDetection = Boolean(detection?.pest) || isNonPest
  const detectionConfidence =
    detection?.confidence === null ||
    detection?.confidence === undefined ||
    detection?.confidence === ''
      ? Number.NaN
      : Number(detection.confidence)
  const confidenceLabel = Number.isFinite(detectionConfidence)
    ? formatModelScore(detectionConfidence)
    : 'N/A'
  const selectedCropRecord = crops.find((crop) => crop.crop_id === selectedCrop)
  const verifiedSolutions = Array.isArray(solution?.solutions)
    ? solution.solutions
    : []
  const liveSolution = verifiedSolutions.find(
    (item) => item.pest_id === detection?.pest_id,
  )
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

    async function loadReferenceData() {
      setCropLoadError('')
      try {
        const [availableCrops, pests] = await Promise.all([
          getCrops(),
          getPests(),
        ])
        if (!active) return
        setCrops(availableCrops)
        setCropSearchResults(availableCrops)
        setPestDirectory(buildPestDirectory(pests))
      } catch (loadError) {
        if (!active) return
        setCropLoadError(loadError.message || 'Unable to load supported crops.')
      }
    }

    loadReferenceData()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const timer = setTimeout(async () => {
      try {
        const results = await getCrops(cropDraft)
        if (active) setCropSearchResults(results)
      } catch (loadError) {
        if (active) setCropLoadError(loadError.message || 'Unable to search crops.')
      }
    }, 180)

    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [cropDraft])

  useEffect(() => {
    let active = true

    async function loadSelectedCropSolutions() {
      if (!selectedCrop) {
        setSolution(null)
        setError('')
        setCanRetry(false)
        setLoadingSolution(false)
        return
      }

      setLoadingSolution(true)
      setError('')
      setCanRetry(false)
      try {
        const result = await getCropSolutions(selectedCrop)
        if (active) setSolution(result)
      } catch (loadError) {
        if (!active) return
        setSolution(null)
        setError(loadError.message || 'Unable to load crop-specific solutions.')
        setCanRetry(true)
      } finally {
        if (active) setLoadingSolution(false)
      }
    }

    loadSelectedCropSolutions()
    return () => {
      active = false
    }
  }, [selectedCrop, retryKey])

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
            Explore evidence-based crop protection. Guidance appears only when
            a pest, crop, risk and source have been reviewed together.
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
        <section className="page-section crop-search-section" aria-labelledby="crop-search-title">
          <div className="section-intro">
            <p className="card-eyebrow">Crop-specific evidence</p>
            <h2 id="crop-search-title">Search by crop</h2>
            <p>Choose from supported crops to view only verified pest relationships and solutions.</p>
          </div>
          <label htmlFor="solution-crop">Search supported Indian crops</label>
          <input
            id="solution-crop"
            type="search"
            maxLength={100}
            value={cropDraft}
            onChange={(event) => {
              setCropDraft(event.target.value)
              setSelectedCrop('')
              setSolution(null)
            }}
            placeholder="Type a crop name"
            aria-describedby="crop-search-help"
          />
          <p id="crop-search-help" className="context-note">
            Crop selection is context you provide. It does not mean the crop or
            any pest has been detected.
          </p>
          {cropLoadError && <p className="inline-error" role="alert">{cropLoadError}</p>}

          {cropDraft.trim().length >= 2 && cropSearchResults.length > 0 && (
            <div className="crop-results" role="listbox" aria-label="Matching supported crops">
              {cropSearchResults.map((crop) => (
                <button
                  key={crop.crop_id}
                  type="button"
                  role="option"
                  aria-selected={selectedCrop === crop.crop_id}
                  className={selectedCrop === crop.crop_id ? 'crop-option is-selected' : 'crop-option'}
                  onClick={() => {
                    setCropDraft(crop.name)
                    setSelectedCrop(crop.crop_id)
                  }}
                >
                  {crop.name}
                </button>
              ))}
            </div>
          )}
          {cropDraft.trim().length >= 2 && !cropLoadError && cropSearchResults.length === 0 && (
            <p className="solution-unavailable">No supported crop matches that search.</p>
          )}
          {selectedCrop && (
            <div className="crop-results-summary" aria-live="polite">
              <strong>{selectedCropRecord?.name || 'Selected crop'}</strong>
              <span> · {loadingSolution ? 'Checking verified records…' : `${verifiedSolutions.length} verified solution${verifiedSolutions.length === 1 ? '' : 's'}`}</span>
            </div>
          )}
        </section>

        <section className="page-section live-detection-section" aria-labelledby="latest-detection-title">
          <div className="section-intro">
            <p className="card-eyebrow">Live field result</p>
            <h2 id="latest-detection-title">Latest Live Detection</h2>
            <p>Detection identity, group, risk and model score are shown as separate values.</p>
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
              {selectedCrop && (
                <p className="detection-crop-match">
                  {liveSolution
                    ? `A verified ${selectedCropRecord?.name || 'crop'} solution matches this pest.`
                    : `No verified ${selectedCropRecord?.name || 'crop'} solution is assigned to this pest.`}
                </p>
              )}
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

        <section className="page-section solutions-results-section" aria-labelledby="crop-guidance-title" aria-live="polite">
          <div className="section-intro">
            <p className="card-eyebrow">Reviewed records only</p>
            <h2 id="crop-guidance-title">
              {selectedCropRecord ? `Guidance for ${selectedCropRecord.name}` : 'Crop Damage & Management'}
            </h2>
            <p>Each record is independently verified for its pest, crop, risk and supporting source.</p>
          </div>

          {!selectedCrop ? (
            <div className="empty-guidance">
              <LeafIcon size={22} />
              <p>Select a crop above to check for source-verified pest relationships.</p>
            </div>
          ) : loadingSolution ? (
            <div className="solution-loading">Loading verified crop-specific solutions…</div>
          ) : error ? (
            <div className="inline-error" role="alert">
              <p>{error}</p>
              {canRetry && <button type="button" className="secondary-button" onClick={() => setRetryKey((value) => value + 1)}>Try again</button>}
            </div>
          ) : verifiedSolutions.length ? (
            <div className="verified-solution-list">
              {verifiedSolutions.map((item) => (
                <VerifiedSolution
                  key={item.solution_id}
                  item={item}
                  isLiveMatch={hasVerifiedLiveDetection && item.pest_id === detection.pest_id}
                />
              ))}
            </div>
          ) : (
            <div className="empty-guidance">
              <LeafIcon size={22} />
              <h3>No verified solutions available</h3>
              <p>
                There is no source-verified pest association and risk-specific
                solution for {selectedCropRecord?.name || 'this crop'} yet.
                Unverified associations and recommendations are not shown.
              </p>
            </div>
          )}
        </section>

        <section className="page-section history-section" aria-labelledby="solution-history-title">
          <div className="history-heading">
            <div className="section-intro">
              <p className="card-eyebrow">Persisted field records</p>
              <h2 id="solution-history-title">Solution History</h2>
              <p>Saved HIGH-risk alerts from the backend. No sample records are displayed.</p>
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
              <h3>No HIGH-risk solution history yet</h3>
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
