import type { Source, SourcePreview, FeedResponse, FeedItem, Stats, PollResult } from './types';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// Sources

export async function getSources(): Promise<Source[]> {
  return fetchJson(`${API_BASE}/sources`);
}

export async function previewSource(url: string): Promise<SourcePreview> {
  return fetchJson(`${API_BASE}/sources/preview`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export async function addSource(url: string): Promise<Source> {
  return fetchJson(`${API_BASE}/sources`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export async function pollSource(sourceId: string): Promise<PollResult> {
  return fetchJson(`${API_BASE}/sources/${sourceId}/poll`, {
    method: 'POST',
  });
}

export async function pollAllSources(): Promise<PollResult[]> {
  return fetchJson(`${API_BASE}/sources/poll-all`, {
    method: 'POST',
  });
}

export async function disableSource(sourceId: string): Promise<void> {
  await fetchJson(`${API_BASE}/sources/${sourceId}`, {
    method: 'DELETE',
  });
}

// Feed

export interface FeedOptions {
  showSeen?: boolean;
  sourceId?: string;
  limit?: number;
  offset?: number;
}

export async function getFeed(options: FeedOptions = {}): Promise<FeedResponse> {
  const params = new URLSearchParams();
  if (options.showSeen) params.set('show_seen', 'true');
  if (options.sourceId) params.set('source_id', options.sourceId);
  if (options.limit) params.set('limit', options.limit.toString());
  if (options.offset) params.set('offset', options.offset.toString());

  const query = params.toString();
  return fetchJson(`${API_BASE}/feed${query ? `?${query}` : ''}`);
}

export async function getItem(itemId: string): Promise<FeedItem> {
  return fetchJson(`${API_BASE}/items/${itemId}`);
}

export async function markSeen(itemId: string): Promise<void> {
  await fetchJson(`${API_BASE}/items/${itemId}/seen`, {
    method: 'POST',
  });
}

export async function markUnseen(itemId: string): Promise<void> {
  await fetchJson(`${API_BASE}/items/${itemId}/seen`, {
    method: 'DELETE',
  });
}

export async function hideItem(itemId: string): Promise<void> {
  await fetchJson(`${API_BASE}/items/${itemId}/hide`, {
    method: 'POST',
  });
}

// Stats

export async function getStats(): Promise<Stats> {
  return fetchJson(`${API_BASE}/stats`);
}

// Feedback

export interface FeedbackPayload {
  time_spent_ms?: number;
  max_scroll_pct?: number;
  completed?: boolean;
  scroll_events?: number;
  [key: string]: unknown;
}

export async function recordFeedback(
  itemId: string,
  eventType: string,
  payload: FeedbackPayload = {}
): Promise<void> {
  await fetchJson(`${API_BASE}/feedback`, {
    method: 'POST',
    body: JSON.stringify({
      item_id: itemId,
      event_type: eventType,
      payload,
    }),
  });
}

export async function getFeedbackStats(sourceId?: string): Promise<import('./types').FeedbackStats> {
  const params = new URLSearchParams();
  if (sourceId) params.set('source_id', sourceId);
  const query = params.toString();
  return fetchJson(`${API_BASE}/feedback/stats${query ? `?${query}` : ''}`);
}

// Feedback dimensions and explicit feedback

export async function getFeedbackDimensions(): Promise<import('./types').FeedbackDimension[]> {
  return fetchJson(`${API_BASE}/feedback/dimensions`);
}

export async function submitExplicitFeedback(
  payload: import('./types').ExplicitFeedbackPayload
): Promise<import('./types').ExplicitFeedback> {
  return fetchJson(`${API_BASE}/feedback/explicit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getItemExplicitFeedback(
  itemId: string
): Promise<import('./types').ExplicitFeedback | null> {
  return fetchJson(`${API_BASE}/feedback/explicit/${itemId}`);
}

// Model

export async function getModelStatus(): Promise<import('./types').ModelStatus> {
  return fetchJson(`${API_BASE}/model/status`);
}

export async function trainModel(): Promise<import('./types').TrainResult> {
  return fetchJson(`${API_BASE}/model/train`, {
    method: 'POST',
  });
}

export interface RefreshEmbeddingsResult {
  updated_count: number;
  skipped_count: number;
  failed_count: number;
}

export async function refreshEmbeddings(): Promise<RefreshEmbeddingsResult> {
  return fetchJson(`${API_BASE}/model/refresh-embeddings`, {
    method: 'POST',
  });
}

// Search / Source Discovery

export interface SearchOptions {
  providers?: string[];
  limit?: number;
}

export async function searchSources(
  query: string,
  options: SearchOptions = {}
): Promise<import('./types').SearchResponse> {
  const params = new URLSearchParams();
  params.set('q', query);
  if (options.providers?.length) {
    params.set('providers', options.providers.join(','));
  }
  if (options.limit) {
    params.set('limit', options.limit.toString());
  }
  return fetchJson(`${API_BASE}/search?${params.toString()}`);
}

export async function getSearchProviders(): Promise<{ providers: import('./types').SearchProvider[] }> {
  return fetchJson(`${API_BASE}/search/providers`);
}

// Discovery

export interface DiscoverOptions {
  prompt?: string;
  limit?: number;
  platforms?: string[];
}

export async function discoverSources(
  options: DiscoverOptions = {}
): Promise<import('./types').DiscoveryResponse> {
  const params = new URLSearchParams();
  if (options.prompt) params.set('prompt', options.prompt);
  if (options.limit) params.set('limit', options.limit.toString());
  if (options.platforms?.length) {
    params.set('platforms', options.platforms.join(','));
  }
  const query = params.toString();
  return fetchJson(`${API_BASE}/discover${query ? `?${query}` : ''}`);
}

export async function getInterestProfile(): Promise<import('./types').InterestProfile | null> {
  return fetchJson(`${API_BASE}/discover/interests`);
}

export async function getLLMStatus(): Promise<import('./types').LLMStatus> {
  return fetchJson(`${API_BASE}/discover/llm-status`);
}
