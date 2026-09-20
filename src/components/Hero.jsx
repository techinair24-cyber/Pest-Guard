import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowIcon, LeafIcon } from './Icons'
import cropField from '../assets/crop-field.png'
import grasshopper from '../assets/grasshopper.png'
import riceLeafSticker from '../assets/stickers/01-rice-leaf.svg'
import grasshopperSticker from '../assets/stickers/04-grasshopper.svg'
import farmAmbience from '../assets/farm-grasshopper-ambience.mp3'

const natureSoundPreference = 'pestGuardNatureSoundMuted'

function Hero() {
  const audioRef = useRef(null)
  const [isMuted, setIsMuted] = useState(true)
  const [isPlaying, setIsPlaying] = useState(false)

  useEffect(() => {
    const audio = audioRef.current

    if (!audio) {
      return
    }

    const savedMuted = localStorage.getItem(natureSoundPreference)
    void savedMuted

    setIsMuted(true)
    audio.loop = true
    audio.volume = 0.18
    audio.muted = true

    const handlePlay = () => {
      setIsPlaying(true)
    }

    const handlePause = () => {
      setIsPlaying(false)
    }

    const handleEnded = () => {
      setIsPlaying(false)
    }

    audio.addEventListener('play', handlePlay)
    audio.addEventListener('pause', handlePause)
    audio.addEventListener('ended', handleEnded)

    return () => {
      audio.pause()
      audio.removeEventListener('play', handlePlay)
      audio.removeEventListener('pause', handlePause)
      audio.removeEventListener('ended', handleEnded)
    }
  }, [])

  useEffect(() => {
    const audio = audioRef.current

    if (!audio) {
      return
    }

    audio.loop = true
    audio.volume = 0.18
    audio.muted = isMuted
  }, [isMuted])

  const toggleNatureSounds = async () => {
    const audio = audioRef.current

    if (!audio) return

    if (audio.muted) {
      audio.muted = false
      audio.volume = 0.18

      try {
        await audio.play()

        setIsMuted(false)
        setIsPlaying(true)
        localStorage.setItem(natureSoundPreference, 'false')
      } catch (error) {
        audio.muted = true
        setIsMuted(true)
        setIsPlaying(false)

        console.error(
          'Unable to start nature sounds:',
          error
        )
      }
    } else {
      audio.muted = true
      audio.pause()

      setIsMuted(true)
      setIsPlaying(false)
      localStorage.setItem(natureSoundPreference, 'true')
    }

    console.log('Audio muted:', audio.muted)
    console.log('Audio paused:', audio.paused)
    console.log('Audio volume:', audio.volume)
  }

  const signalHeights = [
    30, 52, 74, 42,
    86, 60, 80, 38,
    68, 50, 92, 45,
    74, 56, 82, 35,
  ]

  const fieldParticles = [
    { left: '8%', top: '58%', size: 5, delay: '0s', duration: '20s' },
    { left: '15%', top: '74%', size: 7, delay: '4s', duration: '24s' },
    { left: '24%', top: '62%', size: 4, delay: '2s', duration: '18s' },
    { left: '34%', top: '82%', size: 6, delay: '7s', duration: '19s' },
    { left: '52%', top: '69%', size: 5, delay: '5s', duration: '22s' },
    { left: '60%', top: '56%', size: 7, delay: '1s', duration: '26s' },
    { left: '76%', top: '75%', size: 5, delay: '3s', duration: '21s' },
    { left: '88%', top: '66%', size: 6, delay: '6s', duration: '17s' },
  ]

  return (
    <section className="hero-section">
      <div className="hero-image">
        <audio
          ref={audioRef}
          src={farmAmbience}
          loop
          preload="auto"
          aria-hidden="true"
        />
        <img
          className="hero-background"
          src={cropField}
          alt="Indian rice field"
        />
        <div className="hero-overlay" />
        <div className="hero-field-ornaments" aria-hidden="true">
          <span className="hero-sun-glow" />
          <span className="hero-field-leaf hero-field-leaf-one" />
          <span className="hero-field-leaf hero-field-leaf-two" />
          {fieldParticles.map((particle, index) => (
            <span
              key={index}
              className="field-particle"
              style={{
                left: particle.left,
                top: particle.top,
                width: `${particle.size}px`,
                height: `${particle.size}px`,
                animationDelay: particle.delay,
                animationDuration: particle.duration,
              }}
            />
          ))}
        </div>
        <img
          className="hero-grasshopper"
          src={grasshopper}
          alt=""
          aria-hidden="true"
        />
        <img
          className="hero-sticker hero-sticker-left"
          src={riceLeafSticker}
          alt=""
          aria-hidden="true"
        />
        <img
          className="hero-sticker hero-sticker-right"
          src={grasshopperSticker}
          alt=""
          aria-hidden="true"
        />
        <div className="hero-content">
          <p className="hero-kicker">
            <LeafIcon size={14} />
            SMART TECHNOLOGY FOR HEALTHY CROPS
          </p>
          <h1>
            AI-Powered
            <br />
            <em>Crop Pest</em>
            <br />
            Detection
          </h1>
          <p className="hero-copy">
            Pest Guard uses AI and sound analytics to detect
            crop pests early, helping farmers protect crops
            and make better field decisions.
          </p>
          <Link
            className="primary-button"
            to="/live-monitoring"
          >
            View Live Detection
            <ArrowIcon size={17} />
          </Link>
          <div className="hero-benefits">
            <span>
              For Farmers
            </span>
            <i aria-hidden="true" />
            <span>
              For Better Yields
            </span>
            <i aria-hidden="true" />
            <span>
              For a Greener Tomorrow
            </span>
          </div>
        </div>

        <div className="hero-signal" aria-label="Sound analytics status">
          <div className="hero-signal-heading">
            <span className="signal-live-dot" />
            <span>LISTENING...</span>
          </div>
          <div className="signal-bars">
            {signalHeights.map((height, index) => (
              <i
                key={index}
                style={{
                  '--signal-height': `${height}%`,
                  '--signal-delay': `${index * 0.06}s`,
                }}
              />
            ))}
          </div>
          <div className="hero-signal-text">
            <strong>AI ANALYZING...</strong>
            <span>Sound + vibration sensing</span>
          </div>
        </div>

        <button
          className="hero-audio-control nature-sound-toggle"
          type="button"
          onClick={toggleNatureSounds}
          aria-label={isMuted ? 'Enable nature sounds' : 'Mute nature sounds'}
        >
          <span className="hero-audio-icon" aria-hidden="true">
            {isMuted ? '◌' : ')))'}
          </span>
          <span>{isMuted ? 'Nature Sounds Off' : 'Nature Sounds On'}</span>
          {!isMuted && isPlaying && <i className="hero-audio-wave" aria-hidden="true" />}
        </button>
      </div>
    </section>
  )
}

export default Hero