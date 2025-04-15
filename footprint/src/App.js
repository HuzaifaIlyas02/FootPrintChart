// src/App.js
import React, { useState } from 'react';
import ChartContainer from './components/ChartContainer';
import './App.css';

function App() {
  const [timeframe, setTimeframe] = useState('1m');

  const handleTimeframeChange = (e) => {
    setTimeframe(e.target.value);
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Real-Time Footprint Chart (Flask API)</h1>
        <select value={timeframe} onChange={handleTimeframeChange}>
          <option value="1m">1 Minute</option>
          <option value="3m">3 Minute</option>
          <option value="5m">5 Minute</option>
          <option value="15m">15 Minute</option>
          <option value="1h">1 Hour</option>
          <option value="4h">4 Hour</option>
        </select>
      </header>
      <ChartContainer timeframe={timeframe} />
    </div>
  );
}

export default App;
