import { API_BASE_URL } from './api'

const defaultWsUrl =
  API_BASE_URL.replace(/^http/, 'ws') + '/ws/detections'

export const WS_URL =
  import.meta.env.VITE_WS_URL || defaultWsUrl

export function connectDetectionSocket(
  onDetection,
  onStateChange,
) {
  let socket = null
  let stopped = false
  let reconnectTimer = null
  let reconnectAttempt = 0

  const connect = () => {
    if (stopped) {
      return
    }

    onStateChange?.('connecting')

    try {
      socket = new WebSocket(WS_URL)
    } catch (error) {
      console.error(
        'Unable to create detection WebSocket:',
        error,
      )

      onStateChange?.('error')

      scheduleReconnect()
      return
    }

    socket.onopen = () => {
      reconnectAttempt = 0

      console.log(
        'Pest Guard WebSocket connected',
      )

      onStateChange?.('connected')
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (!data || typeof data !== 'object') {
          console.warn(
            'Ignoring invalid detection message:',
            data,
          )
          return
        }

        console.log(
          'Pest Guard detection received:',
          data,
        )

        onDetection?.(data)
      } catch (error) {
        console.error(
          'Invalid WebSocket message:',
          error,
        )
      }
    }

    socket.onerror = (error) => {
      console.error(
        'Pest Guard WebSocket error:',
        error,
      )

      onStateChange?.('error')
    }

    socket.onclose = (event) => {
      socket = null

      if (stopped) {
        onStateChange?.('closed')
        return
      }

      console.warn(
        `Pest Guard WebSocket closed. Code: ${event.code}`,
      )

      onStateChange?.('closed')

      scheduleReconnect()
    }
  }

  const scheduleReconnect = () => {
    if (stopped || reconnectTimer) {
      return
    }

    reconnectAttempt += 1

    const delay = Math.min(
      1000 * 2 ** (reconnectAttempt - 1),
      30000,
    )

    console.log(
      `WebSocket reconnecting in ${delay / 1000}s...`,
    )

    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  connect()

  return () => {
    stopped = true

    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    if (socket) {
      socket.close()
      socket = null
    }
  }
}