import React, { memo } from 'react';
import { TrendingUp, TrendingDown, Minus, Target, BarChart3, Clock } from 'lucide-react';

const SignalPanel = memo(({ signalData }) => {
  const signal = signalData?.signal || 'NO_TRADE';
  const direction = signalData?.direction || 'SIDEWAYS';
  const tradeType = signalData?.trade_type || 'INTRADAY';
  const confidence = signalData?.confidence || 0;

  const signalConfig = {
    BUY_CE: { label: 'BUY CE', className: 'buy-ce', icon: TrendingUp, desc: 'Buy Call Option' },
    BUY_PE: { label: 'BUY PE', className: 'buy-pe', icon: TrendingDown, desc: 'Buy Put Option' },
    NO_TRADE: { label: 'NO TRADE', className: 'no-trade', icon: Minus, desc: 'Stay Out' },
  };

  const directionConfig = {
    UP: { className: 'up', icon: TrendingUp },
    DOWN: { className: 'down', icon: TrendingDown },
    SIDEWAYS: { className: 'sideways', icon: Minus },
  };

  const cfg = signalConfig[signal] || signalConfig.NO_TRADE;
  const dirCfg = directionConfig[direction] || directionConfig.SIDEWAYS;
  const SignalIcon = cfg.icon;
  const DirIcon = dirCfg.icon;

  const confidenceLevel = confidence >= 70 ? 'high' : confidence >= 40 ? 'medium' : 'low';

  return (
    <div className="card" id="signal-panel">
      <div className="card-header">
        <span className="card-title">
          <Target size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Trading Signal
        </span>
        <div style={{ display: 'flex', gap: '8px' }}>
          <span className={`direction-badge ${dirCfg.className}`}>
            <DirIcon size={12} /> {direction}
          </span>
          <span className="direction-badge" style={{
            background: 'var(--accent-soft)', color: 'var(--accent)'
          }}>
            <Clock size={12} /> {tradeType}
          </span>
        </div>
      </div>

      {/* Main Signal */}
      <div style={{ textAlign: 'center', padding: '20px 0' }}>
        <div className={`signal-badge ${cfg.className}`}>
          <SignalIcon size={22} />
          {cfg.label}
        </div>
        <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
          {cfg.desc}
        </div>
      </div>

      {/* Confidence */}
      {confidence > 0 && (
        <div style={{ marginTop: '12px' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', marginBottom: '6px'
          }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              <BarChart3 size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
              Confidence
            </span>
            <span className="text-mono" style={{
              fontSize: '14px', fontWeight: 700,
              color: confidenceLevel === 'high' ? 'var(--bullish)' :
                     confidenceLevel === 'medium' ? 'var(--neutral)' : 'var(--bearish)'
            }}>
              {confidence}%
            </span>
          </div>
          <div className="confidence-bar-outer">
            <div
              className={`confidence-bar-inner ${confidenceLevel}`}
              style={{ width: `${Math.min(confidence, 100)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
});

SignalPanel.displayName = 'SignalPanel';
export default SignalPanel;
