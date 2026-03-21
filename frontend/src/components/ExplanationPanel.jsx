import React, { memo } from 'react';
import { FileText } from 'lucide-react';

const ExplanationPanel = memo(({ explanation, conditions }) => {
  if (!explanation) return null;

  const items = [
    { label: 'EMA Status', value: explanation.ema_status },
    { label: 'VWAP Status', value: explanation.vwap_status },
    { label: 'PCR', value: explanation.pcr_status },
    { label: 'OI Buildup', value: explanation.oi_status },
    { label: 'Momentum', value: explanation.momentum_status },
    { label: 'Sup/Res', value: explanation.support_resistance },
    { label: 'Volume', value: explanation.volume_status },
  ];

  const getBiasColor = (value) => {
    if (!value) return 'var(--text-secondary)';
    const v = value.toLowerCase();
    if (v.includes('bullish') || v.includes('above') || v.includes('upward') || v.includes('bounce') || v.includes('broke above'))
      return 'var(--bullish)';
    if (v.includes('bearish') || v.includes('below') || v.includes('downward') || v.includes('rejection') || v.includes('broke below'))
      return 'var(--bearish)';
    if (v.includes('sideways') || v.includes('near') || v.includes('neutral'))
      return 'var(--neutral)';
    return 'var(--text-secondary)';
  };

  return (
    <div className="card" id="explanation-panel">
      <div className="card-header">
        <span className="card-title">
          <FileText size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Signal Explanation
        </span>
      </div>

      <div>
        {items.map((item, i) => (
          <div className="explanation-item" key={i}>
            <span className="explanation-label">{item.label}</span>
            <span className="explanation-value" style={{ color: getBiasColor(item.value) }}>
              {item.value || 'N/A'}
            </span>
          </div>
        ))}
      </div>

      {/* Final Reasoning */}
      {explanation.final_reasoning && (
        <div style={{
          marginTop: '14px',
          padding: '12px 14px',
          background: 'var(--bg-elevated)',
          borderRadius: 'var(--radius-sm)',
          borderLeft: '3px solid var(--accent)',
        }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>
            Final Reasoning
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5 }}>
            {explanation.final_reasoning}
          </div>
        </div>
      )}

      {/* Conditions pills */}
      {conditions && conditions.length > 0 && (
        <div style={{ marginTop: '14px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {conditions.map((c, i) => (
            <span key={i} className="indicator-pill" style={{
              borderColor: c.bias === 'bullish' ? 'rgba(34,197,94,0.3)' :
                           c.bias === 'bearish' ? 'rgba(239,68,68,0.3)' : 'var(--border-primary)'
            }}>
              <span className="label">{c.name}</span>
              <span style={{
                width: '6px', height: '6px', borderRadius: '50%',
                background: c.bias === 'bullish' ? 'var(--bullish)' :
                            c.bias === 'bearish' ? 'var(--bearish)' : 'var(--neutral)',
              }} />
            </span>
          ))}
        </div>
      )}
    </div>
  );
});

ExplanationPanel.displayName = 'ExplanationPanel';
export default ExplanationPanel;
