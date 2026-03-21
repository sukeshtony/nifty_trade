import React, { useState, useEffect, useCallback } from 'react';
import { ArrowRightLeft, Plus, Trophy, TrendingUp, TrendingDown, XCircle } from 'lucide-react';
import { createTrade, fetchTradeHistory, fetchTradeSummary, fetchActiveTrades, closeTrade } from '../api';

export default function Trades() {
  const [history, setHistory] = useState([]);
  const [summary, setSummary] = useState(null);
  const [activeTrades, setActiveTrades] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    symbol: 'NIFTY', strike: '', option_type: 'CE',
    entry_price: '', qty: 25, trade_type: 'INTRADAY', notes: ''
  });

  const loadData = useCallback(async () => {
    try {
      const [hist, sum, active] = await Promise.allSettled([
        fetchTradeHistory(), fetchTradeSummary(), fetchActiveTrades(),
      ]);
      if (hist.status === 'fulfilled') setHistory(hist.value?.trades || []);
      if (sum.status === 'fulfilled') setSummary(sum.value);
      if (active.status === 'fulfilled') setActiveTrades(active.value?.trades || []);
    } catch (err) { console.error(err); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await createTrade({
        ...form,
        strike: parseInt(form.strike),
        entry_price: parseFloat(form.entry_price),
        qty: parseInt(form.qty),
      });
      setShowForm(false);
      setForm({ symbol: 'NIFTY', strike: '', option_type: 'CE', entry_price: '', qty: 25, trade_type: 'INTRADAY', notes: '' });
      loadData();
    } catch (err) { console.error('Failed to create trade:', err); }
  };

  const handleClose = async (tradeId, exitPrice) => {
    try {
      await closeTrade(tradeId, exitPrice);
      loadData();
    } catch (err) { console.error(err); }
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700 }}>
            <ArrowRightLeft size={20} style={{ verticalAlign: 'middle', marginRight: '8px' }} />
            Trade Management
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            Record, track, and analyze your trades
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={14} /> New Trade
        </button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '12px', marginBottom: '20px' }}>
          {[
            { label: 'Total Trades', value: summary.total_trades, icon: ArrowRightLeft },
            { label: 'Win Rate', value: `${summary.win_rate}%`, icon: Trophy, color: summary.win_rate >= 50 ? 'var(--bullish)' : 'var(--bearish)' },
            { label: 'Total P&L', value: `₹${summary.total_pnl?.toFixed(0)}`, icon: summary.total_pnl >= 0 ? TrendingUp : TrendingDown, color: summary.total_pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)' },
            { label: 'Net P&L', value: `₹${summary.total_net_pnl?.toFixed(0)}`, icon: summary.total_net_pnl >= 0 ? TrendingUp : TrendingDown, color: summary.total_net_pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)' },
            { label: 'Winning', value: summary.winning, color: 'var(--bullish)' },
            { label: 'Losing', value: summary.losing, color: 'var(--bearish)' },
          ].map((item, i) => (
            <div key={i} className="card" style={{ padding: '14px' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{item.label}</div>
              <div className="text-mono" style={{ fontSize: '18px', fontWeight: 700, color: item.color || 'var(--text-primary)', marginTop: '4px' }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* New Trade Form */}
      {showForm && (
        <div className="card" style={{ marginBottom: '20px' }}>
          <div className="card-title" style={{ marginBottom: '14px' }}>Record New Trade</div>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px' }}>
            <div className="form-group">
              <label className="form-label">Strike</label>
              <input type="number" className="form-input" value={form.strike} onChange={(e) => setForm({ ...form, strike: e.target.value })} required />
            </div>
            <div className="form-group">
              <label className="form-label">Type</label>
              <select className="form-select" value={form.option_type} onChange={(e) => setForm({ ...form, option_type: e.target.value })}>
                <option value="CE">CE (Call)</option>
                <option value="PE">PE (Put)</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Entry Price</label>
              <input type="number" step="0.05" className="form-input" value={form.entry_price} onChange={(e) => setForm({ ...form, entry_price: e.target.value })} required />
            </div>
            <div className="form-group">
              <label className="form-label">Quantity</label>
              <input type="number" className="form-input" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Trade Type</label>
              <select className="form-select" value={form.trade_type} onChange={(e) => setForm({ ...form, trade_type: e.target.value })}>
                <option value="INTRADAY">Intraday</option>
                <option value="POSITIONAL">Positional</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input type="text" className="form-input" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Optional" />
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
              <button type="submit" className="btn btn-success">Record Trade</button>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Active Trades */}
      {activeTrades.length > 0 && (
        <div className="card" style={{ marginBottom: '20px' }}>
          <div className="card-title" style={{ marginBottom: '14px' }}>Open Positions</div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th><th>Strike</th><th>Type</th><th>Entry</th><th>Qty</th><th>Trade Type</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {activeTrades.map((t) => (
                <tr key={t.id}>
                  <td>{t.symbol}</td>
                  <td>{t.strike}</td>
                  <td style={{ color: t.option_type === 'CE' ? 'var(--bullish)' : 'var(--bearish)' }}>{t.option_type}</td>
                  <td>₹{t.entry_price}</td>
                  <td>{t.qty}</td>
                  <td>{t.trade_type}</td>
                  <td>
                    <button className="btn btn-danger" style={{ padding: '3px 10px', fontSize: '11px' }}
                      onClick={() => {
                        const exit = prompt('Enter exit price:');
                        if (exit) handleClose(t.id, parseFloat(exit));
                      }}>
                      <XCircle size={12} /> Close
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Trade History */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: '14px' }}>Trade History</div>
        {history.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', fontSize: '13px' }}>
            No completed trades yet
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th><th>Strike</th><th>Type</th><th>Entry</th><th>Exit</th><th>Qty</th><th>P&L</th><th>Net P&L</th><th>Date</th>
              </tr>
            </thead>
            <tbody>
              {history.map((t) => (
                <tr key={t.id}>
                  <td>{t.symbol}</td>
                  <td>{t.strike}</td>
                  <td style={{ color: t.option_type === 'CE' ? 'var(--bullish)' : 'var(--bearish)' }}>{t.option_type}</td>
                  <td>₹{t.entry_price}</td>
                  <td>₹{t.exit_price}</td>
                  <td>{t.qty}</td>
                  <td style={{ color: t.pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)', fontWeight: 600 }}>
                    {t.pnl >= 0 ? '+' : ''}₹{t.pnl?.toFixed(2)}
                  </td>
                  <td style={{ color: t.net_pnl >= 0 ? 'var(--bullish)' : 'var(--bearish)', fontWeight: 600 }}>
                    {t.net_pnl >= 0 ? '+' : ''}₹{t.net_pnl?.toFixed(2)}
                  </td>
                  <td style={{ fontSize: '11px' }}>{t.exit_time ? new Date(t.exit_time).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
