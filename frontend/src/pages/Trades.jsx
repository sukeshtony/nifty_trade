import React, { useState, useEffect, useCallback } from 'react';
import {
  ArrowRightLeft, Plus, Trophy, TrendingUp, TrendingDown,
  XCircle, RefreshCw, IndianRupee, Wallet, ChevronDown, ChevronRight,
  Activity, AlertCircle, CheckCircle
} from 'lucide-react';
import {
  createTrade, fetchTradeHistory, fetchTradeSummary, fetchActiveTrades, closeTrade,
  fetchAngelTradeHistory, fetchAngelTradeSummary, syncAngelTrades, fetchAngelPositions,
} from '../api';

// ── Helpers ────────────────────────────────────────────────────────────────────

const fmt = (v, decimals = 2) => (v ?? 0).toFixed(decimals);
const pnlColor = (v) => (v >= 0 ? 'var(--bullish)' : 'var(--bearish)');
const pnlSign  = (v) => (v >= 0 ? '+' : '');

function SummaryCard({ label, value, color, sub }) {
  return (
    <div className="card" style={{ padding: '14px' }}>
      <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{label}</div>
      <div className="text-mono" style={{ fontSize: '18px', fontWeight: 700, color: color || 'var(--text-primary)', marginTop: '4px' }}>{value}</div>
      {sub && <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>{sub}</div>}
    </div>
  );
}

// ── Charge Breakdown Row (expandable) ─────────────────────────────────────────

function ChargeRow({ trade }) {
  const [open, setOpen] = useState(false);
  const c = trade.charges || {};
  return (
    <>
      <tr
        style={{ cursor: 'pointer', opacity: 0.92 }}
        onClick={() => setOpen(!open)}
      >
        <td style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{trade.symbol}</td>
        <td style={{ fontWeight: 600 }}>{trade.strike}</td>
        <td style={{ color: trade.option_type === 'CE' ? 'var(--bullish)' : 'var(--bearish)', fontWeight: 700 }}>
          {trade.option_type}
        </td>
        <td>₹{fmt(trade.entry_price)}</td>
        <td>₹{fmt(trade.exit_price)}</td>
        <td>{trade.qty} <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>({trade.lots}L)</span></td>
        <td style={{ color: pnlColor(trade.gross_pnl), fontWeight: 600 }}>
          {pnlSign(trade.gross_pnl)}₹{fmt(trade.gross_pnl)}
        </td>
        <td>
          <span style={{ color: 'var(--bearish)', fontSize: '12px' }}>₹{fmt(c.total)}</span>
          <span style={{ marginLeft: 4 }}>{open ? <ChevronDown size={10}/> : <ChevronRight size={10}/>}</span>
        </td>
        <td style={{ color: pnlColor(trade.net_pnl), fontWeight: 700 }}>
          {pnlSign(trade.net_pnl)}₹{fmt(trade.net_pnl)}
        </td>
        <td style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
          {trade.entry_time ? new Date(trade.entry_time).toLocaleString('en-IN', { hour12: false, month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '—'}
        </td>
      </tr>
      {open && (
        <tr style={{ background: 'var(--surface-2)' }}>
          <td colSpan={10} style={{ padding: '10px 16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '8px', fontSize: '11px' }}>
              {[
                ['Brokerage', c.brokerage],
                ['STT', c.stt],
                ['Exch. Charge', c.exchange_charge],
                ['GST (18%)', c.gst],
                ['SEBI Fee', c.sebi_fee],
                ['Stamp Duty', c.stamp_duty],
              ].map(([lbl, val]) => (
                <div key={lbl} style={{ background: 'var(--surface)', borderRadius: 6, padding: '6px 10px' }}>
                  <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>{lbl}</div>
                  <div style={{ fontWeight: 600, color: 'var(--bearish)' }}>₹{(val ?? 0).toFixed(4)}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 8, fontSize: '11px', color: 'var(--text-muted)' }}>
              Order IDs: Buy <code>{trade.buy_order_id}</code> · Sell <code>{trade.sell_order_id}</code>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Angel One Tab ──────────────────────────────────────────────────────────────

function AngelTab() {
  const [trades, setTrades]     = useState([]);
  const [summary, setSummary]   = useState(null);
  const [positions, setPositions] = useState([]);
  const [syncing, setSyncing]   = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [filter, setFilter]     = useState('ALL');
  const [loading, setLoading]   = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const optType = filter === 'ALL' ? null : filter;
      const [hist, sum, pos] = await Promise.allSettled([
        fetchAngelTradeHistory(100, optType),
        fetchAngelTradeSummary(),
        fetchAngelPositions(),
      ]);
      if (hist.status === 'fulfilled') setTrades(hist.value?.trades || []);
      if (sum.status  === 'fulfilled') setSummary(sum.value);
      if (pos.status  === 'fulfilled') setPositions(pos.value?.positions || []);
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true); setSyncResult(null);
    try {
      const res = await syncAngelTrades();
      setSyncResult(res);
      await load();
    } catch (e) {
      setSyncResult({ status: 'error', reason: String(e) });
    } finally { setSyncing(false); }
  };

  const cb = summary?.charge_breakdown || {};

  return (
    <div>
      {/* Top Action Bar */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        <button className="btn btn-primary" onClick={handleSync} disabled={syncing} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />
          {syncing ? 'Syncing…' : 'Sync from Angel One'}
        </button>
        <div style={{ display: 'flex', gap: 6 }}>
          {['ALL', 'CE', 'PE'].map(f => (
            <button key={f} className={`btn ${filter === f ? 'btn-primary' : 'btn-ghost'}`}
              style={{ padding: '4px 12px', fontSize: '12px' }} onClick={() => setFilter(f)}>
              {f}
            </button>
          ))}
        </div>
        {syncResult && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, fontSize: '12px', padding: '4px 10px',
            borderRadius: 6, background: syncResult.status === 'ok' ? 'rgba(0,200,83,0.1)' : 'rgba(255,82,82,0.1)',
            color: syncResult.status === 'ok' ? 'var(--bullish)' : 'var(--bearish)',
          }}>
            {syncResult.status === 'ok'
              ? <><CheckCircle size={12}/> {syncResult.inserted} new · {syncResult.skipped} skipped</>
              : <><AlertCircle size={12}/> {syncResult.reason}</>}
          </div>
        )}
      </div>

      {/* Summary Cards */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, marginBottom: 18 }}>
          <SummaryCard label="Total Trades" value={summary.total_trades} />
          <SummaryCard label="Win Rate" value={`${summary.win_rate}%`}
            color={summary.win_rate >= 50 ? 'var(--bullish)' : 'var(--bearish)'}
            sub={`${summary.winning}W / ${summary.losing}L`} />
          <SummaryCard label="Gross P&L" value={`${pnlSign(summary.gross_pnl)}₹${fmt(summary.gross_pnl)}`}
            color={pnlColor(summary.gross_pnl)} />
          <SummaryCard label="Total Charges" value={`₹${fmt(summary.total_charges)}`} color="var(--bearish)" />
          <SummaryCard label="Net P&L" value={`${pnlSign(summary.net_pnl)}₹${fmt(summary.net_pnl)}`}
            color={pnlColor(summary.net_pnl)} sub="After all charges" />
          <SummaryCard label="Avg Net P&L" value={`${pnlSign(summary.avg_net_pnl)}₹${fmt(summary.avg_net_pnl)}`}
            color={pnlColor(summary.avg_net_pnl)} />
        </div>
      )}

      {/* Charge Breakdown Card */}
      {summary?.total_trades > 0 && (
        <div className="card" style={{ marginBottom: 18, padding: 16 }}>
          <div className="card-title" style={{ marginBottom: 12, fontSize: 13 }}>
            <IndianRupee size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            Cumulative Charges Breakdown
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 8 }}>
            {[
              ['Brokerage', cb.brokerage, '₹20 flat × 2 legs'],
              ['STT',       cb.stt,       '0.05% sell side'],
              ['Exch. Charge', cb.exchange_charge, '0.053% turnover'],
              ['GST (18%)', cb.gst,       'on brokerage+exch'],
              ['SEBI Fee',  cb.sebi_fee,  '₹10/cr turnover'],
              ['Stamp Duty', cb.stamp_duty, '0.003% buy side'],
            ].map(([lbl, val, hint]) => (
              <div key={lbl} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{lbl}</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--bearish)' }}>₹{(val ?? 0).toFixed(2)}</div>
                <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{hint}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open Positions */}
      {positions.length > 0 && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="card-title" style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Activity size={13} /> Open Positions (Live)
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th><th>Net Qty</th><th>Buy Avg</th><th>Sell Avg</th>
                <th>Realised P&L</th><th>Unrealised P&L</th><th>Total P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i}>
                  <td style={{ fontSize: 11 }}>{p.symbol}</td>
                  <td style={{ color: p.net_qty >= 0 ? 'var(--bullish)' : 'var(--bearish)', fontWeight: 600 }}>{p.net_qty}</td>
                  <td>₹{fmt(p.buy_avg_price)}</td>
                  <td>₹{fmt(p.sell_avg_price)}</td>
                  <td style={{ color: pnlColor(p.realised_pnl), fontWeight: 600 }}>{pnlSign(p.realised_pnl)}₹{fmt(p.realised_pnl)}</td>
                  <td style={{ color: pnlColor(p.unrealised_pnl), fontWeight: 600 }}>{pnlSign(p.unrealised_pnl)}₹{fmt(p.unrealised_pnl)}</td>
                  <td style={{ color: pnlColor(p.total_pnl), fontWeight: 700 }}>{pnlSign(p.total_pnl)}₹{fmt(p.total_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Trade History Table */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 12, fontSize: 13 }}>
          Closed Trades — click a row to expand charge breakdown
        </div>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>Loading…</div>
        ) : trades.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)', fontSize: 13 }}>
            No synced trades yet. Click <strong>Sync from Angel One</strong> above.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th><th>Strike</th><th>Type</th><th>Entry</th><th>Exit</th>
                  <th>Qty</th><th>Gross P&L</th><th>Charges ↕</th><th>Net P&L</th><th>Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => <ChargeRow key={t.id} trade={t} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Manual Trades Tab ─────────────────────────────────────────────────────────

function ManualTab() {
  const [history, setHistory]         = useState([]);
  const [summary, setSummary]         = useState(null);
  const [activeTrades, setActiveTrades] = useState([]);
  const [showForm, setShowForm]       = useState(false);
  const [form, setForm] = useState({
    symbol: 'NIFTY', strike: '', option_type: 'CE',
    entry_price: '', qty: 25, trade_type: 'INTRADAY', notes: '',
  });

  const loadData = useCallback(async () => {
    try {
      const [hist, sum, active] = await Promise.allSettled([
        fetchTradeHistory(), fetchTradeSummary(), fetchActiveTrades(),
      ]);
      if (hist.status   === 'fulfilled') setHistory(hist.value?.trades || []);
      if (sum.status    === 'fulfilled') setSummary(sum.value);
      if (active.status === 'fulfilled') setActiveTrades(active.value?.trades || []);
    } catch (err) { console.error(err); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await createTrade({ ...form, strike: parseInt(form.strike), entry_price: parseFloat(form.entry_price), qty: parseInt(form.qty) });
      setShowForm(false);
      setForm({ symbol: 'NIFTY', strike: '', option_type: 'CE', entry_price: '', qty: 25, trade_type: 'INTRADAY', notes: '' });
      loadData();
    } catch (err) { console.error(err); }
  };

  const handleClose = async (tradeId, exitPrice) => {
    try { await closeTrade(tradeId, exitPrice); loadData(); } catch (err) { console.error(err); }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={14} /> New Trade
        </button>
      </div>

      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, marginBottom: 18 }}>
          <SummaryCard label="Total Trades" value={summary.total_trades} />
          <SummaryCard label="Win Rate"     value={`${summary.win_rate}%`} color={summary.win_rate >= 50 ? 'var(--bullish)' : 'var(--bearish)'} />
          <SummaryCard label="Total P&L"    value={`${pnlSign(summary.total_pnl)}₹${fmt(summary.total_pnl)}`} color={pnlColor(summary.total_pnl)} />
          <SummaryCard label="Net P&L"      value={`${pnlSign(summary.total_net_pnl)}₹${fmt(summary.total_net_pnl)}`} color={pnlColor(summary.total_net_pnl)} />
          <SummaryCard label="Winning"      value={summary.winning} color="var(--bullish)" />
          <SummaryCard label="Losing"       value={summary.losing}  color="var(--bearish)" />
        </div>
      )}

      {showForm && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-title" style={{ marginBottom: 14 }}>Record New Trade</div>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Strike</label>
              <input type="number" className="form-input" value={form.strike} onChange={e => setForm({ ...form, strike: e.target.value })} required />
            </div>
            <div className="form-group">
              <label className="form-label">Type</label>
              <select className="form-select" value={form.option_type} onChange={e => setForm({ ...form, option_type: e.target.value })}>
                <option value="CE">CE (Call)</option>
                <option value="PE">PE (Put)</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Entry Price</label>
              <input type="number" step="0.05" className="form-input" value={form.entry_price} onChange={e => setForm({ ...form, entry_price: e.target.value })} required />
            </div>
            <div className="form-group">
              <label className="form-label">Quantity</label>
              <input type="number" className="form-input" value={form.qty} onChange={e => setForm({ ...form, qty: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Trade Type</label>
              <select className="form-select" value={form.trade_type} onChange={e => setForm({ ...form, trade_type: e.target.value })}>
                <option value="INTRADAY">Intraday</option>
                <option value="POSITIONAL">Positional</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input type="text" className="form-input" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Optional" />
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <button type="submit" className="btn btn-success">Record Trade</button>
              <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {activeTrades.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-title" style={{ marginBottom: 14 }}>Open Positions</div>
          <table className="data-table">
            <thead>
              <tr><th>Symbol</th><th>Strike</th><th>Type</th><th>Entry</th><th>Qty</th><th>Trade Type</th><th>Action</th></tr>
            </thead>
            <tbody>
              {activeTrades.map(t => (
                <tr key={t.id}>
                  <td>{t.symbol}</td><td>{t.strike}</td>
                  <td style={{ color: t.option_type === 'CE' ? 'var(--bullish)' : 'var(--bearish)' }}>{t.option_type}</td>
                  <td>₹{t.entry_price}</td><td>{t.qty}</td><td>{t.trade_type}</td>
                  <td>
                    <button className="btn btn-danger" style={{ padding: '3px 10px', fontSize: 11 }}
                      onClick={() => { const exit = prompt('Enter exit price:'); if (exit) handleClose(t.id, parseFloat(exit)); }}>
                      <XCircle size={12} /> Close
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <div className="card-title" style={{ marginBottom: 14 }}>Trade History</div>
        {history.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)', fontSize: 13 }}>No completed trades yet</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Symbol</th><th>Strike</th><th>Type</th><th>Entry</th><th>Exit</th><th>Qty</th><th>P&L</th><th>Net P&L</th><th>Date</th></tr>
            </thead>
            <tbody>
              {history.map(t => (
                <tr key={t.id}>
                  <td>{t.symbol}</td><td>{t.strike}</td>
                  <td style={{ color: t.option_type === 'CE' ? 'var(--bullish)' : 'var(--bearish)' }}>{t.option_type}</td>
                  <td>₹{t.entry_price}</td><td>₹{t.exit_price}</td><td>{t.qty}</td>
                  <td style={{ color: pnlColor(t.pnl), fontWeight: 600 }}>{pnlSign(t.pnl)}₹{fmt(t.pnl)}</td>
                  <td style={{ color: pnlColor(t.net_pnl), fontWeight: 600 }}>{pnlSign(t.net_pnl)}₹{fmt(t.net_pnl)}</td>
                  <td style={{ fontSize: 11 }}>{t.exit_time ? new Date(t.exit_time).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function Trades() {
  const [tab, setTab] = useState('angel');

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>
            <ArrowRightLeft size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />
            Trade Dashboard
          </h1>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            Real trades from Angel One · charges breakdown · P&L tracking
          </p>
        </div>
      </div>

      {/* Tab Switcher */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {[
          { key: 'angel',  label: '📊 Angel One Trades', icon: Wallet },
          { key: 'manual', label: '✏️ Manual Trades',    icon: Plus },
        ].map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '8px 16px', fontSize: 13, fontWeight: tab === key ? 700 : 400,
              color: tab === key ? 'var(--accent)' : 'var(--text-muted)',
              borderBottom: tab === key ? '2px solid var(--accent)' : '2px solid transparent',
              transition: 'all 0.15s',
            }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'angel'  && <AngelTab />}
      {tab === 'manual' && <ManualTab />}
    </div>
  );
}
