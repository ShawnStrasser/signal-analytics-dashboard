const STORAGE_KEY = 'traffic-signal-captcha-verified'

export const CAPTCHA_STORAGE_KEY = STORAGE_KEY

export function isCaptchaVerified() {
  if (typeof window === 'undefined') {
    return false
  }
  return window.localStorage.getItem(STORAGE_KEY) === 'true'
}

export function setCaptchaVerified() {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(STORAGE_KEY, 'true')
}

export function clearCaptchaVerification() {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.removeItem(STORAGE_KEY)
}
