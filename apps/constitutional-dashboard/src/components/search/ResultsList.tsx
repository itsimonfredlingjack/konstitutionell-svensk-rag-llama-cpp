import type { SearchResult } from '../../types';
import ResultCard from './ResultCard';
import { FileSearch } from 'lucide-react';

interface ResultsListProps {
  results: SearchResult[];
  total: number;
  queryTimeMs: number;
  query: string;
  loading: boolean;
}

export default function ResultsList({ results, total, queryTimeMs, query, loading }: ResultsListProps) {
  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="bg-gray-800 border border-gray-700 rounded-lg p-5 animate-pulse">
            <div className="h-6 bg-gray-700 rounded w-3/4 mb-3" />
            <div className="h-4 bg-gray-700 rounded w-1/4 mb-4" />
            <div className="space-y-2">
              <div className="h-3 bg-gray-700 rounded w-full" />
              <div className="h-3 bg-gray-700 rounded w-5/6" />
              <div className="h-3 bg-gray-700 rounded w-4/6" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (results.length === 0 && query) {
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-12 text-center">
        <FileSearch className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <h3 className="text-xl font-semibold text-white mb-2">Inga resultat</h3>
        <p className="text-gray-400">
          Din sökning efter <span className="text-blue-400 font-medium">"{query}"</span> gav inga resultat.
        </p>
        <p className="text-sm text-gray-500 mt-2">
          Försök med andra sökord eller justera filtren.
        </p>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-12 text-center">
        <FileSearch className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <h3 className="text-xl font-semibold text-white mb-2">Sök i myndighetsdokument</h3>
        <p className="text-gray-400">
          Sök bland över 230 000 dokument från riksdagen, kommuner och myndigheter.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Results header */}
      <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm text-gray-400">
            Visar <span className="font-medium text-white">{results.length}</span> av{' '}
            <span className="font-medium text-white">{total.toLocaleString('sv-SE')}</span> resultat
          </p>
          {query && (
            <p className="text-xs text-gray-500 mt-1">
              Sökning: <span className="text-blue-400">"{query}"</span>
            </p>
          )}
        </div>

        <div className="text-xs text-gray-500">
          Svarstid: <span className="font-medium text-gray-400">{queryTimeMs}ms</span>
        </div>
      </div>

      {/* Results grid */}
      <div className="space-y-4">
        {results.map(result => (
          <ResultCard key={result.id} result={result} queryTerms={query} />
        ))}
      </div>

      {/* Load more placeholder */}
      {results.length < total && (
        <div className="mt-6 text-center">
          <button className="px-6 py-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white rounded-lg transition-colors">
            Ladda fler resultat ({total - results.length} kvar)
          </button>
        </div>
      )}
    </div>
  );
}
