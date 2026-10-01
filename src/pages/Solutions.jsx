import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowIcon, LeafIcon, SignalIcon, SparkIcon } from '../components/Icons'
import { formatTemperature, formatHumidity } from '../utils/formatters'
import { useLiveDetection } from '../hooks/useLiveDetection'
import { getPestInfo, getSolution } from '../services/api'
import solutionsField from '../assets/solutions-field.jpg'
import './Solutions.css'

function Solutions() {
  const { detection, loading: detectionLoading } = useLiveDetection()

  const [solution, setSolution] = useState(null)
  const [pest, setPest] = useState(null)
  const [loadingSolution, setLoadingSolution] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    async function loadLivePestSolution() {
      const pestId = detection?.pest

      if (!pestId) {
        setSolution(null)
        setPest(null)
        setError('')
        setLoadingSolution(false)
        return
      }

      setLoadingSolution(true)
      setError('')

      try {
        const [solutionResult, pestResult] = await Promise.allSettled([
          getSolution(pestId),
          getPestInfo(pestId),
        ])

        if (!active) return

        const nextSolution =
          solutionResult.status === 'fulfilled'
            ? solutionResult.value?.solution || solutionResult.value
            : null

        const nextPest =
          pestResult.status === 'fulfilled'
            ? pestResult.value?.pest || pestResult.value
            : null

        setSolution(nextSolution)
        setPest(nextPest)
      } catch {
        if (active) {
          setSolution(null)
          setPest(null)
          setError('Unable to load the live pest information.')
        }
      } finally {
        if (active) {
          setLoadingSolution(false)
        }
      }
    }

    loadLivePestSolution()

    return () => {
      active = false
    }
  }, [detection?.pest])

  const isLoading = detectionLoading || loadingSolution
  const hasLivePest = Boolean(detection?.pest)

  const confidence = Number(detection?.confidence)
  const confidenceLabel = Number.isFinite(confidence)
    ? `${(confidence * 100).toFixed(1)}%`
    : 'Not available'

  const statusLabel =
    detection?.status === 'HARMFUL_PEST'
      ? 'HARMFUL PEST'
      : detection?.pest
        ? 'AI PREDICTION'
        : 'NO LIVE DETECTION'

  return (
    <div className="solutions-page">
      <section className="solutions-hero">
        <div className="solutions-hero-copy">
          <p className="solutions-eyebrow">Live pest solution</p>
          <h1>Action Today<br /><em>Healthier Tomorrow</em></h1>
          <p className="solutions-intro">
            This page shows guidance for the pest currently detected by Pest Guard.
            It does not show a separate static solution library.
          </p>

          <div className="solution-benefits" aria-label="Solution benefits">
            <span><LeafIcon size={18} />Targeted Advice</span>
            <span><SparkIcon size={18} />Sustainable Practice</span>
            <span><SignalIcon size={18} />Crop Protection</span>
          </div>
        </div>

        <div className="solutions-hero-visual">
          <img src={solutionsField} alt="Farmer inspecting tomato crops" />
          <div className="smart-response-card">
            <span className="response-dot" />
            <div>
              <strong>Live response</strong>
              <small>Based on the latest field detection</small>
            </div>
          </div>
        </div>
      </section>

      <section className="solutions-content" aria-live="polite">
        {isLoading && (
          <div className="solution-loading">
            Loading the latest detected pest...
          </div>
        )}

        {!isLoading && error && (
          <div className="solution-error">
            <p>{error}</p>
            <Link className="solutions-button" to="/live-monitoring">
              Back to Live Monitoring <ArrowIcon size={15} />
            </Link>
          </div>
        )}

        {!isLoading && !error && hasLivePest && (
          <article className="active-solution-card">
            <div className="active-solution-topline">
              <div>
                <p className="card-eyebrow">Live detected pest</p>
                <h2>{pest?.name || detection.pest}</h2>
                {pest?.scientific_name && (
                  <p>{pest.scientific_name}</p>
                )}
              </div>

              <div className="risk-block">
                <span>Status</span>
                <strong className={`risk-${String(detection.risk || 'unknown').toLowerCase()}`}>
                  {statusLabel}
                </strong>
              </div>
            </div>

            <div className="confidence-row">
              <span>AI confidence</span>
              <strong>{confidenceLabel}</strong>
            </div>

            <div className="environmental-conditions">
              <div className="env-item">
                <span>Temperature</span>
                <strong>{formatTemperature(detection?.temperature)}</strong>
              </div>
              <div className="env-item">
                <span>Humidity</span>
                <strong>{formatHumidity(detection?.humidity)}</strong>
              </div>
            </div>

            {pest?.description && (
              <div className="solution-sections">
                <section>
                  <span className="section-number">01</span>
                  <div>
                    <h3>About this pest</h3>
                    <p>{pest.description}</p>
                  </div>
                </section>
              </div>
            )}

            {solution ? (
              <div className="solution-sections">
                <section>
                  <span className="section-number">02</span>
                  <div>
                    <h3>Recommended action</h3>
                    <p>{solution.recommended_action}</p>
                  </div>
                </section>

                <section>
                  <span className="section-number">03</span>
                  <div>
                    <h3>Prevention</h3>
                    <p>{solution.prevention}</p>
                  </div>
                </section>
              </div>
            ) : (
              <div className="solution-error">
                <p>
                  This AI-detected pest does not have a curated solution record
                  in the Pest Guard database yet. The detected pest name and AI
                  confidence are shown above without inventing treatment advice.
                </p>
              </div>
            )}

            <Link className="solutions-button" to="/live-monitoring">
              View Live Monitoring <ArrowIcon size={15} />
            </Link>
          </article>
        )}

        {!isLoading && !error && !hasLivePest && (
          <article className="empty-solution-card">
            <div className="empty-solution-icon"><LeafIcon size={25} /></div>
            <p className="card-eyebrow">Waiting for live detection</p>
            <h2>No Live Pest Detected</h2>
            <p>
              Start or wait for a field detection. The detected pest and its
              available solution will appear here automatically.
            </p>
            <Link className="solutions-button" to="/live-monitoring">
              Open Live Monitoring <ArrowIcon size={15} />
            </Link>
          </article>
        )}
      </section>
    </div>
  )
}

export default Solutions
