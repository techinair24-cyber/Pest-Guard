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

    async function loadSolution() {
      if (detection?.status !== 'HARMFUL_PEST' || !detection.pest) {
        setSolution(null)
        setPest(null)
        setError('')
        setLoadingSolution(false)
        return
      }

      setLoadingSolution(true)
      setError('')

      try {
        const [nextSolution, nextPest] = await Promise.all([
          getSolution(detection.pest),
          getPestInfo(detection.pest),
        ])

        if (active) {
          setSolution(nextSolution?.solution || nextSolution)
          setPest(nextPest)
        }
      } catch {
        if (active) {
          setSolution(null)
          setPest(null)
          setError('Unable to load solution information.')
        }
      } finally {
        if (active) {
          setLoadingSolution(false)
        }
      }
    }

    loadSolution()

    return () => {
      active = false
    }
  }, [detection?.pest, detection?.status, retryKey])

  const isHarmfulPest = detection?.status === 'HARMFUL_PEST'
  const isLoading = detectionLoading || (isHarmfulPest && loadingSolution)
  const hasAlert = isHarmfulPest && solution && pest
  const confidence = Number(detection?.confidence)
  const confidenceLabel = Number.isFinite(confidence)
    ? `${(confidence * 100).toFixed(1)}%`
    : 'Not available'

  return (
    <div className="solutions-page">
      <section className="solutions-hero">
        <div className="solutions-hero-copy">
          <p className="solutions-eyebrow">Pest solution</p>
          <h1>Action Today<br /><em>Healthier Tomorrow</em></h1>
          <p className="solutions-intro">
            When a pest is detected, get focused information to protect crops and support better field decisions.
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
              <strong>Smart response</strong>
              <small>Pest-specific guidance</small>
            </div>
          </div>
        </div>
      </section>

      <section className="solutions-content" aria-live="polite">
        {isLoading && (
          <div className="solution-loading">Loading pest solution...</div>
        )}

        {!isLoading && error && (
          <div className="solution-error">
            <p>{error}</p>
            <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
              Try again
            </button>
          </div>
        )}

        {!isLoading && !error && hasAlert && (
          <article className="active-solution-card">
            <div className="active-solution-topline">
              <div>
                <p className="card-eyebrow">Detected pest</p>
                <h2>{pest.name}</h2>
              </div>
              <div className="risk-block">
                <span>Risk level</span>
                <strong className={`risk-${String(detection.risk || 'unknown').toLowerCase()}`}>
                  {detection.risk || 'Not available'}
                </strong>
              </div>
            </div>

            <div className="confidence-row">
              <span>Confidence</span>
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

            <div className="solution-sections">
              <section>
                <span className="section-number">01</span>
                <div>
                  <h3>About this pest</h3>
                  <p>{pest.description}</p>
                </div>
              </section>
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

            <Link className="solutions-button" to="/live-monitoring">
              View Live Monitoring <ArrowIcon size={15} />
            </Link>
          </article>
        )}

        {!isLoading && !error && !hasAlert && (
          <article className="empty-solution-card">
            <div className="empty-solution-icon"><LeafIcon size={25} /></div>
            <p className="card-eyebrow">Pest solution</p>
            <h2>No Active Pest Alert</h2>
            <p>Solutions will appear here automatically when Pest Guard detects a harmful crop pest.</p>
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
