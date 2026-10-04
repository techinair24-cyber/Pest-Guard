import { useEffect, useState } from 'react'

import { Link, useLocation } from 'react-router-dom'

import { ArrowIcon, LeafIcon, SignalIcon, SparkIcon } from '../components/Icons'

import { formatTemperature, formatHumidity } from '../utils/formatters'

import { useLiveDetection } from '../hooks/useLiveDetection'

import {
  API_BASE_URL,
  getHighRiskSolutionHistory,
  getPests,
  getSolution,
} from '../services/api'

import {

  buildPestDirectory,

  getCommonPestName,

  getDisplayPestName,

  normalizePestName,

} from '../utils/pestNames'

import solutionsField from '../assets/solutions-field.jpg'

import './Solutions.css'



async function generateAISolution(payload) {

  let response



  try {

    response = await fetch(`${API_BASE_URL}/api/ai/solution`, {

      method: 'POST',

      headers: { 'Content-Type': 'application/json' },

      body: JSON.stringify(payload),

    })

  } catch (requestError) {

    throw new Error(`Unable to connect to AI solution service: ${requestError.message}`)

  }



  const data = await response.json().catch(() => null)

  if (!response.ok) {

    throw new Error(

      data?.detail || `AI solution request failed with status ${response.status}.`,

    )

  }



  return data

}



function Solutions() {

  const location = useLocation()

  const { detection, loading: detectionLoading } = useLiveDetection()

  const [solution, setSolution] = useState(null)

  const [pest, setPest] = useState(null)

  const [pestDirectory, setPestDirectory] = useState({})

  const [loadingSolution, setLoadingSolution] = useState(false)

  const [error, setError] = useState('')

  const [retryKey, setRetryKey] = useState(0)
  const [highRiskHistory, setHighRiskHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')



  const queryPest = new URLSearchParams(location.search).get('pest')?.trim()

  const requestedPest = queryPest || detection?.pest || ''

  const risk = String(detection?.risk || '').toUpperCase()

  const status = String(detection?.status || '').toUpperCase()

  const isLowRisk = risk === 'LOW'

  const solutionRisk = isLowRisk

    ? null

    : risk === 'HIGH' || status === 'HARMFUL_PEST'

      ? 'HIGH'

      : risk === 'MEDIUM' || status === 'UNKNOWN'

        ? 'MEDIUM'

        : null

  const canShowGuidance = Boolean(solutionRisk)



  useEffect(() => {
    let active = true

    async function loadHighRiskHistory() {
      setHistoryLoading(true)
      setHistoryError('')

      try {
        const history = await getHighRiskSolutionHistory({ limit: 100 })
        if (!active) return
        setHighRiskHistory(Array.isArray(history) ? history : [])
      } catch (loadError) {
        if (!active) return
        setHighRiskHistory([])
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



  useEffect(() => {
    let active = true

    async function loadLiveSolution() {

      if (!requestedPest) {

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

        let pests = []

        let directoryError = ''

        try {

          pests = await getPests()

        } catch (loadError) {

          directoryError = loadError.message

        }



        const nextDirectory = buildPestDirectory(pests)

        setPestDirectory(nextDirectory)

        const normalizedDetection = normalizePestName(requestedPest)

        const nextPest = pests.find(

          (item) =>

            [item?.scientific_name, item?.name, item?.pest_id].some(

              (value) => normalizePestName(value) === normalizedDetection,

            ),

        )



        if (!active) return



        setPest(nextPest)



        if (!canShowGuidance) {

          if (!nextPest && directoryError) {

            setError(`Unable to resolve pest information: ${directoryError}`)

          }

          return

        }



        const scientificName = nextPest?.scientific_name || requestedPest

        const commonName = getCommonPestName(requestedPest, nextDirectory)



        let nextSolution = null

        if (nextPest?.pest_id) {

          try {

            const solutionResult = await getSolution(nextPest.pest_id)

            if (!active) return



            nextSolution = solutionResult?.solution ?? null

          } catch (solutionError) {

            if (!/solution not found|status 404/i.test(solutionError.message || '')) {

              throw solutionError

            }

          }

        }



        if (!active) return



        if (nextSolution) {

          setSolution(nextSolution)

          return

        }



        if (!solutionRisk) {

          setError('No treatment guidance is available for this detection risk.')

          return

        }



        try {

          const generatedSolution = await generateAISolution({

            pest: scientificName,

            common_name: commonName,

            risk: solutionRisk,

            confidence: Number.isFinite(Number(detection?.confidence))

              ? Number(detection.confidence)

              : 0,

            pest_id: nextPest?.pest_id || '',

            pest_description: nextPest?.description || '',

            pest_symptoms: nextPest?.symptoms || '',

          })



          if (!active) return

          setSolution({ ...generatedSolution, generated: true })

        } catch (aiError) {

          if (!active) return

          setError(

            `No curated solution is available, and AI guidance could not be generated: ${aiError.message}`,

          )

        }

      } catch (loadError) {

        if (active) {

          setSolution(null)

          setPest(null)

          setError(`Unable to load pest information: ${loadError.message}`)

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

  }, [requestedPest, solutionRisk, canShowGuidance, detection?.confidence, retryKey])



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



  const pestName = getDisplayPestName(requestedPest, pestDirectory)

  const riskLabel = detection?.risk || pest?.risk || statusLabel



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

                {solution?.generated && <span className="card-eyebrow">AI-generated guidance</span>}

              </div>



              <div className="risk-block">

                <span>Risk</span>

                <strong className={`risk-${String(riskLabel).toLowerCase()}`}>

                  {riskLabel}

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



            {isLowRisk ? (

              <div className="solution-error">

                <p>No treatment guidance shown because this detection is low risk.</p>

                {error && <p>{error}</p>}

              </div>

            ) : canShowGuidance && solution ? (

              <div className="solution-sections">

                <section>

                  <span className="section-number">01</span>

                  <div>

                    <h3>About this pest</h3>

                    <p>

                      {solution.about ||

                        pest?.description ||

                        solution.description ||

                        'Not available.'}

                    </p>

                  </div>

                </section>



                <section>

                  <span className="section-number">02</span>

                  <div>

                    <h3>Recommended action</h3>

                    <p>{solution.recommended_action || 'Not available.'}</p>

                  </div>

                </section>



                <section>

                  <span className="section-number">03</span>

                  <div>

                    <h3>Prevention</h3>

                    <p>{solution.prevention || 'Not available.'}</p>

                  </div>

                </section>



                {solution.generated && (

                  <section>

                    <span className="section-number">04</span>

                    <div>

                      <h3>Precautions</h3>

                      <p>{solution.precautions || 'Not available.'}</p>

                    </div>

                  </section>

                )}

              </div>

            ) : error ? (

              <div className="solution-error">

                <p>{error}</p>

              </div>

            ) : (

              null

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

        <section className="solution-history-section">
          <div className="active-solution-topline">
            <div>
              <p className="card-eyebrow">Saved HIGH-risk alerts</p>
              <h2>Solution History</h2>
            </div>
            <div className="risk-block">
              <span>Saved</span>
              <strong>{highRiskHistory.length}</strong>
            </div>
          </div>

          {historyLoading ? (
            <div className="solution-loading">Loading saved HIGH-risk solutions...</div>
          ) : historyError ? (
            <div className="solution-error">
              <p>{historyError}</p>
              <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
                Try again
              </button>
            </div>
          ) : highRiskHistory.length === 0 ? (
            <div className="empty-solution-card">
              <div className="empty-solution-icon"><LeafIcon size={25} /></div>
              <p className="card-eyebrow">No saved alerts</p>
              <h2>No HIGH-risk solution history yet</h2>
              <p>When a HIGH-risk pest alert is detected, its solution will be saved here for later review.</p>
            </div>
          ) : (
            <div className="solution-sections">
              {highRiskHistory.map((item) => {
                const historyName =
                  item.common_name ||
                  getDisplayPestName(item.pest || item.pest_id || '', pestDirectory)
                const historyConfidence = Number(item.confidence)
                const historyConfidenceLabel = Number.isFinite(historyConfidence)
                  ? `${(historyConfidence * 100).toFixed(1)}%`
                  : 'Not available'

                return (
                  <section key={item.id}>
                    <span className="section-number">HIGH</span>
                    <div>
                      <h3>{historyName}</h3>
                      <p>Risk: <strong>{item.risk || 'HIGH'}</strong></p>
                      <p>AI confidence: <strong>{historyConfidenceLabel}</strong></p>
                      {item.solution_title && <p><strong>{item.solution_title}</strong></p>}
                      {item.solution_description && <p>{item.solution_description}</p>}
                      {item.recommended_action && (
                        <p><strong>Recommended action:</strong> {item.recommended_action}</p>
                      )}
                      {item.prevention && (
                        <p><strong>Prevention:</strong> {item.prevention}</p>
                      )}
                      {item.detected_at && (
                        <p>{new Date(item.detected_at).toLocaleString()}</p>
                      )}
                    </div>
                  </section>
                )
              })}
            </div>
          )}
        </section>

      </section>

    </div>

  )

}



export default Solutions
