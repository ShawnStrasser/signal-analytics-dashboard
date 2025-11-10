<template>
  <div class="captcha-page">
    <div class="captcha-container">
      <h2>Please Verify You're a Human who Likes to Solve Traffic Signal Puzzles</h2>
      <p id="challenge-text">
        <span id="challenge-color" ref="challengeColorRef"></span>
      </p>
      <div class="difficulty-section" role="radiogroup" aria-label="Captcha difficulty">
        <div class="difficulty-options">
          <label
            v-for="option in difficultyOptions"
            :key="option.value"
            :class="['difficulty-option', option.value === difficulty ? 'active' : '']"
          >
            <input
              type="radio"
              :value="option.value"
              v-model="difficulty"
              name="captcha-difficulty"
            />
            <span class="difficulty-name">{{ option.label }}</span>
          </label>
        </div>
      </div>
      <canvas
        id="trafficCanvas"
        ref="canvasRef"
        width="630"
        height="480"
      ></canvas>
      <div id="status-message" ref="statusMessageRef"></div>
      <div v-if="showVictoryPrompt" class="victory-panel">
        <p class="victory-message">
          Ready to enter the site or play again?
        </p>
        <div class="victory-actions">
          <button class="victory-enter" type="button" @click="enterSite">
            Enter the Site
          </button>
          <button class="victory-replay" type="button" @click="playAgain">
            Play Again
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { isCaptchaVerified, setCaptchaVerified } from '../utils/captchaSession'
import confetti from 'canvas-confetti'

const canvasRef = ref(null)
const statusMessageRef = ref(null)
const challengeColorRef = ref(null)
const difficulty = ref('medium')
const showVictoryPrompt = ref(false)

const difficultyOptions = [
  { value: 'easy', label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard', label: 'Hard' }
]

let activeDifficulty = difficulty.value
let difficultyResetHandler = null
let enterSiteHandler = null
let replayHandler = null

const enterSite = () => {
  if (typeof enterSiteHandler === 'function') {
    enterSiteHandler()
  }
}

const playAgain = () => {
  if (typeof replayHandler === 'function') {
    replayHandler()
  }
}

const router = useRouter()
const route = useRoute()

const FALLBACK_REDIRECT = '/travel-time'

function computeRedirectTarget() {
  const { redirect } = route.query
  if (typeof redirect === 'string' && redirect.trim().length > 0) {
    return redirect
  }
  return FALLBACK_REDIRECT
}

function redirectAfterVerification() {
  const target = computeRedirectTarget()
  const destination = target === '/captcha' ? FALLBACK_REDIRECT : target
  router.replace(destination)
}

let detachCanvasListeners = () => {}
let cancelAnimation = () => {}
let detachResizeListener = () => {}
let stopVictoryCelebration = () => {}
let startVictoryCelebration = () => {}
let teardownConfettiEngine = () => {}

const confettiColors = ['#ef4444', '#f97316', '#fcd34d', '#34d399', '#38bdf8', '#c084fc']
let confettiCanvas = null
let confettiEngine = null
let victoryCelebrationActive = false
let victoryCelebrationTimer = 0
let detachConfettiResize = () => {}

const initializeConfettiEngine = () => {
  if (confettiEngine || typeof window === 'undefined') {
    return
  }
  confettiCanvas = document.createElement('canvas')
  confettiCanvas.className = 'global-confetti-canvas'
  document.body.appendChild(confettiCanvas)

  const applyCanvasSizing = () => {
    if (!confettiCanvas) {
      return
    }
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    confettiCanvas.style.position = 'fixed'
    confettiCanvas.style.top = '0'
    confettiCanvas.style.left = '0'
    confettiCanvas.style.width = '100vw'
    confettiCanvas.style.height = '100vh'
    confettiCanvas.style.pointerEvents = 'none'
    confettiCanvas.style.zIndex = '9999'
    confettiCanvas.width = Math.floor(window.innerWidth * ratio)
    confettiCanvas.height = Math.floor(window.innerHeight * ratio)
  }

  applyCanvasSizing()
  const handleResize = () => applyCanvasSizing()
  window.addEventListener('resize', handleResize)
  detachConfettiResize = () => window.removeEventListener('resize', handleResize)

  confettiEngine = confetti.create(confettiCanvas, {
    resize: true,
    useWorker: true,
    disableForReducedMotion: false,
  })
}

const emitLocalizedConfetti = (canvasEl, x, y) => {
  if (!confettiEngine || !canvasEl) {
    return
  }
  const rect = canvasEl.getBoundingClientRect()
  const originX = (rect.left + (x / canvasEl.width) * rect.width) / window.innerWidth
  const originY = (rect.top + (y / canvasEl.height) * rect.height) / window.innerHeight
  confettiEngine({
    particleCount: 40,
    spread: 65,
    startVelocity: 50,
    gravity: 1.1,
    scalar: 0.9,
    ticks: 70,
    colors: confettiColors,
    origin: { x: originX, y: originY },
    drift: (Math.random() - 0.5) * 0.6,
  })
}

const emitVictoryBurst = (intensity = 1) => {
  if (!confettiEngine) {
    return
  }
  const mobileScalar = window.innerWidth <= 640 ? 0.85 : 1.15
  const mobileCountFactor = window.innerWidth <= 640 ? 0.75 : 1
  const randomOrigin = () => ({
    x: Math.random(),
    y: 0.05 + Math.random() * 0.9,
  })

  confettiEngine({
    particleCount: Math.floor(220 * intensity * mobileCountFactor),
    spread: 140 + Math.random() * 40,
    startVelocity: 70 + Math.random() * 15,
    gravity: 0.75,
    ticks: 110,
    scalar: mobileScalar,
    drift: (Math.random() - 0.5) * 1.5,
    colors: confettiColors,
    origin: randomOrigin(),
  })

  confettiEngine({
    particleCount: Math.floor(120 * intensity * mobileCountFactor),
    spread: 90,
    startVelocity: 85,
    decay: 0.92,
    gravity: 1.3,
    scalar: mobileScalar * 0.65,
    colors: confettiColors,
    origin: randomOrigin(),
    drift: (Math.random() - 0.5) * 1.6,
  })

  confettiEngine({
    particleCount: Math.floor(80 * intensity * mobileCountFactor),
    spread: 45,
    startVelocity: 60,
    gravity: 2.4,
    scalar: mobileScalar * 0.5,
    ticks: 60,
    origin: { x: Math.random(), y: 0.95 },
    colors: confettiColors,
  })
}

stopVictoryCelebration = () => {
  victoryCelebrationActive = false
  if (victoryCelebrationTimer) {
    window.clearTimeout(victoryCelebrationTimer)
    victoryCelebrationTimer = 0
  }
}

startVictoryCelebration = () => {
  stopVictoryCelebration()
  if (!confettiEngine) {
    return
  }
  victoryCelebrationActive = true
  const celebrationStart = Date.now()

  const loop = () => {
    if (!victoryCelebrationActive) {
      return
    }
    const elapsed = Date.now() - celebrationStart
    if (elapsed >= 5000) {
      stopVictoryCelebration()
      return
    }
    emitVictoryBurst(1.1 + Math.random() * 0.4)
    victoryCelebrationTimer = window.setTimeout(loop, 230 + Math.random() * 170)
  }

  emitVictoryBurst(1.4)
  emitVictoryBurst(1.2)
  loop()
}

teardownConfettiEngine = () => {
  stopVictoryCelebration()
  if (confettiEngine?.reset) {
    confettiEngine.reset()
  }
  confettiEngine = null
  if (confettiCanvas) {
    confettiCanvas.remove()
    confettiCanvas = null
  }
  detachConfettiResize()
  detachConfettiResize = () => {}
}
watch(
  difficulty,
  (next, prev) => {
    if (next === prev) {
      return
    }
    activeDifficulty = next
    showVictoryPrompt.value = false
    stopVictoryCelebration()
    if (typeof difficultyResetHandler === 'function') {
      difficultyResetHandler()
    }
  }
)

onMounted(() => {
  document.title = "Please Verify You're a Human who Likes to Solve Traffic Signal Puzzles"

  if (isCaptchaVerified()) {
    redirectAfterVerification()
    return
  }

  const canvas = canvasRef.value
  const statusMessageEl = statusMessageRef.value
  const challengeColorEl = challengeColorRef.value

  if (!canvas || !statusMessageEl) {
    return
  }

  const ctx = canvas.getContext('2d')
  if (!ctx) {
    return
  }
  initializeConfettiEngine()

  const BASE_CANVAS_WIDTH = 630
  const BASE_CANVAS_HEIGHT = 480
  const MIN_CANVAS_WIDTH = 220

  const BASE_LIGHT_RADIUS = 25
  const BASE_PADDING = 20
  const BASE_BACKPLATE_MARGIN = 12
  const BASE_SLOT_TOP_OFFSET = 55
  const BASE_SLOT_GAP = 70
  const BASE_SIGNAL_PADDING = 10
  const BASE_SIGNAL_WIDTH = 90
  const BASE_SIGNAL_HEIGHT = 250
  const BASE_SIGNAL_MOVE = 2

  const BASE_SIGNAL_SPEED_MULTIPLIER = 1.5
  const BASE_ROTATION_SPEED = 0.02
  const BASE_FAST_ROTATION_SPEED = 0.04
  const BASE_BACKPLATE_CORNER_RADIUS = 12
  const BASE_SIGNAL_CORNER_RADIUS = 8
  const BASE_LIGHT_START_POSITIONS = [100, 240, 380]
  const LIGHT_OFFSET_EXTRA = 10
  const LIGHT_HIGHLIGHT_OFFSET_RATIO = 0.28
  const LIGHT_HIGHLIGHT_RADIUS_RATIO = 0.4

  const MOVEMENT_DELAY_MS = 2000
  const BASE_SPIN_TRIGGER_MS = 4000
  const FAST_SPIN_TRIGGER_MS = 9000
  const ESCAPE_TRIGGER_MS = 14000
  const touchOptions = { passive: false }
  const HARD_LAUNCH_MODE = 'hard'
  function getDifficultySpeedBoost() {
    if (activeDifficulty === 'easy') {
      return 0
    }
    if (activeDifficulty === 'hard') {
      return 1.45
    }
    return 1
  }

  let scale = 1
  let geometryScale = 1
  let heightScale = 1
  let LIGHT_RADIUS = BASE_LIGHT_RADIUS
  let PADDING = BASE_PADDING
  let BACKPLATE_MARGIN = BASE_BACKPLATE_MARGIN
  let SLOT_TOP_OFFSET = BASE_SLOT_TOP_OFFSET
  let SLOT_GAP = BASE_SLOT_GAP
  let signalPadding = BASE_SIGNAL_PADDING
  let signalSpeedMultiplier = BASE_SIGNAL_SPEED_MULTIPLIER
  let baseRotationSpeed = BASE_ROTATION_SPEED
  let fastRotationSpeed = BASE_FAST_ROTATION_SPEED
  let signalWidth = BASE_SIGNAL_WIDTH
  let signalHeight = BASE_SIGNAL_HEIGHT
  let scaledSignalMove = BASE_SIGNAL_MOVE
  let resizeFrameId = 0

  let signalHead
  let backplate
  let lights

  let isDragging = false
  let dragTarget = null
  let offsetX = 0
  let offsetY = 0
  let isVerified = false
  let redirected = false

  let isSignalMoving = false
  let signalMoveX = 2
  let signalMoveY = 2
  let allowOffPageMovement = false

  let isSpinning = false
  let signalRotation = 0
  let gameStartTime = 0

  let hasEscaped = false
  let fastSpinMessageShown = false
  let placedLights = { red: false, yellow: false, green: false }
  let animationFrameId = 0
  let isMovementPending = false
  let movementStartDeadline = 0
  let pendingLaunchMode = 'normal'
  let allowPostVictoryMotion = false

  function applyResponsiveScaling() {
    const container = canvas.parentElement
    const viewportWidth = Math.max(window.innerWidth || MIN_CANVAS_WIDTH, MIN_CANVAS_WIDTH)
    const fallbackWidth = Math.max(viewportWidth - 32, MIN_CANVAS_WIDTH)
    let availableWidth = fallbackWidth

    if (container && container.clientWidth > 0) {
      const styles = window.getComputedStyle(container)
      const horizontalPadding =
        parseFloat(styles.paddingLeft || '0') + parseFloat(styles.paddingRight || '0')
      const innerWidth = container.clientWidth - horizontalPadding
      if (innerWidth > 0) {
        availableWidth = innerWidth
      }
    }
    const desiredWidth = Math.min(BASE_CANVAS_WIDTH, Math.max(availableWidth, MIN_CANVAS_WIDTH))
    const constrainedWidth = availableWidth < MIN_CANVAS_WIDTH ? availableWidth : desiredWidth
    const targetWidth = Math.round(constrainedWidth)

    scale = targetWidth / BASE_CANVAS_WIDTH
    geometryScale = Math.min(1, Math.pow(scale, 0.7))
    heightScale = scale < 0.9 ? 1 + (0.9 - scale) * 0.35 : 1

    const targetHeight = Math.round(BASE_CANVAS_HEIGHT * scale * heightScale)

    canvas.width = targetWidth
    canvas.height = targetHeight
    canvas.style.width = `${targetWidth}px`
    canvas.style.height = `${targetHeight}px`

    ctx.setTransform(1, 0, 0, 1, 0, 0)

    const movementScale = Math.max(geometryScale * 0.85, 0.32)
    const speedFactor = 0.3 + 0.7 * scale * scale
    const difficultyBoost = getDifficultySpeedBoost()
    const rotationBoost = activeDifficulty === 'hard' ? 1.25 : 1
    const rotationDifficultyFactor = activeDifficulty === 'easy' ? 0 : rotationBoost

    LIGHT_RADIUS = BASE_LIGHT_RADIUS * geometryScale
    PADDING = BASE_PADDING * geometryScale
    BACKPLATE_MARGIN = BASE_BACKPLATE_MARGIN * geometryScale
    SLOT_TOP_OFFSET = BASE_SLOT_TOP_OFFSET * geometryScale
    SLOT_GAP = BASE_SLOT_GAP * geometryScale
    signalPadding = Math.max(BASE_SIGNAL_PADDING * geometryScale, 6)
    signalWidth = BASE_SIGNAL_WIDTH * geometryScale
    signalHeight = BASE_SIGNAL_HEIGHT * geometryScale
    scaledSignalMove = BASE_SIGNAL_MOVE * movementScale
    signalSpeedMultiplier = BASE_SIGNAL_SPEED_MULTIPLIER * speedFactor * difficultyBoost
    baseRotationSpeed = BASE_ROTATION_SPEED * speedFactor * rotationDifficultyFactor
    fastRotationSpeed =
      BASE_FAST_ROTATION_SPEED * Math.max(speedFactor, 0.45) * rotationDifficultyFactor
  }

  if (challengeColorEl) {
    challengeColorEl.textContent = ''
  }

  function defineComponents() {
    const initialSignalWidth = signalWidth
    const initialSignalHeight = signalHeight
    const initialSignalX = canvas.width / 2 - initialSignalWidth / 2
    const initialSignalY = canvas.height / 2 - initialSignalHeight / 2

    signalHead = {
      x: initialSignalX,
      y: initialSignalY,
      width: initialSignalWidth,
      height: initialSignalHeight,
      color: '#374151'
    }

    backplate = {
      x: signalHead.x - BACKPLATE_MARGIN,
      y: signalHead.y - BACKPLATE_MARGIN,
      width: signalHead.width + 2 * BACKPLATE_MARGIN,
      height: signalHead.height + 2 * BACKPLATE_MARGIN,
      color: '#facc15'
    }

    const lightConfigs = [
      { id: 'red', color: '#ef4444' },
      { id: 'yellow', color: '#f59e0b' },
      { id: 'green', color: '#22c55e' }
    ]

    const lightOffsetX = PADDING + LIGHT_RADIUS + LIGHT_OFFSET_EXTRA * geometryScale

    lights = lightConfigs.map((config, index) => {
      const baseY = BASE_LIGHT_START_POSITIONS[index] ?? BASE_LIGHT_START_POSITIONS[BASE_LIGHT_START_POSITIONS.length - 1]
      const lightY = baseY * geometryScale
      return {
        id: config.id,
        x: lightOffsetX,
        y: lightY,
        r: LIGHT_RADIUS,
        color: config.color,
        origX: lightOffsetX,
        origY: lightY,
        isPlaced: false
      }
    })
  }

  function drawBackplate() {
    ctx.save()
    const cx = backplate.x + backplate.width / 2
    const cy = backplate.y + backplate.height / 2
    ctx.translate(cx, cy)
    ctx.rotate(signalRotation)

    ctx.fillStyle = backplate.color
    ctx.beginPath()
    ctx.roundRect(
      -backplate.width / 2,
      -backplate.height / 2,
      backplate.width,
      backplate.height,
      Math.max(BASE_BACKPLATE_CORNER_RADIUS * geometryScale, 4)
    )
    ctx.fill()

    ctx.restore()
  }

  function drawSignalHead() {
    ctx.save()
    const cx = signalHead.x + signalHead.width / 2
    const cy = signalHead.y + signalHead.height / 2
    ctx.translate(cx, cy)
    ctx.rotate(signalRotation)

    ctx.fillStyle = signalHead.color
    ctx.beginPath()
    ctx.roundRect(
      -signalHead.width / 2,
      -signalHead.height / 2,
      signalHead.width,
      signalHead.height,
      Math.max(BASE_SIGNAL_CORNER_RADIUS * geometryScale, 3)
    )
    ctx.fill()

    ctx.fillStyle = '#111827'
    const lightCenterOffsetX = 0
    const slotTopOffsetRel = SLOT_TOP_OFFSET - signalHead.height / 2

    ctx.beginPath()
    ctx.arc(lightCenterOffsetX, slotTopOffsetRel, LIGHT_RADIUS, 0, Math.PI * 2)
    ctx.fill()

    ctx.beginPath()
    ctx.arc(lightCenterOffsetX, slotTopOffsetRel + SLOT_GAP, LIGHT_RADIUS, 0, Math.PI * 2)
    ctx.fill()

    ctx.beginPath()
    ctx.arc(lightCenterOffsetX, slotTopOffsetRel + 2 * SLOT_GAP, LIGHT_RADIUS, 0, Math.PI * 2)
    ctx.fill()

    ctx.restore()
  }

  function drawLights() {
    lights.forEach(light => {
      ctx.beginPath()
      ctx.arc(light.x, light.y, light.r, 0, Math.PI * 2)
      ctx.fillStyle = light.color
      ctx.shadowColor = light.color
      const glowMultiplier = Math.max(geometryScale, 0.6)
      ctx.shadowBlur = (light.isPlaced ? 15 : 5) * glowMultiplier
      ctx.fill()

      ctx.beginPath()
      const highlightOffset = light.r * LIGHT_HIGHLIGHT_OFFSET_RATIO
      ctx.arc(
        light.x - highlightOffset,
        light.y - highlightOffset,
        light.r * LIGHT_HIGHLIGHT_RADIUS_RATIO,
        0,
        Math.PI * 2
      )
      ctx.fillStyle = 'rgba(255, 255, 255, 0.4)'
      ctx.fill()
      ctx.shadowBlur = 0
    })
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    drawBackplate()
    drawSignalHead()
    drawLights()
  }

  function updateStatus(message, className = '') {
    statusMessageEl.textContent = message
    statusMessageEl.className = className
  }

  function requestSignalMovement(mode = 'normal') {
    if (activeDifficulty === 'easy') {
      return
    }
    if (isSignalMoving || isMovementPending) {
      return
    }
    pendingLaunchMode = mode
    isMovementPending = true
    movementStartDeadline = mode === HARD_LAUNCH_MODE ? Date.now() : Date.now() + MOVEMENT_DELAY_MS
  }

  function handleOffPageEscape() {
    if (hasEscaped || isVerified) {
      return
    }
    hasEscaped = true
    //updateStatus('Signal head is roaming outside the frame; keep going!', 'warning')
    lights.forEach(light => {
      light.x = Math.min(Math.max(light.x, LIGHT_RADIUS), canvas.width - LIGHT_RADIUS)
      light.y = Math.min(Math.max(light.y, LIGHT_RADIUS), canvas.height - LIGHT_RADIUS)
    })
    draw()
  }

  function updateSignalPosition() {
    const dropZones = getDropZoneCenters()

    if (isVerified && !allowPostVictoryMotion) {
      syncPlacedLights(dropZones)
      return
    }

    if (!isVerified && activeDifficulty === 'easy') {
      syncPlacedLights(dropZones)
      return
    }

    const now = Date.now()

    if (!isSignalMoving) {
      if (isMovementPending && now >= movementStartDeadline) {
        isMovementPending = false
        isSignalMoving = true
        const launchMode = pendingLaunchMode
        pendingLaunchMode = 'normal'
        gameStartTime = now
        if (launchMode === HARD_LAUNCH_MODE) {
          gameStartTime = now - FAST_SPIN_TRIGGER_MS
          isSpinning = true
          fastSpinMessageShown = true
          updateStatus('Hard mode: the signal head is at full speed!', 'error')
        } else {
          updateStatus('Signal head is moving!', 'warning')
        }
      } else {
        syncPlacedLights(dropZones)
        return
      }
    }

    const elapsedTime = now - gameStartTime
    let currentRotationSpeed = 0

    if (elapsedTime >= ESCAPE_TRIGGER_MS) {
      if (!allowOffPageMovement) {
        allowOffPageMovement = true
        updateStatus('WARNING: Signal is escaping!', 'error')
      }
      fastSpinMessageShown = true
      isSpinning = true
      currentRotationSpeed = fastRotationSpeed
    } else if (elapsedTime >= FAST_SPIN_TRIGGER_MS) {
      if (!fastSpinMessageShown && !hasEscaped) {
        //updateStatus('Rotation Speed Increased!', 'warning')
        fastSpinMessageShown = true
      }
      isSpinning = true
      currentRotationSpeed = fastRotationSpeed
    } else if (elapsedTime >= BASE_SPIN_TRIGGER_MS) {
      if (!isSpinning) {
        isSpinning = true
        //updateStatus('Signal is starting to spin!', 'warning')
      }
      currentRotationSpeed = baseRotationSpeed
    }

    if (isSpinning) {
      signalRotation += currentRotationSpeed
      if (signalRotation > 2 * Math.PI) {
        signalRotation -= 2 * Math.PI
      }
    }

    signalHead.x += signalMoveX * signalSpeedMultiplier
    backplate.x += signalMoveX * signalSpeedMultiplier

    if (!allowOffPageMovement) {
      const hitXMax = signalHead.x + signalHead.width + signalPadding > canvas.width
      const hitXMin = signalHead.x - signalPadding < 0

      if (hitXMax || hitXMin) {
        signalMoveX *= -1
        signalHead.x = hitXMax ? canvas.width - signalHead.width - signalPadding : signalPadding
        backplate.x = signalHead.x - BACKPLATE_MARGIN
      }
    } else {
      const maxDistance = Math.max(canvas.width, canvas.height) * 0.25
      const cx = signalHead.x + signalHead.width / 2
      if (cx < -maxDistance || cx > canvas.width + maxDistance) {
        handleOffPageEscape()
        signalMoveX *= -1
        const targetCx = cx < 0 ? -maxDistance : canvas.width + maxDistance
        signalHead.x = targetCx - signalHead.width / 2
        backplate.x = signalHead.x - BACKPLATE_MARGIN
      }
    }

    signalHead.y += signalMoveY * signalSpeedMultiplier
    backplate.y += signalMoveY * signalSpeedMultiplier

    if (!allowOffPageMovement) {
      const hitYMax = signalHead.y + signalHead.height + signalPadding > canvas.height
      const hitYMin = signalHead.y - signalPadding < 0

      if (hitYMax || hitYMin) {
        signalMoveY *= -1
        signalHead.y = hitYMax ? canvas.height - signalHead.height - signalPadding : signalPadding
        backplate.y = signalHead.y - BACKPLATE_MARGIN
      }
    } else {
      const maxDistance = Math.max(canvas.width, canvas.height) * 0.25
      const cy = signalHead.y + signalHead.height / 2
      if (cy < -maxDistance || cy > canvas.height + maxDistance) {
        handleOffPageEscape()
        signalMoveY *= -1
        const targetCy = cy < 0 ? -maxDistance : canvas.height + maxDistance
        signalHead.y = targetCy - signalHead.height / 2
        backplate.y = signalHead.y - BACKPLATE_MARGIN
      }
    }

    syncPlacedLights(dropZones)
  }

  function animate() {
    updateSignalPosition()
    draw()
    animationFrameId = window.requestAnimationFrame(animate)
  }

  function getDropZoneCenters() {
    const cx = signalHead.x + signalHead.width / 2
    const cy = signalHead.y + signalHead.height / 2
    const halfHeight = signalHead.height / 2

    const relativeCenters = [
      { id: 'red', rx: 0, ry: SLOT_TOP_OFFSET - halfHeight, r: LIGHT_RADIUS + 2 },
      { id: 'yellow', rx: 0, ry: SLOT_TOP_OFFSET + SLOT_GAP - halfHeight, r: LIGHT_RADIUS + 2 },
      { id: 'green', rx: 0, ry: SLOT_TOP_OFFSET + 2 * SLOT_GAP - halfHeight, r: LIGHT_RADIUS + 2 }
    ]

    const cosR = Math.cos(signalRotation)
    const sinR = Math.sin(signalRotation)

    return relativeCenters.map(rc => {
      const rotX = rc.rx * cosR - rc.ry * sinR
      const rotY = rc.rx * sinR + rc.ry * cosR

      return {
        id: rc.id,
        x: cx + rotX,
        y: cy + rotY,
        r: rc.r
      }
    })
  }

  function syncPlacedLights(dropZones) {
    lights.forEach(light => {
      if (light.isPlaced) {
        const zone = dropZones.find(z => z.id === light.id)
        if (zone) {
          light.x = zone.x
          light.y = zone.y
        }
      }
    })
  }

  function getEventPos(e) {
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height

    let clientX
    let clientY

    if (e.touches && e.touches.length > 0) {
      clientX = e.touches[0].clientX
      clientY = e.touches[0].clientY
    } else {
      clientX = e.clientX
      clientY = e.clientY
    }

    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY
    }
  }

  function isPointInCircle(px, py, circle) {
    const dx = px - circle.x
    const dy = py - circle.y
    return dx * dx + dy * dy <= circle.r * circle.r
  }

  function onDown(e) {
    if (isVerified) {
      return
    }
    e.preventDefault()
    const pos = getEventPos(e)

    for (let i = lights.length - 1; i >= 0; i -= 1) {
      if (isPointInCircle(pos.x, pos.y, lights[i])) {
        isDragging = true
        canvas.classList.add('dragging')
        dragTarget = lights[i]
        offsetX = pos.x - dragTarget.x
        offsetY = pos.y - dragTarget.y

        if (dragTarget.isPlaced) {
          placedLights[dragTarget.id] = false
          dragTarget.isPlaced = false
        }

        const item = lights.splice(i, 1)[0]
        lights.push(item)

        if (!isSignalMoving && !isMovementPending) {
          const launchMode = activeDifficulty === 'hard' ? HARD_LAUNCH_MODE : 'normal'
          requestSignalMovement(launchMode)
        }

        draw()
        break
      }
    }
  }

  function onMove(e) {
    if (!isDragging || isVerified || !dragTarget) {
      return
    }
    e.preventDefault()
    const pos = getEventPos(e)
    let nextX = pos.x - offsetX
    let nextY = pos.y - offsetY

    if (hasEscaped) {
      const minX = LIGHT_RADIUS
      const maxX = canvas.width - LIGHT_RADIUS
      const minY = LIGHT_RADIUS
      const maxY = canvas.height - LIGHT_RADIUS
      nextX = Math.min(Math.max(nextX, minX), maxX)
      nextY = Math.min(Math.max(nextY, minY), maxY)
    }

    dragTarget.x = nextX
    dragTarget.y = nextY
  }

  function onUp(e) {
    if (!isDragging || isVerified || !dragTarget) {
      return
    }
    e.preventDefault()
    canvas.classList.remove('dragging')
    isDragging = false

    const actualDropZones = getDropZoneCenters()
    for (const zone of actualDropZones) {
      if (isPointInCircle(dragTarget.x, dragTarget.y, zone)) {
        if (dragTarget.id === zone.id) {
          handleSuccessfulPlacement(zone)
        }
        break
      }
    }

    dragTarget = null
    draw()
  }

  function completeVerification() {
    if (showVictoryPrompt.value) {
      return
    }
    setCaptchaVerified()
    emitVictoryBurst(1.3)
    showVictoryPrompt.value = true
    startVictoryCelebration()
  }

  function handleSuccessfulPlacement(zone) {
    dragTarget.x = zone.x
    dragTarget.y = zone.y

    placedLights[dragTarget.id] = true
    dragTarget.isPlaced = true
    emitLocalizedConfetti(canvas, zone.x, zone.y)

    const allPlaced = Object.values(placedLights).every(status => status === true)

    if (allPlaced) {
      const wasMoving = isSignalMoving
      isVerified = true
      allowPostVictoryMotion = wasMoving
      updateStatus('You have proven your humanity in a sea of AI hacker bots!', 'success')
      removeListeners()
      completeVerification()
    } else {
      //updateStatus(`${dragTarget.id.charAt(0).toUpperCase() + dragTarget.id.slice(1)} placed correctly!`, 'success')
      window.setTimeout(() => {
        if (!isVerified) {
          //updateStatus('Continue configuring the signal head.')
        }
      }, 800)
    }
  }

  function addListeners() {
    canvas.addEventListener('mousedown', onDown)
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseup', onUp)
    canvas.addEventListener('mouseleave', onUp)
    canvas.addEventListener('touchstart', onDown, touchOptions)
    canvas.addEventListener('touchmove', onMove, touchOptions)
    canvas.addEventListener('touchend', onUp)
  }

  function removeListeners() {
    canvas.removeEventListener('mousedown', onDown)
    canvas.removeEventListener('mousemove', onMove)
    canvas.removeEventListener('mouseup', onUp)
    canvas.removeEventListener('mouseleave', onUp)
    canvas.removeEventListener('touchstart', onDown, touchOptions)
    canvas.removeEventListener('touchmove', onMove, touchOptions)
    canvas.removeEventListener('touchend', onUp)
  }

  function handleResize() {
    if (resizeFrameId) {
      window.cancelAnimationFrame(resizeFrameId)
    }
    resizeFrameId = window.requestAnimationFrame(() => {
      resizeFrameId = 0
      init()
    })
  }

  function init() {
    stopVictoryCelebration()
    applyResponsiveScaling()
    canvas.classList.remove('dragging')
    showVictoryPrompt.value = false

    isVerified = false
    redirected = false
    isDragging = false
    dragTarget = null
    isSignalMoving = false
    isSpinning = false
    allowOffPageMovement = false
    hasEscaped = false
    fastSpinMessageShown = false
    signalRotation = 0
    gameStartTime = 0
    placedLights = { red: false, yellow: false, green: false }
    signalMoveX = scaledSignalMove
    signalMoveY = scaledSignalMove
    isMovementPending = false
    movementStartDeadline = 0
    pendingLaunchMode = 'normal'
    allowPostVictoryMotion = false
    updateStatus('')

    defineComponents()

    lights.forEach(light => {
      light.x = light.origX
      light.y = light.origY
      light.isPlaced = false
    })

    removeListeners()
    addListeners()
    draw()
  }

  window.addEventListener('resize', handleResize)
  detachResizeListener = () => window.removeEventListener('resize', handleResize)

  difficultyResetHandler = () => {
    redirected = false
    stopVictoryCelebration()
    init()
  }

  enterSiteHandler = () => {
    if (redirected) {
      return
    }
    redirected = true
    stopVictoryCelebration()
    showVictoryPrompt.value = false
    redirectAfterVerification()
  }

  replayHandler = () => {
    redirected = false
    stopVictoryCelebration()
    showVictoryPrompt.value = false
    init()
  }

  detachCanvasListeners = removeListeners
  cancelAnimation = () => {
    if (animationFrameId) {
      window.cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
  }

  animationFrameId = window.requestAnimationFrame(animate)
  init()
})

onBeforeUnmount(() => {
  detachCanvasListeners()
  detachResizeListener()
  cancelAnimation()
  stopVictoryCelebration()
  difficultyResetHandler = null
  enterSiteHandler = null
  replayHandler = null
  teardownConfettiEngine()
})
</script>

<style scoped>
.captcha-page {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background-color: #f3f4f6;
  color: #1f2937;
  margin: 0;
  user-select: none;
  -webkit-user-select: none;
  -ms-user-select: none;
  padding: clamp(16px, 4vw, 32px);
  box-sizing: border-box;
  width: 100%;
}

.captcha-container {
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
  padding: clamp(24px, 4vw, 32px);
  text-align: center;
  width: min(100%, 650px);
  border: 1px solid #e5e7eb;
  box-sizing: border-box;
  margin: 0 auto;
  position: relative;
}

h2 {
  margin-top: 0;
  font-size: 1.5rem;
  color: #111827;
}

#challenge-text {
  font-size: 1.1rem;
  margin: 12px 0 20px 0;
  color: #4b5563;
}

#challenge-color {
  font-weight: 600;
}

.difficulty-section {
  margin: 8px 0 20px 0;
  text-align: left;
}

.difficulty-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  justify-content: center;
}

.difficulty-option {
  position: relative;
  flex: 0 1 120px;
  min-width: 96px;
  max-width: 140px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #d1d5db;
  cursor: pointer;
  background-color: #f9fafb;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
  display: flex;
  justify-content: center;
  align-items: center;
}

.difficulty-option input {
  position: absolute;
  opacity: 0;
  width: 1px;
  height: 1px;
  margin: -1px;
  border: 0;
  padding: 0;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
}

.difficulty-option.active {
  border-color: #4f46e5;
  background-color: #eef2ff;
  box-shadow: 0 10px 20px rgba(79, 70, 229, 0.18);
}

.difficulty-name {
  font-weight: 700;
  color: #111827;
  font-size: 0.95rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

#trafficCanvas {
  background-color: #f9fafb;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  cursor: grab;
  width: 100%;
  max-width: 630px;
  height: auto;
  display: block;
  margin: 0 auto;
  aspect-ratio: 21 / 16;
}

#trafficCanvas.dragging {
  cursor: grabbing;
}

#status-message {
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 20px;
  min-height: 24px;
  transition: color 0.2s;
}

.victory-panel {
  margin-top: 18px;
  padding: 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #ecfccb 0%, #d9f99d 100%);
  border: 1px solid #bbf7d0;
  text-align: left;
  animation: victory-pop 0.35s ease-out;
}

.victory-message {
  margin: 0 0 14px 0;
  color: #065f46;
  font-weight: 600;
  line-height: 1.4;
}

.victory-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.victory-enter,
.victory-replay {
  border: none;
  border-radius: 999px;
  padding: 10px 18px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.2s ease, background-color 0.2s ease;
  min-width: 140px;
  max-width: 240px;
  width: auto;
  flex: 0 1 auto;
}

.victory-enter {
  background-color: #047857;
  color: #f0fdf4;
  box-shadow: 0 8px 20px rgba(4, 120, 87, 0.25);
}

.victory-enter:hover {
  transform: translateY(-1px);
  background-color: #059669;
}

.victory-replay {
  background-color: #fff;
  color: #1d4ed8;
  border: 2px solid #bfdbfe;
}

.victory-replay:hover {
  transform: translateY(-1px);
  background-color: #eff6ff;
}

@keyframes victory-pop {
  0% {
    opacity: 0;
    transform: scale(0.9);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

.success {
  color: #16a34a;
}

.error {
  color: #dc2626;
}

.warning {
  color: #f59e0b;
}

:global(.global-confetti-canvas) {
  pointer-events: none;
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9999;
}

@media (max-width: 640px) {
  .captcha-page {
    justify-content: flex-start;
  }

  .captcha-container {
    padding: 20px;
  }

  h2 {
    font-size: 1.3rem;
  }

  #challenge-text {
    font-size: 1rem;
  }

  #status-message {
    font-size: 1rem;
  }

  .difficulty-options {
    flex-direction: row;
    justify-content: center;
    gap: 8px;
  }

  .difficulty-option {
    flex: 0 1 90px;
    min-width: 80px;
    max-width: 110px;
    padding: 8px 10px;
  }

  .difficulty-name {
    font-size: 0.9rem;
  }

  .victory-actions {
    flex-direction: column;
    align-items: center;
  }

  .victory-enter,
  .victory-replay {
    width: auto;
    min-width: 0;
    max-width: 140px;
    padding: 9px 12px;
    font-size: 0.85rem;
    text-align: center;
  }

}

@media (max-width: 420px) {
  .captcha-page {
    justify-content: flex-start;
  }

  .captcha-container {
    padding: 16px;
  }

  h2 {
    font-size: 1.1rem;
  }

  #challenge-text,
  #status-message {
    font-size: 0.95rem;
  }
}
</style>
