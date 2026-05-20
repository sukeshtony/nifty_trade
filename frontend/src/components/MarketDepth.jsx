/**
 * MarketDepth — Real-time order book depth widget.
 *
 * Props:
 *   depthData  — from useMarketStream().depthData
 *                Object keyed by instrument label → depth payload
 */

import React, { useState, useMemo } from 'react';

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmtQty = (n) => {
  if (!n) return '0';
  if (n >= 1_00_000) return `${(n / 1_00_000).toFixed(1)}L`;
  if (n >= 1_000)    return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
};

const fmtPrice = (p) => p ? p.toFixed(2) : '—';

const PRESSURE_META = {
  STRONG_BUY:  { label: 'Strong Buy Pressure',  color: '#00e676', bg: 'rgba(0,230,118,0.15)' },
  MILD_BUY:    { label: 'Mild Buy Pressure',     color: '#69f0ae', bg: 'rgba(105,240,174,0.10)' },
  NEUTRAL:     { label: 'Neutral',               color: '#90a4ae', bg: 'rgba(144,164,174,0.08)' },
  MILD_SELL:   { label: 'Mild Sell Pressure',    color: '#ff6e6e', bg: 'rgba(255,110,110,0.10)' },
  STRONG_SELL: { label: 'Strong Sell Pressure',  color: '#ff1744', bg: 'rgba(255,23,68,0.15)' },
};

// ── OBI Gauge ────────────────────────────────────────────────────────────────

function OBIGauge({ obi }) {
  // obi is -1 to +1; map to 0-100 for display
  const pct = Math.round(((obi + 1) / 2) * 100);
  const color = obi > 0.08 ? '#00e676' : obi < -0.08 ? '#ff1744' : '#90a4ae';

  return (
    <div style={{ width: '100%' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: 10, color: 'var(--text-muted)', marginBottom: 3,
      }}>
        <span>Sell</span>
        <span style={{ color, fontWeight: 700 }}>OBI {obi > 0 ? '+' : ''}{obi.toFixed(3)}</span>
        <span>Buy</span>
      </div>
      <div style={{
        height: 8, borderRadius: 4,
        background: 'linear-gradient(to right, #ff1744, #37474f, #00e676)',
        position: 'relative', overflow: 'visible',
      }}>
        {/* needle */}
        <div style={{
          position: 'absolute', top: -3, left: `calc(${pct}% - 2px)`,
          width: 4, height: 14, borderRadius: 2,
          background: color, boxShadow: `0 0 6px ${color}`,
          transition: 'left 0.4s ease',
        }} />
      </div>
    </div>
  );
}

// ── Depth Level Rows ─────────────────────────────────────────────────────────

function DepthLevels({ buyLevels = [], sellLevels = [], maxQty }) {
  const rows = Math.max(buyLevels.length, sellLevels.length, 5);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: '2px 8px', alignItems: 'center' }}>
      {/* Headers */}
      <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'right', paddingBottom: 4 }}>Qty</div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', paddingBottom: 4 }}>Price</div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'left', paddingBottom: 4 }}>Qty</div>

      {Array.from({ length: rows }).map((_, i) => {
        const buy  = buyLevels[i];
        const sell = sellLevels[i];
        const buyPct  = buy  && maxQty ? (buy.quantity  / maxQty) * 100 : 0;
        const sellPct = sell && maxQty ? (sell.quantity / maxQty) * 100 : 0;

        return (
          <React.Fragment key={i}>
            {/* Buy side */}
            <div style={{ position: 'relative', textAlign: 'right' }}>
              {buy && (
                <>
                  <div style={{
                    position: 'absolute', right: 0, top: 0, bottom: 0,
                    width: `${buyPct}%`, background: 'rgba(0,230,118,0.12)',
                    borderRadius: '3px 0 0 3px',
                    transition: 'width 0.3s ease',
                  }} />
                  <span style={{
                    position: 'relative', fontSize: 11, fontWeight: 600,
                    color: '#00e676', fontFamily: 'monospace', padding: '2px 4px',
                  }}>
                    {fmtQty(buy.quantity)}
                  </span>
                </>
              )}
            </div>

            {/* Price (center) */}
            <div style={{
              fontSize: 11, textAlign: 'center', fontFamily: 'monospace',
              color: buy ? '#00e676' : sell ? '#ff4444' : 'var(--text-muted)',
              padding: '1px 6px', background: 'var(--surface-2)', borderRadius: 3,
            }}>
              {buy ? fmtPrice(buy.price) : sell ? fmtPrice(sell.price) : '—'}
            </div>

            {/* Sell side */}
            <div style={{ position: 'relative', textAlign: 'left' }}>
              {sell && (
                <>
                  <div style={{
                    position: 'absolute', left: 0, top: 0, bottom: 0,
                    width: `${sellPct}%`, background: 'rgba(255,68,68,0.12)',
                    borderRadius: '0 3px 3px 0',
                    transition: 'width 0.3s ease',
                  }} />
                  <span style={{
                    position: 'relative', fontSize: 11, fontWeight: 600,
                    color: '#ff4444', fontFamily: 'monospace', padding: '2px 4px',
                  }}>
                    {fmtQty(sell.quantity)}
                  </span>
                </>
              )}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Single Instrument Card ────────────────────────────────────────────────────

function InstrumentDepthCard({ payload }) {
  if (!payload) return null;

  const {
    label, ltp, buy_depth = [], sell_depth = [],
    total_buy_qty = 0, total_sell_qty = 0,
    obi = 0, pressure = 'NEUTRAL', bid_ask_spread = 0,
  } = payload;

  const meta   = PRESSURE_META[pressure] || PRESSURE_META.NEUTRAL;
  const maxQty = Math.max(
    ...buy_depth.map(l => l.quantity || 0),
    ...sell_depth.map(l => l.quantity || 0),
    1,
  );

  const isOption = label && (label.includes(' CE') || label.includes(' PE'));
  const labelColor = label?.includes(' CE') ? '#00e676'
    : label?.includes(' PE') ? '#ff4444'
    : label === 'NIFTY_FUT' ? '#64b5f6'
    : 'var(--text-primary)';

  return (
    <div className="card" style={{
      padding: '14px 16px',
      background: meta.bg,
      border: `1px solid ${meta.color}22`,
      transition: 'border-color 0.3s',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div>
          <span style={{ fontSize: 13, fontWeight: 700, color: labelColor }}>{label}</span>
          {ltp > 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>
              LTP ₹{fmtPrice(ltp)}
            </span>
          )}
        </div>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '2px 8px',
          borderRadius: 10, background: meta.bg, color: meta.color,
          border: `1px solid ${meta.color}44`,
        }}>
          {meta.label}
        </span>
      </div>

      {/* Total buy / sell bar */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
        <div style={{ background: 'rgba(0,230,118,0.1)', borderRadius: 6, padding: '6px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: '#00e676', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Total Buy Qty
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#00e676', fontFamily: 'monospace' }}>
            {fmtQty(total_buy_qty)}
          </div>
        </div>
        <div style={{ background: 'rgba(255,68,68,0.1)', borderRadius: 6, padding: '6px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: 9, color: '#ff4444', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Total Sell Qty
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#ff4444', fontFamily: 'monospace' }}>
            {fmtQty(total_sell_qty)}
          </div>
        </div>
      </div>

      {/* OBI gauge */}
      <div style={{ marginBottom: 12 }}>
        <OBIGauge obi={obi} />
      </div>

      {/* Top-5 depth levels */}
      {(buy_depth.length > 0 || sell_depth.length > 0) ? (
        <DepthLevels buyLevels={buy_depth} sellLevels={sell_depth} maxQty={maxQty} />
      ) : (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          Waiting for depth data…
        </div>
      )}

      {/* Spread */}
      {bid_ask_spread > 0 && (
        <div style={{
          marginTop: 8, fontSize: 10, color: 'var(--text-muted)',
          display: 'flex', justifyContent: 'flex-end',
        }}>
          Spread: <span style={{ color: 'var(--text-primary)', marginLeft: 4, fontFamily: 'monospace' }}>
            {bid_ask_spread.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Tab button ───────────────────────────────────────────────────────────────

function TabBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      background: active ? 'var(--accent)' : 'transparent',
      border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
      color: active ? '#000' : 'var(--text-muted)',
      borderRadius: 6, padding: '4px 12px',
      fontSize: 11, fontWeight: active ? 700 : 400,
      cursor: 'pointer', transition: 'all 0.15s',
      whiteSpace: 'nowrap',
    }}>
      {children}
    </button>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function MarketDepth({ depthData = {} }) {
  const [activeTab, setActiveTab] = useState('all');

  const labels    = Object.keys(depthData);
  const hasData   = labels.length > 0;

  // Tabs: "all" + one per instrument
  const allLabels = useMemo(() => {
    // Order: NIFTY → NIFTY_FUT → CE options → PE options
    const order = ['NIFTY', 'NIFTY_FUT'];
    const opts  = labels.filter(l => !order.includes(l)).sort();
    return [...order.filter(l => labels.includes(l)), ...opts];
  }, [labels]);

  const displayLabels = activeTab === 'all'
    ? allLabels
    : allLabels.filter(l => l === activeTab);

  return (
    <div className="card" style={{ padding: '16px 18px' }}>
      {/* Title */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 16 }}>📊</span> Order Book Depth
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
            Live top-5 bid/ask · quantity (contracts) · buy/sell pressure
          </div>
        </div>
        {hasData && (
          <span style={{
            fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
            background: 'rgba(0,230,118,0.12)', color: '#00e676',
            border: '1px solid rgba(0,230,118,0.3)',
            animation: 'pulse 2s infinite',
          }}>
            ● LIVE
          </span>
        )}
      </div>

      {/* Tabs */}
      {allLabels.length > 1 && (
        <div style={{
          display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12,
          paddingBottom: 10, borderBottom: '1px solid var(--border)',
        }}>
          <TabBtn active={activeTab === 'all'} onClick={() => setActiveTab('all')}>All</TabBtn>
          {allLabels.map(l => (
            <TabBtn key={l} active={activeTab === l} onClick={() => setActiveTab(l)}>
              {l}
            </TabBtn>
          ))}
        </div>
      )}

      {!hasData ? (
        <div style={{
          textAlign: 'center', padding: '28px 0', color: 'var(--text-muted)',
          fontSize: 12,
        }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>📡</div>
          Waiting for WebSocket depth data…
          <div style={{ fontSize: 10, marginTop: 4, opacity: 0.6 }}>
            Requires mode=3 SNAP_QUOTE subscription on Angel One
          </div>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: displayLabels.length === 1
            ? '1fr'
            : 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 12,
        }}>
          {displayLabels.map(label => (
            <InstrumentDepthCard key={label} payload={depthData[label]} />
          ))}
        </div>
      )}
    </div>
  );
}
