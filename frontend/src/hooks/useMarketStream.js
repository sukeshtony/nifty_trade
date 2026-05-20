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
 *   depthData     — object keyed by instrument label (e.g. "NIFTY", "NIFTY_FUT",
 *                   "NIFTY 24850 CE") containing the latest depth payload:
 *                   { label, ltp, buy_depth, sell_depth, total_buy_qty,
 *                     total_sell_qty, obi, pressure, bid_ask_spread }
 *
 *   connected     — boolean: true while the socket is open
 */

import { useEffect, useRef, useState, useCallback } from 'react';

const RECONNECT_DELAY_MS = 3000;

export function useMarketStream() {
  const [priceData, setPriceData]       = useState(null);
  const [optionChain, setOptionChain]   = useState(null);
  const [depthData, setDepthData]       = useState({});   // { [label]: payload }
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

        if (msg.type === 'depth') {
          // Update just the one instrument that arrived — preserve others
          const label = msg.label || msg.token;
          setDepthData(prev => ({
            ...prev,
            [label]: {
              label:          msg.label,
              ltp:            msg.ltp          ?? 0,
              buy_depth:      msg.buy_depth    ?? [],
              sell_depth:     msg.sell_depth   ?? [],
              total_buy_qty:  msg.total_buy_qty  ?? 0,
              total_sell_qty: msg.total_sell_qty ?? 0,
              obi:            msg.obi          ?? 0,
              pressure:       msg.pressure     ?? 'NEUTRAL',
              bid_ask_spread: msg.bid_ask_spread ?? 0,
            },
          }));
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

  return { priceData, optionChain, depthData, connected };
}
