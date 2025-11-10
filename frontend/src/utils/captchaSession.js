const CAPTCHA_BASE = '/api/captcha'

let cachedVerified = false

function setCachedVerified(value) {
  cachedVerified = !!value
}

export function isCaptchaVerifiedCached() {
  return cachedVerified
}

export function resetCaptchaCache() {
  setCachedVerified(false)
}

async function handleResponse(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.error || 'captcha_request_failed')
    error.status = response.status
    error.response = data
    throw error
  }
  return data
}

export async function requestCaptchaNonce() {
  const response = await fetch(`${CAPTCHA_BASE}/start`, {
    method: 'POST',
    credentials: 'include'
  })
  const data = await handleResponse(response)
  if (!data.nonce) {
    throw new Error('missing_nonce')
  }
  setCachedVerified(false)
  return data.nonce
}

export async function submitCaptchaSolve(nonce) {
  const response = await fetch(`${CAPTCHA_BASE}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ nonce })
  })
  const data = await handleResponse(response)
  setCachedVerified(true)
  return data
}

export async function fetchCaptchaStatus() {
  const response = await fetch(`${CAPTCHA_BASE}/status`, {
    method: 'GET',
    credentials: 'include'
  })
  const data = await handleResponse(response)
  setCachedVerified(!!data.verified)
  return data
}
