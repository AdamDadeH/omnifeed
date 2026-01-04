import { useEffect, useState } from 'react';
import { getSources } from '../api/client';
import type { Source } from '../api/types';

export type ViewType = 'explore' | 'subscribed' | 'queue' | 'rated' | 'sources' | 'creators' | 'models' | 'strategies';

interface NavItem {
  id: ViewType;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

interface Props {
  currentView: ViewType;
  onViewChange: (view: ViewType) => void;
  /** For subscribed view - filter by source */
  selectedSource: string | undefined;
  onSelectSource: (id: string | undefined) => void;
}

// Simple icon components
const ExploreIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

const SubscribedIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
  </svg>
);

const QueueIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
  </svg>
);

const RatedIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
  </svg>
);

const SourcesIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
  </svg>
);

const CreatorsIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
  </svg>
);

const ModelsIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
  </svg>
);

const StrategiesIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
  </svg>
);

const navItems: NavItem[] = [
  { id: 'explore', label: 'Explore', icon: <ExploreIcon /> },
  { id: 'subscribed', label: 'Subscribed', icon: <SubscribedIcon /> },
  { id: 'queue', label: 'Queue', icon: <QueueIcon /> },
  { id: 'rated', label: 'Rated', icon: <RatedIcon /> },
  { id: 'sources', label: 'Sources', icon: <SourcesIcon /> },
  { id: 'creators', label: 'Creators', icon: <CreatorsIcon /> },
  { id: 'models', label: 'Models', icon: <ModelsIcon /> },
  { id: 'strategies', label: 'Strategies', icon: <StrategiesIcon /> },
];

export function Sidebar({ currentView, onViewChange, selectedSource, onSelectSource }: Props) {
  const [sources, setSources] = useState<Source[]>([]);
  const [showSourceList, setShowSourceList] = useState(false);

  useEffect(() => {
    getSources().then(setSources).catch(console.error);
  }, []);

  return (
    <aside className="w-56 h-screen bg-neutral-900 border-r border-neutral-800 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-neutral-800">
        <h1 className="text-lg font-semibold text-neutral-100">OmniFeed</h1>
      </div>

      {/* Main navigation */}
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
              currentView === item.id
                ? 'bg-neutral-800 text-neutral-100'
                : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
            }`}
          >
            {item.icon}
            <span>{item.label}</span>
            {item.badge !== undefined && item.badge > 0 && (
              <span className="ml-auto text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded-full">
                {item.badge}
              </span>
            )}
          </button>
        ))}

        {/* Source filter - only show when in subscribed view */}
        {currentView === 'subscribed' && (
          <div className="pt-4 mt-4 border-t border-neutral-800">
            <button
              onClick={() => setShowSourceList(!showSourceList)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs text-neutral-500 hover:text-neutral-400"
            >
              <span>Filter by source</span>
              <svg
                className={`w-4 h-4 transition-transform ${showSourceList ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {showSourceList && (
              <div className="mt-1 space-y-0.5 max-h-48 overflow-y-auto">
                <button
                  onClick={() => onSelectSource(undefined)}
                  className={`w-full text-left px-3 py-1.5 rounded text-xs transition-colors ${
                    !selectedSource
                      ? 'bg-neutral-800 text-neutral-200'
                      : 'text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50'
                  }`}
                >
                  All sources
                </button>
                {sources.map((source) => (
                  <button
                    key={source.id}
                    onClick={() => onSelectSource(source.id)}
                    className={`w-full text-left px-3 py-1.5 rounded text-xs transition-colors truncate ${
                      selectedSource === source.id
                        ? 'bg-neutral-800 text-neutral-200'
                        : 'text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50'
                    }`}
                  >
                    {source.display_name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </nav>
    </aside>
  );
}
