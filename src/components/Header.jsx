import { useState } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { LeafIcon } from './Icons'

const navItems = [
  ['Home', '/'],
  ['About', '/about'],
  ['Pests', '/pests'],
  ['Solutions', '/solutions'],
  ['Live Monitoring', '/live-monitoring'],
]

function Header() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="site-header">
      <div className="header-inner">

        <Link
          className="brand"
          to="/"
          aria-label="Pest Guard home"
          onClick={() => setMenuOpen(false)}
        >
          <span className="brand-mark">
            <LeafIcon size={21} />
          </span>

          <span className="brand-text">
            <span className="brand-name">
              Pest <strong>Guard</strong>
            </span>

            <small>
              AI • Sound Analytics
            </small>
          </span>
        </Link>

        <button
          className="menu-toggle"
          type="button"
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
          aria-controls="main-navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span />
          <span />
          <span />
        </button>

        <nav
          className={menuOpen ? 'main-nav open' : 'main-nav'}
          id="main-navigation"
          aria-label="Main navigation"
        >
          {navItems.map(([label, href]) => (
            <NavLink
              key={label}
              to={href}
              end={href === '/'}
              className={({ isActive }) =>
                isActive ? 'active' : ''
              }
              onClick={() => setMenuOpen(false)}
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <Link
          className="header-action"
          to="/live-monitoring"
        >
          Get Started
          <span aria-hidden="true">↗</span>
        </Link>

      </div>
    </header>
  )
}

export default Header