import React, { useState, useEffect, useCallback } from 'react';
import NiftyPriceBox from '../components/NiftyPriceBox';
import SignalPanel from '../components/SignalPanel';
import ExplanationPanel from '../components/ExplanationPanel';
import IndicatorPanel from '../components/IndicatorPanel';
import OptionsChain from '../components/OptionsChain';
import TradeTracker from '../components/TradeTracker';
import { fetchNiftyPrice, fetchCurrentSignal, fetchOptionsAnalysis, fetchActiveTrades, closeTrade } from '../api';

const POLL_INTERVAL = 3000; // 3 seconds

export default function Dashboard() {
  const [priceData, setPriceData] = useState(null);
  const [signalData, setSignalData] = useState(null);
  const [optionsData, setOptionsData] = useState(null);
  const [activeTrades, setActiveTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const fetchAll = useCallback(async () => {
    try {
      const [price, signal, options, trades] = await Promise.allSettled([
        fetchNiftyPrice(),
        fetchCurrentSignal(),
        fetchOptionsAnalysis(),
        fetchActiveTrades(),
      ]);

      if (price.status === 'fulfilled') setPriceData(price.value);
      if (signal.status === 'fulfilled') setSignalData(signal.value);
      if (options.status === 'fulfilled') setOptionsData(options.value);
      if (trades.status === 'fulfilled') setActiveTrades(trades.value?.trades || []);

      setLastUpdate(new Date());
      setLoading(false);
      setError(null);
    } catch (err) {
      setError('Failed to fetch data');
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleCloseTrade = async (tradeId, exitPrice) => {
    try {
      await closeTrade(tradeId, exitPrice);
      fetchAll();
    } catch (err) {
      console.error('Failed to close trade:', err);
    }
  };

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '60vh', color: 'var(--text-muted)',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: '40px', height: '40px', borderRadius: '50%',
            border: '3px solid var(--border-primary)',
            borderTopColor: 'var(--accent)',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 12px',
          }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          <div>Loading market data...</div>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '24px',
      }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700 }}>Dashboard</h1>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Nifty Options Trading Signals
          </p>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Last update: {lastUpdate?.toLocaleTimeString() || '—'}
          {error && <span style={{ color: 'var(--bearish)', marginLeft: '8px' }}>⚠ {error}</span>}
        </div>
      </div>

      {/* Top Row: Price Box + Signal Panel */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px'
      }}>
        <NiftyPriceBox priceData={priceData} />
        <SignalPanel signalData={signalData} />
      </div>

      {/* Middle Row: Indicators + Explanation */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px'
      }}>
        <IndicatorPanel
          marketState={signalData?.market_state}
          optionsSummary={signalData?.options_summary}
        />
        <ExplanationPanel
          explanation={signalData?.explanation}
          conditions={signalData?.conditions}
        />
      </div>

      {/* Bottom Row: Options Chain (full width) */}
      <div style={{ marginBottom: '20px' }}>
        <OptionsChain optionsData={optionsData} />
      </div>

      {/* Active Trades */}
      <TradeTracker trades={activeTrades} onCloseTrade={handleCloseTrade} />
    </div>
  );
}
