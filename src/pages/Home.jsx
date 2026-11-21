import { useEffect, useRef, useState } from 'react'
import { useLiveDetection } from '../hooks/useLiveDetection'
import FeatureSection from '../components/FeatureSection'
import Hero from '../components/Hero'
import HarmfulPestAlert from '../components/HarmfulPestAlert'
import { isVerifiedPestDetection } from '../utils/detectionHistory'

function Home() {
  const { detection } = useLiveDetection()
  const [alert, setAlert] = useState(null)
  const alertedKeyRef = useRef('')

  useEffect(() => {
    if (!detection) {
      return
    }

    if (!isVerifiedPestDetection(detection)) {
      return
    }

    const eventKey = detection.id ?? detection.detected_at ?? detection.timestamp ?? ''

    if (!eventKey || eventKey === alertedKeyRef.current) {
      return
    }

    alertedKeyRef.current = eventKey
    setAlert(detection)
  }, [detection])

  return (
    <main className="home-page">
      <HarmfulPestAlert detection={alert} onDismiss={() => setAlert(null)} />
      <Hero />

      <FeatureSection />

      <section
        className="closing-section"
        aria-label="Project statement"
      >
        <p className="closing-kicker">
          OUR VISION
        </p>

        <h2>
          A Healthier Tomorrow
          <br />
          for Every Field
        </h2>

        <p className="closing-copy">
          Technology meets nature to support earlier crop
          pest detection and more informed agricultural
          decisions.
        </p>
      </section>
    </main>
  )
}

export default Home