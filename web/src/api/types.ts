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

export interface ExtractedCreator {
  creator_id: string;
  name: string;
  role: string;
  confidence: number;
}

export interface FeedItem {
  id: string;
  source_id: string;
  source_name: string;
  url: string;
  title: string;
  creator_id: string | null;
  creator_name: string;
  published_at: string;
  content_type: string;
  seen: boolean;
  hidden: boolean;
  metadata: Record<string, unknown> & {
    extracted_creators?: ExtractedCreator[];
    thumbnail?: string;
    content_text?: string;
    duration_seconds?: number;
  };
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

// Creator types

export interface Creator {
  id: string;
  name: string;
  creator_type: string;
  avatar_url: string | null;
  bio: string | null;
  url: string | null;
  item_count: number;
  avg_score: number | null;
}

export interface CreatorStats {
  creator_id: string;
  total_items: number;
  total_feedback_events: number;
  avg_reward_score: number | null;
  content_types: Record<string, number>;
}

export interface SourceStats {
  source_id: string;
  total_items: number;
  total_feedback_events: number;
  avg_reward_score: number | null;
  unique_creators: number;
}

// Model status and training

export interface ModelInfo {
  is_trained: boolean;
  model_exists: boolean;
  supports_objectives: boolean;
  is_default: boolean;
  source_count?: number;
  objective_counts?: Record<string, number>;
}

export interface ModelStatus {
  models: Record<string, ModelInfo>;
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

// Discovery

export interface DiscoveryResult {
  url: string;
  name: string;
  source_type: string;
  description: string;
  thumbnail_url: string | null;
  subscriber_count: number | null;
  relevance_score: number;
  explanation: string;
  matched_interests: string[];
  from_query: string;
}

export interface Interest {
  topic: string;
  confidence: number;
  example_items: string[];
}

export interface InterestProfile {
  interests: Interest[];
  top_creators: string[];
  content_types: string[];
  generated_queries: string[];
}

export interface DiscoveryResponse {
  results: DiscoveryResult[];
  queries_used: string[];
  interest_profile: InterestProfile | null;
  mode: 'prompt' | 'auto';
}

export interface LLMStatus {
  current: string | null;
  backends: {
    ollama: { available: boolean; models: string[] };
    openai: { available: boolean; model: string };
    anthropic: { available: boolean; model: string };
  };
}

// Sitemap config

export interface SitemapSelectors {
  title: string | null;
  description: string | null;
  image: string | null;
  author: string | null;
}

export interface SitemapConfig {
  domain: string;
  selectors: SitemapSelectors;
  fetch_content: boolean;
  max_items: number;
}

export interface SitemapConfigPayload {
  selectors?: Partial<SitemapSelectors>;
  fetch_content?: boolean;
  max_items?: number;
}
