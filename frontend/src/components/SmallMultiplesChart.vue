<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useTheme } from 'vuetify'
import * as echarts from 'echarts'

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
const theme = useTheme()

// Before/After colors
const BEFORE_COLOR = '#1976D2' // Blue
const AFTER_COLOR = '#F57C00'  // Orange

onMounted(() => {
  initializeChart()
  updateChart()
})

watch(() => theme.global.current.value.dark, () => {
  updateChart()
})

onUnmounted(() => {
  if (chart) {
    chart.dispose()
  }
})

watch(() => [props.data, props.isTimeOfDay, props.entityType], () => {
  nextTick(() => {
    updateChart()
  })
}, { deep: true })

function initializeChart() {
  chart = echarts.init(chartContainer.value)
  window.addEventListener('resize', () => {
    chart?.resize()
    updateChart()
  })
}

function updateChart() {
  if (!chart || !props.data.length) {
    chart?.clear()
    return
  }

  nextTick(() => {
    chart?.resize()
  })

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'

  // Group data by LEGEND_GROUP and PERIOD
  const entities = {}
  props.data.forEach(d => {
    const entity = String(d.LEGEND_GROUP || 'Unknown')
    if (!entities[entity]) {
      entities[entity] = { before: [], after: [] }
    }

    const xValue = props.isTimeOfDay ? parseTimeOfDay(d.TIME_OF_DAY) : new Date(d.TIMESTAMP).getTime()
    const yValue = Number(d.TRAVEL_TIME_INDEX) || 0

    if (d.PERIOD === 'Before') {
      entities[entity].before.push([xValue, yValue])
    } else {
      entities[entity].after.push([xValue, yValue])
    }
  })

  const entityNames = Object.keys(entities).slice(0, 10) // Max 10 entities
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
        min: globalMinX,
        max: globalMaxX,
        axisLabel: {
          show: row === rows - 1, // Only show on bottom row
          fontSize: 9,
          color: textColor,
          formatter: (value) => {
            const hours = Math.floor(value / 60)
            const minutes = value % 60
            return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
          }
        },
        splitLine: { show: false }
      })
    } else {
      xAxes.push({
        gridIndex: gridIndex,
        type: 'time',
        min: globalMinX,
        max: globalMaxX,
        axisLabel: {
          show: row === rows - 1,
          fontSize: 9,
          color: textColor
        },
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
        fontSize: 9,
        color: textColor,
        formatter: (value) => value.toFixed(1)
      },
      splitLine: { lineStyle: { color: isDark ? '#424242' : '#E0E0E0' } }
    })

    // Before series
    series.push({
      name: 'Before',
      type: 'line',
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
      data: entities[entityName].before,
      smooth: true,
      lineStyle: { color: BEFORE_COLOR, width: 1.5 },
      itemStyle: { color: BEFORE_COLOR },
      symbol: 'none',
      showSymbol: false
    })

    // After series
    series.push({
      name: 'After',
      type: 'line',
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
      data: entities[entityName].after,
      smooth: true,
      lineStyle: { color: AFTER_COLOR, width: 1.5 },
      itemStyle: { color: AFTER_COLOR },
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
        const xValue = params[0].value[0]
        let timeStr
        if (props.isTimeOfDay) {
          const hours = Math.floor(xValue / 60)
          const minutes = xValue % 60
          timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
        } else {
          const date = new Date(xValue)
          timeStr = date.toLocaleString()
        }
        let tooltip = `<strong>${timeStr}</strong><br/>`
        params.forEach(param => {
          tooltip += `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background-color:${param.color};margin-right:5px;"></span>${param.seriesName}: ${param.value[1].toFixed(2)}<br/>`
        })
        return tooltip
      }
    }
  }

  chart.setOption(option, true)
}

function parseTimeOfDay(timeValue) {
  if (typeof timeValue === 'string') {
    const parts = timeValue.split(':')
    return parseInt(parts[0]) * 60 + parseInt(parts[1])
  } else if (typeof timeValue === 'number') {
    const totalSeconds = timeValue / 1000000
    return Math.floor(totalSeconds / 3600) * 60 + Math.floor((totalSeconds % 3600) / 60)
  }
  return 0
}
</script>
