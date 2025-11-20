<template>
  <div class="admin-view">
    <v-card class="mb-6" v-if="!authenticated">
      <v-card-title>Admin Login</v-card-title>
      <v-card-text>
        <p class="text-medium-emphasis mb-4">
          Enter the shared password to unlock the subscriptions database console. Your IP address is limited
          to three attempts every 24 hours.
        </p>
        <v-text-field
          v-model="password"
          :type="showPassword ? 'text' : 'password'"
          label="Admin password"
          autocomplete="current-password"
          variant="outlined"
          prepend-inner-icon="mdi-lock"
          :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
          @click:append-inner="showPassword = !showPassword"
          density="comfortable"
        />
        <v-alert v-if="authError" type="error" variant="tonal" class="mb-4">
          {{ authError }}
        </v-alert>
        <v-btn color="primary" :loading="loginLoading" @click="handleLogin" :disabled="!password.trim()">
          Unlock console
        </v-btn>
      </v-card-text>
    </v-card>

    <template v-else>
      <v-card class="mb-4">
        <v-card-title class="d-flex align-center">
          <span>Available tables</span>
          <v-spacer></v-spacer>
          <v-btn
            icon
            size="small"
            variant="text"
            :loading="tablesLoading"
            @click="loadTables"
          >
            <v-icon>mdi-refresh</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text>
          <div v-if="tablesLoading" class="text-medium-emphasis">
            Loading table metadata...
          </div>
          <v-alert v-else-if="tablesError" type="error" variant="tonal" class="mb-0">
            {{ tablesError }}
          </v-alert>
          <div v-else-if="tables.length === 0" class="text-medium-emphasis">
            No tables found in the subscriptions database.
          </div>
          <div v-else class="table-chip-container">
            <v-chip
              v-for="table in tables"
              :key="table"
              class="ma-1"
              color="primary"
              variant="tonal"
              size="small"
              @click="insertTemplate(table)"
            >
              {{ table }}
            </v-chip>
          </div>
        </v-card-text>
      </v-card>

      <v-card class="mb-6">
        <v-card-title>SQL console</v-card-title>
        <v-card-text>
          <div class="text-medium-emphasis mb-3">
            Only SELECT/WITH/PRAGMA statements are allowed. Results are capped at {{ maxRows }} rows per query.
          </div>
          <v-textarea
            v-model="queryText"
            label="SQL query"
            variant="outlined"
            auto-grow
            rows="4"
            class="mb-4"
            spellcheck="false"
          />
          <div class="d-flex align-center">
            <v-btn color="primary" :loading="runningQuery" :disabled="!queryText.trim()" @click="runQuery">
              Run query
            </v-btn>
            <span v-if="lastExecutedAtLabel" class="text-caption text-medium-emphasis ms-4">
              Last run {{ lastExecutedAtLabel }}
            </span>
          </div>
          <v-alert v-if="queryError" type="error" variant="tonal" class="mt-3">
            {{ queryError }}
          </v-alert>
        </v-card-text>
      </v-card>

      <v-card>
        <v-card-title>Results</v-card-title>
        <v-divider></v-divider>
        <v-card-text>
          <div v-if="!hasResults" class="text-medium-emphasis">
            Run a query to view results. Successful responses will appear here.
          </div>
          <div v-else>
            <div class="text-caption text-medium-emphasis mb-2">
              Showing {{ queryResult.rows.length }} row(s)
              <span v-if="queryResult.truncated">(truncated)</span>
            </div>
            <v-table class="admin-results-table" density="compact">
              <thead>
                <tr>
                  <th v-for="column in queryResult.columns" :key="column">
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, rowIndex) in queryResult.rows" :key="rowIndex">
                  <td v-for="column in queryResult.columns" :key="column">
                    {{ formatCell(row[column]) }}
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ApiService from '@/services/api'

const MAX_ROWS = 500

const password = ref('')
const showPassword = ref(false)
const loginLoading = ref(false)
const authError = ref('')
const authenticated = ref(false)

const tables = ref([])
const tablesLoading = ref(false)
const tablesError = ref('')

const queryText = ref('SELECT * FROM subscriptions LIMIT 20;')
const queryError = ref('')
const queryResult = ref({ columns: [], rows: [], truncated: false })
const runningQuery = ref(false)
const lastExecutedAt = ref(null)

const hasResults = computed(() => Array.isArray(queryResult.value?.rows) && queryResult.value.rows.length > 0)
const lastExecutedAtLabel = computed(() => {
  if (!lastExecutedAt.value) {
    return ''
  }
  return new Date(lastExecutedAt.value).toLocaleString()
})
const maxRows = MAX_ROWS

const loadTables = async () => {
  if (!authenticated.value) {
    return
  }
  tablesLoading.value = true
  tablesError.value = ''
  try {
    const data = await ApiService.fetchAdminTables()
    tables.value = data.tables || []
  } catch (error) {
    if (error.code === 'admin_auth_required') {
      authenticated.value = false
      tables.value = []
      tablesError.value = 'Session expired. Please log in again.'
    } else {
      tablesError.value = error.message || 'Unable to load tables.'
    }
  } finally {
    tablesLoading.value = false
  }
}

const checkExistingSession = async () => {
  tablesLoading.value = true
  tablesError.value = ''
  try {
    const data = await ApiService.fetchAdminTables()
    tables.value = data.tables || []
    authenticated.value = true
  } catch (error) {
    if (error.code === 'admin_auth_required') {
      authenticated.value = false
      tables.value = []
    } else {
      tablesError.value = error.message || 'Unable to load tables.'
    }
  } finally {
    tablesLoading.value = false
  }
}

const handleLogin = async () => {
  authError.value = ''
  queryError.value = ''
  loginLoading.value = true
  try {
    await ApiService.adminLogin(password.value)
    authenticated.value = true
    await loadTables()
  } catch (error) {
    authError.value = error.message || 'Unable to authenticate.'
  } finally {
    loginLoading.value = false
    password.value = ''
  }
}

const runQuery = async () => {
  queryError.value = ''
  runningQuery.value = true
  try {
    const data = await ApiService.runAdminQuery(queryText.value)
    queryResult.value = data
    lastExecutedAt.value = Date.now()
  } catch (error) {
    if (error.code === 'admin_auth_required') {
      authenticated.value = false
      tables.value = []
      queryError.value = 'Session expired. Please log in again.'
    } else {
      queryError.value = error.message || 'Query failed.'
    }
  } finally {
    runningQuery.value = false
  }
}

const insertTemplate = table => {
  queryText.value = `SELECT * FROM ${table} LIMIT 50;`
}

const formatCell = value => {
  if (value === null || value === undefined) {
    return 'NULL'
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (_) {
      return String(value)
    }
  }
  return String(value)
}

onMounted(async () => {
  await checkExistingSession()
})
</script>

<style scoped>
.admin-view {
  max-width: 1100px;
  margin: 0 auto;
}

.table-chip-container {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.admin-results-table {
  overflow-x: auto;
}

.admin-results-table th,
.admin-results-table td {
  white-space: nowrap;
  padding: 6px 12px;
}
</style>
