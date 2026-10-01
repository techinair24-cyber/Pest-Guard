import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowIcon, LeafIcon, SignalIcon, SparkIcon } from '../components/Icons'
import { formatTemperature, formatHumidity } from '../utils/formatters'
import { useLiveDetection } from '../hooks/useLiveDetection'
import { getPestInfo, getSolution } from '../services/api'
import solutionsField from '../assets/solutions-field.jpg'
import './Solutions.css'

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  'https://pest-guard-1q36.onrender.com'

function Solutions() {
  const { detection, loading: detectionLoading } = useLiveDetection()

  const [solution, setSolution] = useState(null)
  const [pest, setPest] = useState(null)
  const [allSolutions, setAllSolutions] = useState([])
  const [loadingSolutions, setLoadingSolutions] = useState(true)
  const [solutionsError, setSolutionsError] = useState('')
  const [loadingSolution, setLoadingSolution] = useState(false)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let active = true

    async function loadAllSolutions() {
      setLoadingSolutions(true)
      setSolutionsError('')

      try {
        const response = await fetch(`${API_BASE}/api/solutions`)

        if (!response.ok) {
          throw new Error(`Solutions request failed: ${response.status}`)
        }

        const data = await response.json()

        if (active) {
          setAllSolutions(Array.isArray(data?.solutions) ? data.solutions : [])
        }
      } catch {
        if (active) {
          setAllSolutions([])
          setSolutionsError('Unable to load the solutions library.')
        }
      } finally {
        if (active) {
          setLoadingSolutions(false)
        }
      }
    }

    loadAllSolutions()

    return () => {
      active = false
    }
  }, [retryKey])

  useEffect(() => {
    let active = true

    async function loadActiveSolution() {
      if (!detection?.pest) {
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

          if (detection?.status === 'HARMFUL_PEST') {
            setError(
              'This AI prediction does not have a detailed curated solution yet.',
            )
          } else {
            setError('')
          }
        }
      } finally {
        if (active) {
          setLoadingSolution(false)
        }
      }
    }

    loadActiveSolution()

    return () => {
      active = false
    }
  }, [detection?.pest, detection?.status, retryKey])

  const isHarmfulPest = detection?.status === 'HARMFUL_PEST'

  const confidence = Number(detection?.confidence)
  const confidenceLabel = Number.isFinite(confidence)
    ? `${(confidence * 100).toFixed(1)}%`
    : 'Not available'

  const isLoading =
    detectionLoading ||
    loadingSolutions ||
    (Boolean(detection?.pest) && loadingSolution)

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
          <div className="solution-loading">
            Loading pest solutions...
          </div>
        )}

        {!isLoading && solutionsError && (
          <div className="solution-error">
            <p>{solutionsError}</p>
            <button
              type="button"
              onClick={() => setRetryKey((value) => value + 1)}
            >
              Try again
            </button>
          </div>
        )}

        {!isLoading && isHarmfulPest && solution && pest && (
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

        {!isLoading && error && !solution && isHarmfulPest && (
          <div className="solution-error">
            <p>{error}</p>
          </div>
        )}

        {!isLoading && allSolutions.length > 0 && (
          <section style={{ marginTop: '28px' }}>
            <div style={{ marginBottom: '18px' }}>
              <p className="card-eyebrow">Solutions library</p>
              <h2 style={{ margin: 0 }}>Available Pest Guidance</h2>
              <p style={{ marginTop: '8px' }}>
                Curated crop-protection guidance available from the Pest Guard backend.
              </p>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '18px',
                alignItems: 'stretch',
              }}
            >
              {allSolutions.map((item) => (
                <article
                  key={item.pest_id}
                  className="active-solution-card"
                  style={{
                    margin: 0,
                    minWidth: 0,
                    height: '100%',
                    boxSizing: 'border-box',
                  }}
                >
                  <p className="card-eyebrow">Pest solution</p>
                  <h2 style={{ marginBottom: '18px' }}>{item.title}</h2>

                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '16px',
                      width: '100%',
                    }}
                  >
                    <div
                      style={{
                        paddingBottom: '14px',
                        borderBottom: '1px solid rgba(42, 69, 56, 0.14)',
                      }}
                    >
                      <span
                        style={{
                          display: 'block',
                          marginBottom: '6px',
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                          opacity: 0.58,
                        }}
                      >
                        Description
                      </span>
                      <p style={{ margin: 0, lineHeight: 1.65 }}>
                        {item.description}
                      </p>
                    </div>

                    <div
                      style={{
                        paddingBottom: '14px',
                        borderBottom: '1px solid rgba(42, 69, 56, 0.14)',
                      }}
                    >
                      <span
                        style={{
                          display: 'block',
                          marginBottom: '6px',
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                          opacity: 0.58,
                        }}
                      >
                        Recommended action
                      </span>
                      <p style={{ margin: 0, lineHeight: 1.65 }}>
                        {item.recommended_action}
                      </p>
                    </div>

                    <div>
                      <span
                        style={{
                          display: 'block',
                          marginBottom: '6px',
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                          opacity: 0.58,
                        }}
                      >
                        Prevention
                      </span>
                      <p style={{ margin: 0, lineHeight: 1.65 }}>
                        {item.prevention}
                      </p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {!isLoading && !solutionsError && allSolutions.length === 0 && !isHarmfulPest && (
          <article className="empty-solution-card">
            <div className="empty-solution-icon"><LeafIcon size={25} /></div>
            <p className="card-eyebrow">Pest solution</p>
            <h2>No Solutions Available</h2>
            <p>The solutions service returned no curated pest guidance.</p>
            <button
              type="button"
              className="solutions-button"
              onClick={() => setRetryKey((value) => value + 1)}
            >
              Reload Solutions <ArrowIcon size={15} />
            </button>
          </article>
        )}

        {!isLoading && detection?.pest && !solution && !isHarmfulPest && (
          <div className="solution-error">
            <p>
              AI prediction: <strong>{detection.pest}</strong>. A curated
              solution for this model class is not currently available.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}

export default Solutions
