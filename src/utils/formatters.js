/**
 * Safe formatting helpers for environmental sensor data
 * These functions handle null, undefined, and invalid values safely
 */

export function formatTemperature(value) {
  // Handle null, undefined, or empty string
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  // Convert to number
  const number = Number(value)

  // Check if it's a valid finite number
  if (!Number.isFinite(number)) {
    return '—'
  }

  // Format to one decimal place
  return `${number.toFixed(1)} °C`
}

export function formatHumidity(value) {
  // Handle null, undefined, or empty string
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  // Convert to number
  const number = Number(value)

  // Check if it's a valid finite number
  if (!Number.isFinite(number)) {
    return '—'
  }

  // Format to one decimal place (max)
  // If the value is a whole number, show it without decimals
  const formatted = number.toFixed(1)
  // Remove trailing .0 if present
  const trimmed = parseFloat(formatted).toString()
  return `${trimmed} %`
}
