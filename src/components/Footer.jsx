import { Link } from 'react-router-dom'
import { LeafIcon } from './Icons'

const footerLinks = [['Home', '/'], ['About', '/about'], ['Pests', '/pests'], ['Solutions', '/solutions'], ['Live Monitoring', '/live-monitoring']]

function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <Link className="brand footer-brand" to="/"><span className="brand-mark"><LeafIcon size={20} /></span><span>Pest <strong>Guard</strong></span></Link>
        <p>Listen to Crops <span>|</span> Protect the Future</p>
        <nav aria-label="Footer navigation">{footerLinks.map(([label, href]) => <Link to={href} key={label}>{label}</Link>)}</nav>
      </div>
      <div className="footer-bottom"><span>Deep Learning-Based Pest Detection System Using Sound Analytics</span><small>Made by Tech in air</small></div>
    </footer>
  )
}

export default Footer