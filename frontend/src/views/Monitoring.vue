<template>
  <div class="monitoring-view">
    <v-card class="auth-card">
      <v-card-text>
        <div class="auth-heading">Email Monitoring Reports</div>
        <template v-if="!authStore.isAuthenticated">
          <p class="auth-description">
            Sign in with your public agency email to subscribe to daily monitoring summaries. You can request up to three sign-in links per day—we will email you a link, no password required.
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
              v-if="verifyingToken && showVerifyingSpinner"
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
            Signed in as <strong>{{ authStore.email }}</strong>. We'll use your saved subscription when sending reports. Adjust the filters on this page, then click <em>{{ authStore.subscribed ? 'Update Subscription' : 'Subscribe' }}</em> to store those selections in your subscription.
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
    <div class="report-surface">
      <v-alert
        v-if="algorithmNotes.length > 0"
        type="warning"
        variant="tonal"
        prominent
        icon="mdi-alert-outline"
        class="algorithm-change-alert"
        data-testid="monitoring-algorithm-change"
      >
        <div class="font-weight-bold mb-1">INRIX algorithm change</div>
        <p v-for="(note, index) in algorithmNotes" :key="index" class="mb-1">{{ note }}</p>
      </v-alert>
      <v-card class="mb-3 summary-card">
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
          Preview of today's emailed report with these filters.
        </v-card-subtitle>
        <v-card-text class="pt-3 pb-4">
          <div class="summary-row">
            <div><strong>Signals:</strong> {{ signalSummary }}</div>
            <div><strong>Maintained By:</strong> {{ maintainedByLabel }}</div>
            <div><strong>Approach:</strong> {{ approachLabel }}</div>
            <div><strong>Valid Geometry:</strong> {{ validGeometryLabel }}</div>
            <div><strong>Monitoring Score Threshold:</strong> >= {{ anomalyThresholdLabel }}</div>
            <div><strong>Changepoint Severity Threshold:</strong> >= {{ changepointSeverityLabel }}</div>
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
        <v-progress-circular
          v-if="showReportSpinner"
          indeterminate
          size="64"
        ></v-progress-circular>
      </div>

      <div v-else class="report-sections">
        <section class="report-section">
          <div class="section-header">
            <div class="section-title">Yesterday&apos;s Anomalies</div>
            <div class="section-subtitle">
              Travel times well above forecast on {{ anomalyTargetLabel }} (score >= {{ anomalyThresholdLabel }}).
            </div>
          </div>
          <div v-if="anomalyCards.length === 0" class="empty-state text-medium-emphasis">
            {{ excludedText.anomalies || 'None matched your filters.' }}
          </div>
          <div v-else class="monitoring-grid anomaly-grid">
            <v-card
              v-for="item in anomalyCards"
              :key="item.key"
              class="chart-card anomaly-card"
            >
              <v-card-title class="py-2 anomaly-card-title">
                <div class="title-block">
                  <div class="headline anomaly-headline">
                    <span class="text-subtitle-1 font-weight-medium">
                      XD {{ item.meta.xd }} | {{ item.meta.roadName || 'Unknown road' }}<span v-if="item.meta.bearing"> ({{ item.meta.bearing }})</span>
                    </span>
                  </div>
                  <div class="meta-line text-body-2 text-medium-emphasis">
                    <span class="meta-item">Signal(s): {{ item.meta.associatedSignals || '--' }}</span>
                  </div>
                </div>
              </v-card-title>
              <v-card-text class="pt-0 anomaly-card-body">
                <div class="chart-stack">
                  <div class="chart-section">
                    <div class="chart-heading">Time of Day (15-minute)</div>
                    <div class="chart-wrapper anomaly-chart">
                      <AnomalyMonitoringChart :series="item.series" />
                    </div>
                  </div>
                </div>
              </v-card-text>
            </v-card>
          </div>
        </section>

        <section
          v-for="group in changepointGroups"
          :key="group.key"
          class="report-section"
        >
          <div class="section-header">
            <div class="section-title">{{ group.title }}</div>
            <div class="section-subtitle">
              {{ group.subtitle }}
            </div>
          </div>
          <div v-if="group.items.length === 0 && group.reported.length === 0" class="empty-state text-medium-emphasis">
            {{ group.emptyText }}
          </div>
          <div v-else-if="group.items.length > 0" class="monitoring-grid">
            <v-card
              v-for="item in group.items"
              :key="item.key"
              class="chart-card"
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
                    <v-chip
                      size="small"
                      :color="item.meta.isEnduring ? 'primary' : undefined"
                      variant="outlined"
                    >
                      {{ item.meta.isEnduring ? 'Enduring' : 'Changepoint' }}
                    </v-chip>
                  </div>
                  <div class="meta-line text-body-2 text-medium-emphasis">
                    <span class="meta-item">{{ item.meta.roadName || 'Unknown road' }}</span>
                    <span class="meta-separator" aria-hidden="true">&bull;</span>
                    <span class="meta-item">{{ formatTimestamp(item.meta.timestamp) }}</span>
                    <span class="meta-separator" aria-hidden="true">&bull;</span>
                    <span class="meta-item">Associated Signal(s): {{ item.meta.associatedSignals || '--' }}</span>
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
          <div v-if="group.reported.length > 0" class="reported-table" data-testid="enduring-reported-table">
            <div class="chart-heading mb-2">Already reported, still present</div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Road</th>
                  <th>XD</th>
                  <th>Signals</th>
                  <th>Changed</th>
                  <th>Before &rarr; After &rarr; Wk 2-3</th>
                  <th class="text-right">Change</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in group.reported" :key="row.key">
                  <td>{{ row.road }}</td>
                  <td><code>{{ row.xd }}</code></td>
                  <td>{{ row.signals }}</td>
                  <td>{{ row.date }}</td>
                  <td>{{ row.travelTimes }}</td>
                  <td class="text-right" :class="row.pctChange > 0 ? 'text-error' : 'text-success'">{{ formatPercent(row.pctChange) }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
  import ApiService from '@/services/api'
  import ChangepointDetailChart from '@/components/ChangepointDetailChart.vue'
  import AnomalyMonitoringChart from '@/components/AnomalyMonitoringChart.vue'
import { useFiltersStore } from '@/stores/filters'
import { useAuthStore } from '@/stores/auth'
import { useDelayedBoolean } from '@/utils/useDelayedBoolean'
import {
  buildChangepointDateSeries,
  buildChangepointTimeOfDaySeries,
  normalizeChangepointDetailRow
} from '@/utils/changepointSeries'
import {
  formatDateRangeLabel,
  getEnduringMonitoringDateStrings,
  getMonitoringDateStrings,
  getMonitoringReportDateString
} from '@/utils/monitoringDate'

// Chart windows (days before/after the change). Enduring changepoints use a longer
// span so the persistence of the shift is visible (mirrors the emailed report).
const NEW_DETAIL_WINDOW = { days_before: 7, days_after: 7 }
const ENDURING_DETAIL_WINDOW = { days_before: 14, days_after: 21 }

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
const loading = ref(false)
const showVerifyingSpinner = useDelayedBoolean(verifyingToken)
const showReportSpinner = useDelayedBoolean(loading)
const error = ref(null)
const charts = ref([])
const enduringCharts = ref([])
const enduringReported = ref([]) // enduring changepoints already reported as new (table, no charts)
const anomalyCards = ref([])
  const anomalyMetadata = ref({
    targetDate: null,
    generatedAt: null,
    threshold: filtersStore.anomalyMonitoringThreshold
  })
  const lastUpdated = ref(null)
  let requestId = 0

// Same windows as the emailed report for report date R (today): anomalies R-1,
// new changepoints R-9, enduring changepoints R-22 (single days).
const reportDateString = computed(() => getMonitoringReportDateString())
const monitoringDateStrings = computed(() => getMonitoringDateStrings())
  const monitoringDateLabel = computed(() => formatDateRangeLabel(monitoringDateStrings.value))
  const enduringDateStrings = computed(() => getEnduringMonitoringDateStrings())
  const enduringDateLabel = computed(() => formatDateRangeLabel(enduringDateStrings.value))
// Sections left out because their day falls inside an INRIX algorithm change (from the API,
// so the wording and rules match the PDF/email exactly)
const algorithmImpact = ref({ notes: [], excluded_sections: [], excluded_text: {} })
const algorithmNotes = computed(() => algorithmImpact.value?.notes ?? [])
const excludedText = computed(() => algorithmImpact.value?.excluded_text ?? {})
  const lastUpdatedLabel = computed(() => lastUpdated.value ? lastUpdated.value.toLocaleString() : '')
  const anomalyThreshold = computed(() => {
    const metadataValue = Number(anomalyMetadata.value?.threshold)
    const storeValue = Number(filtersStore.anomalyMonitoringThreshold ?? 4)
    if (Number.isFinite(metadataValue) && metadataValue > 0) {
      return metadataValue
    }
    return Number.isFinite(storeValue) ? storeValue : 4
  })
  const anomalyThresholdLabel = computed(() => anomalyThreshold.value.toFixed(1))
  const changepointSeverityThreshold = computed(() => {
    const storeValue = Number(filtersStore.changepointSeverityThreshold ?? 0)
    return Number.isFinite(storeValue) ? Math.max(0, storeValue) : 0
  })
  const changepointSeverityLabel = computed(() => changepointSeverityThreshold.value.toFixed(1))
  const anomalyTargetLabel = computed(() => {
    const target = anomalyMetadata.value?.targetDate
    if (!target) {
      return 'yesterday'
    }
    const parsed = new Date(target)
    if (Number.isNaN(parsed.getTime())) {
      return String(target)
    }
    return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  })

const changepointGroups = computed(() => [
  {
    key: 'new',
    title: 'New Changepoints',
    subtitle: `Started ${monitoringDateLabel.value} (severity >= ${changepointSeverityLabel.value}); some may turn out to be temporary.`,
    emptyText: excludedText.value.new || 'None matched your filters.',
    reported: [],
    items: charts.value
  },
  {
    key: 'enduring',
    title: 'Enduring Changepoints',
    subtitle: `Started ${enduringDateLabel.value}, still present ~3 weeks later; charts show ones not reported before.`,
    emptyText: excludedText.value.enduring || 'None matched your filters.',
    reported: enduringReported.value,
    items: enduringCharts.value
  }
])

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

const filterSignature = computed(() => JSON.stringify({
  signals: (filtersStore.selectedSignalIds || []).slice().sort(),
  maintainedBy: filtersStore.maintainedBy,
  approach: filtersStore.approach,
  validGeometry: filtersStore.validGeometry,
  monitoringScore: filtersStore.anomalyMonitoringThreshold,
  severity: filtersStore.changepointSeverityThreshold
}))

watch(filterSignature, () => {
  void loadReport()
}, { immediate: true })

watch(() => authStore.email, (value) => {
  if (typeof value === 'string' && value.length > 0) {
    emailInput.value = value
  }
})

const PUBLIC_AGENCY_SUFFIXES = ['.gov', '.us']
const PUBLIC_AGENCY_EXCEPTIONS = new Set(['cityofsalem.net', 'cityofmedford.org'])

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
  if (typeof value !== 'string') return false

  const trimmed = value.trim()
  if (trimmed.length === 0) return false
  const basicPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!basicPattern.test(trimmed)) return false

  const normalized = trimmed.toLowerCase()
  const parts = normalized.split('@')
  const domain = parts[parts.length - 1] || ''
  if (domain.length === 0) return false

  const hasAllowedSuffix = PUBLIC_AGENCY_SUFFIXES.some((suffix) => domain.endsWith(suffix))
  return hasAllowedSuffix || PUBLIC_AGENCY_EXCEPTIONS.has(domain)
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
    loginError.value = 'Enter a valid public agency email address.'
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
  anomalyCards.value = []

  try {
    let impact = { notes: [], excluded_sections: [], excluded_text: {} }
    try {
      impact = await ApiService.getAlgorithmChangeReportImpact(reportDateString.value) ?? impact
    } catch (impactErr) {
      console.warn('Algorithm change check unavailable for monitoring view:', impactErr)
    }
    if (currentRequest !== requestId) {
      return
    }
    algorithmImpact.value = impact
    const excluded = new Set(impact?.excluded_sections ?? [])
    const emptyTable = { numRows: 0, schema: { fields: [] }, getChild: () => null }

    const params = buildRequestParams()
    const newParams = { ...params, changepoint_type: 'new' }
    const enduringParams = {
      ...params,
      start_date: enduringDateStrings.value.start,
      end_date: enduringDateStrings.value.end,
      // Only enduring changepoints that were not alerted earlier (matches the emailed report)
      changepoint_type: 'enduring_unreported'
    }
    const reportedParams = { ...enduringParams, changepoint_type: 'enduring_reported' }
    const [anomalyResult, changepointResult, enduringResult, reportedResult] = await Promise.allSettled([
      excluded.has('anomalies')
        ? Promise.resolve({ anomalies: [], target_date: null, threshold: params.anomaly_monitoring_threshold })
        : ApiService.getMonitoringAnomalies({ ...params, report_date: reportDateString.value }),
      excluded.has('new') ? Promise.resolve(emptyTable) : ApiService.getChangepointTable(newParams),
      excluded.has('enduring') ? Promise.resolve(emptyTable) : ApiService.getChangepointTable(enduringParams),
      excluded.has('enduring') ? Promise.resolve(emptyTable) : ApiService.getChangepointTable(reportedParams)
    ])

    if (currentRequest !== requestId) {
      return
    }

    if (anomalyResult.status === 'fulfilled' && anomalyResult.value) {
      const response = anomalyResult.value
      const responseThreshold = Number(response.threshold)
      anomalyMetadata.value = {
        targetDate: response.target_date ?? null,
        generatedAt: response.generated_at ?? null,
        threshold: Number.isFinite(responseThreshold) ? responseThreshold : filtersStore.anomalyMonitoringThreshold
      }
      const normalized = Array.isArray(response.anomalies)
        ? response.anomalies.map(normalizeAnomalyRow)
        : []
      anomalyCards.value = normalized.map(item => ({
        key: `anomaly-${item.xd}`,
        meta: item,
        series: item.series
      }))
    } else {
      anomalyMetadata.value = {
        targetDate: null,
        generatedAt: null,
        threshold: filtersStore.anomalyMonitoringThreshold
      }
      if (anomalyResult.status === 'rejected') {
        console.error('Failed to load monitoring anomalies:', anomalyResult.reason)
      }
    }

    if (changepointResult.status !== 'fulfilled') {
      throw changepointResult.reason ?? new Error('Failed to load changepoint table')
    }

    let enduringRows = []
    if (enduringResult.status === 'fulfilled') {
      enduringRows = ApiService.arrowTableToObjects(enduringResult.value)
    } else {
      console.error('Failed to load enduring changepoints for monitoring view:', enduringResult.reason)
    }

    let reportedRows = []
    if (reportedResult.status === 'fulfilled') {
      reportedRows = ApiService.arrowTableToObjects(reportedResult.value)
    } else {
      console.error('Failed to load reported enduring changepoints for monitoring view:', reportedResult.reason)
    }

    const newRows = ApiService.arrowTableToObjects(changepointResult.value)
    const [nextCharts, nextEnduringCharts] = await Promise.all([
      buildChangepointCards(newRows.slice(0, 10), NEW_DETAIL_WINDOW),
      buildChangepointCards(enduringRows.slice(0, 10), ENDURING_DETAIL_WINDOW)
    ])

    if (currentRequest !== requestId) {
      return
    }

    enduringCharts.value = nextEnduringCharts
    enduringReported.value = reportedRows.slice(0, 10).map(normalizeReportedRow)
    charts.value = nextCharts
    lastUpdated.value = new Date()
  } catch (err) {
    if (currentRequest !== requestId) {
      return
    }
    console.error('Failed to load monitoring report:', err)
    error.value = err instanceof Error ? err.message : String(err)
    charts.value = []
    enduringCharts.value = []
    enduringReported.value = []
  } finally {
    if (currentRequest === requestId) {
      loading.value = false
    }
  }
}

// Load detail series for each changepoint row (sequentially, as before) and build chart cards.
async function buildChangepointCards(rows, detailWindow) {
  const cards = []
  for (const row of rows) {
    const meta = normalizeTableRow(row)

    try {
      const detailTable = await ApiService.getChangepointDetail({
        xd: meta.xd,
        timestamp: meta.timestamp,
        ...detailWindow
      })
      const detailRows = ApiService
        .arrowTableToObjects(detailTable)
        .map(normalizeChangepointDetailRow)

      cards.push({
        key: `${meta.xd}-${meta.timestamp}`,
        meta,
        dateSeries: buildChangepointDateSeries(detailRows),
        timeOfDaySeries: buildChangepointTimeOfDaySeries(detailRows),
      })
    } catch (detailErr) {
      console.error('Failed to load changepoint detail for monitoring view:', detailErr)
    }
  }
  return cards
}

// PDF export is handled server-side via the monitoring email/report service.

function buildRequestParams() {
  const params = {
    start_date: monitoringDateStrings.value.start,
    end_date: monitoringDateStrings.value.end,
    anomaly_monitoring_threshold: Math.max(0, Number(filtersStore.anomalyMonitoringThreshold ?? 4)),
    changepoint_severity_threshold: Math.max(0, Number(filtersStore.changepointSeverityThreshold ?? 0)),
    sort_by: 'score',
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

function normalizeAnomalyRow(row) {
  const series = Array.isArray(row.time_of_day_series)
    ? row.time_of_day_series
    : (row.TIME_OF_DAY_SERIES ?? [])

  const normalizedSeries = Array.isArray(series)
    ? series.map(point => ({
      minutes: Number(point?.minutes ?? point?.MINUTES ?? 0),
      actual: point?.actual === null || point?.actual === undefined ? null : Number(point.actual ?? point.ACTUAL),
      prediction: point?.prediction === null || point?.prediction === undefined ? null : Number(point.prediction ?? point.PREDICTION)
    }))
    : []

  return {
    xd: Number(row.xd ?? row.XD ?? 0),
    roadName: row.roadname ?? row.ROADNAME ?? '',
    bearing: row.bearing ?? row.BEARING ?? '',
    associatedSignals: row.associated_signals ?? row.ASSOCIATED_SIGNALS ?? '--',
    anomalyRatio: row.anomaly_ratio ?? row.ANOMALY_RATIO ?? null,
    series: normalizedSeries,
    targetDate: row.target_date ?? row.TARGET_DATE ?? null
  }
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
    bearing: row.BEARING ?? row.bearing ?? '',
    associatedSignals: row.ASSOCIATED_SIGNALS ?? row.associated_signals ?? '',
    isEnduring: (row.IS_ENDURING ?? row.is_enduring) === true
  }
}

function normalizeReportedRow(row) {
  const meta = normalizeTableRow(row)
  const travelTimes = [row.BEFORE_TT, row.AFTER_TT, row.ENDURING_TT]
    .map(value => (value === null || value === undefined || !Number.isFinite(Number(value)) ? '--' : Number(value).toFixed(0)))
    .join(' → ')
  return {
    key: `${meta.xd}-${meta.timestamp}`,
    road: meta.bearing ? `${meta.roadName || 'Unknown road'} (${meta.bearing})` : (meta.roadName || 'Unknown road'),
    xd: meta.xd,
    signals: meta.associatedSignals || '--',
    date: meta.timestamp ? new Date(meta.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '--',
    travelTimes: `${travelTimes} s`,
    pctChange: meta.pctChange
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

.reported-table {
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 10px 12px;
  overflow-x: auto;
}

.algorithm-change-alert p:last-child {
  margin-bottom: 0 !important;
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

.report-sections {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.report-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}

.section-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.empty-state {
  text-align: center;
  padding: 28px 12px;
  border-radius: 12px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.2);
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

.anomaly-headline {
  flex-direction: column;
  align-items: flex-start;
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

.chart-wrapper.anomaly-chart {
  height: 240px;
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

  .chart-wrapper.anomaly-chart {
    height: 200px;
  }

  .chart-wrapper.secondary {
    height: 200px;
  }
}
</style>
