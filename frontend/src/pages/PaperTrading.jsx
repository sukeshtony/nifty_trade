import React, { useEffect, useState, useCallback } from 'react';
import {
  fetchPaperAccount,
  initPaperAccount,
  fetchActivePaperTrades,
  fetchPaperTradeHistory,
  placePaperTrade,
  closePaperTrade,
  fetchPaperOptionChain,
} from '../api';
import { RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';

const fmtPrice = (n) =>
  n != null ? `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';

const fmtOI = (oi) => {
  if (!oi) return '—';
  if (oi >= 10_000_000) return `${(oi / 10_000_000).toFixed(1)}Cr`;
  if (oi >= 100_000) return `${(oi / 100_000).toFixed(1)}L`;
  return oi.toLocaleString('en-IN');
};

const PnlCell = ({ value, suffix = '' }) => {
  if (value == null) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  const positive = value >= 0;
  return (
    <span style={{ color: positive ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
      {positive ? '+' : ''}₹{Math.abs(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{suffix}
    </span>
  );
};

export default function PaperTrading() {
  const [account, setAccount] = useState(null);
  const [optionChain, setOptionChain] = useState([]);
  const [spotPrice, setSpotPrice] = useState(0);
  const [activeTrades, setActiveTrades] = useState([]);
  const [history, setHistory] = useState([]);
  const [initAmount, setInitAmount] = useState(100000);
  const [loading, setLoading] = useState(true);
  const [placingTrade, setPlacingTrade] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      setLoading(true);
      const [acc, chain, active, hist] = await Promise.all([
        fetchPaperAccount(),
        fetchPaperOptionChain(),
        fetchActivePaperTrades(),
        fetchPaperTradeHistory(),
      ]);
      if (acc?.data) setAccount(acc.data);
      if (chain?.data) {
        setOptionChain(chain.data);
        setSpotPrice(chain.spot_price || 0);
      }
      setActiveTrades(active?.data || []);
      setHistory(hist?.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLive = useCallback(async () => {
    try {
      const [chain, active] = await Promise.all([
        fetchPaperOptionChain(),
        fetchActivePaperTrades(),
      ]);
      if (chain?.data) {
        setOptionChain(chain.data);
        setSpotPrice(chain.spot_price || 0);
      }
      setActiveTrades(active?.data || []);
    } catch (e) {}
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(refreshLive, 5000);
    return () => clearInterval(interval);
  }, [loadAll, refreshLive]);

  const handleInit = async () => {
    if (!window.confirm(`Reset paper account to ₹${Number(initAmount).toLocaleString('en-IN')}? All open trades will be closed.`)) return;
    await initPaperAccount(initAmount);
    loadAll();
  };

  const handleBuy = async (strike, optionType, ltp) => {
    if (!ltp) {
      alert('No live LTP for this strike. Market may be closed.');
      return;
    }
    const key = `${strike}-${optionType}`;
    setPlacingTrade(key);
    try {
      await placePaperTrade({
        symbol: 'NIFTY',
        strike,
        option_type: optionType,
        entry_price: ltp,
        qty: 25,
        trade_type: 'INTRADAY',
      });
      await loadAll();
    } catch (e) {
      console.error('Trade failed', e);
      alert('Failed to place trade. Please try again.');
    } finally {
      setPlacingTrade(null);
    }
  };

  const handleExit = async (trade) => {
    // Use live LTP from option chain if available, else fall back to current_ltp from API
    const chainRow = optionChain.find((r) => r.strike === trade.strike);
    const ltp = chainRow
      ? trade.option_type === 'CE' ? chainRow.callLTP : chainRow.putLTP
      : trade.current_ltp;
    const exitPrice = ltp || trade.entry_price;

    if (!window.confirm(`Exit NIFTY ${trade.strike} ${trade.option_type} at ₹${exitPrice}?`)) return;
    try {
      await closePaperTrade(trade.id, exitPrice);
      await loadAll();
    } catch (e) {
      console.error(e);
    }
  };

  const totalUnrealized = activeTrades.reduce((s, t) => s + (t.unrealized_pnl || 0), 0);

  if (loading && !account) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        Loading paper trading...
      </div>
    );
  }

  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: '700', margin: 0 }}>Paper Trading</h1>
          <p style={{ color: 'var(--text-muted)', margin: '4px 0 0 0', fontSize: '13px' }}>
            Buy / Exit Nifty options using live option chain data — no real money at risk
          </p>
        </div>
        <div className="panel" style={{ padding: '8px 18px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>NIFTY 50</span>
          <span style={{ fontSize: '20px', fontWeight: '700' }}>
            {spotPrice ? `₹${spotPrice.toLocaleString('en-IN')}` : '—'}
          </span>
        </div>
      </div>

      {/* ── Account Summary Bar ── */}
      {account && (
        <div className="panel" style={{ padding: '16px 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
            <div style={{ display: 'flex', gap: '36px', flexWrap: 'wrap' }}>
              <Stat label="BALANCE" value={`₹${account.available_balance.toLocaleString('en-IN')}`} />
              <Stat
                label="UNREALIZED P&L"
                value={<PnlCell value={totalUnrealized} />}
              />
              <Stat
                label="REALIZED P&L"
                value={<PnlCell value={account.realized_pnl} />}
              />
              <Stat
                label="WIN RATE"
                value={`${account.win_rate}%`}
                sub={`${account.winning_trades}W / ${account.losing_trades}L`}
              />
              <Stat label="TOTAL TRADES" value={account.total_trades} />
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type="number"
                value={initAmount}
                onChange={(e) => setInitAmount(Number(e.target.value))}
                style={{
                  width: '110px', padding: '6px 10px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-secondary)',
                  background: 'var(--bg-secondary)', color: 'white', fontSize: '13px',
                }}
              />
              <button
                onClick={handleInit}
                style={{
                  padding: '6px 14px', background: 'var(--bg-tertiary)',
                  color: 'var(--text-secondary)', border: 'none',
                  borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px',
                }}
              >
                <RefreshCw size={12} /> Reset
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Option Chain Table ── */}
      <div>
        <h2 style={{ fontSize: '15px', fontWeight: '600', margin: '0 0 8px 0' }}>
          Nifty Option Chain
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 400, marginLeft: '8px' }}>
            ATM ±5 strikes · live LTP · click BUY to paper trade at market price
          </span>
        </h2>
        <div className="panel" style={{ overflow: 'auto' }}>
          {optionChain.length === 0 ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              Option chain unavailable — market may be closed or data feed disconnected.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-primary)' }}>
                  {/* CALL side headers */}
                  <th style={{ padding: '10px 12px', color: 'var(--success)', fontWeight: 500, textAlign: 'right', whiteSpace: 'nowrap' }}>OI (Lots)</th>
                  <th style={{ padding: '10px 12px', color: 'var(--success)', fontWeight: 500, textAlign: 'right' }}>LTP</th>
                  <th style={{ padding: '10px 12px', color: 'var(--success)', fontWeight: 500, textAlign: 'right', width: '90px' }}>BUY CE</th>
                  {/* Strike */}
                  <th style={{ padding: '10px 20px', color: 'var(--text-secondary)', fontWeight: 600, textAlign: 'center', whiteSpace: 'nowrap' }}>STRIKE</th>
                  {/* PUT side headers */}
                  <th style={{ padding: '10px 12px', color: 'var(--danger)', fontWeight: 500, textAlign: 'left', width: '90px' }}>BUY PE</th>
                  <th style={{ padding: '10px 12px', color: 'var(--danger)', fontWeight: 500, textAlign: 'left' }}>LTP</th>
                  <th style={{ padding: '10px 12px', color: 'var(--danger)', fontWeight: 500, textAlign: 'left', whiteSpace: 'nowrap' }}>OI (Lots)</th>
                </tr>
              </thead>
              <tbody>
                {optionChain.map((row) => {
                  const ceKey = `${row.strike}-CE`;
                  const peKey = `${row.strike}-PE`;
                  return (
                    <tr
                      key={row.strike}
                      style={{
                        borderBottom: '1px solid var(--border-primary)',
                        background: row.isATM ? 'rgba(99,102,241,0.07)' : 'transparent',
                      }}
                    >
                      {/* CALL OI */}
                      <td style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {fmtOI(row.callOI)}
                      </td>
                      {/* CALL LTP */}
                      <td style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 600, color: 'var(--success)' }}>
                        {row.callLTP ? `₹${row.callLTP.toFixed(1)}` : '—'}
                      </td>
                      {/* BUY CE */}
                      <td style={{ padding: '7px 12px', textAlign: 'right' }}>
                        <button
                          onClick={() => handleBuy(row.strike, 'CE', row.callLTP)}
                          disabled={placingTrade === ceKey || !row.callLTP}
                          style={{
                            padding: '4px 12px', borderRadius: '100px',
                            background: placingTrade === ceKey ? 'rgba(34,197,94,0.3)' : 'rgba(34,197,94,0.12)',
                            color: 'var(--success)',
                            border: '1px solid rgba(34,197,94,0.3)',
                            cursor: row.callLTP ? 'pointer' : 'not-allowed',
                            fontSize: '11px', fontWeight: '600',
                            opacity: row.callLTP ? 1 : 0.35,
                            transition: 'background 0.15s',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {placingTrade === ceKey ? '...' : 'BUY CE'}
                        </button>
                      </td>
                      {/* STRIKE */}
                      <td style={{ padding: '9px 20px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                        <span style={{ fontWeight: row.isATM ? 700 : 500, color: row.isATM ? 'var(--accent)' : 'var(--text-primary)' }}>
                          {row.strike.toLocaleString('en-IN')}
                        </span>
                        {row.isATM && (
                          <span style={{
                            fontSize: '9px', marginLeft: '6px', color: 'var(--accent)',
                            background: 'rgba(99,102,241,0.15)', padding: '1px 5px',
                            borderRadius: '4px', fontWeight: 600,
                          }}>
                            ATM
                          </span>
                        )}
                      </td>
                      {/* BUY PE */}
                      <td style={{ padding: '7px 12px', textAlign: 'left' }}>
                        <button
                          onClick={() => handleBuy(row.strike, 'PE', row.putLTP)}
                          disabled={placingTrade === peKey || !row.putLTP}
                          style={{
                            padding: '4px 12px', borderRadius: '100px',
                            background: placingTrade === peKey ? 'rgba(239,68,68,0.3)' : 'rgba(239,68,68,0.12)',
                            color: 'var(--danger)',
                            border: '1px solid rgba(239,68,68,0.3)',
                            cursor: row.putLTP ? 'pointer' : 'not-allowed',
                            fontSize: '11px', fontWeight: '600',
                            opacity: row.putLTP ? 1 : 0.35,
                            transition: 'background 0.15s',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {placingTrade === peKey ? '...' : 'BUY PE'}
                        </button>
                      </td>
                      {/* PUT LTP */}
                      <td style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--danger)' }}>
                        {row.putLTP ? `₹${row.putLTP.toFixed(1)}` : '—'}
                      </td>
                      {/* PUT OI */}
                      <td style={{ padding: '9px 12px', textAlign: 'left', color: 'var(--text-secondary)' }}>
                        {fmtOI(row.putOI)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Open Positions ── */}
      <div>
        <h2 style={{ fontSize: '15px', fontWeight: '600', margin: '0 0 8px 0' }}>
          Open Positions
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 400, marginLeft: '8px' }}>
            ({activeTrades.length} active · P&L updates every 5s)
          </span>
        </h2>
        <div className="panel" style={{ overflow: 'auto' }}>
          {activeTrades.length === 0 ? (
            <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              No open positions. Buy CE or PE from the option chain above.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-primary)' }}>
                  <th style={th('left')}>Contract</th>
                  <th style={th('center')}>Qty</th>
                  <th style={th('right')}>Entry</th>
                  <th style={th('right')}>Current LTP</th>
                  <th style={th('right')}>Unrealized P&L</th>
                  <th style={th('center')}>Entry Time</th>
                  <th style={th('right')}>Action</th>
                </tr>
              </thead>
              <tbody>
                {activeTrades.map((t) => {
                  const pnl = t.unrealized_pnl || 0;
                  const pct = t.unrealized_pnl_pct || 0;
                  const ltp = t.current_ltp;
                  return (
                    <tr key={t.id} style={{ borderBottom: '1px solid var(--border-primary)' }}>
                      <td style={{ padding: '10px 14px' }}>
                        <TypeBadge type={t.option_type} />
                        <span style={{ fontWeight: 500 }}>NIFTY {t.strike}</span>
                      </td>
                      <td style={{ padding: '10px 14px', textAlign: 'center' }}>{t.qty}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right' }}>{fmtPrice(t.entry_price)}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600 }}>
                        {ltp ? fmtPrice(ltp) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                      <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                        <div>
                          <PnlCell value={pnl} />
                        </div>
                        <div style={{ fontSize: '11px', color: pnl >= 0 ? 'var(--success)' : 'var(--danger)', opacity: 0.7 }}>
                          ({pct >= 0 ? '+' : ''}{pct.toFixed(1)}%)
                        </div>
                      </td>
                      <td style={{ padding: '10px 14px', textAlign: 'center', color: 'var(--text-muted)' }}>
                        {new Date(t.entry_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                        <button
                          onClick={() => handleExit(t)}
                          style={{
                            padding: '5px 12px', borderRadius: '100px',
                            background: 'rgba(99,102,241,0.12)',
                            color: 'var(--accent)',
                            border: '1px solid rgba(99,102,241,0.3)',
                            cursor: 'pointer', fontSize: '11px', fontWeight: '600',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {ltp ? `Exit @ ₹${ltp.toFixed(0)}` : 'Exit'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Trade History ── */}
      <div>
        <h2 style={{ fontSize: '15px', fontWeight: '600', margin: '0 0 8px 0' }}>
          Trade History
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 400, marginLeft: '8px' }}>
            ({history.length} closed trades)
          </span>
        </h2>
        <div className="panel" style={{ overflow: 'auto' }}>
          {history.length === 0 ? (
            <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              No closed trades yet.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ background: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-primary)' }}>
                  <th style={th('left')}>Contract</th>
                  <th style={th('right')}>Entry</th>
                  <th style={th('right')}>Exit</th>
                  <th style={th('right')}>Gross P&L</th>
                  <th style={th('right')}>Charges</th>
                  <th style={th('right')}>Net P&L</th>
                  <th style={th('center')}>Entry → Exit</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.id} style={{ borderBottom: '1px solid var(--border-primary)' }}>
                    <td style={{ padding: '10px 14px' }}>
                      <TypeBadge type={t.option_type} />
                      <span style={{ fontWeight: 500 }}>NIFTY {t.strike}</span>
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>{fmtPrice(t.entry_price)}</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>{fmtPrice(t.exit_price)}</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                      <PnlCell value={t.pnl} />
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '12px' }}>
                      ₹{(t.charges || 0).toFixed(2)}
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                      <PnlCell value={t.net_pnl} />
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                      <div>{new Date(t.entry_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
                      <div>→ {t.exit_time ? new Date(t.exit_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  );
}

// ── Small reusable sub-components ──

function Stat({ label, value, sub }) {
  return (
    <div>
      <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '3px', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: '17px', fontWeight: '700' }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>{sub}</div>}
    </div>
  );
}

function TypeBadge({ type }) {
  const isCE = type === 'CE';
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: '4px',
      fontSize: '10px', fontWeight: '700', marginRight: '8px',
      background: isCE ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
      color: isCE ? 'var(--success)' : 'var(--danger)',
    }}>
      {type}
    </span>
  );
}

function th(align = 'left') {
  return { padding: '10px 14px', color: 'var(--text-secondary)', fontWeight: 500, textAlign: align };
}
