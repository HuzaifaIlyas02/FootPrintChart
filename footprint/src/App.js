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
        <h1>Real-Time Footprint Chart</h1>
        <div style={{ margin: '10px 0', display: 'inline-block', position: 'relative' }}>
          <select
            value={timeframe}
            onChange={handleTimeframeChange}
            style={{
              padding: '10px',
              borderRadius: '5px',
              width: '150px',
              border: '1px solid #ccc',
              fontSize: '18px',
              appearance: 'none',
              fontWeight: 'bold',
              backgroundColor: '#f9f9f9',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="1m">1 Minute</option>
            <option value="3m">3 Minute</option>
            <option value="5m">5 Minute</option>
            <option value="15m">15 Minute</option>
            <option value="1h">1 Hour</option>
            <option value="4h">4 Hour</option>
          </select>
          <span
            style={{
              position: 'absolute',
              right: '10px',
              top: '50%',
              transform: 'translateY(-50%)',
              pointerEvents: 'none',
              fontSize: '16px',
              color: '#888',
            }}
          >
            ▼
          </span>
        </div>
      </header>
      <ChartContainer timeframe={timeframe} />
    </div>
  );
}

export default App;
