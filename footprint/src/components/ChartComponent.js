// src/components/ChartComponent.js
import React, {
  useMemo,
  useRef,
  useState,
  useEffect,
  useCallback,
} from "react";
import { format } from "d3-format";
import { timeFormat } from "d3-time-format";
import {
  ChartCanvas,
  Chart,
  XAxis,
  YAxis,
  CandlestickSeries,
  MouseCoordinateX,
  MouseCoordinateY,
  discontinuousTimeScaleProvider,
  OHLCTooltip,
  last,
  withSize,
  ZoomButtons,
} from "react-financial-charts";

function ChartComponent({ footprints, width, height }) {
  // --- State for canvas z-axis scale (new feature) ---
  const [zAxis, setZAxis] = useState(1);

  // --- Constants for candle configuration ---
  const candleWidth = 0.5;
  // const visibleCandleCount = 15;
  const yOffset = 0;

  // Ref for ChartCanvas to attach the wheel event on its container.
  const chartRef = useRef();

  // 1) Sort footprints by ascending date (if not already sorted)
  const sortedFootprints = useMemo(() => {
    return footprints.slice().sort((a, b) => {
      return parseInt(a.bucket, 10) - parseInt(b.bucket, 10);
    });
  }, [footprints]);


  // This will help you see the structure of the data and identify any issues.
  // console.log(footprints);

  // 2) Map and sanitize data into the shape expected by react‑financial‑charts.
  //    In addition, filter out outliers using a threshold.
  const rawData = useMemo(() => {
    return sortedFootprints.map((item) => ({
      date: new Date(parseInt(item.bucket, 10) * 1000),
      open: parseFloat(item.open),
      high: parseFloat(item.high),
      low: parseFloat(item.low),
      close: parseFloat(item.close),
    }));
  }, [sortedFootprints]);

  // Filter out any data points that are likely outliers.
  // Adjust the thresholds (e.g., high below 10000 and low above 0) as needed.
  const data = useMemo(() => {
    const filtered = rawData.filter((d) => {
      if (isNaN(d.open) || isNaN(d.high) || isNaN(d.low) || isNaN(d.close)) {
        console.log("Dropping row due to NaN:", d);
        return false;
      }
      

      // Check for weird date
      if (d.date.getFullYear() < 2000 || d.date.getFullYear() > 2050) {
        console.log("Dropping row due to suspicious date:", d);
        return false;
      }

      // For example, reject values that are too high or too low.
      // Check for out-of-range prices
      if (
        d.open <= 0 ||
        d.open > 100000 ||
        d.high <= 0 ||
        d.high > 100000 ||
        d.low <= 0 ||
        d.low > 100000 ||
        d.close <= 0 ||
        d.close > 100000
      ) {
        console.log("Dropping row due to out-of-range price:", d);
        return false;
      }
      return true;
    });
    return filtered;
  }, [rawData]);

  // --- Use discontinuousTimeScaleProvider to handle the date scale ---
  const xScaleProvider = discontinuousTimeScaleProvider.inputDateAccessor(
    (d) => d.date
  );
  const {
    data: chartData,
    xScale,
    xAccessor,
    displayXAccessor,
  } = xScaleProvider(data);

  // 3) Calculate the last index (the current candle) & center it
  const lastIndex = xAccessor(last(chartData));
  // const halfVisible = visibleCandleCount / 2;
  const visibleCandles = Math.min(15, chartData.length);
  // const xExtents = [lastIndex - halfVisible, lastIndex + halfVisible];
  const xExtents = [lastIndex - visibleCandles + 1, lastIndex + 1];
  // const chartKey = `${chartData.length}-${lastIndex}-${visibleCandleCount}`;

  // --- Custom Y-Extents so we can apply yOffset ---
  const yExtentsFunction = (candlesInput) => {
    const arr = Array.isArray(candlesInput) ? candlesInput : [candlesInput];
    const lows = arr.map((c) => c.low);
    const highs = arr.map((c) => c.high);
    return [
      Math.min(...lows) - 0.5 - yOffset,
      Math.max(...highs) + 0.5 - yOffset,
    ];
  };

  // --- New Wheel Handler to control the canvas z-axis ---
  const handleWheel = useCallback((event) => {
    event.preventDefault();
    const zStep = 0.1;
    if (event.deltaY < 0) {
      // Scrolling up: increase z-axis scale
      setZAxis((prev) => prev + zStep);
    } else {
      // Scrolling down: decrease the z-axis scale (minimum of 0.1)
      setZAxis((prev) => Math.max(prev - zStep, 0.1));
    }
  }, []);

  // --- Attach the mouse wheel event handler to the ChartCanvas container ---
  useEffect(() => {
    const containerElem =
      chartRef.current && chartRef.current.getCanvasContainer
        ? chartRef.current.getCanvasContainer()
        : null;
    if (containerElem) {
      containerElem.addEventListener("wheel", handleWheel, { passive: false });
      return () => {
        containerElem.removeEventListener("wheel", handleWheel, {
          passive: false,
        });
      };
    }
  }, [handleWheel]);

  // Ensure chartData exists. Hooks are always run, so here we conditionally render.
  const isDataReady = chartData && chartData.length > 0;

  return !isDataReady ? (
    <div>Loading chart…</div>
  ) : (
    // Wrap the ChartCanvas with a container that applies a 3D transform.
    <div
      style={{
        width: "100vw",
        height: "100vh",
        transform: `perspective(1000px) scaleZ(${zAxis})`,
        transition: "transform 0.1s ease-out",
      }}
    >
      <ChartCanvas
        // key={chartKey}
        ref={chartRef}
        height={height}
        width={width}
        ratio={1}
        margin={{ left: 50, right: 70, top: 30, bottom: 30 }}
        data={chartData}
        xScale={xScale}
        xAccessor={xAccessor}
        displayXAccessor={displayXAccessor}
        xExtents={xExtents}
        clamp={false}
        zoomEvent={true}
        panEvent={true}
        mouseMoveEvent={true}
      >
        <Chart id={1} yExtents={yExtentsFunction}>
          <XAxis tickLabelFill="#555" />
          <YAxis tickLabelFill="#555" />
          <MouseCoordinateX displayFormat={timeFormat("%H:%M")} />
          <MouseCoordinateY displayFormat={format(".2f")} />

          {/* Render candlesticks with a fixed widthRatio */}
          <CandlestickSeries widthRatio={candleWidth} />

          <OHLCTooltip
            origin={[8, 16]}
            fontSize={20}
            fontWeight={20}
            textFill="blue"
          />
          <ZoomButtons
            onReset={() => {
              if (chartRef.current && chartRef.current.resetYDomain) {
                chartRef.current.resetYDomain();
                chartRef.current.resetXDomain();
              }
            }}
          />
        </Chart>
      </ChartCanvas>
    </div>
  );
}

// Make the chart fill the entire viewport
export default withSize()(ChartComponent);
