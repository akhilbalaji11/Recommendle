import { useEffect, useState } from 'react';
import { formatPrice, getGameSummary } from '../lib/api';

function MiniBarChart({ data, label, color }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="mini-chart">
      <h4>{label}</h4>
      <div className="chart-bars">
        {data.map((d) => (
          <div key={d.label} className="chart-bar-col">
            <div
              className="chart-bar"
              style={{
                height: `${(d.value / max) * 100}%`,
                background: d.highlight ? color : 'var(--border)',
              }}
            />
            <span className="chart-bar-label">{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScoreChart({ roundStats }) {
  if (!roundStats || roundStats.length === 0) return null;
  const maxScore = Math.max(
    ...roundStats.map((r) => Math.max(r.cumulative_human, r.cumulative_ai)),
    10,
  );
  const w = 280;
  const h = 120;
  const pad = 24;
  const plotW = w - pad * 2;
  const plotH = h - pad * 2;

  const humanPts = roundStats.map((r, i) => {
    const x = pad + (i / (roundStats.length - 1 || 1)) * plotW;
    const y = pad + plotH - (r.cumulative_human / maxScore) * plotH;
    return `${x},${y}`;
  });
  const aiPts = roundStats.map((r, i) => {
    const x = pad + (i / (roundStats.length - 1 || 1)) * plotW;
    const y = pad + plotH - (r.cumulative_ai / maxScore) * plotH;
    return `${x},${y}`;
  });

  return (
    <div className="mini-chart">
      <h4>Score Progression</h4>
      <svg viewBox={`0 0 ${w} ${h}`} className="line-chart">
        <line x1={pad} y1={pad} x2={pad} y2={pad + plotH} stroke="var(--border)" />
        <line x1={pad} y1={pad + plotH} x2={pad + plotW} y2={pad + plotH} stroke="var(--border)" />
        <polyline points={humanPts.join(' ')} fill="none" stroke="var(--correct)" strokeWidth="2.5" />
        <polyline points={aiPts.join(' ')} fill="none" stroke="var(--present)" strokeWidth="2.5" />
        {roundStats.map((r, i) => {
          const x = pad + (i / (roundStats.length - 1 || 1)) * plotW;
          return (
            <text key={i} x={x} y={pad + plotH + 14} textAnchor="middle" fontSize="9" fill="var(--ink-faint)">
              R{r.round_number}
            </text>
          );
        })}
        <circle cx={pad + 10} cy={8} r="4" fill="var(--correct)" />
        <text x={pad + 18} y={11} fontSize="8" fill="var(--ink-soft)">You</text>
        <circle cx={pad + 50} cy={8} r="4" fill="var(--present)" />
        <text x={pad + 58} y={11} fontSize="8" fill="var(--ink-soft)">AI</text>
      </svg>
    </div>
  );
}

export default function FinalSummary({
  playerName,
  humanScore,
  aiScore,
  gameId,
  leaderboard,
  onRestart,
  onViewPlayer,
}) {
  const [summary, setSummary] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!gameId) return;
    getGameSummary(gameId)
      .then(setSummary)
      .catch((err) => setLoadError(err.message));
  }, [gameId]);

  const delta = humanScore - aiScore;
  let verdict = 'Tie Game';
  if (delta > 0) verdict = 'You Win!';
  if (delta < 0) verdict = 'AI Wins!';

  const roundAccuracyData = summary?.round_stats?.map((r) => ({
    label: `R${r.round_number}`,
    value: r.ai_correct ? 1 : 0,
    highlight: r.ai_correct,
  })) || [];

  const coherenceData = summary?.round_stats?.map((r) => ({
    label: `R${r.round_number}`,
    value: r.coherence,
    highlight: true,
  })) || [];

  return (
    <section className="screen shell">
      <header className="section-header" style={{ textAlign: 'center', justifyContent: 'center', flexDirection: 'column', alignItems: 'center' }}>
        <p className="eyebrow">Game Over</p>
        <h2 style={{ fontSize: 'clamp(1.6rem, 4vw, 2.4rem)' }}>{verdict}</h2>
        <p className="muted">{playerName} · Final Score: You {humanScore} — AI {aiScore}</p>
      </header>

      {/* Accuracy stats */}
      {summary && (
        <div className="stats-row">
          <div className="stat-card">
            <span className="stat-value">{(summary.accuracy.top3_rate * 100).toFixed(0)}%</span>
            <span className="stat-label">AI Top-3 Accuracy</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{(summary.accuracy.exact_rate * 100).toFixed(0)}%</span>
            <span className="stat-label">AI Exact Match Rate</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{summary.total_rounds}</span>
            <span className="stat-label">Rounds Played</span>
          </div>
        </div>
      )}

      {/* Charts row */}
      {summary && (
        <div className="charts-row">
          <ScoreChart roundStats={summary.round_stats} />
          <MiniBarChart
            data={roundAccuracyData}
            label="AI Correct by Round"
            color="var(--correct)"
          />
          <MiniBarChart
            data={coherenceData}
            label="Preference Coherence"
            color="var(--present)"
          />
        </div>
      )}

      {/* What the AI learned */}
      {summary && (summary.learned_preferences?.length > 0 || summary.learned_dislikes?.length > 0) && (
        <div className="panel">
          <h3>What the AI Learned About You</h3>
          {summary.learned_preferences?.length > 0 && (
            <div style={{ marginTop: '0.5rem' }}>
              <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
                You Tend to Prefer
              </h4>
              <div className="tag-list">
                {summary.learned_preferences.map(([name, weight]) => (
                  <span key={name} className="feature-tag positive">
                    {name} (+{weight})
                  </span>
                ))}
              </div>
            </div>
          )}
          {summary.learned_dislikes?.length > 0 && (
            <div style={{ marginTop: '0.5rem' }}>
              <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
                You Tend to Avoid
              </h4>
              <div className="tag-list">
                {summary.learned_dislikes.map(([name, weight]) => (
                  <span key={name} className="feature-tag negative">
                    {name} ({weight})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Top 5 Recommendations */}
      {summary?.top5_recommendations?.length > 0 && (
        <div className="panel">
          <h3>AI's Top 5 Picks for You</h3>
          <p className="muted" style={{ marginBottom: '0.75rem' }}>
            Based on everything the model learned, these are the products it thinks you'd love most.
          </p>
          <ul className="rec-list">
            {summary.top5_recommendations.map((rec, i) => (
              <li key={rec.id} className="rec-item">
                <span className="rec-rank">#{i + 1}</span>
                <div className="rec-info">
                  <strong>{rec.title}</strong>
                  <span className="muted">{rec.vendor} · {formatPrice(rec.price_min, rec.price_max)}</span>
                </div>
                <span className="rec-score">{rec.score.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {loadError && <p className="muted" style={{ textAlign: 'center' }}>Could not load game insights: {loadError}</p>}

      {/* Leaderboard */}
      <div className="panel leaderboard-panel">
        <h3>Leaderboard</h3>
        {leaderboard.length === 0 ? (
          <p className="muted">No completed sessions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Player</th>
                <th>Human</th>
                <th>AI</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((entry) => (
                <tr
                  key={`${entry.player_name}-${entry.created_at}`}
                  className="leaderboard-row-clickable"
                  onClick={() => onViewPlayer && onViewPlayer(entry.player_name)}
                  title={`View ${entry.player_name}'s stats`}
                >
                  <td>{entry.rank}</td>
                  <td className="player-name-cell">{entry.player_name}</td>
                  <td>{entry.human_score}</td>
                  <td>{entry.ai_score}</td>
                  <td>{entry.score_difference >= 0 ? '+' : ''}{entry.score_difference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="round-actions" style={{ justifyContent: 'center' }}>
        <button type="button" onClick={onRestart}>Play Again</button>
      </div>
    </section>
  );
}
