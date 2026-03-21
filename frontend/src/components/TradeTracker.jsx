import React, { memo, useState } from 'react';
import { Briefcase, X, ArrowUpRight, ArrowDownRight } from 'lucide-react';

const TradeTracker = memo(({ trades, onCloseTrade }) => {
  const [closingId, setClosingId] = useState(null);
  const [exitPrice, setExitPrice] = useState('');

  const handleClose = (tradeId) => {
    if (exitPrice && onCloseTrade) {
      onCloseTrade(tradeId, parseFloat(exitPrice));
      setClosingId(null);
      setExitPrice('');
    }
  };

  return (
    <div className="card" id="trade-tracker">
      <div className="card-header">
        <span className="card-title">
          <Briefcase size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Active Trades
        </span>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          {trades?.length || 0} open
        </span>
      </div>

      {(!trades || trades.length === 0) ? (
        <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', fontSize: '13px' }}>
          No active trades
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {trades.map((trade) => {
            const isProfit = (trade.live_pnl || 0) >= 0;
            return (
              <div key={trade.id} style={{
                padding: '14px',
                background: 'var(--bg-elevated)',
                borderRadius: 'var(--radius-sm)',
                border: `1px solid ${isProfit ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '14px' }}>
                      {trade.symbol} {trade.strike} {trade.option_type}
                    </span>
                    <span style={{
                      marginLeft: '8px', fontSize: '11px', padding: '2px 8px',
                      borderRadius: '4px',
                      background: trade.option_type === 'CE' ? 'var(--bullish-soft)' : 'var(--bearish-soft)',
                      color: trade.option_type === 'CE' ? 'var(--bullish)' : 'var(--bearish)',
                    }}>
                      {trade.option_type}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="text-mono" style={{
                      fontSize: '16px', fontWeight: 700,
                      color: isProfit ? 'var(--bullish)' : 'var(--bearish)',
                    }}>
                      {isProfit ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {' '}₹{Math.abs(trade.live_pnl || trade.pnl || 0).toFixed(2)}
                    </span>
                    {closingId === trade.id ? (
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <input
                          type="number"
                          step="0.05"
                          placeholder="Exit"
                          value={exitPrice}
                          onChange={(e) => setExitPrice(e.target.value)}
                          className="form-input"
                          style={{ width: '80px', padding: '4px 8px', fontSize: '12px' }}
                        />
                        <button className="btn btn-success" style={{ padding: '4px 8px', fontSize: '11px' }}
                          onClick={() => handleClose(trade.id)}>OK</button>
                        <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '11px' }}
                          onClick={() => setClosingId(null)}><X size={12} /></button>
                      </div>
                    ) : (
                      <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: '11px' }}
                        onClick={() => setClosingId(trade.id)}>Close</button>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span>Entry: <span className="text-mono">₹{trade.entry_price}</span></span>
                  <span>Qty: <span className="text-mono">{trade.qty}</span></span>
                  <span>Type: {trade.trade_type}</span>
                  {trade.entry_time && <span>Time: {new Date(trade.entry_time).toLocaleTimeString()}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});

TradeTracker.displayName = 'TradeTracker';
export default TradeTracker;
