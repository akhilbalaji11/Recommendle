import React from 'react';
import logo from '../assets/logo.svg';

export default function WelcomeScreen({ playerName, setPlayerName, onStart, loading }) {
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
          <p>Choose 10 pens from a pool of 50 to build your taste profile.</p>
        </div>
        <div className="step-tile">
          <div className="step-num">2</div>
          <p>Rate your initial set so the AI can learn your preferences.</p>
        </div>
        <div className="step-tile">
          <div className="step-num">3</div>
          <p>Pick your favorite each round — see if the AI can match you.</p>
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
        <button type="button" onClick={onStart} disabled={loading || !playerName.trim()}>
          {loading ? 'Starting...' : 'Play'}
        </button>
      </div>
    </section>
  );
}
