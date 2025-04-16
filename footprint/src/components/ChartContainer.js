// src/components/ChartContainer.js
import React from "react";
import useHistoricalFootprint from "../hooks/useHistoricalFootprint";
import ChartComponent from "./ChartComponent";

export default function ChartContainer({ timeframe }) {
  const footprints = useHistoricalFootprint(timeframe);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "700px",
        marginTop: "20px",
        marginLeft: "20px",
      }}
    >
      <ChartComponent footprints={footprints} />
    </div>
  );
}
