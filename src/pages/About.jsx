import { Link } from 'react-router-dom'
import cropField from '../assets/crop-field.png'
import riceStemSticker from '../assets/stickers/02-rice-stem.svg'
import './About.css'

function About() {
  const highlights = [
    {
      number: '01',
      title: 'Early Detection',
      text: 'Identify harmful pest activity before crop damage becomes severe.',
    },
    {
      number: '02',
      title: 'AI Detection',
      text: 'Use sound and vibration analysis with a deep learning model.',
    },
    {
      number: '03',
      title: 'Smart Farming',
      text: 'Give farmers useful information for faster field decisions.',
    },
  ]

  const stories = [
    {
      title: 'The Agricultural Challenge',
      text: 'Crop pests can cause significant yield loss, often going unnoticed until damage is severe.',
    },
    {
      title: 'Our Approach',
      text: 'We analyze insect sounds and crop vibrations with AI to identify harmful pests early.',
    },
    {
      title: 'Our Impact',
      text: 'Pest Guard is designed to support healthier crops, better monitoring, and more informed farming decisions.',
    },
  ]

  const process = [
    {
      number: '01',
      title: 'INMP441',
      text: 'Microphone',
    },
    {
      number: '02',
      title: 'DFR0052',
      text: 'Vibration Sensor',
    },
    {
      number: '03',
      title: 'ESP32-S3',
      text: 'Field Unit',
    },
    {
      number: '04',
      title: 'AI CNN',
      text: 'Pest Classification',
    },
    {
      number: '05',
      title: 'FastAPI',
      text: 'Backend',
    },
    {
      number: '06',
      title: 'Pest Guard',
      text: 'Web Application',
    },
  ]

  return (
    <main className="about-page">
      {/* Hero */}
      <section className="about-hero">
        <div className="about-hero-content">
          <p className="about-eyebrow">Our Story</p>

          <h1 className="about-title">
            About <em>Pest Guard</em>
          </h1>

          <h2 className="about-subtitle">
            Using sound, AI, and IoT to build healthier crops and a more
            sustainable future.
          </h2>

          <p className="about-lead">
            Pest Guard is a deep learning-based crop pest detection system
            using sound analytics and vibration sensing to support early crop
            monitoring. Our goal is to make intelligent crop protection more
            accessible to farmers.
          </p>

          <Link
            className="about-hero-button"
            to="/live-monitoring"
          >
            Explore Live Monitoring
            <span>↗</span>
          </Link>
        </div>

        <div className="about-hero-image">
          <img
            className="about-hero-photo"
            src={cropField}
            alt="Indian agricultural field with rice crops"
          />

          <img
            className="about-floating-sticker"
            src={riceStemSticker}
            alt=""
            aria-hidden="true"
          />

          <div className="about-image-card">
            <span>Built around the field</span>
            <strong>Listen. Detect. Protect.</strong>
          </div>
        </div>
      </section>

      {/* Highlights */}
      <section className="about-highlights">
        {highlights.map((item) => (
          <article
            className="about-highlight"
            key={item.number}
          >
            <span className="about-highlight-number">
              {item.number}
            </span>

            <h3>{item.title}</h3>

            <p>{item.text}</p>
          </article>
        ))}
      </section>

      {/* Story */}
      <section className="about-section">
        <div className="about-section-heading">
          <p className="eyebrow">Why Pest Guard</p>

          <h2>
            From an agricultural challenge to an intelligent monitoring
            system.
          </h2>
        </div>

        <div className="about-story-grid">
          {stories.map((story) => (
            <article
              className="about-story-card"
              key={story.title}
            >
              <h3>{story.title}</h3>

              <p>{story.text}</p>
            </article>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="about-process-section">
        <div className="about-process-inner">
          <p className="eyebrow">How It Works</p>

          <h2>
            From field signals to farmer insights.
          </h2>

          <p className="about-process-intro">
            A microphone and piezoelectric sensor listen to the field.
            The ESP32-S3 processes the signals, the CNN model classifies
            the sound, and the result reaches the Pest Guard website.
          </p>

          <div className="about-process-grid">
            {process.map((item, index) => (
              <article
                className="about-process-step"
                key={item.number}
              >
                <span className="about-process-step-number">
                  {item.number}
                </span>

                <h3>{item.title}</h3>

                <p>{item.text}</p>

                {index < process.length - 1 && (
                  <span
                    className="about-process-arrow"
                    aria-hidden="true"
                  >
                    →
                  </span>
                )}
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Closing */}
      <section className="about-final">
        <h2>
          Smarter listening for healthier fields.
        </h2>

        <p>
          Pest Guard brings together field sensing, deep learning, IoT,
          and a simple web interface to support early crop pest detection.
        </p>
      </section>
    </main>
  )
}

export default About