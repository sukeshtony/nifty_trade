import React, { useEffect, useState } from 'react';
import { 
  fetchPaperAccount, 
  initPaperAccount, 
  fetchActivePaperTrades, 
  fetchPaperTradeHistory, 
  placePaperTrade, 
  closePaperTrade,
  fetchNiftyPrice 
} from '../api';
import { Wallet, RefreshCw, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

export default function PaperTrading() {
  const [account, setAccount] = useState(null);
  const [activeTrades, setActiveTrades] = useState([]);
  const [history, setHistory] = useState([]);
  const [niftyPrice, setNiftyPrice] = useState(0);
  const [initAmount, setInitAmount] = useState(100000);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      setLoading(true);
      const acc = await fetchPaperAccount();
      setAccount(acc.data);
      const active = await fetchActivePaperTrades();
      setActiveTrades(active.data);
      const hist = await fetchPaperTradeHistory();
      setHistory(hist.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const getPrice = async () => {
    try {
      const p = await fetchNiftyPrice();
      setNiftyPrice(p.ltp || p.current_price || 0);
    } catch(e) {}
  };

  useEffect(() => {
    loadData();
    getPrice();
    const interval = setInterval(() => {
      getPrice();
      // Periodically refresh active trades to update
      fetchActivePaperTrades().then(res => setActiveTrades(res.data)).catch(()=>{});
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleInit = async () => {
    if (!window.confirm(`Reset paper account to ₹${initAmount}? All open trades will be closed.`)) return;
    await initPaperAccount(initAmount);
    loadData();
  };

  const handlePlaceTrade = async (optionType) => {
    if (!niftyPrice) return alert("Waiting for live price...");
    
    // Simple mock logic: Strike is nearest 50 to current Nifty
    const strike = Math.round(niftyPrice / 50) * 50;
    // Mock premium price. We don't have option chain directly fetched here easily unless we call it. 
    // Usually premium is ~100 for ATM. We will use a dummy premium of 150 for this paper trade UI or fetch from option chain.
    const mockPremium = 150.0; 

    try {
      await placePaperTrade({
        symbol: "NIFTY",
        strike,
        option_type: optionType,
        entry_price: mockPremium,
        qty: 25,
        trade_type: "INTRADAY" // default
      });
      loadData();
    } catch (e) {
      console.error("Trade failed", e);
    }
  };

  const handleCloseTrade = async (id, entryType, entryPrice) => {
    // For a real app, exit price should be live premium. 
    // Here we will mock it based on Nifty movement if it's not available easily.
    // If NIFTY moved by +10, CE premium moves +5, PE premium moves -5.
    // Simplified: Provide a prompt or just mock it.
    const mockExit = parseFloat(prompt("Enter exit premium price for testing:", entryPrice + 10));
    if (isNaN(mockExit)) return;

    try {
      await closePaperTrade(id, mockExit);
      loadData();
    } catch (e) {
      console.error(e);
    }
  };

  if (loading && !account) return <div className="panel" style={{margin:'20px'}}>Loading Paper Trading...</div>;

  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: '700', margin: 0 }}>Paper Trading Environment</h1>
          <p style={{ color: 'var(--text-muted)', margin: '4px 0 0 0', fontSize: '14px' }}>
            Test your strategies with live data without risking real money
          </p>
        </div>
        <div className="panel" style={{ display: 'flex', gap: '10px', alignItems: 'center', padding: '10px 20px' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Nifty 50</span>
          <span style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--text-primary)' }}>
            ₹{niftyPrice ? niftyPrice.toLocaleString() : '---'}
          </span>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
        {/* Account Info Panel */}
        <div className="panel" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
            <Wallet size={24} color="var(--accent)" />
            <h2 style={{ fontSize: '18px', margin: 0 }}>Account Summary</h2>
          </div>
          
          {account && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Available Capital</span>
                <span style={{ fontSize: '24px', fontWeight: '700' }}>₹{account.available_balance.toLocaleString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Realized P&L</span>
                <span style={{ 
                  fontWeight: '600', 
                  color: account.realized_pnl >= 0 ? 'var(--success)' : 'var(--danger)' 
                }}>
                  {account.realized_pnl >= 0 ? '+' : ''}₹{account.realized_pnl.toLocaleString()}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Win Rate</span>
                <span>{account.win_rate}% ({account.winning_trades}W / {account.losing_trades}L)</span>
              </div>
            </div>
          )}

          <div style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid var(--border-primary)', display: 'flex', gap: '10px' }}>
            <input 
              type="number" 
              value={initAmount} 
              onChange={e => setInitAmount(Number(e.target.value))}
              style={{ padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-secondary)', background: 'var(--bg-secondary)', color: 'white', width: '120px' }}
            />
            <button 
              onClick={handleInit}
              style={{ flex: 1, padding: '8px 16px', background: 'var(--bg-tertiary)', color: 'white', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent:'center', gap: '8px' }}
            >
              <RefreshCw size={14} /> Reset Account
            </button>
          </div>
        </div>

        {/* Quick Trade Panel */}
        <div className="panel" style={{ padding: '24px' }}>
           <h2 style={{ fontSize: '18px', margin: '0 0 20px 0' }}>Quick Paper Trade</h2>
           <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: 1.5 }}>
             Buy ATM options at the current Nifty spot price. Premium prices are simulated for this demo interface.
           </p>

           <div style={{ display: 'flex', gap: '15px', height: '100px' }}>
             <button
               onClick={() => handlePlaceTrade('CE')}
               style={{ 
                 flex: 1, borderRadius: 'var(--radius-md)', 
                 background: 'rgba(34, 197, 94, 0.1)', color: 'var(--success)', 
                 cursor: 'pointer', display: 'flex', flexDirection: 'column', 
                 alignItems: 'center', justifyContent: 'center', gap: '8px',
                 border: '1px solid rgba(34, 197, 94, 0.2)', transition: 'all 0.2s',
               }}
               onMouseOver={(e) => e.currentTarget.style.background = 'rgba(34, 197, 94, 0.2)'}
               onMouseOut={(e) => e.currentTarget.style.background = 'rgba(34, 197, 94, 0.1)'}
             >
               <TrendingUp size={24} />
               <span style={{ fontWeight: '600', fontSize: '16px' }}>BUY CE</span>
               <span style={{ fontSize: '11px', opacity: 0.8 }}>Bullish</span>
             </button>

             <button
               onClick={() => handlePlaceTrade('PE')}
               style={{ 
                 flex: 1, borderRadius: 'var(--radius-md)', 
                 background: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', 
                 cursor: 'pointer', display: 'flex', flexDirection: 'column', 
                 alignItems: 'center', justifyContent: 'center', gap: '8px',
                 border: '1px solid rgba(239, 68, 68, 0.2)', transition: 'all 0.2s',
               }}
               onMouseOver={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'}
               onMouseOut={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'}
             >
               <TrendingDown size={24} />
               <span style={{ fontWeight: '600', fontSize: '16px' }}>BUY PE</span>
               <span style={{ fontSize: '11px', opacity: 0.8 }}>Bearish</span>
             </button>
           </div>
        </div>
      </div>

      {/* Active Trades */}
      <h2 style={{ fontSize: '18px', margin: '10px 0 0 0' }}>Open Paper Trades</h2>
      <div className="panel" style={{ overflow: 'hidden' }}>
        {activeTrades.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
            No active paper trades currently open.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ background: 'var(--bg-tertiary)', textAlign: 'left', borderBottom: '1px solid var(--border-primary)' }}>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Contract</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Entry Time</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Qty</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Entry Price</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500, textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {activeTrades.map(t => (
                <tr key={t.id} style={{ borderBottom: '1px solid var(--border-primary)' }}>
                  <td style={{ padding: '12px 15px', fontWeight: '500' }}>
                    <span style={{ color: t.option_type === 'CE' ? 'var(--success)' : 'var(--danger)', marginRight: '6px' }}>
                      {t.option_type === 'CE' ? <TrendingUp size={14} style={{verticalAlign: 'middle'}}/> : <TrendingDown size={14} style={{verticalAlign: 'middle'}}/>}
                    </span>
                    {t.symbol} {t.strike} {t.option_type}
                  </td>
                  <td style={{ padding: '12px 15px', color: 'var(--text-muted)' }}>{new Date(t.entry_time).toLocaleTimeString()}</td>
                  <td style={{ padding: '12px 15px' }}>{t.qty}</td>
                  <td style={{ padding: '12px 15px' }}>₹{t.entry_price.toFixed(2)}</td>
                  <td style={{ padding: '12px 15px', textAlign: 'right' }}>
                    <button 
                      onClick={() => handleCloseTrade(t.id, t.option_type, t.entry_price)}
                      style={{ padding: '6px 14px', borderRadius: '100px', background: 'var(--accent)', color: 'white', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}
                    >
                      Close Position
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Trade History */}
      <h2 style={{ fontSize: '18px', margin: '10px 0 0 0' }}>Paper Trade History</h2>
      <div className="panel" style={{ overflow: 'hidden' }}>
        {history.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
             No historical trades available.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ background: 'var(--bg-tertiary)', textAlign: 'left', borderBottom: '1px solid var(--border-primary)' }}>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Contract</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Entry / Exit</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>Prices</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-secondary)', fontWeight: 500 }}>P&L (Net)</th>
              </tr>
            </thead>
            <tbody>
              {history.map(t => (
                <tr key={t.id} style={{ borderBottom: '1px solid var(--border-primary)' }}>
                  <td style={{ padding: '12px 15px', fontWeight: '500' }}>
                    {t.symbol} {t.strike} {t.option_type}
                  </td>
                  <td style={{ padding: '12px 15px', color: 'var(--text-muted)' }}>
                    <div>In: {new Date(t.entry_time).toLocaleTimeString()}</div>
                    <div>Out: {new Date(t.exit_time).toLocaleTimeString()}</div>
                  </td>
                  <td style={{ padding: '12px 15px', color: 'var(--text-muted)' }}>
                    <div>En: ₹{t.entry_price.toFixed(2)}</div>
                    <div>Ex: ₹{t.exit_price?.toFixed(2)}</div>
                  </td>
                  <td style={{ padding: '12px 15px' }}>
                    <div style={{ color: t.net_pnl >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: '600', fontSize: '14px' }}>
                      {t.net_pnl >= 0 ? '+' : ''}₹{t.net_pnl.toFixed(2)}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Charges: ₹{t.charges.toFixed(2)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
