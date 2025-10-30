<template>
  <div class="monitoring-view">
    <v-card class="auth-card">
      <v-card-text>
        <div class="auth-heading">Email Monitoring Reports</div>
        <template v-if="!authStore.isAuthenticated">
          <p class="auth-description">
            Sign in with your email to subscribe to daily monitoring summaries. We will email you a link—no password required.
          </p>
          <v-text-field
            v-model="emailInput"
            label="Email address"
            type="email"
            density="comfortable"
            variant="outlined"
            autocomplete="email"
            :disabled="isSendingLink || verifyingToken"
            class="mb-3"
          />
          <div class="auth-actions">
            <v-btn
              color="primary"
              :loading="isSendingLink"
              :disabled="isSendingLink || verifyingToken"
              @click="sendLoginLink"
            >
              Send Sign-In Link
            </v-btn>
            <v-progress-circular
              v-if="verifyingToken"
              indeterminate
              size="22"
              class="ml-3"
            ></v-progress-circular>
          </div>
          <v-alert
            v-if="loginMessage"
            type="success"
            variant="tonal"
            class="mt-3"
          >
            {{ loginMessage }}
          </v-alert>
          <v-alert
            v-if="loginError"
            type="error"
            variant="tonal"
            class="mt-3"
          >
            {{ loginError }}
          </v-alert>
        </template>
        <template v-else>
          <p class="auth-description">
            Signed in as <strong>{{ authStore.email }}</strong>. We'll use your current filter selections when sending reports.
          </p>
          <div class="auth-status-row">
            <v-chip
              v-if="authStore.subscribed"
              size="small"
              color="success"
              variant="tonal"
            >
              Subscribed to daily alerts
            </v-chip>
            <v-chip
              v-else
              size="small"
              color="warning"
              variant="tonal"
            >
              Not currently subscribed
            </v-chip>
          </div>
          <div class="auth-actions mt-3">
            <v-btn
              color="primary"
              :loading="isSavingSubscription"
              :disabled="isSavingSubscription || verifyingToken"
              @click="subscribeToReport"
            >
              {{ authStore.subscribed ? 'Update Subscription' : 'Subscribe' }}
            </v-btn>
            <v-btn
              color="secondary"
              variant="outlined"
              :loading="isSendingTestEmail"
              :disabled="isSendingTestEmail || verifyingToken"
              @click="sendTestEmail"
            >
              Send Test Email
            </v-btn>
            <v-btn
              color="error"
              variant="text"
              :disabled="!authStore.subscribed || isSavingSubscription || verifyingToken"
              @click="unsubscribeFromReport"
            >
              Unsubscribe
            </v-btn>
          </div>
          <v-alert
            v-if="verifyingToken"
            type="info"
            variant="outlined"
            class="mt-3"
          >
            Completing sign-in&hellip;
          </v-alert>
          <v-alert
            v-if="subscriptionMessage"
            type="success"
            variant="tonal"
            class="mt-3"
          >
            {{ subscriptionMessage }}
          </v-alert>
          <v-alert
            v-if="subscriptionError"
            type="error"
            variant="tonal"
            class="mt-3"
          >
            {{ subscriptionError }}
          </v-alert>
        </template>
      </v-card-text>
    </v-card>
    <div class="toolbar">
      <v-btn
        color="primary"
        class="export-btn"
        size="large"
        :loading="isExporting"
        :disabled="loading || charts.length === 0"
        @click="exportToPdf"
      >
        <v-icon left>mdi-file-pdf-box</v-icon>
        Export PDF
      </v-btn>
    </div>

    <v-alert
      v-if="exportError"
      type="error"
      variant="tonal"
      class="mb-3"
    >
      {{ exportError }}
    </v-alert>

    <div ref="reportRef" class="report-surface">
      <v-card class="mb-3 summary-card pdf-section">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          <div class="d-flex align-center">
            <v-icon left>mdi-monitor-dashboard</v-icon>
            <span>Monitoring Report</span>
          </div>
          <v-spacer></v-spacer>
          <span class="text-caption text-medium-emphasis" v-if="lastUpdatedLabel">
            Last updated {{ lastUpdatedLabel }}
          </span>
        </v-card-title>
        <v-card-subtitle class="py-0">
          Changepoints detected on {{ monitoringDateLabel }}. Filters apply to signals, maintained by, approach, valid geometry, and percent change thresholds.
        </v-card-subtitle>
        <v-card-text class="pt-3 pb-4">
          <div class="summary-row">
            <div><strong>Signals:</strong> {{ signalSummary }}</div>
            <div><strong>Maintained By:</strong> {{ maintainedByLabel }}</div>
            <div><strong>Approach:</strong> {{ approachLabel }}</div>
            <div><strong>Valid Geometry:</strong> {{ validGeometryLabel }}</div>
            <div><strong>Percent Change:</strong> {{ percentChangeLabel }}</div>
          </div>
        </v-card-text>
      </v-card>

      <v-alert
        v-if="error"
        type="error"
        variant="outlined"
        class="mb-3"
      >
        {{ error }}
      </v-alert>

      <div v-if="loading" class="d-flex justify-center py-10">
        <v-progress-circular indeterminate size="64"></v-progress-circular>
      </div>

      <div v-else-if="charts.length === 0" class="d-flex justify-center py-10">
        <span class="text-medium-emphasis">
          No changepoints matched the selected filters for {{ monitoringDateLabel }}.
        </span>
      </div>

      <div v-else class="monitoring-grid">
        <v-card
          v-for="item in charts"
          :key="item.key"
          class="chart-card pdf-section"
        >
          <v-card-title class="py-2">
            <div class="title-block">
              <div class="headline">
                <span class="text-subtitle-1 font-weight-medium">XD {{ item.meta.xd }}</span>
                <v-chip
                  size="small"
                  class="ml-2"
                  :color="item.meta.pctChange > 0 ? 'error' : (item.meta.pctChange < 0 ? 'success' : 'info')"
                  variant="tonal"
                >
                  {{ formatPercent(item.meta.pctChange) }}
                </v-chip>
              </div>
              <div class="meta-line text-body-2 text-medium-emphasis">
                <span class="meta-item">{{ item.meta.roadName || 'Unknown road' }}</span>
                <span class="meta-separator" aria-hidden="true">&bull;</span>
                <span class="meta-item">{{ formatTimestamp(item.meta.timestamp) }}</span>
              </div>
            </div>
          </v-card-title>
          <v-card-text class="pt-0">
            <div class="metrics-row">
              <div class="metric">
                <span class="metric-label">Avg Before</span>
                <span class="metric-value">{{ formatSeconds(item.meta.avgBefore) }}</span>
              </div>
              <div class="metric">
                <span class="metric-label">Avg After</span>
                <span class="metric-value">{{ formatSeconds(item.meta.avgAfter) }}</span>
              </div>
              <div class="metric">
                <span class="metric-label">Avg Delta</span>
                <span class="metric-value">{{ formatSeconds(item.meta.avgDiff) }}</span>
              </div>
            </div>
            <div class="chart-stack">
              <div class="chart-section">
                <div class="chart-heading">Daily Travel Time Trend</div>
                <div class="chart-wrapper primary">
                  <ChangepointDetailChart
                    :series="item.dateSeries"
                    :show-legend="true"
                    :show-title="false"
                  />
                </div>
              </div>
              <div class="chart-section">
                <div class="chart-heading">Time of Day Profile</div>
                <div class="chart-wrapper secondary">
                  <ChangepointDetailChart
                    :series="item.timeOfDaySeries"
                    :is-time-of-day="true"
                    :show-legend="false"
                    :show-title="false"
                  />
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ApiService from '@/services/api'
import ChangepointDetailChart from '@/components/ChangepointDetailChart.vue'
import { useFiltersStore } from '@/stores/filters'
import { useAuthStore } from '@/stores/auth'
import {
  buildChangepointDateSeries,
  buildChangepointTimeOfDaySeries,
  normalizeChangepointDetailRow
} from '@/utils/changepointSeries'
import { getMonitoringDateStrings } from '@/utils/monitoringDate'

const filtersStore = useFiltersStore()
const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const emailInput = ref('')
const loginMessage = ref('')
const loginError = ref('')
const subscriptionMessage = ref('')
const subscriptionError = ref('')
const isSendingLink = ref(false)
const isSavingSubscription = ref(false)
const isSendingTestEmail = ref(false)
const verifyingToken = ref(false)

const reportRef = ref(null)
const loading = ref(false)
const isExporting = ref(false)
const exportError = ref(null)
const error = ref(null)
const charts = ref([])
const lastUpdated = ref(null)
let requestId = 0

const monitoringDateStrings = computed(() => getMonitoringDateStrings())
const monitoringDateLabel = computed(() => `${monitoringDateStrings.value.start} to ${monitoringDateStrings.value.end}`)
const lastUpdatedLabel = computed(() => lastUpdated.value ? lastUpdated.value.toLocaleString() : '')

const signalSummary = computed(() => {
  const count = filtersStore.selectedSignalIds?.length ?? 0
  return count > 0 ? `${count} selected` : 'All signals'
})

const maintainedByLabel = computed(() => {
  const value = filtersStore.maintainedBy
  if (!value || value === 'all') return 'All'
  if (value === 'odot') return 'ODOT Only'
  return 'Other Agencies'
})

const approachLabel = computed(() => {
  const value = filtersStore.approach
  if (value === true) return 'True'
  if (value === false) return 'False'
  return 'All'
})

const validGeometryLabel = computed(() => {
  const value = filtersStore.validGeometry
  if (value === 'valid') return 'Valid Only'
  if (value === 'invalid') return 'Invalid Only'
  return 'All'
})

const percentChangeLabel = computed(() => {
  const improve = Number(filtersStore.pctChangeImprovement ?? 0)
  const degrade = Number(filtersStore.pctChangeDegradation ?? 0)
  const improveText = improve > 0 ? `<= -${improve.toFixed(1)}%` : '<= 0%'
  const degradeText = degrade > 0 ? `>= +${degrade.toFixed(1)}%` : '>= 0%'
  return `${improveText} / ${degradeText}`
})

const filterSignature = computed(() => JSON.stringify({
  signals: (filtersStore.selectedSignalIds || []).slice().sort(),
  maintainedBy: filtersStore.maintainedBy,
  approach: filtersStore.approach,
  validGeometry: filtersStore.validGeometry,
  pctImprove: filtersStore.pctChangeImprovement,
  pctDegrade: filtersStore.pctChangeDegradation
}))

watch(filterSignature, () => {
  void loadReport()
}, { immediate: true })

watch(() => authStore.email, (value) => {
  if (typeof value === 'string' && value.length > 0) {
    emailInput.value = value
  }
})

onMounted(async () => {
  await authStore.fetchSession()
  if (authStore.email) {
    emailInput.value = authStore.email
    if (authStore.subscribed) {
      subscriptionMessage.value = 'Subscription active. Reports are sent at 6:00 AM when alerts are detected.'
    }
  }

  const tokenParam = route.query.loginToken
  if (typeof tokenParam === 'string' && tokenParam.trim().length > 0) {
    verifyingToken.value = true
    try {
      const session = await authStore.verifyToken(tokenParam.trim())
      loginMessage.value = `Signed in as ${session.email}`
      loginError.value = ''
    } catch (err) {
      console.error('Failed to verify login token:', err)
      loginError.value = err instanceof Error ? err.message : 'Login link is invalid or expired.'
      loginMessage.value = ''
    } finally {
      verifyingToken.value = false
      const nextQuery = { ...route.query }
      delete nextQuery.loginToken
      void router.replace({ query: nextQuery })
    }
  }
})

function isValidEmail(value) {
  return typeof value === 'string' && /\S+@\S+\.\S+/.test(value)
}

function buildSubscriptionSettings() {
  const params = buildRequestParams()
  if (Array.isArray(params.signal_ids) && params.signal_ids.length > 0) {
    params.selected_signals = params.signal_ids.slice()
  }
  return params
}

async function sendLoginLink() {
  loginMessage.value = ''
  loginError.value = ''

  if (!isValidEmail(emailInput.value)) {
    loginError.value = 'Enter a valid email address.'
    return
  }

  isSendingLink.value = true
  try {
    await authStore.requestLoginLink(emailInput.value.trim())
    loginMessage.value = 'Check your inbox for a sign-in link.'
  } catch (err) {
    console.error('Failed to send login email:', err)
    loginError.value = err instanceof Error ? err.message : 'Failed to send login email.'
  } finally {
    isSendingLink.value = false
  }
}

async function subscribeToReport() {
  subscriptionMessage.value = ''
  subscriptionError.value = ''
  isSavingSubscription.value = true

  try {
    await authStore.subscribe(buildSubscriptionSettings())
    subscriptionMessage.value = 'Subscription saved. We will email reports at 6:00 AM when alerts are detected.'
  } catch (err) {
    console.error('Failed to save subscription:', err)
    subscriptionError.value = err instanceof Error ? err.message : 'Failed to save subscription.'
  } finally {
    isSavingSubscription.value = false
  }
}

async function unsubscribeFromReport() {
  subscriptionMessage.value = ''
  subscriptionError.value = ''
  isSavingSubscription.value = true

  try {
    await authStore.unsubscribe()
    subscriptionMessage.value = 'You have been unsubscribed from monitoring emails.'
  } catch (err) {
    console.error('Failed to unsubscribe:', err)
    subscriptionError.value = err instanceof Error ? err.message : 'Failed to unsubscribe.'
  } finally {
    isSavingSubscription.value = false
  }
}

async function sendTestEmail() {
  subscriptionMessage.value = ''
  subscriptionError.value = ''
  isSendingTestEmail.value = true

  try {
    const result = await authStore.sendTestEmail(buildSubscriptionSettings())
    if (result && result.message && result.message.includes('No changepoints')) {
      subscriptionMessage.value = result.message
    } else {
      subscriptionMessage.value = 'Test email sent. Check your inbox for the PDF report.'
    }
  } catch (err) {
    console.error('Failed to send test email:', err)
    subscriptionError.value = err instanceof Error ? err.message : 'Failed to send test email.'
  } finally {
    isSendingTestEmail.value = false
  }
}

async function loadReport() {
  const currentRequest = ++requestId
  loading.value = true
  error.value = null

  try {
    const params = buildRequestParams()
    const table = await ApiService.getChangepointTable(params)
    const rows = ApiService.arrowTableToObjects(table)
    const topRows = rows.slice(0, 10)

    const nextCharts = []

    for (const row of topRows) {
      const meta = normalizeTableRow(row)

      try {
        const detailTable = await ApiService.getChangepointDetail({
          xd: meta.xd,
          timestamp: meta.timestamp
        })
        const detailRows = ApiService
          .arrowTableToObjects(detailTable)
          .map(normalizeChangepointDetailRow)

        nextCharts.push({
          key: `${meta.xd}-${meta.timestamp}`,
          meta,
          dateSeries: buildChangepointDateSeries(detailRows),
          timeOfDaySeries: buildChangepointTimeOfDaySeries(detailRows),
        })
      } catch (detailErr) {
        console.error('Failed to load changepoint detail for monitoring view:', detailErr)
      }
    }

    if (currentRequest !== requestId) {
      return
    }

    charts.value = nextCharts
    lastUpdated.value = new Date()
  } catch (err) {
    if (currentRequest !== requestId) {
      return
    }
    console.error('Failed to load monitoring report:', err)
    error.value = err instanceof Error ? err.message : String(err)
    charts.value = []
  } finally {
    if (currentRequest === requestId) {
      loading.value = false
    }
  }
}

async function exportToPdf() {
  if (!reportRef.value) {
    return
  }

  exportError.value = null
  isExporting.value = true

  const rootElement = reportRef.value
  const previousScrollY = window.scrollY

  rootElement.classList.add('pdf-exporting')

  try {
    await nextTick()

    const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
      import('html2canvas'),
      import('jspdf')
    ])

    window.scrollTo(0, 0)

    const bodyStyle = getComputedStyle(document.body)
    const exportBackground = bodyStyle.backgroundColor || '#ffffff'

    const sections = Array
      .from(rootElement.querySelectorAll('.pdf-section'))
      .filter((section) => section.offsetParent !== null)

    if (sections.length === 0) {
      throw new Error('No report content available to export.')
    }

    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'pt',
      format: 'a4'
    })

    const margin = 28
    const footerHeight = 42
    const sectionSpacing = 18

    const pageSize = pdf.internal.pageSize
    const pageWidth = pageSize.getWidth()
    const pageHeight = pageSize.getHeight()
    const maxContentWidth = pageWidth - margin * 2
    const maxContentHeight = pageHeight - margin - footerHeight

    let cursorY = margin

    for (const section of sections) {
      const canvas = await html2canvas(section, {
        scale: window.devicePixelRatio > 1 ? 2 : 1.5,
        backgroundColor: exportBackground,
        useCORS: true,
        scrollX: 0,
        scrollY: 0
      })

      const naturalWidth = canvas.width
      const naturalHeight = canvas.height

      if (!naturalWidth || !naturalHeight) {
        continue
      }

      const widthScale = maxContentWidth / naturalWidth
      const heightScale = maxContentHeight / naturalHeight
      const scale = Math.min(widthScale, heightScale, 1)

      const renderWidth = naturalWidth * scale
      const renderHeight = naturalHeight * scale

      if (cursorY + renderHeight > pageHeight - footerHeight) {
        pdf.addPage()
        cursorY = margin
      }

      const offsetX = margin + (maxContentWidth - renderWidth) / 2
      const imageData = canvas.toDataURL('image/png')

      pdf.addImage(imageData, 'PNG', offsetX, cursorY, renderWidth, renderHeight, undefined, 'FAST')

      cursorY += renderHeight + sectionSpacing
    }

    const totalPages = pdf.internal.getNumberOfPages()
    const dateStamp = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date())

    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(9)
    pdf.setTextColor(102, 102, 102)
    pdf.setDrawColor(200, 200, 200)
    pdf.setLineWidth(0.5)

    for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) {
      pdf.setPage(pageNumber)
      const size = pdf.internal.pageSize
      const width = size.getWidth()
      const height = size.getHeight()
      const footerTop = height - footerHeight + 12
      const footerTextY = height - margin / 2

      pdf.line(margin, footerTop, width - margin, footerTop)
      pdf.text(dateStamp, margin, footerTextY)
      pdf.text(`Page ${pageNumber} / ${totalPages}`, width - margin, footerTextY, { align: 'right' })
    }

    const filename = `monitoring-report-${monitoringDateStrings.value.start}.pdf`
    pdf.save(filename)
  } catch (err) {
    console.error('Failed to export monitoring PDF:', err)
    if (err instanceof Error && err.message === 'No report content available to export.') {
      exportError.value = 'There is no report content to export right now.'
    } else {
      exportError.value = 'Failed to export report. Please try again.'
    }
  } finally {
    rootElement.classList.remove('pdf-exporting')
    window.scrollTo(0, previousScrollY)
    isExporting.value = false
  }
}

function buildRequestParams() {
  const params = {
    start_date: monitoringDateStrings.value.start,
    end_date: monitoringDateStrings.value.end,
    pct_change_improvement: Number(filtersStore.pctChangeImprovement ?? 0) / 100,
    pct_change_degradation: Number(filtersStore.pctChangeDegradation ?? 0) / 100,
    sort_by: 'pct_change',
    sort_dir: 'desc'
  }

  if (Array.isArray(filtersStore.selectedSignalIds) && filtersStore.selectedSignalIds.length > 0) {
    params.signal_ids = filtersStore.selectedSignalIds.slice()
    params.selected_signals = filtersStore.selectedSignalIds.slice()
  }

  if (filtersStore.approach !== null && filtersStore.approach !== undefined) {
    params.approach = filtersStore.approach
  }

  if (filtersStore.validGeometry && filtersStore.validGeometry !== 'all') {
    params.valid_geometry = filtersStore.validGeometry
  }

  if (filtersStore.maintainedBy && filtersStore.maintainedBy !== 'all') {
    params.maintained_by = filtersStore.maintainedBy
  }

  return params
}

function normalizeTableRow(row) {
  return {
    xd: Number(row.XD ?? row.xd ?? 0),
    timestamp: row.TIMESTAMP ?? row.timestamp ?? null,
    pctChange: Number(row.PCT_CHANGE ?? row.pct_change ?? 0),
    avgDiff: Number(row.AVG_DIFF ?? row.avg_diff ?? 0),
    avgBefore: Number(row.AVG_BEFORE ?? row.avg_before ?? 0),
    avgAfter: Number(row.AVG_AFTER ?? row.avg_after ?? 0),
    roadName: row.ROADNAME ?? row.road_name ?? '',
    bearing: row.BEARING ?? row.bearing ?? ''
  }
}

function formatTimestamp(value) {
  if (!value) {
    return '--'
  }
  return new Date(value).toLocaleString()
}

function formatPercent(value) {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatSeconds(value) {
  if (value === null || value === undefined) {
    return '--'
  }
  return `${Number(value).toFixed(1)} s`
}
</script>

<style scoped>
.monitoring-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.auth-card {
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.auth-heading {
  font-weight: 600;
  font-size: 1.1rem;
  margin-bottom: 4px;
}

.auth-description {
  margin-bottom: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.auth-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.auth-status-row {
  margin-top: 4px;
}

.toolbar {
  display: flex;
  justify-content: flex-end;
}

.report-surface {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1120px;
  margin: 0 auto 24px;
}

.summary-card {
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  font-size: 0.9rem;
}

.monitoring-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 20px;
}

.chart-card {
  display: flex;
  flex-direction: column;
  break-inside: avoid;
}

.title-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.headline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.meta-item {
  color: inherit;
}

.meta-separator {
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background-color: rgba(var(--v-theme-on-surface), 0.03);
}

.metric-label {
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.metric-value {
  font-size: 1.05rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}

.chart-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chart-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chart-heading {
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.chart-wrapper {
  height: 260px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background-color: rgb(var(--v-theme-surface));
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.05);
}

.chart-wrapper.secondary {
  height: 220px;
}

.report-surface.pdf-exporting {
  gap: 24px;
}

.report-surface.pdf-exporting .monitoring-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.report-surface.pdf-exporting .chart-card {
  max-width: none;
  break-inside: avoid;
}

.report-surface.pdf-exporting .chart-wrapper {
  box-shadow: none;
}

@media (max-width: 600px) {
  .monitoring-grid {
    grid-template-columns: 1fr;
  }

  .metric {
    padding: 8px 10px;
  }

  .chart-wrapper {
    height: 220px;
    padding: 10px;
  }

  .chart-wrapper.secondary {
    height: 200px;
  }
}
</style>
