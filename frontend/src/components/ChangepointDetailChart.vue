<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import * as echarts from 'echarts'

const props = defineProps({
  series: {
    type: Object,
    default: () => ({ before: [], after: [] })
  },
  isTimeOfDay: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: 'Travel Time Before/After'
  },
  subtitle: {
    type: String,
    default: ''
  },
  showLegend: {
    type: Boolean,
    default: true
  },
  showTitle: {
    type: Boolean,
    default: true
  }
})

const chartContainer = ref(null)
let chart = null
const theme = useTheme()
const themeStore = useThemeStore()

const BEFORE_COLOR = computed(() => '#1976D2')
const AFTER_COLOR = computed(() => (themeStore.colorblindMode ? '#E69F00' : '#F57C00'))

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

  if (!clientWidth || !clientHeight) {
    return
  }

  chart = echarts.init(container)
  window.addEventListener('resize', handleResize)
}

function handleResize() {
  chart?.resize()
  updateChart()
}

onMounted(() => {
  initializeChart()
  updateChart()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})

watch(
  () => [props.series, props.isTimeOfDay, props.title, props.subtitle, props.showLegend, props.showTitle],
  () => nextTick(updateChart),
  { deep: true }
)

watch(() => theme.global.current.value.dark, () => nextTick(updateChart))
watch(() => themeStore.colorblindMode, () => nextTick(updateChart))

function updateChart() {
  if (!chart) {
    initializeChart()
  }

  if (!chart) {
    return
  }

  const beforeSeries = props.series?.before ?? []
  const afterSeries = props.series?.after ?? []

  if ((!beforeSeries.length) && (!afterSeries.length)) {
    chart.clear()
    return
  }

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const splitLineColor = isDark ? '#424242' : '#E0E0E0'
  const isMobile = window.innerWidth < 600

  const beforeColor = BEFORE_COLOR.value
  const afterColor = AFTER_COLOR.value

  const combinedSeries = [
    {
      name: 'After',
      type: 'line',
      data: afterSeries,
      smooth: true,
      lineStyle: { color: afterColor, width: 2 },
      itemStyle: { color: afterColor },
      symbol: 'circle',
      symbolSize: 4
    },
    {
      name: 'Before',
      type: 'line',
      data: beforeSeries,
      smooth: true,
      lineStyle: { color: beforeColor, width: 2 },
      itemStyle: { color: beforeColor },
      symbol: 'circle',
      symbolSize: 4
    }
  ]

  const allPoints = [...beforeSeries, ...afterSeries]
  const allYValues = allPoints.map(point => point[1]).filter(value => Number.isFinite(value))
  const minY = allYValues.length ? Math.min(...allYValues) : 0
  const maxY = allYValues.length ? Math.max(...allYValues) : 0
  const range = maxY - minY
  const padding = range === 0 ? Math.max(5, minY * 0.1) : range * 0.05
  const yAxisMin = Math.max(0, Math.floor((minY - padding)))
  const yAxisMax = Math.ceil(maxY + padding)

  let xAxisConfig
  let tooltipFormatter

  if (props.isTimeOfDay) {
    const minutesValues = allPoints.map(point => point[0]).filter(value => Number.isFinite(value))
    const minMinutes = minutesValues.length ? Math.max(0, Math.min(...minutesValues)) : 0
    const maxMinutes = minutesValues.length ? Math.min(1440, Math.max(...minutesValues)) : 1440

    xAxisConfig = {
      type: 'value',
      name: 'Time of Day',
      nameLocation: 'middle',
      nameGap: isMobile ? 40 : 35,
      min: minMinutes,
      max: maxMinutes,
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12,
        rotate: isMobile ? 45 : 0,
        formatter: (value) => formatMinutes(value)
      },
      axisLine: { lineStyle: { color: textColor } },
      splitLine: { lineStyle: { color: splitLineColor } },
      nameTextStyle: { color: textColor, fontSize: isMobile ? 12 : 13, fontWeight: 'bold' }
    }

    tooltipFormatter = (params) => {
      if (!params.length) return ''
      const label = formatMinutes(params[0].value[0])
      const lines = params.map(item => {
        const value = Number(item.value[1]).toFixed(2)
        return `<span style="color:${item.color}">●</span> ${item.seriesName}: ${value} s`
      })
      lines.unshift(`<strong>${label}</strong>`)
      return lines.join('<br/>')
    }
  } else {
    xAxisConfig = {
      type: 'time',
      name: 'Date & Time',
      nameLocation: 'middle',
      nameGap: isMobile ? 40 : 35,
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12,
        rotate: isMobile ? 45 : 0
      },
      axisLine: { lineStyle: { color: textColor } },
      splitLine: { lineStyle: { color: splitLineColor } },
      nameTextStyle: { color: textColor, fontSize: isMobile ? 12 : 13, fontWeight: 'bold' }
    }

    tooltipFormatter = (params) => {
      if (!params.length) return ''
      const label = new Date(params[0].value[0]).toLocaleString()
      const lines = params.map(item => {
        const value = Number(item.value[1]).toFixed(2)
        return `<span style="color:${item.color}">●</span> ${item.seriesName}: ${value} s`
      })
      lines.unshift(`<strong>${label}</strong>`)
      return lines.join('<br/>')
    }
  }

  const titleOption = props.showTitle
    ? {
        text: props.title,
        subtext: props.subtitle,
        left: 'center',
        textStyle: { color: textColor, fontSize: isMobile ? 13 : 16 },
        subtextStyle: { color: textColor, fontSize: isMobile ? 10 : 11 }
      }
    : { show: false }

  const legendTop = props.showLegend
    ? (props.showTitle
        ? (props.subtitle ? (isMobile ? 105 : 110) : (isMobile ? 95 : 100))
        : (isMobile ? 20 : 24))
    : 0

  const legendOption = {
    show: props.showLegend,
    data: ['After', 'Before'],
    top: legendTop,
    textStyle: { color: textColor, fontSize: isMobile ? 10 : 12 }
  }

  const gridTop = (() => {
    if (props.showTitle) {
      return props.subtitle ? (isMobile ? '150px' : '155px') : (isMobile ? '140px' : '145px')
    }
    if (props.showLegend) {
      return props.isTimeOfDay ? (isMobile ? '80px' : '85px') : (isMobile ? '90px' : '95px')
    }
    return isMobile ? '35px' : '45px'
  })()

  const option = {
    title: titleOption,
    tooltip: {
      trigger: 'axis',
      formatter: tooltipFormatter
    },
    legend: legendOption,
    xAxis: xAxisConfig,
    yAxis: {
      type: 'value',
      name: 'Travel Time (seconds)',
      nameLocation: 'middle',
      nameGap: isMobile ? 45 : 55,
      min: yAxisMin,
      max: yAxisMax,
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12,
        formatter: (value) => Number(value).toFixed(1)
      },
      axisLine: { lineStyle: { color: textColor } },
      splitLine: { lineStyle: { color: splitLineColor } },
      nameTextStyle: { color: textColor, fontSize: isMobile ? 12 : 13, fontWeight: 'bold' }
    },
    series: combinedSeries,
    grid: {
      left: isMobile ? '60px' : '80px',
      right: isMobile ? '20px' : '50px',
      bottom: isMobile ? '70px' : '60px',
      top: gridTop
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0
      }
    ]
  }

  chart.setOption(option, true)
}

function formatMinutes(totalMinutes) {
  const minutes = Math.floor(totalMinutes)
  const hours = Math.floor(minutes / 60)
  const remaining = minutes % 60
  return `${String(hours).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
}
</script>
