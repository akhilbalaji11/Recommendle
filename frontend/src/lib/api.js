const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8015').replace(/\/$/, '');

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch {
      // Ignore JSON parsing errors; use status text.
    }
    throw new Error(detail);
  }

  return response.json();
}

export async function startGame(playerName) {
  return request('/api/game/start', {
    method: 'POST',
    body: JSON.stringify({ player_name: playerName }),
  });
}

export async function getOnboarding(gameId) {
  return request(`/api/game/${gameId}/onboarding`);
}

export async function submitOnboarding(gameId, selectedProductIds, rating) {
  return request(`/api/game/${gameId}/onboarding/submit`, {
    method: 'POST',
    body: JSON.stringify({
      selected_product_ids: selectedProductIds,
      rating,
    }),
  });
}

export async function startRound(gameId) {
  return request(`/api/game/${gameId}/round/start`, {
    method: 'POST',
  });
}

export async function submitRoundPick(gameId, roundNumber, productId) {
  return request(`/api/game/${gameId}/round/${roundNumber}/pick`, {
    method: 'POST',
    body: JSON.stringify({ product_id: productId }),
  });
}

export async function getGameStatus(gameId) {
  return request(`/api/game/${gameId}/status`);
}

export async function getLeaderboard(limit = 10) {
  return request(`/api/game/leaderboard?limit=${limit}`);
}

export function formatPrice(priceMin, priceMax) {
  if (typeof priceMin !== 'number' && typeof priceMax !== 'number') {
    return 'N/A';
  }
  if (typeof priceMin === 'number' && typeof priceMax === 'number' && priceMin !== priceMax) {
    return `$${priceMin.toFixed(0)} - $${priceMax.toFixed(0)}`;
  }
  const value = typeof priceMin === 'number' ? priceMin : priceMax;
  return `$${value.toFixed(0)}`;
}
