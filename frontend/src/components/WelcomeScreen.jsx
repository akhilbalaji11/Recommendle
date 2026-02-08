import React from 'react';

export default function WelcomeScreen({ playerName, setPlayerName, onStart, loading }) {
  return (
    <section className="screen shell welcome-screen">
      <div className="hero">
        <p className="eyebrow">Decidio Senior Design Prototype</p>
        <h1>Sequential Preference Duel</h1>
        <p className="subtitle">
          Build a preference profile from 10 fountain pens, then play 10 rounds where the AI tries to match your next choice.
        </p>
      </div>

      <div className="panel">
        <h2>Game Loop</h2>
        <ol className="steps">
          <li>Select exactly 10 pens from a diverse set of 50.</li>
          <li>Rate the selected set once to initialize prefix quality.</li>
          <li>In each round, pick your favorite from 10 candidates before the AI prediction is revealed.</li>
        </ol>

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
          <button type="button" onClick={onStart} disabled={loading || !playerName.trim()}>
            {loading ? 'Starting session...' : 'Start Session'}
          </button>
        </div>
      </div>
    </section>
  );
}
