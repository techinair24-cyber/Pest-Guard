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
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let active = true

    async function loadLiveSolution() {
      if (!detection?.pest) {
        setSolution(null)
        setPest(null)
        setError('')
        setLoadingSolution(false)
        return
      }

      setLoadingSolution(true)
      setError('')
      setSolution(null)
      setPest(null)

      try {
        const [solutionResult, pestResult] = await Promise.allSettled([
          getSolution(detection.pest),
          getPestInfo(detection.pest),
        ])

        if (!active) return

        const nextSolution =
          solutionResult.status === 'fulfilled'
            ? solutionResult.value?.solution || solutionResult.value
            : null

        const nextPest =
          pestResult.status === 'fulfilled' ? pestResult.value : null

        setSolution(nextSolution)
        setPest(nextPest)

        if (!nextSolution) {
          setError(
            'A live AI prediction was received, but detailed curated solution guidance is not available for this model class yet.',
          )
        }
      } catch {
        if (active) {
          setSolution(null)
          setPest(null)
          setError('Unable to load the live pest solution information.')
        }
      } finally {
        if (active) {
          setLoadingSolution(false)
        }
      }
    }

    loadLiveSolution()

    return () => {
      active = false
    }
  }, [detection?.pest, detection?.status, retryKey])

  const isLoading = detectionLoading || loadingSolution
  const hasLiveDetection = Boolean(detection?.pest)
  const confidence = Number(detection?.confidence)
  const confidenceLabel = Number.isFinite(confidence)
    ? `${(confidence * 100).toFixed(1)}%`
    : 'Not available'

  const statusLabel =
    detection?.status === 'HARMFUL_PEST'
      ? 'HARMFUL PEST'
      : detection?.status === 'NON_PEST'
        ? 'NON-PEST'
        : 'AI PREDICTION'

  const pestName = pest?.name || detection?.pest || 'Detected insect'

  return (
    <div className="solutions-page">
      <section className="solutions-hero">
        <div className="solutions-hero-copy">
          <p className="solutions-eyebrow">Live pest solution</p>
          <h1>Action Today<br /><em>Healthier Tomorrow</em></h1>
          <p className="solutions-intro">
            This page follows the latest live AI detection and shows the available guidance for that detected insect.
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
              <small>Following the latest AI detection</small>
            </div>
          </div>
        </div>
      </section>

      <section className="solutions-content" aria-live="polite">
        {isLoading && (
          <div className="solution-loading">Loading live pest solution...</div>
        )}

        {!isLoading && !hasLiveDetection && (
          <article className="empty-solution-card">
            <div className="empty-solution-icon"><LeafIcon size={25} /></div>
            <p className="card-eyebrow">Live detection</p>
            <h2>No Live Pest Detection Yet</h2>
            <p>
              Run a fresh detection from the field unit. This page will automatically show the latest detected insect and its available solution.
            </p>
            <Link className="solutions-button" to="/live-monitoring">
              Open Live Monitoring <ArrowIcon size={15} />
            </Link>
          </article>
        )}

        {!isLoading && hasLiveDetection && (
          <article className="active-solution-card">
            <div className="active-solution-topline">
              <div>
                <p className="card-eyebrow">Latest live detection</p>
                <h2>{pestName}</h2>
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

            {pest && (
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
                <p>{error}</p>
              </div>
            )}

            <Link className="solutions-button" to="/live-monitoring">
              View Live Monitoring <ArrowIcon size={15} />
            </Link>
          </article>
        )}

        {!isLoading && hasLiveDetection && error && solution && (
          <div className="solution-error">
            <p>{error}</p>
          </div>
        )}

        {!isLoading && error && !hasLiveDetection && (
          <div className="solution-error">
            <p>{error}</p>
            <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
              Try again
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

export default Solutions
