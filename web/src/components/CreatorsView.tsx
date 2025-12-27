import { useEffect, useState } from 'react';
import { getCreators } from '../api/client';
import type { Creator } from '../api/types';

interface Props {
  onClose: () => void;
  onSelectCreator?: (creator: Creator) => void;
}

export function CreatorsView({ onClose, onSelectCreator }: Props) {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<'name' | 'items' | 'score'>('items');
  const [sortAsc, setSortAsc] = useState(false);

  const loadCreators = async () => {
    try {
      const data = await getCreators(500);
      setCreators(data);
    } catch (err) {
      console.error('Failed to load creators:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCreators();
  }, []);

  const sortedCreators = [...creators].sort((a, b) => {
    let cmp = 0;
    switch (sortBy) {
      case 'name':
        cmp = a.name.localeCompare(b.name);
        break;
      case 'items':
        cmp = (a.item_count ?? 0) - (b.item_count ?? 0);
        break;
      case 'score':
        cmp = (a.avg_score ?? 0) - (b.avg_score ?? 0);
        break;
    }
    return sortAsc ? cmp : -cmp;
  });

  const handleSort = (field: 'name' | 'items' | 'score') => {
    if (sortBy === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortBy(field);
      setSortAsc(field === 'name');
    }
  };

  const formatScore = (score: number | null) => {
    if (score === null) return '-';
    return score.toFixed(1);
  };

  const getCreatorTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      individual: 'Individual',
      company: 'Company',
      group: 'Group',
      ai_agent: 'AI Agent',
      unknown: 'Unknown',
    };
    return labels[type] || type;
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-neutral-900 rounded-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-4 py-3 border-b border-neutral-800 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium">Creators</h2>
            <p className="text-xs text-neutral-500">{creators.length} creators</p>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-white transition-colors"
          >
            Close
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center text-neutral-500 py-8">Loading...</div>
          ) : creators.length === 0 ? (
            <div className="text-center text-neutral-500 py-8">No creators found.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-700 text-left text-neutral-400">
                  <th className="pb-2 pr-4">
                    <button
                      onClick={() => handleSort('name')}
                      className="hover:text-white"
                    >
                      Creator {sortBy === 'name' ? (sortAsc ? '↑' : '↓') : ''}
                    </button>
                  </th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4 text-right">
                    <button
                      onClick={() => handleSort('items')}
                      className="hover:text-white"
                    >
                      Items {sortBy === 'items' ? (sortAsc ? '↑' : '↓') : ''}
                    </button>
                  </th>
                  <th className="pb-2 pr-4 text-right">
                    <button
                      onClick={() => handleSort('score')}
                      className="hover:text-white"
                    >
                      Avg Score {sortBy === 'score' ? (sortAsc ? '↑' : '↓') : ''}
                    </button>
                  </th>
                  <th className="pb-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedCreators.map((creator) => (
                  <tr
                    key={creator.id}
                    className="border-b border-neutral-800 hover:bg-neutral-800/50"
                  >
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-3">
                        {creator.avatar_url ? (
                          <img
                            src={creator.avatar_url}
                            alt={creator.name}
                            className="w-8 h-8 rounded-full"
                          />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-neutral-700 flex items-center justify-center text-xs">
                            {creator.name.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-medium">{creator.name}</div>
                          {creator.url && (
                            <a
                              href={creator.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-400 hover:underline"
                            >
                              website
                            </a>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-neutral-400">
                      {getCreatorTypeLabel(creator.creator_type)}
                    </td>
                    <td className="py-3 pr-4 text-right">
                      {creator.item_count}
                    </td>
                    <td className="py-3 pr-4 text-right">
                      <span
                        className={
                          creator.avg_score !== null
                            ? creator.avg_score >= 3.5
                              ? 'text-green-400'
                              : creator.avg_score >= 2.5
                              ? 'text-yellow-400'
                              : 'text-neutral-400'
                            : 'text-neutral-500'
                        }
                      >
                        {formatScore(creator.avg_score)}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {onSelectCreator && (
                          <button
                            onClick={() => onSelectCreator(creator)}
                            className="px-2 py-1 text-xs bg-neutral-700 hover:bg-neutral-600 rounded"
                          >
                            View Items
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
