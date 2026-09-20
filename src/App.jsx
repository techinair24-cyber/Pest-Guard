import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Header from './components/Header'
import Footer from './components/Footer'
import PageTransition from './components/PageTransition'
import Home from './pages/Home'
import About from './pages/About'
import Pests from './pages/Pests'
import Solutions from './pages/Solutions'
import LiveMonitoring from './pages/LiveMonitoring'

function App() {
  return (
    <BrowserRouter>
      <div className="site-shell">
        <Header />
        <main>
          <PageTransition>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/home" element={<Home />} />
              <Route path="/about" element={<About />} />
              <Route path="/pests" element={<Pests />} />
              <Route path="/solutions" element={<Solutions />} />
              <Route path="/live-monitoring" element={<LiveMonitoring />} />
            </Routes>
          </PageTransition>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}

export default App
