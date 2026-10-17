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
 getDisplayPestName,
 getDetectionRiskEstimate,
 normalizePestName,
} from '../utils/pestNames'

import solutionsField from '../assets/solutions-field.jpg'

import './Solutions.css'

async function requestPestSolution(payload) {

 let response

 try {

  response = await fetch(`${API_BASE_URL}/api/ai/solution`, {

   method: 'POST',

   headers: { 'Content-Type': 'application/json' },

   body: JSON.stringify(payload),

  })

 } catch (requestError) {

  throw new Error(`Unable to connect to Pest Guard solution service: ${requestError.message}`)

 }

 const data = await response.json().catch(() => null)

 if (!response.ok) {

  throw new Error(

   data?.detail || `Pest solution request failed with status ${response.status}.`,

  )

 }

 return data
}

function getPesticideRecommendation(uncertain) {
 if (uncertain) {
  return 'The pest identification is uncertain. Do not choose or apply a pest-specific pesticide. Confirm the pest and crop with a local agricultural officer first.'
 }

 return 'Pest Guard has no verified locally registered product or crop-specific label dose for this pest. Do not guess a product or dose. Ask a local agricultural officer to confirm a registered product and its label rate.'
}

function toSteps(value) {
 return String(value || '')
  .split(/\r?\n/)
  .map((step) => step.replace(/^\s*\d+[.)]\s*/, '').trim())
  .filter(Boolean)
}

function SolutionSections({ solution, pest, uncertain }) {
 const damageSteps = uncertain
  ? toSteps(solution?.about || solution?.description || 'The pest identification is uncertain.')
  : [
    ...toSteps(pest?.description || solution?.about || solution?.description),
    ...toSteps(pest?.symptoms),
   ]
 const protectSteps = [
  ...(pest?.symptoms && !uncertain
   ? [`Inspect affected and nearby plants for these signs: ${pest.symptoms}`]
   : []),
  ...toSteps(solution?.recommended_action),
 ]
 const pesticideSteps = toSteps(
  getPesticideRecommendation(uncertain),
 )
 const safeApplicationSteps = [
  uncertain
   ? 'Do not apply a pesticide based on this uncertain identification. Confirm the pest and crop with a local agricultural officer first.'
   : 'Do not apply a pesticide until a locally registered product and its label are confirmed for this pest and crop.',
  'If an officer recommends a product, wear the protective equipment listed on its label. Follow label instructions for mixing, spraying, re-entry, storage, and disposal. Never mix products.',
  "Follow the label's pre-harvest waiting period. Pest Guard has no verified product label or waiting period for this case.",
 ]
 const preventionSteps = [
  ...toSteps(solution?.prevention || pest?.prevention),
  'Inspect the affected and nearby plants again in 2–3 days. If damage spreads, record what you see and ask a local agricultural officer for help.',
 ]
 const sections = [
  ['Pest and Crop Damage', damageSteps],
  ['How to Protect the Crop', protectSteps],
  ['Recommended Pesticide/Medicine', pesticideSteps],
  ['Safe Application Instructions', safeApplicationSteps],
  ['Prevention and Follow-up', preventionSteps],
 ]

 return (
  <div className="solution-sections">
   {sections.map(([heading, steps], index) => (
    <section key={heading}>
     <span className="section-number">{String(index + 1).padStart(2, '0')}</span>
     <div>
      <h3>{heading}</h3>
      {steps.length ? (
       <ol className="solution-steps">
        {steps.map((step, stepIndex) => <li key={`${heading}-${stepIndex}`}>{step}</li>)}
       </ol>
      ) : (
       <ol className="solution-steps"><li>Not available.</li></ol>
      )}
     </div>
    </section>
   ))}
  </div>
 )
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

 const [clearingHistory, setClearingHistory] = useState(false)

 const [confirmClearHistory, setConfirmClearHistory] = useState(false)

 const [clearHistoryError, setClearHistoryError] = useState('')

 const queryPest = new URLSearchParams(location.search).get('pest')?.trim()

 const requestedPest = queryPest || detection?.pest || ''
 const status = String(detection?.status || '').toUpperCase()

 const detectionConfidence =
  detection?.confidence === null ||
  detection?.confidence === undefined ||
  detection?.confidence === ''
   ? Number.NaN
   : Number(detection.confidence)

 const riskEstimate = getDetectionRiskEstimate(detection, pestDirectory)

 const hasVerifiedCatalogMatch =
  detection?.pest_verified === true &&
  Boolean(detection?.pest_id) &&
  detection.pest_id === pest?.pest_id

 const canShowSpeciesGuidance =
  hasVerifiedCatalogMatch &&
  status === 'HARMFUL_PEST' &&
  (!queryPest ||
   normalizePestName(queryPest) === normalizePestName(detection?.pest))

 const isNonPest = status === 'NON_PEST'

 const solutionRisk = canShowSpeciesGuidance
  ? riskEstimate.risk
  : 'UNKNOWN'

 const canShowGuidance = !isNonPest

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

   if (historyLoading) {
    return
   }

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

    if (isNonPest) {
     return
    }

    const allowSpeciesGuidance =
     canShowSpeciesGuidance && Boolean(nextPest?.pest_id)

    if (!allowSpeciesGuidance) {
     if (directoryError) {
      setError(
       `Unable to verify the pest catalog; showing general guidance instead: ${directoryError}`,
      )
     }

     const uncertainSolution = await requestPestSolution({
      pest:
       nextPest?.scientific_name ||
       nextPest?.name ||
       requestedPest ||
       'Unknown insect',
      common_name: nextPest?.name || 'Unconfirmed insect',
      risk: 'UNKNOWN',
      confidence: Number.isFinite(detectionConfidence)
       ? detectionConfidence
       : 0,
      pest_id: nextPest?.pest_id || '',
      pest_description: nextPest?.description || '',
      pest_symptoms: nextPest?.symptoms || '',
     })

     if (!active) return

     setSolution(uncertainSolution)
     return
    }

    const scientificName =
     nextPest.scientific_name || nextPest.name
    const commonName = nextPest.name

    const savedHistory = highRiskHistory.find(
     (item) =>
      item?.pest_verified === true &&
      item?.pest_id === nextPest.pest_id
    )

    if (savedHistory) {
      setSolution({
        about: savedHistory.solution_description || '',
        description: savedHistory.solution_description || '',
        recommended_action: savedHistory.recommended_action || '',
        prevention: savedHistory.prevention || '',
        precautions: savedHistory.precautions || '',
        generated: true,
      })
      return
    }

    let nextSolution = null

    if (nextPest.pest_id) {

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

    try {

     const generatedSolution = await requestPestSolution({

      pest: scientificName,

      common_name: commonName,

      risk: solutionRisk,

      confidence: detectionConfidence,

      pest_id: nextPest?.pest_id || '',

      pest_description: nextPest?.description || '',

      pest_symptoms: nextPest?.symptoms || '',

     })

     if (!active) return

     setSolution(generatedSolution)

    } catch (aiError) {

     if (!active) return

     setError(

      `No curated solution is available, and fallback guidance could not be loaded: ${aiError.message}`,

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

 }, [
  requestedPest,
  status,
  canShowSpeciesGuidance,
  solutionRisk,
  detectionConfidence,
  isNonPest,
  retryKey,
  historyLoading,
  highRiskHistory,
])

 const isLoading = detectionLoading || loadingSolution

 const hasLiveDetection = Boolean(detection?.pest)

 const confidence = detectionConfidence

 const confidenceLabel = Number.isFinite(confidence)
  ? `${(confidence * 100).toFixed(1)}%`
  : 'N/A'

 const resolvedScientificName =
  detection?.scientific_name ||
  pestDirectory[normalizePestName(requestedPest)]?.scientificName ||
  ''
 const pestName = requestedPest
  ? getDisplayPestName(requestedPest, pestDirectory, detection)
  : 'No pest class available'

 const riskLabel = riskEstimate.risk

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

    {

     method: 'DELETE',

    },

   )

   const data = await response.json().catch(() => null)

   if (!response.ok) {

    throw new Error(

     data?.detail ||

      `Clear history failed with status ${response.status}.`,

    )

   }

   setHighRiskHistory([])
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

  <div className="solutions-page">

   <section className="solutions-hero">

    <div className="solutions-hero-copy">

     <p className="solutions-eyebrow">Live pest solution</p>

     <h1>Action Today<br /><em>Healthier Tomorrow</em></h1>

     <p className="solutions-intro">

      This page follows the latest live AI prediction. Model scores are not calibrated proof of identity; pest-specific treatment guidance requires independent verification.

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
        {requestedPest && (
         <p className="scientific-name-detail">
          {resolvedScientificName
           ? `Scientific name: ${resolvedScientificName}`
           : `Scientific name unavailable; model class: ${requestedPest}`}
         </p>
        )}
        <p className="identification-note">AI Detection</p>

       </div>

       <div className="risk-block">

        <span>Risk Level</span>

        <strong className={`risk-${String(riskLabel).toLowerCase()}`}>

         {riskLabel}

        </strong>

       </div>

      </div>

      <div className="confidence-row">

       <span>Model score (not calibrated confidence)</span>

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

      {isNonPest ? (

       <div className="solution-error">

        <p>No pest-specific guidance is needed because the latest event was classified as a non-pest sound.</p>

        {error && <p>{error}</p>}

       </div>

      ) : canShowGuidance && solution ? (

       <>
        <SolutionSections
         solution={solution}
         pest={pest}
         uncertain={!canShowSpeciesGuidance}
        />
       </>

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

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>

       <div className="risk-block">

        <span>Saved</span>

        <strong>{highRiskHistory.length}</strong>

       </div>

       <button

        type="button"

        onClick={handleClearHistory}

        disabled={clearingHistory}

        style={{

         border: '1px solid rgba(166, 79, 53, 0.28)',

         background: confirmClearHistory ? '#a64f35' : '#fffdf8',

         color: confirmClearHistory ? '#ffffff' : '#a64f35',

         borderRadius: '10px',

         padding: '10px 14px',

         fontWeight: 700,

         cursor: clearingHistory ? 'wait' : 'pointer',

         opacity: clearingHistory ? 0.65 : 1,

        }}

       >

        {clearingHistory ? 'Clearing...' : confirmClearHistory ? 'Confirm Clear History' : 'Clear History'}

       </button>

       {confirmClearHistory && !clearingHistory && (

        <button

         type="button"

         onClick={() => { setConfirmClearHistory(false); setClearHistoryError('') }}

         style={{

          border: '1px solid rgba(20, 70, 57, 0.18)',

          background: '#ffffff',

          color: '#144639',

          borderRadius: '10px',

          padding: '10px 14px',

          fontWeight: 700,

          cursor: 'pointer',

         }}

        >

         Cancel

        </button>

       )}

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

      <div

       className="solution-history-grid"

       style={{

        display: 'grid',

        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',

        gap: '22px',

        marginTop: '24px',

       }}

      >

       {highRiskHistory.map((item) => {

        const historyKey = item.pest || item.pest_id || ''

        const historyConfidence =
         item.confidence === null ||
         item.confidence === undefined ||
         item.confidence === ''
          ? Number.NaN
          : Number(item.confidence)

        const historyName = getDisplayPestName(historyKey, pestDirectory)

        const historyPestRecord =
         pestDirectory[normalizePestName(historyKey)]

        const verifiedHistoryPest =
         item.pest_verified === true &&
         Boolean(item.pest_id) &&
         item.pest_id === historyPestRecord?.pestId

        const historyRisk = getDetectionRiskEstimate(item, pestDirectory)

        const historyConfidenceLabel = Number.isFinite(historyConfidence)

         ? `${(historyConfidence * 100).toFixed(1)}%`

         : 'N/A'

        const detectedLabel = item.detected_at

         ? new Date(item.detected_at).toLocaleString()

         : 'Time not available'

        return (

         <details

          key={item.id}

          className="history-alert-card"

          style={{

           background: '#fffdf8',

           border: '1px solid rgba(20, 70, 57, 0.14)',

           borderRadius: '18px',

           overflow: 'hidden',

           boxShadow: '0 10px 28px rgba(20, 70, 57, 0.07)',

          }}

         >

          <summary

           style={{

            listStyle: 'none',

            cursor: 'pointer',

            padding: '22px',

           }}

          >

           <div

            style={{

             display: 'flex',

             justifyContent: 'space-between',

             alignItems: 'flex-start',

             gap: '16px',

            }}

           >

            <div>

             <p

              className="card-eyebrow"

              style={{ marginBottom: '7px' }}

             >

              AI DETECTION

             </p>

             <h3

              style={{

               margin: 0,

               fontSize: '1.45rem',

               lineHeight: 1.15,

              }}

             >

              {historyName}

             </h3>

            </div>
            <span className={`history-risk risk-${historyRisk.risk.toLowerCase()}`}>

             {historyRisk.risk}

            </span>

           </div>

           <div

            style={{

             display: 'grid',

             gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',

             gap: '10px',

             marginTop: '20px',

            }}

           >

            <div>

             <span className="card-eyebrow">Model score</span>

             <strong style={{ display: 'block', marginTop: '5px' }}>

              {historyConfidenceLabel}

             </strong>

            </div>

            <div>

             <span className="card-eyebrow">Detected</span>

             <strong

              style={{

               display: 'block',

               marginTop: '5px',

               fontSize: '0.82rem',

              }}

             >

              {detectedLabel}

             </strong>

            </div>

            <div>

             <span className="card-eyebrow">Device</span>

             <strong

              style={{

               display: 'block',

               marginTop: '5px',

               fontSize: '0.82rem',

              }}

             >

              {item.device_id || 'Field Unit'}

             </strong>

            </div>

           </div>

           <div

            style={{

             marginTop: '18px',

             paddingTop: '15px',

             borderTop: '1px solid rgba(20, 70, 57, 0.10)',

             fontSize: '0.78rem',

             fontWeight: 700,

            }}

           >

            View saved solution ↓

           </div>

          </summary>

          <div

           style={{

            padding: '0 22px 24px',

            borderTop: '1px solid rgba(20, 70, 57, 0.10)',

           }}

          >

           <SolutionSections
            solution={verifiedHistoryPest ? {
             about: item.solution_description,
             recommended_action: item.recommended_action,
             prevention: item.prevention,
             precautions: item.precautions,
            } : null}
            pest={verifiedHistoryPest ? historyPestRecord || {
             description: item.pest_description,
             symptoms: item.pest_symptoms,
            } : null}
            uncertain={!verifiedHistoryPest}
           />

           {item.temperature != null || item.humidity != null ? (

            <div

             style={{

              display: 'flex',

              gap: '24px',

              paddingTop: '16px',

              borderTop: '1px solid rgba(20, 70, 57, 0.10)',

             }}

            >

             {item.temperature != null && (

              <div>

               <span className="card-eyebrow">Temperature</span>

               <strong style={{ display: 'block', marginTop: '5px' }}>

                {formatTemperature(item.temperature)}

               </strong>

              </div>

             )}

             {item.humidity != null && (

              <div>

               <span className="card-eyebrow">Humidity</span>

               <strong style={{ display: 'block', marginTop: '5px' }}>

                {formatHumidity(item.humidity)}

               </strong>

              </div>

             )}

            </div>

           ) : null}

          </div>

         </details>

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
