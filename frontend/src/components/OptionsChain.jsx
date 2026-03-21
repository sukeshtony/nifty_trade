import React, { memo } from 'react';
import { Layers } from 'lucide-react';

const OptionsChain = memo(({ optionsData }) => {
  const strikes = optionsData?.strikes || [];

  if (!strikes.length) {
    return (
      <div className="card" id="options-chain">
        <div className="card-header">
          <span className="card-title">
            <Layers size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            Option Chain (ATM ± 3)
          </span>
        </div>
        <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
          Option chain data not available
        </div>
      </div>
    );
  }

  const formatOI = (oi) => {
    if (!oi) return '—';
    if (oi >= 100000) return `${(oi / 100000).toFixed(1)}L`;
    if (oi >= 1000) return `${(oi / 1000).toFixed(1)}K`;
    return oi.toLocaleString();
  };

  return (
    <div className="card" id="options-chain" style={{ overflow: 'auto' }}>
      <div className="card-header">
        <span className="card-title">
          <Layers size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Option Chain (ATM ± 3)
        </span>
        <div style={{ display: 'flex', gap: '8px' }}>
          <span className="indicator-pill">
            <span className="label">PCR</span>
            <span className="value">{optionsData?.pcr?.toFixed(2) || '—'}</span>
          </span>
          <span className="indicator-pill">
            <span className="label">Max Pain</span>
            <span className="value">{optionsData?.max_pain?.toLocaleString() || '—'}</span>
          </span>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th style={{ color: 'var(--bullish)' }}>Call OI</th>
            <th style={{ color: 'var(--bullish)' }}>Call Chg</th>
            <th style={{ color: 'var(--bullish)' }}>Call LTP</th>
            <th style={{ textAlign: 'center', color: 'var(--accent)' }}>Strike</th>
            <th style={{ color: 'var(--bearish)' }}>Put LTP</th>
            <th style={{ color: 'var(--bearish)' }}>Put Chg</th>
            <th style={{ color: 'var(--bearish)' }}>Put OI</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((row, i) => (
            <tr key={i} className={row.isATM ? 'atm-row' : ''}>
              <td style={{ color: row.callOIChg > 0 ? 'var(--bullish)' : row.callOIChg < 0 ? 'var(--bearish)' : undefined }}>
                {formatOI(row.callOI)}
              </td>
              <td style={{ color: row.callOIChg > 0 ? 'var(--bullish)' : row.callOIChg < 0 ? 'var(--bearish)' : undefined }}>
                {row.callOIChg ? `${row.callOIChg > 0 ? '+' : ''}${formatOI(row.callOIChg)}` : '—'}
              </td>
              <td>{row.callLTP ? row.callLTP.toFixed(2) : '—'}</td>
              <td style={{ textAlign: 'center', fontWeight: 700, color: row.isATM ? 'var(--accent)' : 'var(--text-primary)' }}>
                {row.strike?.toLocaleString()}
                {row.isATM && <span style={{ fontSize: '9px', color: 'var(--accent)', display: 'block' }}>ATM</span>}
              </td>
              <td>{row.putLTP ? row.putLTP.toFixed(2) : '—'}</td>
              <td style={{ color: row.putOIChg > 0 ? 'var(--bullish)' : row.putOIChg < 0 ? 'var(--bearish)' : undefined }}>
                {row.putOIChg ? `${row.putOIChg > 0 ? '+' : ''}${formatOI(row.putOIChg)}` : '—'}
              </td>
              <td style={{ color: row.putOIChg > 0 ? 'var(--bullish)' : row.putOIChg < 0 ? 'var(--bearish)' : undefined }}>
                {formatOI(row.putOI)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

OptionsChain.displayName = 'OptionsChain';
export default OptionsChain;
