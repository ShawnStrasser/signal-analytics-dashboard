<template>
  <div ref="chartContainer" class="anomaly-monitoring-chart"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import * as echarts from 'echarts'

const props = defineProps({
  series: {
    type: Array,
    default: () => []
  }
})

const chartContainer = ref(null)
let chart = null
const theme = useTheme()
const themeStore = useThemeStore()

function formatMinutes(value) {
  const total = Math.round(Number(value) || 0)
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`
}

function getSeriesData() {
  const minutes = []
  const actual = []
  const forecast = []

  props.series.forEach(point => {
    const minuteValue = Number(point?.minutes ?? point?.MINUTES ?? 0)
    minutes.push(minuteValue)

    const actualValue = point?.actual ?? point?.ACTUAL ?? point?.TOTAL_ACTUAL_TRAVEL_TIME
    const predictionValue = point?.prediction ?? point?.PREDICTION ?? point?.FORECAST

    const actualNumber = Number(actualValue)
    actual.push(Number.isFinite(actualNumber) ? actualNumber : null)

    const forecastNumber = Number(predictionValue)
    forecast.push(Number.isFinite(forecastNumber) ? forecastNumber : null)
  })

  return { minutes, actual, forecast }
}

function computeYAxisRange(actual, forecast) {
  const combined = actual.concat(forecast).filter(value => value !== null && Number.isFinite(value))
  if (!combined.length) {
    return { min: 0, max: 1 }
  }

  const minValue = Math.min(...combined)
  const maxValue = Math.max(...combined)
  if (minValue === maxValue) {
    const padding = Math.max(minValue * 0.05, 1)
    return { min: Math.max(minValue - padding, 0), max: maxValue + padding }
  }

  const rangePadding = (maxValue - minValue) * 0.1
  return {
    min: Math.max(minValue - rangePadding, 0),
    max: maxValue + rangePadding
  }
}

function renderChart() {
  if (!chart) {
    return
  }

  const { minutes, actual, forecast } = getSeriesData()
  const actualSeries = minutes.map((minute, index) => [minute, actual[index]])
  const forecastSeries = minutes.map((minute, index) => [minute, forecast[index]])
  const { min, max } = computeYAxisRange(actual, forecast)

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const gridColor = isDark ? '#424242' : '#E0E0E0'

  const beforeColor = '#1976D2'
  const afterColor = themeStore.colorblindMode ? '#E69F00' : '#F57C00'
  const actualColor = afterColor
  const forecastColor = beforeColor

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        if (!params || !params.length) {
          return ''
        }
        const label = formatMinutes(params[0].value[0])
        const lines = params
          .filter(item => item.value && Number.isFinite(item.value[1]))
          .map(item => {
            const value = Number(item.value[1]).toFixed(1)
            return `<span style="color:${item.color}">●</span> ${item.seriesName}: ${value} s`
          })
        lines.unshift(`<strong>${label}</strong>`)
        return lines.join('<br/>')
      }
    },
    legend: {
      data: ['Actual', 'Forecast'],
      top: 0,
      textStyle: { color: textColor, fontSize: 11 }
    },
    grid: {
      left: '60px',
      right: '30px',
      bottom: '40px',
      top: '40px'
    },
    xAxis: {
      type: 'value',
      min: 0,
      max: 24 * 60,
      axisLabel: {
        formatter: formatMinutes,
        color: textColor,
        fontSize: 10
      },
      axisLine: {
        lineStyle: { color: textColor }
      },
      splitLine: {
        lineStyle: { color: gridColor }
      },
      name: 'Time of Day',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: {
        color: textColor,
        fontSize: 11,
        fontWeight: 'bold'
      }
    },
    yAxis: {
      type: 'value',
      min,
      max,
      axisLabel: {
        color: textColor,
        fontSize: 10,
        formatter(value) {
          return Number(value).toFixed(1)
        }
      },
      axisLine: {
        lineStyle: { color: textColor }
      },
      splitLine: {
        lineStyle: { color: gridColor }
      },
      name: 'Travel Time (seconds)',
      nameLocation: 'middle',
      nameGap: 48,
      nameTextStyle: {
        color: textColor,
        fontSize: 11,
        fontWeight: 'bold'
      }
    },
    series: [
      {
        name: 'Actual',
        type: 'line',
        data: actualSeries,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: {
          color: actualColor,
          width: 2.6
        },
        itemStyle: {
          color: actualColor
        },
        connectNulls: false
      },
      {
        name: 'Forecast',
        type: 'line',
        data: forecastSeries,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: {
          color: forecastColor,
          width: 1.6,
          type: 'solid'
        },
        itemStyle: {
          color: forecastColor
        },
        connectNulls: false
      }
    ]
  }

  chart.setOption(option, true)
}

function initializeChart(attempt = 0) {
  const container = chartContainer.value
  if (!container || chart) {
    return
  }

  const { clientWidth, clientHeight } = container
  if ((!clientWidth || !clientHeight) && attempt < 10) {
    requestAnimationFrame(() => initializeChart(attempt + 1))
    return
  }

  chart = echarts.init(container)
  window.addEventListener('resize', handleResize, { passive: true })
  renderChart()
}

function disposeChart() {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
}

function handleResize() {
  if (chart) {
    chart.resize()
  }
}

watch(
  () => props.series,
  () => nextTick(renderChart),
  { deep: true }
)

watch(() => theme.global.current.value.dark, () => nextTick(renderChart))
watch(() => themeStore.colorblindMode, () => nextTick(renderChart))

onMounted(() => {
  initializeChart()
})

onUnmounted(() => {
  disposeChart()
})
</script>

<style scoped>
.anomaly-monitoring-chart {
  height: 240px;
  width: 100%;
}
</style>
