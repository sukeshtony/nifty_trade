import React, { useState, useEffect, useCallback } from 'react';
import NiftyPriceBox from '../components/NiftyPriceBox';
import SignalPanel from '../components/SignalPanel';
import ExplanationPanel from '../components/ExplanationPanel';
import IndicatorPanel from '../components/IndicatorPanel';
import OptionsChain from '../components/OptionsChain';
import TradeTracker from '../components/TradeTracker';
import { fetchCurrentSignal, fetchOptionsAnalysis, fetchActiveTrades, closeTrade } from '../api';
import { useMarketStream } from '../hooks/useMarketStream';

// Signals and options are expensive — poll infrequently
const SIGNAL_INTERVAL  = 15000;  // 15 s
const OPTIONS_INTERVAL = 30000;  // 30 s
const TRADES_INTERVAL  = 10000;  // 10 s

export default function Dashboard() {
  const [signalData, setSignalData]     = useState(null);
  const [optionsData, setOptionsData]   = useState(null);
  const [activeTrades, setActiveTrades] = useState([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [lastUpdate, setLastUpdate]     = useState(null);

  // ── Live data from WebSocket (price + indicators + option chain) ──
  const { priceData, optionChain, connected } = useMarketStream();

  // Prefer WebSocket price data for NiftyPriceBox — instant updates on every tick
  // Prefer WebSocket option chain for OptionsChain panel — live LTPs every 10 s
  // Fall back to REST data when WebSocket hasn't received anything yet

  const liveMarketState = priceData
    ? {
        price:    priceData.ltp,
        vwap:     priceData.vwap,
        ema_9:    priceData.ema_9,
        ema_21:   priceData.ema_21,
        candle_ema_9: signalData?.market_state?.candle_ema_9,
        candle_ema_21: signalData?.market_state?.candle_ema_21,
        atr:      priceData.atr,
        momentum: priceData.momentum,
      }
    : signalData?.market_state;

  const liveOptionsSummary = optionChain
    ? {
        pcr:          optionChain.pcr,
        max_pain:     optionChain.max_pain,
        oi_support:   optionChain.oi_support,
        oi_resistance: optionChain.oi_resistance,
      }
    : signalData?.options_summary;

  // Build an optionsData shape compatible with <OptionsChain> from the WS message
  const liveOptionsData = optionChain
    ? {
        spot_price:        optionChain.spot_price,
        strikes:           optionChain.data,
        pcr:               optionChain.pcr,
        pcr_interpretation: optionChain.pcr_interpretation,
        max_pain:          optionChain.max_pain,
        oi_support:        optionChain.oi_support,
        oi_resistance:     optionChain.oi_resistance,
        dominant_buildup:  optionChain.dominant_buildup,
      }
    : optionsData;

  // ── REST polling — only for slow-changing data ──────────────────────────────

  const fetchSignal = useCallback(async () => {
    try {
      const data = await fetchCurrentSignal();
      setSignalData(data);
      setError(null);
    } catch (err) {
      setError('Signal fetch failed');
    }
  }, []);

  const fetchOptions = useCallback(async () => {
    try {
      const data = await fetchOptionsAnalysis();
      setOptionsData(data);
    } catch (_) {}
  }, []);

  const fetchTrades = useCallback(async () => {
    try {
      const data = await fetchActiveTrades();
      setActiveTrades(data?.trades || []);
    } catch (_) {}
  }, []);

  // Initial load — fetch everything once so page isn't blank before first WS tick
  useEffect(() => {
    (async () => {
      await Promise.allSettled([fetchSignal(), fetchOptions(), fetchTrades()]);
      setLoading(false);
      setLastUpdate(new Date());
    })();
  }, [fetchSignal, fetchOptions, fetchTrades]);

  // Slow REST polling — signals, options REST backup, trades
  useEffect(() => {
    const s = setInterval(fetchSignal,  SIGNAL_INTERVAL);
    const o = setInterval(fetchOptions, OPTIONS_INTERVAL);
    const t = setInterval(fetchTrades,  TRADES_INTERVAL);
    return () => { clearInterval(s); clearInterval(o); clearInterval(t); };
  }, [fetchSignal, fetchOptions, fetchTrades]);

  // Update "last update" timestamp on every WebSocket tick
  useEffect(() => {
    if (priceData) setLastUpdate(new Date());
  }, [priceData]);

  const handleCloseTrade = async (tradeId, exitPrice) => {
    try {
      await closeTrade(tradeId, exitPrice);
      fetchTrades();
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', color: 'var(--text-muted)' }}>
          {/* WebSocket connection indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{
              width: '7px', height: '7px', borderRadius: '50%',
              background: connected ? 'var(--success)' : 'var(--danger)',
              display: 'inline-block',
            }} />
            <span>{connected ? 'Live' : 'Reconnecting...'}</span>
          </div>
          <span>Updated: {lastUpdate?.toLocaleTimeString() || '—'}</span>
          {error && <span style={{ color: 'var(--danger)' }}>⚠ {error}</span>}
        </div>
      </div>

      {/* Top Row: Price Box + Signal Panel */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px',
      }}>
        {/* priceData from WebSocket — NiftyPriceBox gets tick-level updates */}
        <NiftyPriceBox priceData={priceData || signalData?.market_state && {
          ltp:          signalData.market_state.price,
          change:       0,
          changePct:    0,
          session_high: 0,
          session_low:  0,
        }} />
        <SignalPanel signalData={signalData} />
      </div>

      {/* Middle Row: Indicators + Explanation */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px',
      }}>
        <IndicatorPanel
          marketState={liveMarketState}
          optionsSummary={liveOptionsSummary}
        />
        <ExplanationPanel
          explanation={signalData?.explanation}
          conditions={signalData?.conditions}
        />
      </div>

      {/* Options Chain — live from WebSocket, falls back to REST */}
      <div style={{ marginBottom: '20px' }}>
        <OptionsChain optionsData={liveOptionsData} />
      </div>

      {/* Active Trades */}
      <TradeTracker trades={activeTrades} onCloseTrade={handleCloseTrade} />
    </div>
  );
}
