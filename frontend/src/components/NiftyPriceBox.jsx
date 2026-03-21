import React, { memo, useState, useEffect, useRef } from 'react';

const NiftyPriceBox = memo(({ priceData }) => {
  const [pulseClass, setPulseClass] = useState('');
  const prevPriceRef = useRef(null);

  const ltp = priceData?.ltp || 0;
  const change = priceData?.change || 0;
  const changePct = priceData?.changePct || 0;
  const isUp = change >= 0;

  useEffect(() => {
    if (prevPriceRef.current !== null && prevPriceRef.current !== ltp) {
      setPulseClass(ltp > prevPriceRef.current ? 'pulse-up' : 'pulse-down');
      const timer = setTimeout(() => setPulseClass(''), 1500);
      return () => clearTimeout(timer);
    }
    prevPriceRef.current = ltp;
  }, [ltp]);

  return (
    <div className={`card ${pulseClass}`} id="nifty-price-box" style={{
      borderColor: isUp ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)',
      background: isUp
        ? 'linear-gradient(135deg, #0a0e17 0%, rgba(34, 197, 94, 0.05) 100%)'
        : 'linear-gradient(135deg, #0a0e17 0%, rgba(239, 68, 68, 0.05) 100%)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px'
          }}>
            <span className="status-dot live" />
            <span style={{
              fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)',
              textTransform: 'uppercase', letterSpacing: '1px'
            }}>
              NIFTY 50
            </span>
          </div>
          <div className="price-value" style={{ color: isUp ? 'var(--bullish)' : 'var(--bearish)' }}>
            {ltp ? ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '—'}
          </div>
          <div className="price-change" style={{
            color: isUp ? 'var(--bullish)' : 'var(--bearish)', marginTop: '4px'
          }}>
            {isUp ? '+' : ''}{change.toFixed(2)} ({isUp ? '+' : ''}{changePct.toFixed(2)}%)
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          {priceData?.session_high ? (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              <div>H: <span className="text-mono">{priceData.session_high.toLocaleString('en-IN')}</span></div>
              <div>L: <span className="text-mono">{priceData.session_low?.toLocaleString('en-IN')}</span></div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
});

NiftyPriceBox.displayName = 'NiftyPriceBox';
export default NiftyPriceBox;
