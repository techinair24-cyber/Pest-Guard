function Waveform() {
  return (
    <div className="waveform" aria-label="Animated audio waveform" role="img">
      {Array.from({ length: 42 }, (_, index) => <i key={index} style={{ '--bar-height': `${18 + ((index * 17) % 42)}%`, '--delay': `${index * 35}ms` }} />)}
    </div>
  )
}

export default Waveform
