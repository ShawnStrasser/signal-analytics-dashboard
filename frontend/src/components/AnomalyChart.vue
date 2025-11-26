<template>
  <div ref="chartContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, onActivated } from 'vue'
import { useTheme } from 'vuetify'
import { useThemeStore } from '@/stores/theme'
import * as echarts from 'echarts'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  selectedSignal: {
    type: [String, Number, null],
    default: null
  },
  chartMode: {
    type: String,
    default: 'forecast' // 'forecast' or 'percent'
  },
  legendBy: {
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

function getNiceInterval(range, desiredTicks = 6) {
  if (!Number.isFinite(range) || range <= 0) {
    return 1
  }

  const tickCount = Math.max(desiredTicks, 1)
  const roughInterval = range / tickCount
  const exponent = Math.floor(Math.log10(roughInterval))
  const base = Math.pow(10, exponent)
  const multiples = [1, 2, 5, 10]
  const niceMultiple = multiples.find(multiple => roughInterval <= multiple * base) ?? 10

  return niceMultiple * base
}

function formatSeconds(value, options = {}) {
  const {
    compact = false,
    maxFractionDigits = 1,
    minFractionDigits = 0
  } = options

  if (!Number.isFinite(value)) {
    return ''
  }

  const fractionDigits = {
    minimumFractionDigits: minFractionDigits,
    maximumFractionDigits: Math.max(maxFractionDigits, minFractionDigits)
  }

  if (compact && typeof Intl !== 'undefined' && typeof Intl.NumberFormat === 'function') {
    try {
      const abs = Math.abs(value)
      const compactFractionDigits = {
        minimumFractionDigits: minFractionDigits,
        maximumFractionDigits: abs >= 100 ? 0 : abs >= 10 ? Math.min(fractionDigits.maximumFractionDigits, 1) : fractionDigits.maximumFractionDigits
      }

      const formatted = new Intl.NumberFormat('en-US', {
        notation: 'compact',
        ...compactFractionDigits
      }).format(value)

      return `${formatted} s`
    } catch (error) {
      // Fallback to standard formatting below
    }
  }

  if (typeof Intl !== 'undefined' && typeof Intl.NumberFormat === 'function') {
    const formatted = new Intl.NumberFormat('en-US', fractionDigits).format(value)
    return `${formatted} s`
  }

  return `${value.toFixed(fractionDigits.maximumFractionDigits)} s`
}

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

// Watch for theme changes
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

watch(() => [props.data, props.selectedSignal, props.chartMode, props.legendBy], () => {
  const watchStart = performance.now()
  debugLog('📊 ANOMALY CHART WATCH: data changed, deferring to nextTick', {
    dataLength: props.data?.length,
    chartMode: props.chartMode,
    legendBy: props.legendBy
  })
  // Defer chart update to next tick to avoid updating during render
  nextTick(() => {
    const tickStart = performance.now()
    debugLog(`📊 ANOMALY CHART: nextTick triggered, delay from watch: ${(tickStart - watchStart).toFixed(2)}ms`)
    updateChart()
    const tickEnd = performance.now()
    debugLog(`📊 ANOMALY CHART: updateChart complete, took ${(tickEnd - tickStart).toFixed(2)}ms`)
  })
}, { deep: true })

function initializeChart() {
  if (!chartContainer.value || chart) {
    return
  }

  chart = echarts.init(chartContainer.value)

  // Handle window resize
  windowResizeHandler = () => {
    requestChartResize()
    // Re-render chart with updated responsive settings
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
  const t0 = performance.now()
  if (!chart || !props.data.length) {
    debugLog('📊 ANOMALY CHART: updateChart skipped (no chart or data)')
    return
  }
  debugLog('📊 ANOMALY CHART: updateChart START', {
    dataPoints: props.data.length,
    chartMode: props.chartMode,
    legendBy: props.legendBy
  })

  // Use nextTick to ensure chart resize happens after DOM updates
  requestChartResize()

  const isDark = theme.global.current.value.dark
  const textColor = isDark ? '#E0E0E0' : '#333333'
  const backgroundColor = isDark ? 'transparent' : 'transparent'

  // Check if data has LEGEND_GROUP column
  const hasLegend = props.data.length > 0 && props.data[0].LEGEND_GROUP !== undefined

  // Detect mobile screen size
  const isMobile = window.innerWidth < 600

  // Use same color palette as TravelTimeChart
  const lightModePalette = [
    '#1976D2', '#388E3C', '#F57C00', '#D32F2F', '#7B1FA2',
    '#00796B', '#C2185B', '#5D4037', '#455A64', '#0097A7'
  ]

  const darkModePalette = [
    '#64B5F6', '#81C784', '#FFB74D', '#E57373', '#BA68C8',
    '#4DB6AC', '#F06292', '#A1887F', '#90A4AE', '#4DD0E1'
  ]

  // Colorblind-friendly palettes (based on Wong 2011 / IBM Design / Okabe Ito)
  const lightModeColorblindPalette = [
    '#0072B2', '#E69F00', '#009E73', '#D55E00', '#CC79A7',
    '#56B4E9', '#F0E442', '#999999', '#000000', '#882255'
  ]

  const darkModeColorblindPalette = [
    '#56B4E9', '#F0E442', '#009E73', '#E69F00', '#CC79A7',
    '#0072B2', '#D55E00', '#CCCCCC', '#999999', '#882255'
  ]

  let colorPalette
  if (themeStore.colorblindMode) {
    colorPalette = isDark ? darkModeColorblindPalette : lightModeColorblindPalette
  } else {
    colorPalette = isDark ? darkModePalette : lightModePalette
  }

  // Changepoint comparison colors (Before=baseline, After=current)
  const changepointBeforeColor = '#1976D2'
  const changepointAfterColor = themeStore.colorblindMode ? '#E69F00' : '#F57C00'

  let xAxisConfig, tooltipFormatter, title, yAxisName
  let seriesData = []
  let series = []

  // Group data by LEGEND_GROUP if present (timestamp mode only)
  if (hasLegend) {
    const groupedData = {}
    props.data.forEach(d => {
      const group = String(d.LEGEND_GROUP || 'Unknown')
      if (!groupedData[group]) {
        groupedData[group] = { actual: [], forecast: [], percent: [] }
      }

      const timestamp = new Date(d.TIMESTAMP).getTime()
      if (props.chartMode === 'percent') {
        groupedData[group].percent.push([timestamp, Number(d.ANOMALY_PERCENT) || 0])
      } else {
        groupedData[group].actual.push([timestamp, Number(d.TOTAL_ACTUAL_TRAVEL_TIME) || 0])
        groupedData[group].forecast.push([timestamp, Number(d.TOTAL_PREDICTION) || 0])
      }
    })

    seriesData = Object.entries(groupedData)
  } else {
    // Single series
    const singleData = { actual: [], forecast: [], percent: [] }
    props.data.forEach(d => {
      const timestamp = new Date(d.TIMESTAMP).getTime()
      if (props.chartMode === 'percent') {
        singleData.percent.push([timestamp, Number(d.ANOMALY_PERCENT) || 0])
      } else {
        singleData.actual.push([timestamp, Number(d.TOTAL_ACTUAL_TRAVEL_TIME) || 0])
        singleData.forecast.push([timestamp, Number(d.TOTAL_PREDICTION) || 0])
      }
    })
    seriesData = [['All Data', singleData]]
  }

  title = props.chartMode === 'percent'
    ? 'Anomaly Percentage Over Time'
    : 'Travel Time Forecast vs Actual Over Time'

  // Determine aggregation level from data timestamps
  let xAxisName = 'Time'
  if (props.data.length >= 2) {
    const timestamps = props.data.slice(0, 10).map(d => new Date(d.TIMESTAMP).getTime())
    const intervals = []
    for (let i = 1; i < timestamps.length; i++) {
      intervals.push(timestamps[i] - timestamps[i - 1])
    }
    const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length
    const avgMinutes = avgInterval / (1000 * 60)

    // Determine aggregation level based on average interval
    if (avgMinutes < 30) {
      xAxisName = 'Date & Time (15-minute)'
    } else if (avgMinutes < 90) {
      xAxisName = 'Date & Time (Hourly)'
    } else if (avgMinutes < 1440) {
      xAxisName = 'Date & Time'
    } else {
      xAxisName = 'Date'
    }
  }

  xAxisConfig = {
    type: 'time',
    name: xAxisName,
    nameLocation: 'middle',
    nameGap: isMobile ? 40 : 35,
    nameTextStyle: {
      color: textColor,
      fontSize: isMobile ? 12 : 13,
      fontWeight: 'bold'
    },
    axisLabel: {
      color: textColor,
      rotate: isMobile ? 45 : 0,
      fontSize: isMobile ? 10 : 12,
      formatter: function(value) {
        const date = new Date(value)
        const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        const dayOfWeek = dayNames[date.getDay()]
        const month = String(date.getMonth() + 1).padStart(2, '0')
        const day = String(date.getDate()).padStart(2, '0')
        const hours = String(date.getHours()).padStart(2, '0')
        const minutes = String(date.getMinutes()).padStart(2, '0')

        // Show date with day-of-week when day changes (midnight)
        if (date.getHours() === 0 && date.getMinutes() === 0) {
          if (isMobile) {
            // Compact format for mobile
            return `${month}/${day}\n${hours}:${minutes}`
          }
          return `${dayOfWeek} ${month}/${day}\n${hours}:${minutes}`
        }

        return `${hours}:${minutes}`
      }
    },
    axisLine: {
      lineStyle: {
        color: textColor
      }
    }
  }

  tooltipFormatter = function(params) {
    if (params.length > 0) {
      const data = params[0]
      const date = new Date(data.value[0])
      const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
      const dayOfWeek = dayNames[date.getDay()]
      const time = date.toLocaleString()

      // Build tooltip with all series at this timestamp
      let tooltip = `<strong>${dayOfWeek} ${time}</strong><br/>`
    params.forEach(param => {
      const seriesName = param.seriesName
      const value = props.chartMode === 'percent'
        ? `${param.value[1].toFixed(2)}%`
        : formatSeconds(param.value[1], { maxFractionDigits: 1, minFractionDigits: 1 })
      const color = param.color
      tooltip += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${color};margin-right:5px;"></span>${seriesName}: ${value}<br/>`
    })
      return tooltip
    }
    return ''
  }

  // Build series array
  if (props.chartMode === 'percent') {
    // Percent Anomaly mode: one series per entity
    yAxisName = 'Anomaly Percentage (%)'
    series = seriesData.map(([groupName, data], index) => {
      const color = colorPalette[index % colorPalette.length]
      return {
        name: groupName,
        type: 'line',
        data: data.percent,
        smooth: true,
        lineStyle: {
          color: color,
          width: 2
        },
        itemStyle: {
          color: color
        },
        symbol: 'circle',
        symbolSize: hasLegend ? 3 : 4
      }
    })
  } else {
    // Forecast vs Actual mode: two series per entity (same color, different line styles)
    yAxisName = 'Total Travel Time (seconds)'
    series = []
    seriesData.forEach(([groupName, data], index) => {
      const baseColor = colorPalette[index % colorPalette.length]
      const actualColor = hasLegend ? baseColor : changepointAfterColor
      const forecastColor = hasLegend ? baseColor : changepointBeforeColor
      const forecastLineType = hasLegend ? 'dashed' : 'solid'

      // Actual series (solid line)
      series.push({
        name: hasLegend ? groupName : 'Actual Travel Time',
        type: 'line',
        data: data.actual,
        smooth: true,
        lineStyle: {
          color: actualColor,
          width: 2,
          type: 'solid'
        },
        itemStyle: {
          color: actualColor
        },
        symbol: 'circle',
        symbolSize: hasLegend ? 3 : 4,
        // Custom property to identify as actual
        _customType: 'actual'
      })

      // Forecast series (dashed line, same color)
      series.push({
        name: hasLegend ? groupName : 'Predicted Travel Time',
        type: 'line',
        data: data.forecast,
        smooth: true,
        lineStyle: {
          color: forecastColor,
          width: 2,
          type: forecastLineType
        },
        itemStyle: {
          color: forecastColor
        },
        symbol: 'circle',
        symbolSize: hasLegend ? 3 : 4,
        // Custom property to identify as forecast
        _customType: 'forecast'
      })
    })
  }

  // Calculate dynamic y-axis range
  const allValues = series.flatMap(s => s.data.map(d => d[1]))
  const minValue = Math.min(...allValues)
  const maxValue = Math.max(...allValues)
  const valueRange = maxValue - minValue

  // Safety check: ensure values are valid numbers
  if (!isFinite(minValue) || !isFinite(maxValue) || allValues.length === 0) {
    console.error('📊 ANOMALY CHART ERROR: Invalid y-axis data', { minValue, maxValue })
    return
  }

  // Set min/max with 2% padding, but round to nice intervals
  const rawMin = Math.max(0, minValue - (valueRange * 0.02))
  const rawMax = maxValue + (valueRange * 0.02)

  // Determine appropriate interval based on range
  const paddedRange = rawMax - rawMin
  const desiredTickCount = isMobile ? 4 : 6
  let interval
  if (props.chartMode === 'percent') {
    // For percentage, use finer intervals
    if (paddedRange < 5) {
      interval = 0.5
    } else if (paddedRange < 10) {
      interval = 1
    } else if (paddedRange < 20) {
      interval = 2
    } else if (paddedRange < 50) {
      interval = 5
    } else {
      interval = 10
    }
  } else {
    interval = getNiceInterval(paddedRange || Math.max(maxValue, 1), desiredTickCount)
  }

  if (!Number.isFinite(interval) || interval === 0) {
    interval = getNiceInterval(Math.max(maxValue, 1), desiredTickCount) || 1
  }

  // Round min down and max up to nearest interval
  let yAxisMin = Math.floor(rawMin / interval) * interval
  let yAxisMax = Math.ceil(rawMax / interval) * interval

  if (yAxisMax === yAxisMin) {
    yAxisMax = yAxisMin + interval
  }

  const axisSecondsFractionDigits = interval < 1 ? 2 : interval < 10 ? 1 : 0

  // Build legend configuration
  let legendConfig = undefined
  if (hasLegend && props.chartMode === 'forecast') {
    // In forecast mode with legend, show only unique entity names (not "Actual" and "Forecast" for each)
    const uniqueNames = [...new Set(seriesData.map(([name, _]) => name))]
    legendConfig = {
      type: 'scroll',
      orient: isMobile ? 'horizontal' : 'vertical',
      right: isMobile ? 'auto' : 10,
      left: isMobile ? 'center' : 'auto',
      top: isMobile ? 80 : 'center', // More space at top for custom legend
      data: uniqueNames,
      textStyle: {
        color: textColor,
        fontSize: isMobile ? 10 : 12
      },
      pageTextStyle: {
        color: textColor
      }
    }
  } else if (hasLegend && props.chartMode === 'percent') {
    // In percent mode with legend, standard legend
    legendConfig = {
      type: 'scroll',
      orient: isMobile ? 'horizontal' : 'vertical',
      right: isMobile ? 'auto' : 10,
      left: isMobile ? 'center' : 'auto',
      top: isMobile ? 35 : 'center',
      textStyle: {
        color: textColor,
        fontSize: isMobile ? 10 : 12
      },
      pageTextStyle: {
        color: textColor
      }
    }
  } else if (!hasLegend && props.chartMode === 'forecast') {
    // No legend grouping, but show Actual vs Predicted
    legendConfig = {
      data: ['Actual Travel Time', 'Predicted Travel Time'],
      top: isMobile ? 30 : 30,
      textStyle: {
        color: textColor,
        fontSize: isMobile ? 10 : 12
      }
    }
  }

  // Add custom legend for line types in Forecast mode with legend
  let graphicElements = []
  if (hasLegend && props.chartMode === 'forecast') {
    // Add custom legend showing line type meanings at the top
    graphicElements = [
      {
        type: 'group',
        left: 'center',
        top: isMobile ? 35 : 20,
        children: [
          {
            type: 'rect',
            z: 100,
            left: 0,
            top: 0,
            shape: {
              width: isMobile ? 200 : 250,
              height: isMobile ? 35 : 40
            },
            style: {
              fill: isDark ? 'rgba(0, 0, 0, 0.5)' : 'rgba(255, 255, 255, 0.8)',
              stroke: isDark ? '#555' : '#ccc',
              lineWidth: 1
            }
          },
          {
            type: 'line',
            z: 101,
            left: 10,
            top: isMobile ? 12 : 15,
            shape: {
              x1: 0,
              y1: 0,
              x2: 30,
              y2: 0
            },
            style: {
              stroke: textColor,
              lineWidth: 2
            }
          },
          {
            type: 'text',
            z: 101,
            left: 45,
            top: isMobile ? 8 : 10,
            style: {
              text: 'Actual',
              fill: textColor,
              fontSize: isMobile ? 10 : 12
            }
          },
          {
            type: 'line',
            z: 101,
            left: isMobile ? 110 : 130,
            top: isMobile ? 12 : 15,
            shape: {
              x1: 0,
              y1: 0,
              x2: 30,
              y2: 0
            },
            style: {
              stroke: textColor,
              lineWidth: 2,
              lineDash: [5, 5]
            }
          },
          {
            type: 'text',
            z: 101,
            left: isMobile ? 145 : 165,
            top: isMobile ? 8 : 10,
            style: {
              text: 'Forecast',
              fill: textColor,
              fontSize: isMobile ? 10 : 12
            }
          }
        ]
      }
    ]
  }

  const option = {
    backgroundColor: backgroundColor,
    title: {
      text: title,
      left: 'center',
      textStyle: {
        fontSize: isMobile ? 13 : 16,
        color: textColor
      }
    },
    tooltip: {
      trigger: 'axis',
      formatter: tooltipFormatter
    },
    legend: legendConfig,
    graphic: graphicElements,
    xAxis: xAxisConfig,
    yAxis: {
      type: 'value',
      name: yAxisName,
      nameLocation: 'middle',
      nameGap: isMobile ? 45 : 55,
      min: yAxisMin,
      max: yAxisMax,
      interval: interval,
      nameTextStyle: {
        color: textColor,
        fontSize: isMobile ? 12 : 13,
        fontWeight: 'bold'
      },
      axisLabel: {
        color: textColor,
        fontSize: isMobile ? 10 : 12,
        formatter(value) {
          if (props.chartMode === 'percent') {
            return value.toFixed(1)
          }
          return formatSeconds(value, {
            compact: true,
            maxFractionDigits: axisSecondsFractionDigits
          })
        }
      },
      axisLine: {
        lineStyle: {
          color: textColor
        }
      },
      splitLine: {
        lineStyle: {
          color: isDark ? '#424242' : '#E0E0E0'
        }
      }
    },
    series: series,
    grid: {
      left: isMobile ? '60px' : '80px',
      right: hasLegend ? (isMobile ? '20px' : '200px') : (isMobile ? '20px' : '50px'),
      bottom: isMobile ? '70px' : '60px',
      top: hasLegend && props.chartMode === 'forecast' ? (isMobile ? '120px' : '100px') : (isMobile ? '80px' : '80px')
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0
      }
    ]
  }

  const setOptionStart = performance.now()
  chart.setOption(option, true)
  const t1 = performance.now()
  debugLog(`📊 ANOMALY CHART: setOption took ${(t1 - setOptionStart).toFixed(2)}ms`)
  debugLog(`📊 ANOMALY CHART: updateChart COMPLETE, total ${(t1 - t0).toFixed(2)}ms`)
}
</script>
