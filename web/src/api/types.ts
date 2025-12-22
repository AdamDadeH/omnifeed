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
