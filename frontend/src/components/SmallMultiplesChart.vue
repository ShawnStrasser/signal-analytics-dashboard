<template>
  <div ref="chartContainer" :style="{ height: containerHeight, width: '100%' }"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed, onActivated } from 'vue'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import * as echarts from 'echarts'
import {
  DATE_TIME_STEP_MILLISECONDS,
  formatDateTimeAxisLabel,
  formatDateTimeTooltipLabel,
  formatTimeOfDayAxisLabel,
  formatTimeOfDayLabel,
  getDisplayStepMinutesForRange,
  parseTimeOfDayToMinutes,
  snapMinutesToTimeBucket,
  snapTimestampToTimeBucket,
  startOfLocalDayTimestamp,
} from '@/utils/chartTime'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  isTimeOfDay: {
    type: Boolean,
    default: false
  },
  entityType: {
    type: String,
    default: 'none'
  }
})

const chartContainer = ref(null)
let chart = null
let windowResizeHandler = null
let needsResizeAfterShow = false
const theme = useTheme()
const themeStore = useThemeStore()

// Calculate dynamic container height based on number of entities
const containerHeight = computed(() => {
  if (!props.data.length) return '500px'

  // Count unique entities
  const entities = new Set(props.data.map(d => String(d.LEGEND_GROUP || 'Unknown')))
  const numEntities = Math.min(entities.size, 12) // Max 12 entities
  const cols = 2
  const rows = Math.ceil(numEntities / cols)

  // 250px per row + 50px for legend
  const height = rows * 250 + 50
  return `${height}px`
})

// Before/After colors (colorblind-safe when enabled)
const BEFORE_COLOR = computed(() => {
  // Blue is already colorblind-safe, keep consistent
  return '#1976D2'
})

const AFTER_COLOR = computed(() => {
  if (themeStore.colorblindMode) {
    return '#E69F00' // Colorblind-safe orange
  } else {
    return '#F57C00'  // Standard orange
  }
})

onMounted(() => {
  initializeChart()
  updateChart()
})

onActivated(() => {
  nextTick(() => {
    requestChartResize(true)
    if (needsResizeAfterShow) {
      requestAnimationFrame(() => requestChartResize(true))
    }
  })
})

watch(() => theme.global.current.value.dark, () => {
  updateChart()
})

// Watch for colorblind mode changes
watch(() => themeStore.colorblindMode, () => {
  updateChart()
})

onUnmounted(() => {
  if (windowResizeHandler) {
    window.removeEventListener('resize', windowResizeHandler)
    windowResizeHandler = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
  needsResizeAfterShow = false
})

watch(() => [props.data, props.isTimeOfDay, props.entityType], () => {
  nextTick(() => {
    updateChart()
  })
}, { deep: true })

function initializeChart() {
  if (!chartContainer.value || chart) {
    return
  }

  chart = echarts.init(chartContainer.value)
  windowResizeHandler = () => {
    requestChartResize()
    updateChart()
  }
  window.addEventListener('resize', windowResizeHandler)
}

function requestChartResize(immediate = false) {
  const resizeAction = () => {
    if (!chart || !chartContainer.value) {
      return
    }

    const { offsetWidth, offsetHeight } = chartContainer.value
    if (!offsetWidth || !offsetHeight) {
      needsResizeAfterShow = true
      return
    }

    chart.resize()
    needsResizeAfterShow = false
  }

  if (immediate) {
    resizeAction()
  } else {
    nextTick(resizeAction)
  }
}

function updateChart() {
  if (!chart || !props.data.length) {
    chart?.clear()
    return
  }

  requestChartResize()

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const isMobile = window.innerWidth < 600
  const totalWidth = chartContainer.value?.offsetWidth || window.innerWidth

  // Group data by LEGEND_GROUP and PERIOD
  const entities = {}
  props.data.forEach(d => {
    const entity = String(d.LEGEND_GROUP || 'Unknown')
    if (!entities[entity]) {
      entities[entity] = { before: [], after: [] }
    }

    const xValue = props.isTimeOfDay ? parseTimeOfDayToMinutes(d.TIME_OF_DAY) : new Date(d.TIMESTAMP).getTime()
    const yValue = Number(d.TRAVEL_TIME_INDEX) || 0

    if (d.PERIOD === 'Before') {
      entities[entity].before.push([xValue, yValue])
    } else {
      entities[entity].after.push([xValue, yValue])
    }
  })

  const entityNames = Object.keys(entities).slice(0, 12) // Max 12 entities
  const numEntities = entityNames.length

  // Calculate grid layout (2 columns)
  const cols = 2
  const rows = Math.ceil(numEntities / cols)

  // Create grid configuration
  const gridWidth = 45 // percentage
  const gridHeight = 90 / rows // percentage
  const gridGap = 2 // percentage

  const grids = []
  const xAxes = []
  const yAxes = []
  const series = []
  const titles = []

  // Find global min/max for shared axes
  let globalMinX = Infinity
  let globalMaxX = -Infinity
  let globalMinY = Infinity
  let globalMaxY = -Infinity

  Object.values(entities).forEach(entity => {
    [...entity.before, ...entity.after].forEach(([x, y]) => {
      globalMinX = Math.min(globalMinX, x)
      globalMaxX = Math.max(globalMaxX, x)
      globalMinY = Math.min(globalMinY, y)
      globalMaxY = Math.max(globalMaxY, y)
    })
  })

  // Calculate y-axis range with padding
  const yRange = globalMaxY - globalMinY
  const yPadding = yRange * 0.05
  const yMin = Math.max(0, globalMinY - yPadding)
  const yMax = globalMaxY + yPadding
  const xMin = props.isTimeOfDay
    ? snapMinutesToTimeBucket(globalMinX, 'floor')
    : snapTimestampToTimeBucket(globalMinX, 'floor')
  const xMax = props.isTimeOfDay
    ? snapMinutesToTimeBucket(globalMaxX, 'ceil')
    : snapTimestampToTimeBucket(globalMaxX, 'ceil')
  const plotWidth = totalWidth * 0.45
  const maxLabelCount = Math.max(2, Math.floor(plotWidth / (isMobile ? 90 : 120)))
  const timeOfDayDisplayStep = props.isTimeOfDay ? getDisplayStepMinutesForRange(xMax - xMin, { maxLabels: maxLabelCount }) : null
  const dateTimeDisplayStep = props.isTimeOfDay ? null : getDisplayStepMinutesForRange((xMax - xMin) / (1000 * 60), { maxLabels: maxLabelCount })
  const dateTimeAnchor = !props.isTimeOfDay && dateTimeDisplayStep >= 1440 ? startOfLocalDayTimestamp(xMin) : xMin

  entityNames.forEach((entityName, index) => {
    const row = Math.floor(index / cols)
    const col = index % cols

    const left = col * (gridWidth + gridGap) + 5
    const top = row * gridHeight + 5
    const gridIndex = index

    // Grid
    grids.push({
      left: `${left}%`,
      top: `${top}%`,
      width: `${gridWidth}%`,
      height: `${gridHeight - gridGap}%`
    })

    // Title
    titles.push({
      text: entityName,
      left: `${left + gridWidth / 2}%`,
      top: `${top}%`,
      textAlign: 'center',
      textStyle: {
        fontSize: 12,
        color: textColor,
        fontWeight: 'bold'
      }
    })

    // X-axis
    if (props.isTimeOfDay) {
      xAxes.push({
        gridIndex: gridIndex,
        type: 'value',
        min: xMin,
        max: xMax,
        minInterval: 15,
        maxInterval: 15,
        interval: 15,
        axisLabel: {
          show: row === rows - 1, // Only show on bottom row
          fontSize: isMobile ? 10 : 12,
          color: textColor,
          hideOverlap: true,
          formatter: (value) => formatTimeOfDayAxisLabel(value, { displayStepMinutes: timeOfDayDisplayStep, anchorMinutes: xMin })
        },
        axisTick: { show: false },
        splitLine: { show: false }
      })
    } else {
      xAxes.push({
        gridIndex: gridIndex,
        type: 'time',
        min: xMin,
        max: xMax,
        minInterval: DATE_TIME_STEP_MILLISECONDS,
        maxInterval: DATE_TIME_STEP_MILLISECONDS,
        interval: DATE_TIME_STEP_MILLISECONDS,
        axisLabel: {
          show: row === rows - 1,
          fontSize: isMobile ? 10 : 12,
          color: textColor,
          hideOverlap: true,
          formatter: (value) => formatDateTimeAxisLabel(value, { isMobile, displayStepMinutes: dateTimeDisplayStep, anchorTimestamp: dateTimeAnchor })
        },
        axisTick: { show: false },
        splitLine: { show: false }
      })
    }

    // Y-axis
    yAxes.push({
      gridIndex: gridIndex,
      type: 'value',
      min: yMin,
      max: yMax,
      axisLabel: {
        show: col === 0, // Only show on left column
        fontSize: isMobile ? 10 : 12,
        color: textColor,
        formatter: (value) => value.toFixed(1)
      },
      splitLine: { lineStyle: { color: isDark ? '#424242' : '#E0E0E0' } }
    })

    // Before series (dashed line)
    series.push({
      name: 'Before',
      type: 'line',
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
      data: entities[entityName].before,
      smooth: true,
      lineStyle: { color: BEFORE_COLOR.value, width: 1.5, type: 'dashed' },
      itemStyle: { color: BEFORE_COLOR.value },
      symbol: 'none',
      showSymbol: false
    })

    // After series (solid line)
    series.push({
      name: 'After',
      type: 'line',
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
      data: entities[entityName].after,
      smooth: true,
      lineStyle: { color: AFTER_COLOR.value, width: 1.5, type: 'solid' },
      itemStyle: { color: AFTER_COLOR.value },
      symbol: 'none',
      showSymbol: false
    })
  })

  const option = {
    title: titles,
    legend: {
      data: ['Before', 'After'],
      top: 0,
      left: 'center',
      textStyle: { color: textColor, fontSize: 12 },
      itemWidth: 20,
      itemHeight: 10
    },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    series: series,
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        if (!params.length) return ''
        let timeStr
        if (props.isTimeOfDay) {
          timeStr = formatTimeOfDayLabel(params[0].value[0])
        } else {
          timeStr = formatDateTimeTooltipLabel(params[0].value[0])
        }
        const visibleParams = params.filter(param => {
          const pointValue = Array.isArray(param.value) ? param.value[1] : param.value
          return Number.isFinite(Number(pointValue))
        })
        let tooltip = `<strong>${timeStr}</strong><br/>`
        visibleParams.forEach(param => {
          const pointValue = Array.isArray(param.value) ? param.value[1] : param.value
          tooltip += `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background-color:${param.color};margin-right:5px;"></span>${param.seriesName}: ${Number(pointValue).toFixed(2)}<br/>`
        })
        return tooltip
      }
    }
  }

  chart.setOption(option, true)
}
</script>
