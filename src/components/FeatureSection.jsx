import { SignalIcon, SparkIcon, WaveIcon } from './Icons'

const features = [
  { id: 'pests', icon: WaveIcon, title: 'AI Detection', text: 'Identifies crop pests using sound and vibration.' },
  { id: undefined, icon: SignalIcon, title: 'Real-Time Monitoring', text: 'Keeps track of field activity through the connected device.' },
  { id: 'solutions', icon: SparkIcon, title: 'Smart Solutions', text: 'Provides pest information and validated recommended actions.' },
]

function FeatureSection() {
  return (
    <section className="feature-section" id="about" aria-labelledby="features-title">
      <div className="feature-heading">
        <p className="eyebrow">Field intelligence, naturally</p>
        <h2 id="features-title">A clearer way to care for crops.</h2>
      </div>
      <div className="feature-list">
        {features.map(({ id, icon: Icon, title, text }) => (
          <article className="feature-item" id={id} key={title}>
            <div className="feature-icon"><Icon /></div>
            <div><h3>{title}</h3><p>{text}</p></div>
          </article>
        ))}
      </div>
    </section>
  )
}

export default FeatureSection