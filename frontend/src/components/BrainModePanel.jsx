import React from 'react';

export default function BrainModePanel({ mode, onModeChange }) {
  return (
    <div className="brain-mode-panel">
      <div className="mode-buttons" role="tablist" aria-label="Explore mode">
        <button
          type="button"
          role="tab"
          className={mode === 'visual' ? 'active' : ''}
          onClick={() => onModeChange('visual')}
        >
          Visual Mode
        </button>
        <button
          type="button"
          role="tab"
          className={mode === 'feature' ? 'active' : ''}
          onClick={() => onModeChange('feature')}
        >
          Feature Mode
        </button>
      </div>
      <p className="mode-caption">
        Visual mode prioritizes product imagery. Feature mode emphasizes vendor, price, and tag signals.
      </p>
    </div>
  );
}
