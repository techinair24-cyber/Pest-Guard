import { useEffect, useRef, useState } from 'react'

import {
  getDeviceStatusById,
  getLatestDetection,
} from '../services/api'

import { connectDetectionSocket } from '../services/websocket'

const DEVICE_ID =
  import.meta.env.VITE_DEVICE_ID || 'FIELD-UNIT-01'

const DEVICE_CACHE_KEY =
  'pest_guard_device_status'

const DEVICE_STALE_MS =
  3 * 1000

function parseServerTimestamp(value) {
  if (!value) {
    return null
  }

  const text = String(value).trim()

  if (!text) {
    return null
  }

  const hasTimezone =
    /[zZ]|[+-]\d{2}:\d{2}$/.test(text)

  const normalizedText =
    hasTimezone
      ? text
      : `${text}Z`

  const date =
    new Date(normalizedText)

  if (
    Number.isNaN(
      date.getTime(),
    )
  ) {
    return null
  }

  return date
}

function isDeviceFresh(device) {
  if (!device) {
    return false
  }

  const lastSeen =
    parseServerTimestamp(
      device.last_seen ||
        device.lastSeen,
    )

  if (!lastSeen) {
    return false
  }

  const age =
    Date.now() -
    lastSeen.getTime()

  return (
    age >= 0 &&
    age <= DEVICE_STALE_MS
  )
}

function normalizeDevice(device) {
  if (!device) {
    return null
  }

  const fresh =
    isDeviceFresh(device)

  return {
    ...device,

    status:
      fresh
        ? (
            device.status ||
            'ONLINE'
          )
        : 'OFFLINE',

    connection:
      fresh
        ? (
            device.connection ||
            'CONNECTED'
          )
        : 'DISCONNECTED',
  }
}

function getCachedDevice() {
  try {
    const cached =
      window.localStorage.getItem(
        DEVICE_CACHE_KEY,
      )

    if (!cached) {
      return null
    }

    const device =
      JSON.parse(cached)

    if (
      !device ||
      !device.device_id
    ) {
      return null
    }

    return normalizeDevice(
      device,
    )
  } catch {
    return null
  }
}

function cacheDevice(device) {
  if (!device) {
    return
  }

  try {
    window.localStorage.setItem(
      DEVICE_CACHE_KEY,
      JSON.stringify(device),
    )
  } catch {
    // Ignore storage failures.
  }
}

export function useLiveDetection() {
  const mountedRef =
    useRef(false)

  const [liveStatus, setLiveStatus] =
    useState(() => ({
      detection: null,
      device: getCachedDevice(),
    }))

  const [loading, setLoading] =
    useState(() => {
      const cached =
        getCachedDevice()

      return !cached
    })

  const [error, setError] =
    useState(null)

  const updateDeviceStatus =
    async () => {
      try {
        const response =
          await getDeviceStatusById(
            DEVICE_ID,
          )

        if (!mountedRef.current) {
          return
        }

        if (!response) {
          throw new Error(
            'Pest Guard device status was empty.',
          )
        }

        const normalizedDevice =
          normalizeDevice(
            response,
          )

        cacheDevice(
          normalizedDevice,
        )

        setLiveStatus(
          (current) => ({
            ...current,
            device:
              normalizedDevice,
          }),
        )

        setError(null)
        setLoading(false)
      } catch (deviceError) {
        if (!mountedRef.current) {
          return
        }

        console.error(
          'Unable to update device status:',
          deviceError,
        )

        setLiveStatus(
          (current) => {
            if (!current.device) {
              return current
            }

            const refreshedDevice =
              normalizeDevice(
                current.device,
              )

            cacheDevice(
              refreshedDevice,
            )

            return {
              ...current,
              device:
                refreshedDevice,
            }
          },
        )

        setError(deviceError)
        setLoading(false)
      }
    }

  const loadLatestDetection =
    async () => {
      try {
        const response =
          await getLatestDetection()

        if (!mountedRef.current) {
          return
        }

        setLiveStatus(
          (current) => ({
            ...current,
            detection:
              response?.detection ||
              null,
          }),
        )
      } catch (
        detectionError
      ) {
        if (!mountedRef.current) {
          return
        }

        console.error(
          'Unable to load latest detection:',
          detectionError,
        )
      }
    }

  const loadInitialData =
    async () => {
      await Promise.allSettled([
        updateDeviceStatus(),
        loadLatestDetection(),
      ])
    }

  useEffect(() => {
    mountedRef.current = true

    loadInitialData()

    const detectionRefreshTimer =
      window.setInterval(
        () => {
          loadLatestDetection()
        },
        10000,
      )

    const deviceRefreshTimer =
      window.setInterval(
        () => {
          updateDeviceStatus()
        },
        1000,
      )

    const disconnect =
      connectDetectionSocket(
        async (
          incomingDetection,
        ) => {
          if (
            !mountedRef.current
          ) {
            return
          }

          if (
            !incomingDetection
          ) {
            return
          }

          console.log(
            'New Pest Guard detection:',
            incomingDetection,
          )

          setLiveStatus(
            (current) => ({
              ...current,
              detection:
                incomingDetection,
            }),
          )

          setError(null)

          await updateDeviceStatus()
        },

        (socketState) => {
          if (
            !mountedRef.current
          ) {
            return
          }

          if (
            socketState === 'error'
          ) {
            console.error(
              'Detection WebSocket error',
            )
          }
        },
      )

    return () => {
      mountedRef.current = false

      disconnect()

      window.clearInterval(
        detectionRefreshTimer,
      )

      window.clearInterval(
        deviceRefreshTimer,
      )
    }
  }, [])

  return {
    detection:
      liveStatus.detection,

    device:
      liveStatus.device,

    loading,

    error,
  }
}