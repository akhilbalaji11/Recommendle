import logo from '../assets/logo.svg';

export default function WelcomeScreen({
  playerName,
  setPlayerName,
  categories = [],
  selectedCategory,
  setSelectedCategory,
  onStart,
  loading,
  leaderboard,
  onViewPlayer,
}) {
  const activeCategory = categories.find((c) => c.id === selectedCategory);
  const plural = activeCategory?.item_plural || 'items';
  const singular = activeCategory?.item_singular || 'item';

  return (
    <section className="screen shell welcome-screen">
      <div className="hero">
        <img src={logo} alt="Recommendle" className="app-logo" style={{ marginBottom: '0.75rem' }} />
        <h1>Can you out-pick the AI?</h1>
        <p className="subtitle">
          Build a taste profile, then go head-to-head for 5 rounds. Pick your favorite before the AI reveals its prediction.
        </p>
      </div>

      <div className="how-to-play">
        <div className="step-tile">
          <div className="step-num">1</div>
          <p>Choose 10 {plural} from a pool of 50 to build your taste profile.</p>
        </div>
        <div className="step-tile">
          <div className="step-num">2</div>
          <p>Rate your initial set so the AI can learn your preferences.</p>
        </div>
        <div className="step-tile">
          <div className="step-num">3</div>
          <p>Pick your favorite {singular} each round and see if the AI can match you.</p>
        </div>
      </div>

      <div className="start-form">
        <label htmlFor="player-name">Player name</label>
        <input
          id="player-name"
          value={playerName}
          onChange={(event) => setPlayerName(event.target.value)}
          placeholder="Enter your name"
          maxLength={80}
          disabled={loading}
        />

        <label htmlFor="category-select">Category</label>
        <select
          id="category-select"
          className="category-select"
          value={selectedCategory}
          onChange={(event) => setSelectedCategory(event.target.value)}
          disabled={loading || categories.length === 0}
        >
          {categories.map((category) => (
            <option key={category.id} value={category.id} disabled={category.available_count < 50}>
              {category.display_name} ({category.available_count}){category.available_count < 50 ? ' - ingest required' : ''}
            </option>
          ))}
        </select>

        <button type="button" onClick={onStart} disabled={loading || !playerName.trim()}>
          {loading ? 'Starting...' : 'Play'}
        </button>
      </div>

      {leaderboard && leaderboard.length > 0 && (
        <div className="panel leaderboard-panel welcome-leaderboard">
          <h3>Leaderboard</h3>
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
        </div>
      )}
    </section>
  );
}
