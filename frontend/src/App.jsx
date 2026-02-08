import { useEffect, useState } from 'react';
import logo from './assets/logo.svg';
import BrainModePanel from './components/BrainModePanel';
import FinalSummary from './components/FinalSummary';
import OnboardingGrid from './components/OnboardingGrid';
import PlayerStatsModal from './components/PlayerStatsModal';
import RoundArena from './components/RoundArena';
import RoundResultPanel from './components/RoundResultPanel';
import SetRatingModal from './components/SetRatingModal';
import WelcomeScreen from './components/WelcomeScreen';
import {
    getLeaderboard,
    getOnboarding,
    startGame,
    startRound,
    submitOnboarding,
    submitRoundPick,
} from './lib/api';

const VIEW = {
  WELCOME: 'welcome',
  ONBOARDING: 'onboarding',
  ROUND: 'round',
  RESULT: 'result',
  FINAL: 'final',
};

export default function App() {
  const [view, setView] = useState(VIEW.WELCOME);
  const [playerName, setPlayerName] = useState('');
  const [game, setGame] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [rating, setRating] = useState(3);
  const [ratingModalOpen, setRatingModalOpen] = useState(false);
  const [roundData, setRoundData] = useState(null);
  const [selectedRoundPick, setSelectedRoundPick] = useState('');
  const [roundResult, setRoundResult] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [mode, setMode] = useState('visual');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState({
    start: false,
    onboarding: false,
    pick: false,
    next: false,
  });
  const [welcomeLeaderboard, setWelcomeLeaderboard] = useState([]);
  const [viewingPlayer, setViewingPlayer] = useState(null);

  // Load leaderboard for the welcome page on initial render
  useEffect(() => {
    getLeaderboard(10)
      .then(setWelcomeLeaderboard)
      .catch(() => {});
  }, []);

  const totalRounds = game?.total_rounds ?? 5;
  const humanScore = game?.human_score ?? 0;
  const aiScore = game?.ai_score ?? 0;

  function resetAll() {
    setView(VIEW.WELCOME);
    setGame(null);
    setOnboarding(null);
    setSelectedIds([]);
    setRating(3);
    setRatingModalOpen(false);
    setRoundData(null);
    setSelectedRoundPick('');
    setRoundResult(null);
    setLeaderboard([]);
    setError('');
    setBusy({ start: false, onboarding: false, pick: false, next: false });
    // Refresh welcome leaderboard
    getLeaderboard(10)
      .then(setWelcomeLeaderboard)
      .catch(() => {});
  }

  async function loadNextRound(gameId) {
    const round = await startRound(gameId);
    setRoundData(round);
    setSelectedRoundPick('');
    setView(VIEW.ROUND);
  }

  async function handleStart() {
    setError('');
    setBusy((prev) => ({ ...prev, start: true }));
    try {
      const created = await startGame(playerName);
      const onboardingPayload = await getOnboarding(created.id);
      setGame(created);
      setOnboarding(onboardingPayload);
      setSelectedIds([]);
      setView(VIEW.ONBOARDING);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, start: false }));
    }
  }

  function handleToggleOnboarding(productId) {
    setSelectedIds((prev) => {
      if (prev.includes(productId)) {
        return prev.filter((id) => id !== productId);
      }
      if (prev.length >= 10) {
        return prev;
      }
      return [...prev, productId];
    });
  }

  async function handleSubmitOnboarding() {
    if (!game || selectedIds.length !== 10) {
      setError('Select exactly 10 products before continuing.');
      return;
    }

    setError('');
    setBusy((prev) => ({ ...prev, onboarding: true }));
    try {
      await submitOnboarding(game.id, selectedIds, rating);
      setGame((prev) => ({ ...prev, status: 'playing' }));
      setRatingModalOpen(false);
      await loadNextRound(game.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, onboarding: false }));
    }
  }

  async function handleSubmitRoundPick() {
    if (!game || !roundData || !selectedRoundPick) {
      return;
    }

    setError('');
    setBusy((prev) => ({ ...prev, pick: true }));
    try {
      const result = await submitRoundPick(game.id, roundData.round_number, selectedRoundPick);
      setRoundResult(result);
      setGame((prev) => ({
        ...prev,
        human_score: result.total_human_score,
        ai_score: result.total_ai_score,
      }));
      setView(VIEW.RESULT);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, pick: false }));
    }
  }

  async function handleResultNext() {
    if (!game || !roundResult) {
      return;
    }

    setError('');
    setBusy((prev) => ({ ...prev, next: true }));
    try {
      if (roundResult.game_complete) {
        const board = await getLeaderboard(10);
        setLeaderboard(board);
        setView(VIEW.FINAL);
      } else {
        await loadNextRound(game.id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, next: false }));
    }
  }

  return (
    <main className="app-root">
      {view !== VIEW.WELCOME && (
        <header className="app-header">
          <img src={logo} alt="Recommendle" className="app-logo" />
        </header>
      )}

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button type="button" onClick={() => setError('')}>Dismiss</button>
        </div>
      )}

      {view !== VIEW.WELCOME && view !== VIEW.FINAL && (
        <BrainModePanel mode={mode} onModeChange={setMode} />
      )}

      {view === VIEW.WELCOME && (
        <WelcomeScreen
          playerName={playerName}
          setPlayerName={setPlayerName}
          onStart={handleStart}
          loading={busy.start}
          leaderboard={welcomeLeaderboard}
          onViewPlayer={(name) => setViewingPlayer(name)}
        />
      )}

      {viewingPlayer && (
        <PlayerStatsModal
          playerName={viewingPlayer}
          onClose={() => setViewingPlayer(null)}
        />
      )}

      {view === VIEW.ONBOARDING && onboarding && (
        <>
          <OnboardingGrid
            products={onboarding.products}
            selectedIds={selectedIds}
            onToggle={handleToggleOnboarding}
            onOpenRating={() => setRatingModalOpen(true)}
            mode={mode}
          />
          <SetRatingModal
            open={ratingModalOpen}
            rating={rating}
            setRating={setRating}
            loading={busy.onboarding}
            onClose={() => setRatingModalOpen(false)}
            onSubmit={handleSubmitOnboarding}
          />
        </>
      )}

      {view === VIEW.ROUND && (
        <RoundArena
          round={roundData}
          totalRounds={totalRounds}
          humanScore={humanScore}
          aiScore={aiScore}
          mode={mode}
          selectedPick={selectedRoundPick}
          onSelectPick={setSelectedRoundPick}
          onSubmitPick={handleSubmitRoundPick}
          submitting={busy.pick}
        />
      )}

      {view === VIEW.RESULT && (
        <RoundResultPanel
          result={roundResult}
          onNext={handleResultNext}
          loadingNext={busy.next}
        />
      )}

      {view === VIEW.FINAL && (
        <FinalSummary
          playerName={playerName}
          humanScore={humanScore}
          aiScore={aiScore}
          gameId={game?.id}
          leaderboard={leaderboard}
          onRestart={resetAll}
          onViewPlayer={(name) => setViewingPlayer(name)}
        />
      )}
    </main>
  );
}
