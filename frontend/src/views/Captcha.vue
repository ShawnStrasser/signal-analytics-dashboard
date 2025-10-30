<template>
  <div class="captcha-page">
    <div class="captcha-container">
      <h2>Please Verify You're a Human who Likes to Solve Traffic Signal Puzzles</h2>
      <p id="challenge-text">
        <span id="challenge-color" ref="challengeColorRef"></span>
      </p>
      <canvas
        id="trafficCanvas"
        ref="canvasRef"
        width="630"
        height="480"
      ></canvas>
      <div id="status-message" ref="statusMessageRef"></div>
      <button id="reset-button" ref="resetButtonRef" type="button">
        Reset Challenge
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { isCaptchaVerified, setCaptchaVerified } from '../utils/captchaSession'

const canvasRef = ref(null)
const statusMessageRef = ref(null)
const resetButtonRef = ref(null)
const challengeColorRef = ref(null)

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
let detachResetHandler = () => {}
let cancelAnimation = () => {}
let clearRedirectTimer = () => {}

onMounted(() => {
  document.title = "Please Verify You're a Human who Likes to Solve Traffic Signal Puzzles"

  if (isCaptchaVerified()) {
    redirectAfterVerification()
    return
  }

  const canvas = canvasRef.value
  const statusMessageEl = statusMessageRef.value
  const resetButton = resetButtonRef.value
  const challengeColorEl = challengeColorRef.value

  if (!canvas || !statusMessageEl || !resetButton) {
    return
  }

  const ctx = canvas.getContext('2d')
  if (!ctx) {
    return
  }

  const LIGHT_RADIUS = 25
  const PADDING = 20
  const BACKPLATE_MARGIN = 12
  const SLOT_TOP_OFFSET = 55
  const SLOT_GAP = 70
  const BASE_ROTATION_SPEED = 0.02
  const FAST_ROTATION_SPEED = 0.04
  const MOVEMENT_DELAY_MS = 2000
  const BASE_SPIN_TRIGGER_MS = 4000
  const FAST_SPIN_TRIGGER_MS = 9000
  const ESCAPE_TRIGGER_MS = 14000
  const signalSpeedMultiplier = 1.5
  const signalPadding = 10
  const touchOptions = { passive: false }

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
  let verificationRedirectTimer = 0
  let isMovementPending = false
  let movementStartDeadline = 0

  if (challengeColorEl) {
    challengeColorEl.textContent = ''
  }

  function defineComponents() {
    const initialSignalWidth = 90
    const initialSignalHeight = 250
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

    lights = [
      {
        id: 'red',
        x: PADDING + LIGHT_RADIUS + 10,
        y: 100,
        r: LIGHT_RADIUS,
        color: '#ef4444',
        origX: PADDING + LIGHT_RADIUS + 10,
        origY: 100,
        isPlaced: false
      },
      {
        id: 'yellow',
        x: PADDING + LIGHT_RADIUS + 10,
        y: 240,
        r: LIGHT_RADIUS,
        color: '#f59e0b',
        origX: PADDING + LIGHT_RADIUS + 10,
        origY: 240,
        isPlaced: false
      },
      {
        id: 'green',
        x: PADDING + LIGHT_RADIUS + 10,
        y: 380,
        r: LIGHT_RADIUS,
        color: '#22c55e',
        origX: PADDING + LIGHT_RADIUS + 10,
        origY: 380,
        isPlaced: false
      }
    ]
  }

  function drawBackplate() {
    ctx.save()
    const cx = backplate.x + backplate.width / 2
    const cy = backplate.y + backplate.height / 2
    ctx.translate(cx, cy)
    ctx.rotate(signalRotation)

    ctx.fillStyle = backplate.color
    ctx.beginPath()
    ctx.roundRect(-backplate.width / 2, -backplate.height / 2, backplate.width, backplate.height, 12)
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
    ctx.roundRect(-signalHead.width / 2, -signalHead.height / 2, signalHead.width, signalHead.height, 8)
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
      ctx.shadowBlur = light.isPlaced ? 15 : 5
      ctx.fill()

      ctx.beginPath()
      ctx.arc(light.x - 7, light.y - 7, light.r * 0.4, 0, Math.PI * 2)
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
    if (isVerified) {
      return
    }

    const now = Date.now()

    if (!isSignalMoving) {
      if (isMovementPending && now >= movementStartDeadline) {
        isMovementPending = false
        isSignalMoving = true
        gameStartTime = now
        updateStatus('Signal head is moving!', 'warning')
      } else {
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
      currentRotationSpeed = FAST_ROTATION_SPEED
    } else if (elapsedTime >= FAST_SPIN_TRIGGER_MS) {
      if (!fastSpinMessageShown && !hasEscaped) {
        //updateStatus('Rotation Speed Increased!', 'warning')
        fastSpinMessageShown = true
      }
      isSpinning = true
      currentRotationSpeed = FAST_ROTATION_SPEED
    } else if (elapsedTime >= BASE_SPIN_TRIGGER_MS) {
      if (!isSpinning) {
        isSpinning = true
        //updateStatus('Signal is starting to spin!', 'warning')
      }
      currentRotationSpeed = BASE_ROTATION_SPEED
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
      const maxDistance = 200
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
      const maxDistance = 200
      const cy = signalHead.y + signalHead.height / 2
      if (cy < -maxDistance || cy > canvas.height + maxDistance) {
        handleOffPageEscape()
        signalMoveY *= -1
        const targetCy = cy < 0 ? -maxDistance : canvas.height + maxDistance
        signalHead.y = targetCy - signalHead.height / 2
        backplate.y = signalHead.y - BACKPLATE_MARGIN
      }
    }

    const dropZones = getDropZoneCenters()
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
          isMovementPending = true
          movementStartDeadline = Date.now() + MOVEMENT_DELAY_MS
          //updateStatus('Signal head will start moving in a moment...', 'warning')
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
    if (redirected) {
      return
    }
    redirected = true
    setCaptchaVerified()
    clearRedirectTimer()
    verificationRedirectTimer = window.setTimeout(() => {
      redirectAfterVerification()
    }, 600)
    clearRedirectTimer = () => {
      if (verificationRedirectTimer) {
        window.clearTimeout(verificationRedirectTimer)
        verificationRedirectTimer = 0
      }
    }
  }

  function handleSuccessfulPlacement(zone) {
    dragTarget.x = zone.x
    dragTarget.y = zone.y

    placedLights[dragTarget.id] = true
    dragTarget.isPlaced = true

    const allPlaced = Object.values(placedLights).every(status => status === true)

    if (allPlaced) {
      isVerified = true
      isSignalMoving = false
      isSpinning = false
      updateStatus('Configuration Complete! You are Human.', 'success')
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

  function init() {
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
    signalMoveX = 2
    signalMoveY = 2
    isMovementPending = false
    movementStartDeadline = 0
    clearRedirectTimer()
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

  resetButton.addEventListener('click', init)
  detachResetHandler = () => resetButton.removeEventListener('click', init)

  detachCanvasListeners = removeListeners
  cancelAnimation = () => {
    if (animationFrameId) {
      window.cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
  }

  clearRedirectTimer = () => {
    if (verificationRedirectTimer) {
      window.clearTimeout(verificationRedirectTimer)
      verificationRedirectTimer = 0
    }
  }

  animationFrameId = window.requestAnimationFrame(animate)
  init()
})

onBeforeUnmount(() => {
  detachCanvasListeners()
  detachResetHandler()
  cancelAnimation()
  clearRedirectTimer()
})
</script>

<style scoped>
.captcha-page {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  display: grid;
  place-items: center;
  min-height: 100vh;
  background-color: #f3f4f6;
  color: #1f2937;
  margin: 0;
  user-select: none;
  -webkit-user-select: none;
  -ms-user-select: none;
  padding: 16px;
  box-sizing: border-box;
}

.captcha-container {
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
  padding: 28px;
  text-align: center;
  width: 95%;
  max-width: 650px;
  border: 1px solid #e5e7eb;
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

#trafficCanvas {
  background-color: #f9fafb;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  cursor: grab;
  max-width: 100%;
  height: auto;
  width: 630px;
  height: 480px;
}

#trafficCanvas.dragging {
  cursor: grabbing;
}

#status-message {
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 20px;
  height: 24px;
  transition: color 0.2s;
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

#reset-button {
  background-color: #4f46e5;
  color: white;
  border: none;
  padding: 10px 16px;
  font-size: 0.9rem;
  font-weight: 500;
  border-radius: 8px;
  cursor: pointer;
  margin-top: 12px;
  transition: background-color 0.2s ease, transform 0.1s ease;
  box-shadow: 0 4px #3730a3;
}

#reset-button:hover {
  background-color: #4338ca;
}

#reset-button:active {
  transform: translateY(2px);
  box-shadow: 0 2px #3730a3;
}
</style>
