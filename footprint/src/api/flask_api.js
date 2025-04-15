// src/api/flask_api.js
import axios from 'axios';

const SERVER_URL = 'http://localhost:5000';

export async function fetchHistoricalFootprint(timeframe) {
  try {
    // We call the endpoint that returns all candle summary rows from the CSV.
    const response = await axios.get(`${SERVER_URL}/api/footprint/history/${timeframe}`);
    return response.data; // Expected to be an array of candle summary objects.
  } catch (error) {
    console.error("Error fetching historical footprint:", error);
    return [];
  }
}
