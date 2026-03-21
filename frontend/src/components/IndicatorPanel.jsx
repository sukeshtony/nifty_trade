import React, { memo } from 'react';
import { Activity } from 'lucide-react';

const IndicatorPanel = memo(({ marketState, optionsSummary }) => {
  const indicators = [
    { label: 'EMA 9', value: marketState?.ema_9, format: 'price' },
    { label: 'EMA 21', value: marketState?.ema_21, format: 'price' },
    { label: 'VWAP', value: marketState?.vwap, format: 'price' },
    { label: 'Momentum', value: marketState?.momentum, format: 'change' },
    { label: 'PCR', value: optionsSummary?.pcr, format: 'ratio' },
    { label: 'Max Pain', value: optionsSummary?.max_pain, format: 'price' },
    { label: 'OI Support', value: optionsSummary?.oi_support, format: 'price' },
    { label: 'OI Resistance', value: optionsSummary?.oi_resistance, format: 'price' },
  ];

  const formatValue = (value, format) => {
    if (value === null || value === undefined) return '—';
    switch (format) {
      case 'price': return Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2 });
      case 'change': return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
      case 'ratio': return value.toFixed(2);
      default: return String(value);
    }
  };

  const getValueColor = (label, value) => {
    if (value === null || value === undefined) return 'var(--text-secondary)';
    if (label === 'Momentum') return value >= 0 ? 'var(--bullish)' : 'var(--bearish)';
    if (label === 'PCR') return value > 1 ? 'var(--bullish)' : value < 0.7 ? 'var(--bearish)' : 'var(--neutral)';
    return 'var(--text-primary)';
  };

  return (
    <div className="card" id="indicator-panel">
      <div className="card-header">
        <span className="card-title">
          <Activity size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Key Indicators
        </span>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '10px'
      }}>
        {indicators.map((ind, i) => (
          <div key={i} style={{
            padding: '10px 12px',
            background: 'var(--bg-elevated)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>
              {ind.label}
            </div>
            <div className="text-mono" style={{
              fontSize: '14px', fontWeight: 600,
              color: getValueColor(ind.label, ind.value),
            }}>
              {formatValue(ind.value, ind.format)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

IndicatorPanel.displayName = 'IndicatorPanel';
export default IndicatorPanel;
