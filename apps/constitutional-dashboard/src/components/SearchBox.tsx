import { useState } from 'react';
import { Search, Loader2, ExternalLink } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import type { SearchResult } from '../types';
import { API_BASE } from '../types';

export function SearchBox() {
  const [query, setQuery] = useState('');
  const { data, loading, fetch } = useApi<{ results: SearchResult[] }>();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    try {
      await fetch(`${API_BASE}/api/constitutional/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 5 }),
      });
    } catch (err) {
      console.error('Search failed:', err);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
        <Search className="w-6 h-6" />
        Snabbsök
      </h2>

      <form onSubmit={handleSubmit} className="mb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Sök i dokumentdatabas..."
            className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Söker...
              </>
            ) : (
              'Sök'
            )}
          </button>
        </div>
      </form>

      {data && data.results.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm text-gray-400 mb-3">
            Visar de 3 bästa träffarna av {data.results.length}:
          </p>
          {data.results.slice(0, 3).map((result) => (
            <div
              key={result.id}
              className="p-4 bg-gray-700/50 rounded-lg border border-gray-600 hover:border-gray-500 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-white">{result.title}</h3>
                <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-1 rounded">
                  {((result.score ?? 0) * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-gray-300 mb-2 line-clamp-2">{result.excerpt}</p>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Källa: {result.source}</span>
                {result.url && (
                  <a
                    href={result.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-blue-400 hover:text-blue-300"
                  >
                    Öppna
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {data && data.results.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          Inga resultat hittades för "{query}"
        </div>
      )}
    </div>
  );
}
