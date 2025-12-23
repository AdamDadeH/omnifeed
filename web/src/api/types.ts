export interface Source {
  id: string;
  source_type: string;
  uri: string;
  display_name: string;
  avatar_url: string | null;
  status: string;
  created_at: string;
  last_polled_at: string | null;
  item_count: number;
}

export interface SourcePreview {
  source_type: string;
  uri: string;
  display_name: string;
  avatar_url: string | null;
  description: string | null;
}

export interface FeedItem {
  id: string;
  source_id: string;
  source_name: string;
  url: string;
  title: string;
  creator_name: string;
  published_at: string;
  content_type: string;
  seen: boolean;
  hidden: boolean;
  metadata: Record<string, unknown>;
  score: number | null;
}

export interface FeedResponse {
  items: FeedItem[];
  total_count: number;
  unseen_count: number;
}

export interface Stats {
  source_count: number;
  total_items: number;
  unseen_items: number;
  hidden_items: number;
}

export interface PollResult {
  source_id: string;
  source_name: string;
  new_items: number;
}

export interface FeedbackEvent {
  id: string;
  item_id: string;
  event_type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface StatsFilter {
  source_id?: string;
  source_name?: string;
  content_type?: string;
}

export interface EngagementStats {
  total_events: number;
  total_engagements: number;
  avg_time_spent_ms: number;
  avg_progress_pct: number;
  completion_rate: number;
  total_time_spent_ms: number;
}

export interface StatsSlice {
  filter: StatsFilter;
  stats: EngagementStats;
}

export interface FeedbackStats {
  total_events: number;
  slices: StatsSlice[];
  recent_events: FeedbackEvent[];
}

// Feedback dimensions and explicit feedback

export interface FeedbackOption {
  id: string;
  dimension_id: string;
  label: string;
  description: string | null;
  sort_order: number;
  active: boolean;
}

export interface FeedbackDimension {
  id: string;
  name: string;
  description: string | null;
  allow_multiple: boolean;
  active: boolean;
  options: FeedbackOption[];
}

export interface ExplicitFeedback {
  id: string;
  item_id: string;
  timestamp: string;
  reward_score: number;
  selections: Record<string, string[]>;
  notes: string | null;
  completion_pct: number | null;
  is_checkpoint: boolean;
}

export interface ExplicitFeedbackPayload {
  item_id: string;
  reward_score: number;
  selections?: Record<string, string[]>;
  notes?: string;
  completion_pct?: number;
  is_checkpoint?: boolean;
}

// Model status and training

export interface ModelStatus {
  is_trained: boolean;
  source_count: number;
  model_path: string;
  model_exists: boolean;
}

export interface TrainResult {
  status: string;
  example_count: number;
  click_examples: number;
  reward_examples: number;
  // Diagnostic fields (when insufficient_data)
  total_items?: number;
  items_with_embeddings?: number;
  click_events?: number;
  explicit_feedbacks?: number;
  engaged_items?: number;
  missing_embeddings?: number;
  issues?: string[];
}

// Search / Source Discovery

export interface SearchSuggestion {
  url: string;
  name: string;
  source_type: string;
  description: string;
  thumbnail_url: string | null;
  subscriber_count: number | null;
  provider: string;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  query: string;
  results: SearchSuggestion[];
  providers_used: string[];
}

export interface SearchProvider {
  id: string;
  source_types: string[];
}
