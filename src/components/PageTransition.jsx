import { cloneElement, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import './PageTransition.css'

function PageTransition({ children }) {
  const location = useLocation()
  const [displayLocation, setDisplayLocation] = useState(location)
  const [transitionStage, setTransitionStage] = useState('enter')

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.scrollTo({
        top: 0,
        left: 0,
        behavior: 'instant',
      })
    }
  }, [location.pathname])

  useEffect(() => {
    if (location.pathname === displayLocation.pathname) {
      return undefined
    }

    setTransitionStage('exit')

    const exitTimer = window.setTimeout(() => {
      setDisplayLocation(location)
      setTransitionStage('enter')
    }, 260)

    return () => window.clearTimeout(exitTimer)
  }, [location, displayLocation])

  const routeContent = cloneElement(children, {
    key: displayLocation.pathname,
    location: displayLocation,
  })

  return (
    <div className={`page-transition-shell page-transition-${transitionStage}`}>
      <div className="page-transition-leaf" aria-hidden="true" />
      <div className="page-transition-page">
        {routeContent}
      </div>
    </div>
  )
}

export default PageTransition
