import React from 'react';
import { formatPrice } from '../lib/api';

function ResultCard({ title, product, showScore = true }) {
  return (
    <div className="result-card">
      <h4>{title}</h4>
      <p className="result-title">{product.title}</p>
      <p className="muted">{product.vendor || 'Unknown vendor'} · {formatPrice(product.price_min, product.price_max)}</p>
      {showScore && <p className="score-pill">Score {product.score.toFixed(2)}</p>}
    </div>
  );
}

export default function RoundResultPanel({ result, onNext, loadingNext }) {
  if (!result) {
    return null;
  }

  return (
    <section className="screen shell">
      <header className="section-header">
        <div>
          <p className="eyebrow">Round Results</p>
          <h2>Round {result.round_number} complete</h2>
        </div>
        <div className="scoreline">
          <span>You +{result.human_points}</span>
          <span>AI +{result.ai_points}</span>
        </div>
      </header>

      <div className="result-grid">
        <ResultCard title="Your pick" product={result.human_pick} showScore={false} />
        <ResultCard title="AI pick" product={result.ai_pick} />
      </div>

      <div className="panel result-details">
        <h3>AI Explanation</h3>
        <p>{result.ai_explanation.reason}</p>
        <ul>
          {result.ai_explanation.top_candidates.map((candidate) => (
            <li key={candidate.id}>
              <span>{candidate.title}</span>
              <strong>{candidate.score.toFixed(2)}</strong>
            </li>
          ))}
        </ul>
        <div className="metric-strip">
          <span>Post Coherence {result.post_round_metrics.coherence_score.toFixed(2)}</span>
          <span>Post Predicted Rating {result.post_round_metrics.predicted_prefix_rating.toFixed(2)}</span>
        </div>
      </div>

      <div className="round-actions">
        <button type="button" onClick={onNext} disabled={loadingNext}>
          {loadingNext ? 'Loading...' : result.game_complete ? 'View Final Summary' : 'Next Round'}
        </button>
      </div>
    </section>
  );
}
