/**
 * Tree-shaken ECharts build: registers only what the dashboard charts use
 * (line series, cartesian grid, title/legend/tooltip/dataZoom/graphic, mark helpers).
 * Importing the full 'echarts' package added ~1MB to the bundle.
 */
import * as echarts from 'echarts/core'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TitleComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  GraphicComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  AxisPointerComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TitleComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  GraphicComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  AxisPointerComponent,
  CanvasRenderer
])

export { echarts }
export default echarts
