// src/hooks/useHistoricalFootprint.js
import { useState, useEffect } from 'react';
import { fetchHistoricalFootprint } from '../api/flask_api';

export default function useHistoricalFootprint(timeframe) {
  const [footprints, setFootprints] = useState([]);

  // Load history once when timeframe changes.
  useEffect(() => {
    async function loadHistory() {
      const data = await fetchHistoricalFootprint(timeframe);
      console.log("Loaded historical footprint data for", timeframe, data);
      setFootprints(data);
    }
    loadHistory();
  }, [timeframe]);

  // Poll every second for real-time updates.
  useEffect(() => {
    const intervalId = setInterval(async () => {
      const data = await fetchHistoricalFootprint(timeframe);
      setFootprints(data);
    }, 1000);
    return () => clearInterval(intervalId);
  }, [timeframe]);

  return footprints;
}
