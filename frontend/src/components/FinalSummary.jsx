import React from 'react';

export default function FinalSummary({
  playerName,
  humanScore,
  aiScore,
  leaderboard,
  onRestart,
}) {
  const delta = humanScore - aiScore;
  let verdict = 'Tie game';
  if (delta > 0) verdict = 'Human wins';
  if (delta < 0) verdict = 'AI wins';

  return (
    <section className="screen shell">
      <header className="section-header">
        <div>
          <p className="eyebrow">Final Summary</p>
          <h2>{verdict}</h2>
          <p className="muted">{playerName} · score delta {delta >= 0 ? '+' : ''}{delta}</p>
        </div>
        <div className="scoreline">
          <span>You: {humanScore}</span>
          <span>AI: {aiScore}</span>
        </div>
      </header>

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
                <tr key={`${entry.player_name}-${entry.created_at}`}>
                  <td>{entry.rank}</td>
                  <td>{entry.player_name}</td>
                  <td>{entry.human_score}</td>
                  <td>{entry.ai_score}</td>
                  <td>{entry.score_difference >= 0 ? '+' : ''}{entry.score_difference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="round-actions">
        <button type="button" onClick={onRestart}>Start New Session</button>
      </div>
    </section>
  );
}
