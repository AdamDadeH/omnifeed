import { useState, useEffect, useCallback } from 'react';
import { previewSource, addSource, pollSource, searchSources, getSearchProviders, discoverSources, getLLMStatus } from '../api/client';
import type { SourcePreview, SearchSuggestion, SearchProvider, DiscoveryResult, InterestProfile, LLMStatus } from '../api/types';

interface Props {
  onClose: () => void;
  onAdded: () => void;
}

type Tab = 'search' | 'discover' | 'url';

export function AddSourceModal({ onClose, onAdded }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('search');

  // URL tab state
  const [url, setUrl] = useState('');
  const [preview, setPreview] = useState<SourcePreview | null>(null);

  // Search tab state
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchSuggestion[]>([]);
  const [providers, setProviders] = useState<SearchProvider[]>([]);
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);

  // Discover tab state
  const [discoverPrompt, setDiscoverPrompt] = useState('');
  const [discoverResults, setDiscoverResults] = useState<DiscoveryResult[]>([]);
  const [interestProfile, setInterestProfile] = useState<InterestProfile | null>(null);
  const [llmStatus, setLLMStatus] = useState<LLMStatus | null>(null);
  const [discoverMode, setDiscoverMode] = useState<'prompt' | 'auto'>('auto');

  // Shared state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

  // Load providers and LLM status on mount
  useEffect(() => {
    getSearchProviders()
      .then(({ providers }) => setProviders(providers))
      .catch(console.error);

    getLLMStatus()
      .then(setLLMStatus)
      .catch(console.error);
  }, []);

  // URL tab handlers
  const handlePreview = async () => {
    if (!url.trim()) return;

    setLoading(true);
    setError(null);
    setPreview(null);

    try {
      const data = await previewSource(url.trim());
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview source');
    } finally {
      setLoading(false);
    }
  };

  const handleAddUrl = async () => {
    if (!url.trim()) return;
    await addSourceByUrl(url.trim());
  };

  // Search tab handlers
  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResults([]);

    try {
      const data = await searchSources(query.trim(), {
        providers: selectedProviders.length ? selectedProviders : undefined,
        limit: 15,
      });
      setResults(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }, [query, selectedProviders]);

  // Discover tab handlers
  const handleDiscover = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDiscoverResults([]);

    try {
      const data = await discoverSources({
        prompt: discoverMode === 'prompt' ? discoverPrompt.trim() : undefined,
        limit: 15,
      });
      setDiscoverResults(data.results);
      if (data.interest_profile) {
        setInterestProfile(data.interest_profile);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setLoading(false);
    }
  }, [discoverPrompt, discoverMode]);

  // Shared add handler
  const addSourceByUrl = async (sourceUrl: string) => {
    setAddingUrl(sourceUrl);
    setError(null);

    try {
      const source = await addSource(sourceUrl);
      await pollSource(source.id);
      onAdded();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add source');
      setAddingUrl(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !loading) {
      if (activeTab === 'url') {
        if (preview) {
          handleAddUrl();
        } else {
          handlePreview();
        }
      } else if (activeTab === 'search') {
        handleSearch();
      } else if (activeTab === 'discover' && discoverMode === 'prompt') {
        handleDiscover();
      }
    }
    if (e.key === 'Escape') {
      onClose();
    }
  };

  const toggleProvider = (id: string) => {
    setSelectedProviders(prev =>
      prev.includes(id)
        ? prev.filter(p => p !== id)
        : [...prev, id]
    );
  };

  const formatSubscribers = (count: number | null) => {
    if (!count) return null;
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
    if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
    return count.toString();
  };

  const getProviderColor = (provider: string) => {
    switch (provider) {
      case 'youtube': return 'bg-red-600';
      case 'bandcamp': return 'bg-cyan-600';
      case 'qobuz': return 'bg-blue-600';
      case 'feedly': return 'bg-green-600';
      default: return 'bg-neutral-600';
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-neutral-900 rounded-lg shadow-xl w-full max-w-lg mx-4 overflow-hidden max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with Tabs */}
        <div className="px-4 py-3 border-b border-neutral-800">
          <div className="flex gap-4">
            <button
              onClick={() => setActiveTab('search')}
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                activeTab === 'search'
                  ? 'text-blue-400 border-blue-400'
                  : 'text-neutral-400 border-transparent hover:text-neutral-200'
              }`}
            >
              Search
            </button>
            <button
              onClick={() => setActiveTab('discover')}
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                activeTab === 'discover'
                  ? 'text-purple-400 border-purple-400'
                  : 'text-neutral-400 border-transparent hover:text-neutral-200'
              }`}
            >
              Discover
            </button>
            <button
              onClick={() => setActiveTab('url')}
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                activeTab === 'url'
                  ? 'text-blue-400 border-blue-400'
                  : 'text-neutral-400 border-transparent hover:text-neutral-200'
              }`}
            >
              Add by URL
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-4 flex-1 overflow-y-auto">
          {activeTab === 'search' ? (
            <div className="space-y-4">
              {/* Search Input */}
              <div>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search for creators, topics, channels..."
                  className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-blue-500"
                  autoFocus
                />
              </div>

              {/* Provider Filters */}
              {providers.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {providers.map(p => (
                    <button
                      key={p.id}
                      onClick={() => toggleProvider(p.id)}
                      className={`px-2 py-1 text-xs rounded transition-colors ${
                        selectedProviders.length === 0 || selectedProviders.includes(p.id)
                          ? `${getProviderColor(p.id)} text-white`
                          : 'bg-neutral-800 text-neutral-500'
                      }`}
                    >
                      {p.id}
                    </button>
                  ))}
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="text-sm text-red-400 bg-red-900/20 px-3 py-2 rounded">
                  {error}
                </div>
              )}

              {/* Results */}
              {results.length > 0 && (
                <div className="space-y-2">
                  {results.map((result, idx) => (
                    <div
                      key={`${result.url}-${idx}`}
                      className="flex items-center gap-3 p-2 bg-neutral-800/50 rounded hover:bg-neutral-800 transition-colors"
                    >
                      {/* Thumbnail */}
                      {result.thumbnail_url ? (
                        <img
                          src={result.thumbnail_url}
                          alt=""
                          className="w-10 h-10 rounded object-cover flex-shrink-0"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded bg-neutral-700 flex-shrink-0" />
                      )}

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{result.name}</div>
                        <div className="text-xs text-neutral-500 truncate">
                          {result.description}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`px-1.5 py-0.5 text-xs rounded ${getProviderColor(result.provider)}`}>
                            {result.provider}
                          </span>
                          {result.subscriber_count && (
                            <span className="text-xs text-neutral-500">
                              {formatSubscribers(result.subscriber_count)} subscribers
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Add Button */}
                      <button
                        onClick={() => addSourceByUrl(result.url)}
                        disabled={addingUrl !== null}
                        className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded transition-colors flex-shrink-0"
                      >
                        {addingUrl === result.url ? 'Adding...' : 'Add'}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Empty state */}
              {!loading && query && results.length === 0 && !error && (
                <div className="text-center py-8 text-neutral-500 text-sm">
                  No results found. Try different keywords.
                </div>
              )}
            </div>
          ) : activeTab === 'discover' ? (
            <div className="space-y-4">
              {/* LLM Status Check */}
              {llmStatus && !llmStatus.backends.ollama.available && !llmStatus.backends.openai.available && !llmStatus.backends.anthropic.available && (
                <div className="text-sm text-yellow-400 bg-yellow-900/20 px-3 py-2 rounded">
                  No LLM backend available. Start Ollama or set OPENAI_API_KEY / ANTHROPIC_API_KEY.
                </div>
              )}

              {/* Mode Toggle */}
              <div className="flex gap-2">
                <button
                  onClick={() => setDiscoverMode('auto')}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    discoverMode === 'auto'
                      ? 'bg-purple-600 text-white'
                      : 'bg-neutral-800 text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  From My Interests
                </button>
                <button
                  onClick={() => setDiscoverMode('prompt')}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    discoverMode === 'prompt'
                      ? 'bg-purple-600 text-white'
                      : 'bg-neutral-800 text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  Custom Search
                </button>
              </div>

              {/* Prompt Input (only for prompt mode) */}
              {discoverMode === 'prompt' && (
                <div>
                  <input
                    type="text"
                    value={discoverPrompt}
                    onChange={(e) => setDiscoverPrompt(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="What are you looking for? (e.g., 'jazz piano tutorials')"
                    className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-purple-500"
                    autoFocus
                  />
                </div>
              )}

              {/* Interest Profile Preview (for auto mode) */}
              {discoverMode === 'auto' && interestProfile && (
                <div className="bg-neutral-800/50 rounded p-3 space-y-2">
                  <div className="text-xs text-neutral-400 font-medium uppercase">Your Interests</div>
                  <div className="flex flex-wrap gap-1.5">
                    {interestProfile.interests.slice(0, 5).map((interest, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded"
                      >
                        {interest.topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="text-sm text-red-400 bg-red-900/20 px-3 py-2 rounded">
                  {error}
                </div>
              )}

              {/* Results */}
              {discoverResults.length > 0 && (
                <div className="space-y-2">
                  {discoverResults.map((result, idx) => (
                    <div
                      key={`${result.url}-${idx}`}
                      className="flex items-start gap-3 p-2 bg-neutral-800/50 rounded hover:bg-neutral-800 transition-colors"
                    >
                      {/* Thumbnail */}
                      {result.thumbnail_url ? (
                        <img
                          src={result.thumbnail_url}
                          alt=""
                          className="w-10 h-10 rounded object-cover flex-shrink-0"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded bg-neutral-700 flex-shrink-0" />
                      )}

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{result.name}</div>
                        <div className="text-xs text-purple-400 mt-0.5">
                          {result.explanation}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`px-1.5 py-0.5 text-xs rounded ${getProviderColor(result.source_type.split('_')[0])}`}>
                            {result.source_type}
                          </span>
                          <span className="text-xs text-neutral-500">
                            {Math.round(result.relevance_score * 100)}% match
                          </span>
                        </div>
                      </div>

                      {/* Add Button */}
                      <button
                        onClick={() => addSourceByUrl(result.url)}
                        disabled={addingUrl !== null}
                        className="px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded transition-colors flex-shrink-0"
                      >
                        {addingUrl === result.url ? 'Adding...' : 'Add'}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Empty state */}
              {!loading && discoverResults.length === 0 && !error && (
                <div className="text-center py-8 text-neutral-500 text-sm">
                  {discoverMode === 'auto'
                    ? "Click 'Discover' to find sources based on your interests."
                    : "Enter what you're looking for and click 'Discover'."}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {/* URL Input */}
              <div>
                <label className="block text-sm text-neutral-400 mb-1">
                  Feed URL
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setPreview(null);
                    setError(null);
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="https://example.com/feed.xml"
                  className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-blue-500"
                  autoFocus={activeTab === 'url'}
                />
              </div>

              {/* Error */}
              {error && (
                <div className="text-sm text-red-400 bg-red-900/20 px-3 py-2 rounded">
                  {error}
                </div>
              )}

              {/* Preview */}
              {preview && (
                <div className="bg-neutral-800/50 rounded p-3 space-y-2">
                  <div className="font-medium">{preview.display_name}</div>
                  <div className="text-sm text-neutral-400">
                    Type: {preview.source_type}
                  </div>
                  {preview.description && (
                    <div className="text-sm text-neutral-500 line-clamp-2">
                      {preview.description}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-neutral-800 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            Cancel
          </button>
          {activeTab === 'search' ? (
            <button
              onClick={handleSearch}
              disabled={loading || !query.trim()}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          ) : activeTab === 'discover' ? (
            <button
              onClick={handleDiscover}
              disabled={loading || (discoverMode === 'prompt' && !discoverPrompt.trim())}
              className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Discovering...' : 'Discover'}
            </button>
          ) : preview ? (
            <button
              onClick={handleAddUrl}
              disabled={loading || addingUrl !== null}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded transition-colors"
            >
              {addingUrl ? 'Adding...' : 'Add Source'}
            </button>
          ) : (
            <button
              onClick={handlePreview}
              disabled={loading || !url.trim()}
              className="px-4 py-2 text-sm bg-neutral-700 hover:bg-neutral-600 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Loading...' : 'Preview'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
