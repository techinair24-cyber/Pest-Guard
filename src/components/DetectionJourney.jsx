import { useEffect, useRef, useState } from 'react'
import './DetectionJourney.css'
import soundCapture from '../assets/agriculture/sound-capture.jpg'
import aphidImage from '../assets/pests/aphid.jpg'
import armywormImage from '../assets/pests/armyworm.jpg'
import brownPlanthopperImage from '../assets/pests/brown-planthopper.jpg'
import fallArmywormImage from '../assets/pests/fall-armyworm.jpg'
import riceLeafFolderImage from '../assets/pests/rice-leaf-folder.jpg'
import ricePlanthopperImage from '../assets/pests/rice-planthopper.jpg'
import riceStemBorerImage from '../assets/pests/rice-stem-borer.jpg'

function formatPercent(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '—'
  }

  return `${(number * 100).toFixed(0)}%`
}

function getPestImage(pestName) {
  const normalized = String(pestName || '').trim().toLowerCase()

  if (!normalized) {
    return null
  }

  const lookup = {
    aphid: aphidImage,
    armyworm: armywormImage,
    'fall armyworm': fallArmywormImage,
    'rice planthopper': ricePlanthopperImage,
    'brown planthopper': brownPlanthopperImage,
    'rice leaf folder': riceLeafFolderImage,
    'rice stem borer': riceStemBorerImage,
  }

  return lookup[normalized] || null
}

function DetectionJourney({ detection }) {
  const [stepIndex, setStepIndex] = useState(0)
  const lastKeyRef = useRef('')

  useEffect(() => {
    if (!detection) {
      setStepIndex(0)
      return undefined
    }

    const key = detection.id ?? detection.detected_at ?? detection.timestamp ?? detection.pest ?? 'latest'

    if (key === lastKeyRef.current) {
      return undefined
    }

    lastKeyRef.current = key
    setStepIndex(0)

    const timers = [
      window.setTimeout(() => setStepIndex(1), 260),
      window.setTimeout(() => setStepIndex(2), 720),
      window.setTimeout(() => setStepIndex(3), 1180),
    ]

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [detection])

  const steps = [
    { key: 'capture', label: 'Sound Captured', note: 'Field sound detected' },
    { key: 'processing', label: 'Signal Processing', note: 'Waveform refined' },
    { key: 'analysis', label: 'AI Analyzing', note: 'Spectral pattern review' },
    { key: 'identified', label: 'Pest Identified', note: 'Classification complete' },
  ]

  const hasDetection = Boolean(detection)
  const pestName = detection?.pest || ''
  const confidence = formatPercent(detection?.confidence)
  const pestAsset = hasDetection ? getPestImage(pestName) : null

  return (
    <section className="detection-journey" aria-live="polite">
      <div className="journey-header">
        <div>
          <p className="journey-kicker">Field intelligence</p>
          <h2>What Pest Was Heard?</h2>
        </div>
      </div>

      <p className="journey-subtitle">Follow the journey from field sound to AI detection.</p>

      <div className="journey-track" aria-label="AI detection processing pipeline">
        <span className="journey-route-line" aria-hidden="true" />
        <span className="journey-route-dot" aria-hidden="true" />

        {steps.map((step, index) => {
          const isComplete = stepIndex > index
          const isActive = stepIndex === index
          const isLast = index === steps.length - 1

          return (
            <div
              key={step.key}
              className={[
                'journey-stage',
                `stage-${step.key}`,
                isActive ? 'is-active' : '',
                isComplete ? 'is-complete' : '',
                isLast ? 'is-last' : '',
              ].join(' ')}
            >
              <div className="stage-visual" aria-hidden="true">
                {step.key === 'capture' && (
                  <>
                    <img className="stage-sound-capture" src={soundCapture} alt="" />
                    <span className="sound-ripple ripple-one" aria-hidden="true" />
                    <span className="sound-ripple ripple-two" aria-hidden="true" />
                    <span className="sound-ripple ripple-three" aria-hidden="true" />
                  </>
                )}

                {step.key === 'processing' && (
                  <div className="stage-waveform">
                    <span style={{ '--wave-height': '18%' }} />
                    <span style={{ '--wave-height': '32%' }} />
                    <span style={{ '--wave-height': '58%' }} />
                    <span style={{ '--wave-height': '78%' }} />
                    <span style={{ '--wave-height': '48%' }} />
                    <span style={{ '--wave-height': '35%' }} />
                    <span style={{ '--wave-height': '64%' }} />
                    <span style={{ '--wave-height': '42%' }} />
                    <span className="signal-particle particle-one" aria-hidden="true" />
                    <span className="signal-particle particle-two" aria-hidden="true" />
                    <span className="signal-particle particle-three" aria-hidden="true" />
                  </div>
                )}

                {step.key === 'analysis' && (
                  <div className="stage-spectrogram" aria-hidden="true">
                    <span /><span /><span /><span /><span /><span />
                    <span /><span /><span /><span /><span /><span />
                    <span className="analysis-point point-one" />
                    <span className="analysis-point point-two" />
                    <span className="analysis-point point-three" />
                    <span className="scan-line" />
                  </div>
                )}

                {step.key === 'identified' && (
                  <>
                    {hasDetection && pestAsset ? (
                      <img className="stage-pest-image" src={pestAsset} alt={pestName} />
                    ) : (
                      <div className="stage-neutral-panel" aria-label="Waiting for pest detection">
                        <span className="neutral-ring ring-one" />
                        <span className="neutral-ring ring-two" />
                        <span className="neutral-core" />
                      </div>
                    )}
                    {hasDetection && <span className="stage-pest-ring" aria-hidden="true" />}
                    {hasDetection && <span className="stage-confidence-badge">{confidence}</span>}
                  </>
                )}
              </div>

              <div className="journey-step-copy">
                <strong>{step.label}</strong>
                <small>{step.note}</small>
              </div>

              {!isLast && <span className="journey-arrow" aria-hidden="true" />}
            </div>
          )
        })}
      </div>

      {hasDetection ? (
        <div className="journey-result">
          <span className="result-label">Detected pest</span>
          <strong>{pestName}</strong>
          <small>{confidence}</small>
        </div>
      ) : (
        <div className="journey-empty-state">
          <strong>Listening to the field...</strong>
          <span>Waiting for an AI detection.</span>
        </div>
      )}
    </section>
  )
}

export default DetectionJourney
