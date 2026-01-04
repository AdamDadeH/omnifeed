import { useState, useEffect, useCallback } from 'react';
import {
  getRetrieverHierarchy,
  getExplorationConfig,
  updateExplorationConfig,
  getExplorationStats,
  updateRetriever,
  getStrategies,
  enableStrategy,
  disableStrategy,
} from '../api/client';
import type {
  RetrieverHierarchyNode,
  ExplorationConfig,
  ExplorationStats,
  Strategy,
} from '../api/types';

interface Props {
  onClose: () => void;
  isFullPage?: boolean;
}

export function StrategiesView({ onClose, isFullPage }: Props) {
  const [hierarchy, setHierarchy] = useState<RetrieverHierarchyNode[]>([]);
  const [config, setConfig] = useState<ExplorationConfig | null>(null);
  const [stats, setStats] = useState<ExplorationStats | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [editingConfig, setEditingConfig] = useState(false);
  const [pendingConfig, setPendingConfig] = useState<ExplorationConfig | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [h, c, s, strats] = await Promise.all([
        getRetrieverHierarchy(),
        getExplorationConfig(),
        getExplorationStats(),
        getStrategies(),
      ]);
      setHierarchy(h);
      setConfig(c);
      setStats(s);
      setStrategies(strats);
    } catch (err) {
      console.error('Failed to load strategies data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleNode = (id: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleToggleEnabled = async (id: string, currentEnabled: boolean) => {
    try {
      await updateRetriever(id, { is_enabled: !currentEnabled });
      loadData();
    } catch (err) {
      console.error('Failed to toggle retriever:', err);
    }
  };

  const handleToggleStrategy = async (strategyId: string, currentEnabled: boolean) => {
    try {
      if (currentEnabled) {
        await disableStrategy(strategyId);
      } else {
        await enableStrategy(strategyId);
      }
      loadData();
    } catch (err) {
      console.error('Failed to toggle strategy:', err);
    }
  };

  const handleSaveConfig = async () => {
    if (!pendingConfig) return;
    try {
      const updated = await updateExplorationConfig(pendingConfig);
      setConfig(updated);
      setEditingConfig(false);
      setPendingConfig(null);
    } catch (err) {
      console.error('Failed to update config:', err);
    }
  };

  const startEditingConfig = () => {
    setPendingConfig(config);
    setEditingConfig(true);
  };

  const formatScore = (score: number | null, confidence: number | null) => {
    if (score === null) return <span className="text-neutral-600">--</span>;
    const confLabel = confidence !== null ? ` (${(confidence * 100).toFixed(0)}%)` : '';
    const color =
      score >= 0.7 ? 'text-green-400' : score >= 0.4 ? 'text-yellow-400' : 'text-red-400';
    return <span className={color}>{score.toFixed(2)}{confLabel}</span>;
  };

  const renderNode = (node: RetrieverHierarchyNode, depth: number = 0) => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedNodes.has(node.id);

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-2 py-1.5 px-2 hover:bg-neutral-800/50 rounded ${
            depth > 0 ? 'ml-4' : ''
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {hasChildren ? (
            <button
              onClick={() => toggleNode(node.id)}
              className="w-5 h-5 flex items-center justify-center text-neutral-500 hover:text-neutral-300"
            >
              <svg
                className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5l7 7-7 7"
                />
              </svg>
            </button>
          ) : (
            <span className="w-5" />
          )}

          <button
            onClick={() => handleToggleEnabled(node.id, node.is_enabled)}
            className={`w-4 h-4 rounded border ${
              node.is_enabled
                ? 'bg-blue-600 border-blue-600'
                : 'border-neutral-600 hover:border-neutral-500'
            }`}
          >
            {node.is_enabled && (
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            )}
          </button>

          <span className={`flex-1 text-sm ${node.is_enabled ? 'text-neutral-200' : 'text-neutral-500'}`}>
            {node.display_name}
          </span>

          <span className="text-xs text-neutral-500 px-1.5 py-0.5 bg-neutral-800 rounded">
            {node.kind}
          </span>

          <span className="text-xs text-neutral-600 px-1.5 py-0.5">
            {node.handler_type}
          </span>

          <span className="w-20 text-right text-xs">
            {formatScore(node.score, node.confidence)}
          </span>

          {node.sample_size !== null && node.sample_size > 0 && (
            <span className="text-xs text-neutral-600 w-12 text-right">
              n={node.sample_size}
            </span>
          )}
        </div>

        {hasChildren && isExpanded && (
          <div className="border-l border-neutral-800 ml-4">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  const content = (
    <div className="space-y-6 p-4">
      {loading ? (
        <div className="text-neutral-500">Loading...</div>
      ) : (
        <>
          {/* Stats Overview */}
          <section>
            <h3 className="text-sm font-medium text-neutral-300 mb-3">Overview</h3>
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-neutral-800/50 rounded-lg p-3">
                <div className="text-2xl font-bold">{strategies.length}</div>
                <div className="text-xs text-neutral-500">Strategies</div>
              </div>
              <div className="bg-neutral-800/50 rounded-lg p-3">
                <div className="text-2xl font-bold text-green-400">
                  {strategies.filter(s => s.is_enabled).length}
                </div>
                <div className="text-xs text-neutral-500">Enabled</div>
              </div>
              <div className="bg-neutral-800/50 rounded-lg p-3">
                <div className="text-2xl font-bold text-blue-400">
                  {strategies.filter(s => s.score !== null).length}
                </div>
                <div className="text-xs text-neutral-500">With Scores</div>
              </div>
              <div className="bg-neutral-800/50 rounded-lg p-3">
                <div className="text-2xl font-bold text-yellow-400">
                  {strategies.filter(s => s.retriever_id !== null).length}
                </div>
                <div className="text-xs text-neutral-500">Used</div>
              </div>
            </div>

            {/* Provider breakdown */}
            <div className="flex gap-6 mt-3 text-sm">
              <div>
                <span className="text-neutral-500">By Provider:</span>{' '}
                {Object.entries(
                  strategies.reduce((acc, s) => {
                    acc[s.provider] = (acc[s.provider] || 0) + 1;
                    return acc;
                  }, {} as Record<string, number>)
                ).map(([k, v]) => (
                  <span key={k} className="ml-2 text-neutral-400">
                    {k}: <span className="text-neutral-200">{v}</span>
                  </span>
                ))}
              </div>
            </div>
          </section>

          {/* Exploration Strategies */}
          <section>
            <h3 className="text-sm font-medium text-neutral-300 mb-3">Exploration Strategies</h3>
            <div className="bg-neutral-800/30 rounded-lg divide-y divide-neutral-800">
              {strategies.length === 0 ? (
                <div className="p-3 text-sm text-neutral-500">No strategies available</div>
              ) : (
                strategies.map((s) => (
                  <div key={s.strategy_id} className="p-3 flex items-center gap-3">
                    <button
                      onClick={() => handleToggleStrategy(s.strategy_id, s.is_enabled)}
                      className={`w-4 h-4 rounded border flex-shrink-0 ${
                        s.is_enabled
                          ? 'bg-blue-600 border-blue-600'
                          : 'border-neutral-600 hover:border-neutral-500'
                      }`}
                    >
                      {s.is_enabled && (
                        <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm ${s.is_enabled ? 'text-neutral-200' : 'text-neutral-500'}`}>
                          {s.display_name}
                        </span>
                        <span className="text-xs text-neutral-600 px-1.5 py-0.5 bg-neutral-800 rounded">
                          {s.provider}
                        </span>
                      </div>
                      <div className="text-xs text-neutral-500 mt-0.5 truncate">
                        {s.description}
                      </div>
                    </div>

                    <div className="text-right flex-shrink-0">
                      {s.retriever_id ? (
                        <div className="text-xs">
                          {formatScore(s.score, s.confidence)}
                          {s.sample_size !== null && s.sample_size > 0 && (
                            <span className="text-neutral-600 ml-1">n={s.sample_size}</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-neutral-600">not used yet</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          {/* Exploration Config */}
          {config && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-neutral-300">Explore / Exploit Balance</h3>
                {!editingConfig ? (
                  <button
                    onClick={startEditingConfig}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    Edit
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditingConfig(false);
                        setPendingConfig(null);
                      }}
                      className="text-xs text-neutral-400 hover:text-neutral-300"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSaveConfig}
                      className="text-xs text-green-400 hover:text-green-300"
                    >
                      Save
                    </button>
                  </div>
                )}
              </div>

              {!editingConfig ? (
                <div className="bg-neutral-800/50 rounded-lg p-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Explore Ratio</div>
                      <div className="text-neutral-200">{(config.explore_ratio * 100).toFixed(0)}%</div>
                      <div className="text-xs text-neutral-600 mt-1">
                        Reserved for discovering new sources
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Min Exploit Confidence</div>
                      <div className="text-neutral-200">{(config.min_exploit_confidence * 100).toFixed(0)}%</div>
                      <div className="text-xs text-neutral-600 mt-1">
                        Required confidence to prioritize a source
                      </div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Max Depth</div>
                      <div className="text-neutral-200">{config.max_depth}</div>
                    </div>
                    <div>
                      <div className="text-neutral-500 text-xs mb-1">Default Limit</div>
                      <div className="text-neutral-200">{config.default_limit}</div>
                    </div>
                  </div>

                  {/* Visual representation of explore/exploit split */}
                  <div className="mt-4">
                    <div className="text-xs text-neutral-500 mb-1">Selection Strategy</div>
                    <div className="flex h-4 rounded overflow-hidden">
                      <div
                        className="bg-blue-600 flex items-center justify-center text-xs text-white"
                        style={{ width: `${(1 - config.explore_ratio) * 100}%` }}
                      >
                        Exploit
                      </div>
                      <div
                        className="bg-yellow-600 flex items-center justify-center text-xs text-white"
                        style={{ width: `${config.explore_ratio * 100}%` }}
                      >
                        Explore
                      </div>
                    </div>
                  </div>
                </div>
              ) : pendingConfig && (
                <div className="bg-neutral-800/50 rounded-lg p-4 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-neutral-500 text-xs mb-1 block">
                        Explore Ratio ({(pendingConfig.explore_ratio * 100).toFixed(0)}%)
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={pendingConfig.explore_ratio * 100}
                        onChange={(e) =>
                          setPendingConfig({
                            ...pendingConfig,
                            explore_ratio: parseInt(e.target.value) / 100,
                          })
                        }
                        className="w-full"
                      />
                    </div>
                    <div>
                      <label className="text-neutral-500 text-xs mb-1 block">
                        Min Exploit Confidence ({(pendingConfig.min_exploit_confidence * 100).toFixed(0)}%)
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={pendingConfig.min_exploit_confidence * 100}
                        onChange={(e) =>
                          setPendingConfig({
                            ...pendingConfig,
                            min_exploit_confidence: parseInt(e.target.value) / 100,
                          })
                        }
                        className="w-full"
                      />
                    </div>
                    <div>
                      <label className="text-neutral-500 text-xs mb-1 block">Max Depth</label>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={pendingConfig.max_depth}
                        onChange={(e) =>
                          setPendingConfig({
                            ...pendingConfig,
                            max_depth: parseInt(e.target.value) || 1,
                          })
                        }
                        className="w-full bg-neutral-700 border border-neutral-600 rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-neutral-500 text-xs mb-1 block">Default Limit</label>
                      <input
                        type="number"
                        min="1"
                        max="100"
                        value={pendingConfig.default_limit}
                        onChange={(e) =>
                          setPendingConfig({
                            ...pendingConfig,
                            default_limit: parseInt(e.target.value) || 20,
                          })
                        }
                        className="w-full bg-neutral-700 border border-neutral-600 rounded px-2 py-1 text-sm"
                      />
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}

          {/* Top Performers & Needs Exploration */}
          {stats && (
            <section className="grid grid-cols-2 gap-4">
              <div>
                <h3 className="text-sm font-medium text-neutral-300 mb-3">Top Performers</h3>
                <div className="bg-neutral-800/30 rounded-lg divide-y divide-neutral-800">
                  {stats.top_performers.length === 0 ? (
                    <div className="p-3 text-sm text-neutral-500">No scored retrievers yet</div>
                  ) : (
                    stats.top_performers.map((r) => (
                      <div key={r.id} className="p-2 flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-neutral-200 truncate">{r.display_name}</div>
                          <div className="text-xs text-neutral-500">{r.kind} / {r.handler_type}</div>
                        </div>
                        <div className="text-sm ml-2">
                          {formatScore(r.score, r.confidence)}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-medium text-neutral-300 mb-3">Needs Exploration</h3>
                <div className="bg-neutral-800/30 rounded-lg divide-y divide-neutral-800">
                  {stats.needs_exploration.length === 0 ? (
                    <div className="p-3 text-sm text-neutral-500">All retrievers have high confidence</div>
                  ) : (
                    stats.needs_exploration.map((r) => (
                      <div key={r.id} className="p-2 flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-neutral-200 truncate">{r.display_name}</div>
                          <div className="text-xs text-neutral-500">{r.kind} / {r.handler_type}</div>
                        </div>
                        <div className="text-sm ml-2">
                          {formatScore(r.score, r.confidence)}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </section>
          )}

          {/* Retriever Hierarchy */}
          <section>
            <h3 className="text-sm font-medium text-neutral-300 mb-3">Retriever Hierarchy</h3>
            <div className="bg-neutral-800/30 rounded-lg py-2">
              {hierarchy.length === 0 ? (
                <div className="p-3 text-sm text-neutral-500">No retrievers configured</div>
              ) : (
                hierarchy.map((node) => renderNode(node))
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );

  if (isFullPage) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-medium">Exploration Strategies</h2>
              <p className="text-sm text-neutral-500 mt-1">
                Configure explore/exploit balance and view retriever performance
              </p>
            </div>
            <button
              onClick={loadData}
              className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
            >
              Refresh
            </button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto">{content}</div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-neutral-900 rounded-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
        <header className="px-4 py-3 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="text-lg font-medium">Exploration Strategies</h2>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-200">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>
        <div className="flex-1 overflow-y-auto">{content}</div>
      </div>
    </div>
  );
}
