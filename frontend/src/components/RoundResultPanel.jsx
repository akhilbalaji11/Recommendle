import { formatPrice } from '../lib/api';

function ResultCard({ label, product, variant, showScore = false }) {
  return (
    <div className={`result-card ${variant}`}>
      <h4>{label}</h4>
      <p className="result-title">{product.title}</p>
      <p className="muted">
        {product.vendor || 'Unknown vendor'} · {formatPrice(product.price_min, product.price_max)}
      </p>
      {showScore && product.score != null && (
        <p className="score-pill">AI Score {product.score.toFixed(2)}</p>
      )}
    </div>
  );
}

function FeatureTag({ name }) {
  return <span className="feature-tag">{name}</span>;
}

export default function RoundResultPanel({ result, onNext, loadingNext }) {
  if (!result) return null;

  const { ai_correct, ai_exact, ai_rank_of_pick, ai_explanation, post_round_metrics } = result;

  const outcomeClass = ai_correct ? 'outcome-ai' : 'outcome-human';
  const outcomeText = ai_correct
    ? (ai_exact ? 'AI Exact Match!' : `AI Top-3 Hit (Rank #${ai_rank_of_pick})`)
    : `AI Missed — Your pick was #${ai_rank_of_pick}`;

  return (
    <section className="screen shell">
      <div className={`outcome-banner ${outcomeClass}`}>
        <span className="outcome-label">{outcomeText}</span>
        <div className="scoreline">
          <span>You +{result.human_points}</span>
          <span>AI +{result.ai_points}</span>
        </div>
      </div>

      <header className="section-header">
        <div>
          <p className="eyebrow">Round {result.round_number} Results</p>
          <h2>Score: You {result.total_human_score} — AI {result.total_ai_score}</h2>
        </div>
      </header>

      <div className="result-grid">
        <ResultCard label="Your Pick" product={result.human_pick} variant="human-pick" />
        <ResultCard label="AI's #1 Pick" product={result.ai_pick} variant="ai-pick" showScore />
      </div>

      <div className="panel result-details">
        <h3>AI Reasoning</h3>
        <p>{ai_explanation.reason}</p>

        <h4 style={{ marginTop: '1rem', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)' }}>
          AI's Top 5 Candidates
        </h4>
        <ul>
          {ai_explanation.top_candidates.map((c, i) => (
            <li key={c.id} className={result.human_pick.id === c.id ? 'matched' : ''}>
              <span>
                <strong style={{ marginRight: '0.4rem', color: 'var(--ink-faint)' }}>#{i + 1}</strong>
                {c.title}
              </span>
              <strong>{c.score.toFixed(2)}</strong>
            </li>
          ))}
        </ul>

        {ai_explanation.shared_features?.length > 0 && (
          <div style={{ marginTop: '0.75rem' }}>
            <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
              Shared Features (Your Pick ∩ AI Pick)
            </h4>
            <div className="tag-list">
              {ai_explanation.shared_features.map((f) => (
                <FeatureTag key={f} name={f} />
              ))}
            </div>
          </div>
        )}

        {ai_explanation.learned_preferences?.length > 0 && (
          <div style={{ marginTop: '0.75rem' }}>
            <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
              What the AI Thinks You Like
            </h4>
            <div className="tag-list">
              {ai_explanation.learned_preferences.slice(0, 6).map(([name, weight]) => (
                <span key={name} className="feature-tag positive">
                  {name} ({weight > 0 ? '+' : ''}{weight})
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="metric-strip" style={{ justifyContent: 'center' }}>
        <span>Coherence {post_round_metrics.coherence_score.toFixed(2)}</span>
        <span>Predicted Rating {post_round_metrics.predicted_prefix_rating.toFixed(2)}</span>
      </div>

      <div className="round-actions">
        <button type="button" onClick={onNext} disabled={loadingNext}>
          {loadingNext ? 'Loading...' : result.game_complete ? 'View Final Summary' : 'Next Round →'}
        </button>
      </div>
    </section>
  );
}
