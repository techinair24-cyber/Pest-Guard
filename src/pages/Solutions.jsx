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
 getDisplayPestName,
 getDetectionRiskEstimate,
 normalizePestName,
} from '../utils/pestNames'

import solutionsField from '../assets/solutions-field.jpg'

import './Solutions.css'

function SolutionSections({ solution }) {
 const sections = [
  ['Pest description', solution.description],
  ['Identification signs', solution.identification_signs],
  ['Damage to this crop', solution.crop_damage],
  ['Recommended treatment', solution.recommended_treatment],
  ['Immediate control measures', solution.immediate_control_measures],
  ['Biological control', solution.biological_control_options],
  ['Cultural control', solution.cultural_control_methods],
  ['Mechanical or physical control', solution.mechanical_control_methods],
  ['Chemical control', solution.chemical_control_options],
  ['Prevention', solution.prevention],
  ['Monitoring and follow-up', solution.monitoring],
  ['Safety precautions', solution.safety_precautions],
  ['When to seek expert advice', solution.expert_advice],
 ]

 return (
  <div className="solution-sections">
   {sections.map(([heading, text], index) => (
    <section key={heading}>
     <span className="section-number">{String(index + 1).padStart(2, '0')}</span>
     <div>
      <h3>{heading}</h3>
      {text ? (
       <p>{text}</p>
      ) : (
       <p className="solution-unavailable">Not verified for this pest and crop.</p>
      )}
     </div>
    </section>
   ))}
   <section>
    <span className="section-number">14</span>
    <div>
     <h3>Sources</h3>
     <ul>
      {solution.source_references.map((source) => (
       <li key={source.url}>
        <a href={source.url} target="_blank" rel="noreferrer">
         {source.title} — {source.organization}
        </a>
        {' · Reviewed '}
        {source.reviewed_on}
       </li>
      ))}
     </ul>
     <p className="solution-unavailable">Record reviewed {solution.reviewed_on}.</p>
    </div>
   </section>
  </div>
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
 const detectionConfidence =
  detection?.confidence === null ||
  detection?.confidence === undefined ||
  detection?.confidence === ''
   ? Number.NaN
   : Number(detection.confidence)

 const isNonPest = status === 'NON_PEST'
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

 const isLoading = detectionLoading || loadingSolution
 const hasLiveDetection = Boolean(detection?.pest) || isNonPest
 const confidence = detectionConfidence
 const confidenceLabel = Number.isFinite(confidence)
  ? `${(confidence * 100).toFixed(1)}%`
  : 'N/A'
 const selectedCropRecord = crops.find((crop) => crop.crop_id === selectedCrop)
 const liveSolution = solution?.solutions?.find(
  (item) => item.pest_id === detection?.pest_id,
 )
 const pestName = hasVerifiedLiveDetection
  ? getDisplayPestName(detectionPest.name, pestDirectory, detection)
  : 'Unconfirmed model prediction'
 const riskLabel = hasVerifiedLiveDetection ? catalogRisk : 'UNCONFIRMED'

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

     <p className="solutions-eyebrow">Verified pest solutions</p>

     <h1>Action Today<br /><em>Healthier Tomorrow</em></h1>

     <p className="solutions-intro">

      Crop-specific guidance is displayed only when supported by a reviewed source for that pest, crop, risk and region. No external AI generates recommendations.

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

    <article className="active-solution-card">
     <div className="active-solution-topline">
      <div>
       <p className="card-eyebrow">India crop solution library</p>
       <h2>Search by crop</h2>
       <p>Only source-verified pest-to-crop records appear in the results.</p>
      </div>
     </div>

     <label htmlFor="solution-crop" className="card-eyebrow" style={{ display: 'block', margin: '18px 0 8px' }}>
      Search supported crops
     </label>
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
      placeholder="Search supported crops"
      aria-describedby="crop-search-help"
      style={{
       boxSizing: 'border-box',
       width: '100%',
       maxWidth: '520px',
       minHeight: '42px',
       padding: '10px 12px',
       border: '1px solid rgba(20, 70, 57, 0.22)',
       borderRadius: '8px',
       font: 'inherit',
      }}
     />
     <p id="crop-search-help" style={{ margin: '7px 0 0', fontSize: '0.8rem', lineHeight: 1.45 }}>
      Choose a crop from the supported Indian crop list. Crop selection is user-provided context and is not a detection.
     </p>

     {cropLoadError && (
      <div className="solution-error" role="alert">
       <p>{cropLoadError}</p>
      </div>
     )}

     {cropDraft.trim().length >= 2 && cropSearchResults.length > 0 && (
      <div role="listbox" aria-label="Matching supported crops" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '14px' }}>
       {cropSearchResults.map((crop) => (
        <button
         key={crop.crop_id}
         type="button"
         role="option"
         aria-selected={selectedCrop === crop.crop_id}
         onClick={() => {
          setCropDraft(crop.name)
          setSelectedCrop(crop.crop_id)
         }}
         className="solutions-button"
         style={{ cursor: 'pointer' }}
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
      <div style={{ marginTop: '24px' }}>
       <p className="card-eyebrow">
        {selectedCropRecord?.name || 'Selected crop'}
       </p>
       {loadingSolution ? (
        <div className="solution-loading">Loading verified crop-specific solutions...</div>
       ) : error ? (
        <div className="solution-error" role="alert">
         <p>{error}</p>
         {canRetry && (
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}>
           Try again
          </button>
         )}
        </div>
       ) : solution?.solutions?.length ? (
        <div className="solution-history-grid">
         {solution.solutions.map((item) => (
          <article key={item.solution_id} className="history-alert-card" style={{ padding: '20px' }}>
           <div className="active-solution-topline">
            <div>
             <p className="card-eyebrow">
              {item.insect_group}{item.region ? ` · ${item.region}` : ''}
             </p>
             <h3>{item.pest_name}</h3>
             <p className="scientific-name-detail">Scientific name: {item.scientific_name}</p>
            </div>
            <div className="risk-block">
             <span>Catalogue risk</span>
             <strong className={`risk-${item.risk.toLowerCase()}`}>{item.risk}</strong>
            </div>
           </div>
           {hasVerifiedLiveDetection && item.pest_id === detection.pest_id && (
            <p className="identification-note">This source-verified solution matches the current verified detection.</p>
           )}
           <SolutionSections solution={item} />
          </article>
         ))}
        </div>
       ) : (
        <div className="empty-solution-card">
         <p className="card-eyebrow">No verified crop mapping yet</p>
         <h3>No verified solutions available for {selectedCropRecord?.name || 'this crop'}</h3>
         <p>
          The current catalogue has not established a source-verified pest association and risk-specific solution for this crop. No recommendations are inferred from unrelated crops.
         </p>
        </div>
       )}
      </div>
     )}
    </article>

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

    {!isLoading && hasLiveDetection && !hasVerifiedLiveDetection && (
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

    {!isLoading && hasLiveDetection && hasVerifiedLiveDetection && (

     <article className="active-solution-card">

      <div className="active-solution-topline">

       <div>

        <p className="card-eyebrow">Latest live detection</p>

        <h2>{pestName}</h2>
        {detection?.pest && (
         <p className="scientific-name-detail">
          {detectionPest.scientific_name
           ? `Scientific name: ${detectionPest.scientific_name}`
           : 'Scientific name unavailable in the catalogue.'}
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

      <p className="identification-note">
       {selectedCrop && liveSolution
        ? `A verified ${selectedCropRecord?.name} solution is listed above for this detection.`
        : 'Crop-specific guidance is not assigned to a detection unless the exact pest ID, selected crop, and catalogue risk match a verified record.'}
      </p>

      <Link className="solutions-button" to="/live-monitoring">

       View Live Monitoring <ArrowIcon size={15} />

      </Link>

     </article>

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
            View persisted detection record
           </div>

          </summary>

          <div

           style={{

            padding: '0 22px 24px',

            borderTop: '1px solid rgba(20, 70, 57, 0.10)',

           }}

          >

           <p className="solution-unavailable">
            No verified solution content is available for this saved detection.
           </p>

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
