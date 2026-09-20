import { useEffect, useMemo, useState } from 'react'
import {
  getDetectionHistory,
  getPests,
} from '../services/api'
import './Pests.css'

import aphidImage from '../assets/pests/aphid.jpg'
import armywormImage from '../assets/pests/armyworm.jpg'
import brownPlanthopperImage from '../assets/pests/brown-planthopper.jpg'
import fallArmywormImage from '../assets/pests/fall-armyworm.jpg'
import riceLeafFolderImage from '../assets/pests/rice-leaf-folder.jpg'
import ricePlanthopperImage from '../assets/pests/rice-planthopper.jpg'
import riceStemBorerImage from '../assets/pests/rice-stem-borer.jpg'
import pestsHeroImage from '../assets/pests/pests-hero.png'
import riceGrainsSticker from '../assets/stickers/03-rice-grains.svg'

const pestImages = {
  aphid: aphidImage,
  armyworm: armywormImage,
  brown_plant_hopper: brownPlanthopperImage,
  fall_armyworm: fallArmywormImage,
  rice_leaf_folder: riceLeafFolderImage,
  rice_planthopper: ricePlanthopperImage,
  stem_borer: riceStemBorerImage,
}

function getRiskClass(risk) {
  const value = String(risk || '').toUpperCase()

  if (value === 'HIGH') {
    return 'risk-high'
  }

  if (value === 'MEDIUM') {
    return 'risk-medium'
  }

  return 'risk-low'
}

function Pests() {
  const [pests, setPests] = useState([])
  const [detectionCount, setDetectionCount] =
    useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('ALL')

  useEffect(() => {
    let active = true

    async function loadPests() {
      try {
        setLoading(true)
        setError('')

        const data = await getPests()

        if (active) {
          setPests(Array.isArray(data) ? data : [])
        }
      } catch (err) {
        if (active) {
          setError(
            err?.message ||
              'Unable to load pest information.'
          )
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadPests()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true

    async function loadDetectionCount() {
      try {
        const data = await getDetectionHistory({
          limit: 500,
        })

        if (active) {
          setDetectionCount(
            Array.isArray(data?.detections)
              ? data.detections.length
              : 0
          )
        }
      } catch {
        if (active) {
          setDetectionCount(0)
        }
      }
    }

    loadDetectionCount()

    return () => {
      active = false
    }
  }, [])

  const filteredPests = useMemo(() => {
    const query = search.trim().toLowerCase()

    return pests.filter((pest) => {
      const matchesSearch =
        !query ||
        pest.name?.toLowerCase().includes(query) ||
        pest.scientific_name
          ?.toLowerCase()
          .includes(query) ||
        pest.description
          ?.toLowerCase()
          .includes(query)

      const matchesRisk =
        riskFilter === 'ALL' ||
        String(pest.risk || '').toUpperCase() ===
          riskFilter

      return matchesSearch && matchesRisk
    })
  }, [pests, search, riskFilter])

  return (
    <main className="pests-page">
      {/* HERO */}
      <section className="pests-hero">
        <div className="pests-hero-content">
          <p className="pests-eyebrow">
            Crop Threat Library
          </p>

          <h1 className="pests-title">
            Know the pests
            <em>that threaten our crops.</em>
          </h1>

          <p className="pests-intro">
            Explore agricultural pests, their
            characteristics, symptoms, and the crops they
            can affect. Pest Guard combines field sensing
            with AI sound analysis to support earlier
            detection.
          </p>

          <div className="pests-hero-stats">
            <div>
              <strong>{pests.length}</strong>
              <span>PEST TYPES IN LIBRARY</span>
            </div>

            <div>
              <strong>{detectionCount}</strong>
              <span>PESTS DETECTED</span>
            </div>

            <div>
              <strong>AI</strong>
              <span>SOUND ANALYTICS</span>
            </div>
          </div>
        </div>

        {/* HERO VISUAL */}
        <div className="pests-hero-visual">
          <div className="pests-visual-field">
            <img
              className="pests-hero-image"
              src={pestsHeroImage}
              alt="Agricultural pest on a rice crop leaf"
            />

            <div className="pests-image-overlay" />

            <div className="pests-listening-card">
              <span className="listening-dot" />

              <div>
                <strong>Field listening</strong>
                <small>
                  Sound + vibration sensing
                </small>
              </div>
            </div>

            <img
              className="pests-floating-sticker"
              src={riceGrainsSticker}
              alt=""
              aria-hidden="true"
            />

            <span className="pests-listen-label">
              LISTEN
            </span>
          </div>
        </div>
      </section>

      {/* PEST LIBRARY */}
      <section className="pests-library">
        <div className="pests-toolbar">
          <div>
            <p className="toolbar-label">
              Pest Library
            </p>

            <h2>Threats in the field</h2>
          </div>

          <div className="pests-controls">
            <label className="search-box">
              <span>⌕</span>

              <input
                type="search"
                value={search}
                onChange={(event) =>
                  setSearch(event.target.value)
                }
                placeholder="Search pests..."
                aria-label="Search pests"
              />
            </label>

            <div className="risk-filters">
              {['ALL', 'HIGH', 'MEDIUM'].map((risk) => (
                <button
                  key={risk}
                  type="button"
                  className={
                    riskFilter === risk
                      ? 'risk-filter active'
                      : 'risk-filter'
                  }
                  onClick={() =>
                    setRiskFilter(risk)
                  }
                >
                  {risk === 'ALL'
                    ? 'All'
                    : `${risk} risk`}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* LOADING */}
        {loading && (
          <div className="pests-state">
            <div className="state-loader" />

            <h3>
              Loading pest information
            </h3>

            <p>
              Connecting to the Pest Guard backend...
            </p>
          </div>
        )}

        {/* ERROR */}
        {!loading && error && (
          <div className="pests-state error-state">
            <span className="state-icon">!</span>

            <h3>
              Unable to load pest information
            </h3>

            <p>{error}</p>
          </div>
        )}

        {/* EMPTY */}
        {!loading &&
          !error &&
          filteredPests.length === 0 && (
            <div className="pests-state">
              <span className="state-icon">⌕</span>

              <h3>No pests found</h3>

              <p>
                Try a different pest name or risk
                category.
              </p>
            </div>
          )}

        {/* PEST CARDS */}
        {!loading &&
          !error &&
          filteredPests.length > 0 && (
            <div className="pests-grid">
              {filteredPests.map((pest, index) => {
                const risk = String(
                  pest.risk || 'LOW'
                ).toUpperCase()

                const image =
                  pestImages[pest.pest_id]

                return (
                  <article
                    className="pest-card"
                    key={
                      pest.pest_id ||
                      pest.id ||
                      pest.name
                    }
                  >
                    <div className="pest-card-top">
                      <span className="pest-index">
                        {String(index + 1).padStart(
                          2,
                          '0'
                        )}
                      </span>

                      <span
                        className={`pest-risk ${getRiskClass(
                          risk
                        )}`}
                      >
                        {risk} RISK
                      </span>
                    </div>

                    {/* REAL PEST IMAGE */}
                    <div className="pest-visual">
                      {image ? (
                        <img
                          src={image}
                          alt={`${pest.name} agricultural pest`}
                        />
                      ) : (
                        <div className="pest-image-missing">
                          <span>
                            No image available
                          </span>
                        </div>
                      )}

                      <div className="pest-image-overlay" />

                      <span className="sound-label">
                        SOUND PROFILE
                      </span>
                    </div>

                    {/* CONTENT */}
                    <div className="pest-card-content">
                      <h3>{pest.name}</h3>

                      {pest.scientific_name && (
                        <p className="scientific-name">
                          {pest.scientific_name}
                        </p>
                      )}

                      <p className="pest-description">
                        {pest.description ||
                          'Information about this agricultural pest.'}
                      </p>

                      {pest.symptoms && (
                        <div className="symptoms-block">
                          <span>
                            Common symptoms
                          </span>

                          <p>{pest.symptoms}</p>
                        </div>
                      )}
                    </div>

                    {/* FOOTER */}
                    <div className="pest-card-footer">
                      <span>
                        AI detection target
                      </span>

                      <span className="footer-arrow">
                        →
                      </span>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
      </section>
    </main>
  )
}

export default Pests