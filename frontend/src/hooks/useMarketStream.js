/**
 * useMarketStream — connects to the backend WebSocket at /ws and returns live
 * market data pushed by the server on every Angel One tick.
 *
 * Returns:
 *   priceData     — shaped like the REST /market/nifty-price response so that
 *                   NiftyPriceBox and IndicatorPanel work without changes:
 *                   { ltp, change, changePct, vwap, ema_9, ema_21, atr,
 *                     momentum, session_high, session_low, trend }
 *
 *   optionChain   — { spot_price, data: [...strikes], pcr, pcr_interpretation,
 *                     max_pain, oi_support, oi_resistance, dominant_buildup }
 *
 *   connected     — boolean: true while the socket is open
 */

import { useEffect, useRef, useState, useCallback } from 'react';

const RECONNECT_DELAY_MS = 3000;

export function useMarketStream() {
  const [priceData, setPriceData]       = useState(null);
  const [optionChain, setOptionChain]   = useState(null);
  const [connected, setConnected]       = useState(false);

  const wsRef            = useRef(null);
  const reconnectTimer   = useRef(null);
  const unmountedRef     = useRef(false);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) { ws.close(); return; }
      setConnected(true);
    };

    ws.onmessage = (e) => {
      if (unmountedRef.current) return;
      try {
        const msg = JSON.parse(e.data);

        if (msg.type === 'tick') {
          // Shape to match NiftyPriceBox / IndicatorPanel expectations
          setPriceData({
            ltp:          msg.price,
            change:       msg.change       ?? 0,
            changePct:    msg.change_pct   ?? 0,
            vwap:         msg.vwap,
            ema_9:        msg.ema_9,
            ema_21:       msg.ema_21,
            atr:          msg.atr,
            momentum:     msg.momentum     ?? 0,
            session_high: msg.session_high ?? 0,
            session_low:  msg.session_low  ?? 0,
            trend:        msg.trend        ?? {},
          });
        }

        if (msg.type === 'option_chain') {
          setOptionChain(msg);
        }
      } catch (_) {}
    };

    ws.onclose = () => {
      if (unmountedRef.current) return;
      setConnected(false);
      // Auto-reconnect after delay
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      // onclose fires right after onerror — reconnect handled there
      ws.close();
    };
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { priceData, optionChain, connected };
}
