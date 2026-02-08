import { useEffect, useState } from 'react';
import { formatPrice, getGameSummary, getPlayerHistory } from '../lib/api';

export default function PlayerStatsModal({ playerName, onClose }) {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedGameId, setExpandedGameId] = useState(null);
  const [gameSummary, setGameSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  useEffect(() => {
    if (!playerName) return;
    setLoading(true);
    getPlayerHistory(playerName)
      .then(setGames)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [playerName]);

  async function handleExpandGame(gameId) {
    if (expandedGameId === gameId) {
      setExpandedGameId(null);
      setGameSummary(null);
      return;
    }
    setExpandedGameId(gameId);
    setGameSummary(null);
    setSummaryLoading(true);
    try {
      const summary = await getGameSummary(gameId);
      setGameSummary(summary);
    } catch (err) {
      setGameSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }

  // Aggregate stats
  const totalGames = games.length;
  const totalWins = games.filter((g) => g.human_score > g.ai_score).length;
  const avgAccuracy = totalGames > 0
    ? (games.reduce((sum, g) => sum + g.ai_accuracy, 0) / totalGames * 100).toFixed(0)
    : 0;
  const bestDelta = totalGames > 0
    ? Math.max(...games.map((g) => g.score_difference))
    : 0;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="player-stats-card" onClick={(e) => e.stopPropagation()}>
        <div className="player-stats-header">
          <div>
            <p className="eyebrow">Player Profile</p>
            <h2>{playerName}</h2>
          </div>
          <button type="button" className="ghost close-btn" onClick={onClose}>Close</button>
        </div>

        {loading && <p className="muted" style={{ textAlign: 'center', padding: '2rem' }}>Loading...</p>}
        {error && <p className="muted" style={{ textAlign: 'center', padding: '2rem' }}>Error: {error}</p>}

        {!loading && !error && totalGames === 0 && (
          <p className="muted" style={{ textAlign: 'center', padding: '2rem' }}>No completed games yet.</p>
        )}

        {!loading && !error && totalGames > 0 && (
          <>
            {/* Aggregate stats */}
            <div className="stats-row">
              <div className="stat-card">
                <span className="stat-value">{totalGames}</span>
                <span className="stat-label">Games Played</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{totalWins}</span>
                <span className="stat-label">Wins</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{avgAccuracy}%</span>
                <span className="stat-label">Avg AI Accuracy</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">+{bestDelta}</span>
                <span className="stat-label">Best Margin</span>
              </div>
            </div>

            {/* Game history */}
            <div className="game-history">
              <h3 style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.5rem' }}>
                Game History
              </h3>
              <ul className="history-list">
                {games.map((g) => {
                  const delta = g.score_difference;
                  const won = delta > 0;
                  const tied = delta === 0;
                  const outcome = won ? 'Won' : tied ? 'Tied' : 'Lost';
                  const isExpanded = expandedGameId === g.game_id;

                  return (
                    <li key={g.game_id} className={`history-item ${isExpanded ? 'expanded' : ''}`}>
                      <button
                        type="button"
                        className="history-row"
                        onClick={() => handleExpandGame(g.game_id)}
                      >
                        <span className={`history-outcome ${won ? 'win' : tied ? 'tie' : 'loss'}`}>
                          {outcome}
                        </span>
                        <span className="history-score">
                          {g.human_score} – {g.ai_score}
                        </span>
                        <span className="history-accuracy">
                          {(g.ai_accuracy * 100).toFixed(0)}% AI
                        </span>
                        <span className="history-date">
                          {new Date(g.created_at).toLocaleDateString()}
                        </span>
                        <span className="history-expand">{isExpanded ? '▲' : '▼'}</span>
                      </button>

                      {isExpanded && (
                        <div className="history-detail">
                          {summaryLoading && <p className="muted">Loading game details...</p>}
                          {!summaryLoading && gameSummary && (
                            <>
                              {/* Round-by-round */}
                              <div className="detail-section">
                                <h4>Round Results</h4>
                                <div className="round-pills">
                                  {gameSummary.round_stats.map((r) => (
                                    <span
                                      key={r.round_number}
                                      className={`round-pill ${r.ai_correct ? 'ai-won' : 'human-won'}`}
                                      title={`R${r.round_number}: AI rank #${r.ai_rank_of_pick ?? '?'}`}
                                    >
                                      R{r.round_number}
                                    </span>
                                  ))}
                                </div>
                              </div>

                              {/* Learned preferences */}
                              {gameSummary.learned_preferences?.length > 0 && (
                                <div className="detail-section">
                                  <h4>Learned Preferences</h4>
                                  <div className="tag-list">
                                    {gameSummary.learned_preferences.slice(0, 6).map(([name, weight]) => (
                                      <span key={name} className="feature-tag positive">
                                        {name}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Top recs */}
                              {gameSummary.top5_recommendations?.length > 0 && (
                                <div className="detail-section">
                                  <h4>Top Recommendations</h4>
                                  <ul className="detail-rec-list">
                                    {gameSummary.top5_recommendations.slice(0, 3).map((rec, i) => (
                                      <li key={rec.id}>
                                        <strong>#{i + 1}</strong> {rec.title}
                                        <span className="muted"> · {rec.vendor} · {formatPrice(rec.price_min, rec.price_max)}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
