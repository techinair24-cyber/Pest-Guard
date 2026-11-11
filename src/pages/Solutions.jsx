import { useEffect, useState } from 'react'

import { Link, useLocation } from 'react-router-dom'

import { ArrowIcon, LeafIcon, SignalIcon, SparkIcon } from '../components/Icons'

import { useLiveDetection } from '../hooks/useLiveDetection'

import {

 API_BASE_URL,

 getHighRiskSolutionHistory,

 getPests,


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

 const requiredFields = [
  'about',
  'recommended_action',
  'prevention',
 ]
 if (
  !data ||
  requiredFields.some((field) => typeof data[field] !== 'string' || !data[field].trim()) ||
  data.pest !== payload.pest ||
  data.common_name !== payload.common_name ||
  data.pest_id !== payload.pest_id ||
  data.risk !== payload.risk ||
  !Number.isFinite(data.confidence)
 ) {
  throw new Error('The solution service returned incomplete or mismatched data.')
 }

 return data
}

function toSteps(value) {
 return (typeof value === 'string' ? value : '')
  .split(/\r?\n/)
  .map((step) => step.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
  .filter(Boolean)
}

function SolutionSections({ solution }) {
 const sections = [
  ['Pest & Crop Damage', solution?.about],
  ['How to Protect the Crop', solution?.recommended_action],
  ['Recommended Pesticide/Medicine and Correct Label Dose', solution?.pesticide_recommendation],
  ['How to Apply It Safely', solution?.precautions],
  ['Prevention and Follow-up Steps', solution?.prevention],
 ]

 return (
  <div className="solution-sections">
   {sections.map(([heading, steps], index) => (
    <section key={heading}>
     <span className="section-number">{String(index + 1).padStart(2, '0')}</span>
     <div>
      <h3>{heading}</h3>
      {toSteps(steps).length ? (
       <ol className="solution-steps">
        {toSteps(steps).map((step, stepIndex) => <li key={`${heading}-${stepIndex}`}>{step}</li>)}
       </ol>
      ) : (
       <p className="solution-unavailable">No verified information is currently available.</p>
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
 const [canRetry, setCanRetry] = useState(false)

 const [retryKey, setRetryKey] = useState(0)
 const [cropDraft, setCropDraft] = useState('')
 const [selectedCrop, setSelectedCrop] = useState('')

 const [highRiskHistory, setHighRiskHistory] = useState([])

 const [highRiskHistoryTotal, setHighRiskHistoryTotal] = useState(null)

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

 const isNonPest = status === 'NON_PEST'
 const catalogRisk = String(pest?.risk || '').trim().toUpperCase()
 const supportedRisk = ['HIGH', 'MEDIUM', 'LOW', 'NO_RISK'].includes(catalogRisk)
 const hasVerifiedCatalogMatch =
  detection?.pest_verified === true &&
  Boolean(detection?.pest_id) &&
  detection.pest_id === pest?.pest_id &&
  supportedRisk
 const queryMatchesDetection =
  !queryPest ||
  normalizePestName(queryPest) === normalizePestName(detection?.pest)
 const canShowSpeciesGuidance =
  hasVerifiedCatalogMatch &&
  status === 'HARMFUL_PEST' &&
  queryMatchesDetection

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
   setCanRetry(false)

   setSolution(null)

   setPest(null)

   if (historyLoading) {
    return
   }

   try {

    const pests = await getPests()

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

    const matchingPest =
     nextPest &&
     detection?.pest_verified === true &&
     Boolean(detection?.pest_id) &&
     detection.pest_id === nextPest.pest_id &&
     status === 'HARMFUL_PEST' &&
     queryMatchesDetection &&
     ['HIGH', 'MEDIUM', 'LOW', 'NO_RISK'].includes(
      String(nextPest.risk || '').trim().toUpperCase(),
     )

    if (!matchingPest) {
     setError(
      'A verified species-level detection with a matching catalogue risk is required before a pest-specific solution can be generated.',
     )
     return
    }

    if (!Number.isFinite(detectionConfidence)) {
     setError('The model score is unavailable. A solution cannot be requested without the prediction data.')
     return
    }

    const scientificName =
     nextPest.scientific_name || nextPest.name
    const commonName = nextPest.name

    try {

     const generatedSolution = await requestPestSolution({

      pest: scientificName,

      common_name: commonName,

      risk: String(nextPest.risk).trim().toUpperCase(),

      confidence: detectionConfidence,

      pest_id: nextPest?.pest_id || '',

      pest_description: nextPest?.description || '',

      pest_symptoms: nextPest?.symptoms || '',

      crop: selectedCrop,

     })

     if (!active) return

     setSolution(generatedSolution)

    } catch (aiError) {

     if (!active) return

     setError(

      `Gemini solution generation failed: ${aiError.message}`,

     )
     setCanRetry(true)

    }

   } catch (loadError) {

    if (active) {

     setSolution(null)

     setPest(null)

     setError(`Unable to load pest information: ${loadError.message}`)
     setCanRetry(true)

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
  detection?.pest,
  detection?.pest_id,
  detection?.pest_verified,
  detectionConfidence,
  isNonPest,
  queryMatchesDetection,
  retryKey,
  historyLoading,
  selectedCrop,
])

 const isLoading = detectionLoading || loadingSolution

 const hasLiveDetection = Boolean(detection?.pest) || isNonPest

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

 const riskLabel = canShowSpeciesGuidance ? catalogRisk : 'UNCONFIRMED'

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

    {!isLoading && hasLiveDetection && !canShowSpeciesGuidance && (
     <article className="empty-solution-card">
      <div className="empty-solution-icon"><LeafIcon size={25} /></div>
      <p className="card-eyebrow">Live detection status</p>
      <h2>{isNonPest ? 'No Pest-specific Guidance' : 'Verified Species Identification Unavailable'}</h2>
      <p>
       {isNonPest
        ? 'The latest backend record is classified as a non-pest sound. No pest solution is available for this result.'
        : 'A verified species-level detection and matching catalogue risk are required before pest-specific guidance can be shown.'}
      </p>
      {error && <div className="solution-error"><p>{error}</p></div>}
      {canRetry && (
       <button
        type="button"
        className="solutions-button"
        onClick={() => setRetryKey((value) => value + 1)}
       >
        Try again
       </button>
      )}
      <Link className="solutions-button" to="/live-monitoring">
       Open Live Monitoring <ArrowIcon size={15} />
      </Link>
     </article>
    )}

    {!isLoading && hasLiveDetection && canShowSpeciesGuidance && (

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
        <p className="identification-note">
         Verified catalogue match
        </p>

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

      <form
        className="solution-crop-form"
        onSubmit={(event) => {
         event.preventDefault()
         setSelectedCrop(cropDraft.trim())
         setRetryKey((value) => value + 1)
        }}
        style={{
         display: 'flex',
         flexWrap: 'wrap',
         alignItems: 'end',
         gap: '12px',
         margin: '20px 0',
         padding: '16px',
         border: '1px solid rgba(20, 70, 57, 0.14)',
         borderRadius: '12px',
        }}
       >
        <div style={{ flex: '1 1 240px', minWidth: 0 }}>
         <label htmlFor="solution-crop" className="card-eyebrow" style={{ display: 'block', marginBottom: '8px' }}>
          Crop for crop-specific advice
         </label>
         <input
          id="solution-crop"
          type="text"
          maxLength={100}
          value={cropDraft}
          onChange={(event) => setCropDraft(event.target.value)}
          placeholder="Enter crop name"
          style={{
           boxSizing: 'border-box',
           width: '100%',
           minHeight: '42px',
           padding: '10px 12px',
           border: '1px solid rgba(20, 70, 57, 0.22)',
           borderRadius: '8px',
           font: 'inherit',
          }}
         />
         <p style={{ margin: '7px 0 0', fontSize: '0.8rem', lineHeight: 1.45 }}>
          This is user-provided context, not a crop detection. No verified pesticide products or doses are available.
         </p>
        </div>
        <button
         type="submit"
         className="solutions-button"
         style={{ cursor: 'pointer', minHeight: '42px', flex: '0 0 auto' }}
        >
         {selectedCrop ? 'Regenerate Solution' : 'Generate Solution'}
        </button>
        </form>

      {solution ? (

       <>
        <SolutionSections
         solution={solution}
        />
       </>

      ) : error ? (

       <div className="solution-error">

        <p>{error}</p>
        {canRetry && (
         <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
          Try again
         </button>
        )}

       </div>

      ) : null}

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

      {canRetry && (
       <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
        Try again
       </button>
      )}

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

        <strong>
         {historyLoading || historyError || highRiskHistoryTotal === null
          ? '—'
          : highRiskHistoryTotal}
        </strong>

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

      {clearHistoryError && (
       <div className="solution-error">
        <p>{clearHistoryError}</p>
       </div>
      )}

      {historyLoading ? (

      <div className="solution-loading">Loading saved HIGH-risk solutions...</div>

     ) : historyError ? (

      <div className="solution-error">

       <p>{historyError}</p>

       {canRetry && (
        <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
         Try again
        </button>
       )}

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
        const hasVerifiedHistorySolution =
         verifiedHistoryPest &&
         ['CATALOG', 'GEMINI'].includes(item.solution_source)

        const historyRisk = getDetectionRiskEstimate(item, pestDirectory)

        const historyConfidenceLabel = Number.isFinite(historyConfidence)
         && verifiedHistoryPest
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

              {verifiedHistoryPest
               ? 'VERIFIED CATALOGUE MATCH'
               : 'UNCONFIRMED MODEL PREDICTION'}

             </p>

             <h3

              style={{

               margin: 0,

               fontSize: '1.45rem',

               lineHeight: 1.15,

              }}

             >

              {verifiedHistoryPest ? historyName : 'Unconfirmed model prediction'}

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

              {item.device_id || 'Unavailable'}

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
            {hasVerifiedHistorySolution
             ? 'View saved solution'
             : 'View persisted detection record'}
           </div>

          </summary>

          <div

           style={{

            padding: '0 22px 24px',

            borderTop: '1px solid rgba(20, 70, 57, 0.10)',

           }}

          >

           {hasVerifiedHistorySolution ? (
            <SolutionSections
             solution={{
              about: item.solution_description,
              recommended_action: item.recommended_action,
              prevention: item.prevention,
             }}
            />
           ) : (
            <p className="solution-unavailable">
             No verified solution content is available for this saved detection.
            </p>
           )}

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
