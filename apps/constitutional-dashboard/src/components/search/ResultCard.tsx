import { ExternalLink } from 'lucide-react';
import type { SearchResult } from '../../types';

interface ResultCardProps {
  result: SearchResult;
  queryTerms?: string;
}

export default function ResultCard({ result, queryTerms }: ResultCardProps) {
  // Determine relevance color
  const getRelevanceColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-500';
    if (score >= 0.5) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  // Get source badge color
  const getSourceBadgeColor = (source: string) => {
    const colors: Record<string, string> = {
      riksdagen: 'bg-blue-600',
      kommun: 'bg-purple-600',
      myndighet: 'bg-green-600',
      sou: 'bg-orange-600',
      prop: 'bg-pink-600',
    };
    return colors[source] || 'bg-gray-600';
  };

  // Highlight query terms in snippet
  const highlightSnippet = (text: string) => {
    if (!queryTerms) return text;

    const terms = queryTerms.toLowerCase().split(' ').filter(t => t.length > 2);
    let highlighted = text;

    terms.forEach(term => {
      const regex = new RegExp(`(${term})`, 'gi');
      highlighted = highlighted.replace(regex, '<mark class="bg-yellow-400 text-gray-900 px-1 rounded">$1</mark>');
    });

    return highlighted;
  };

  const snippet = result.snippet || result.excerpt || '';
  const relevanceScore = result.relevance_score ?? result.score ?? 0;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-5 hover:border-blue-500 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-white mb-2 line-clamp-2">
            {result.title}
          </h3>

          <div className="flex flex-wrap items-center gap-2">
            {/* Source badge */}
            <span className={`px-2 py-1 text-xs font-medium text-white rounded ${getSourceBadgeColor(result.source)}`}>
              {result.source.toUpperCase()}
            </span>

            {/* Date */}
            {result.date && (
              <span className="text-xs text-gray-400">
                {new Date(result.date).toLocaleDateString('sv-SE')}
              </span>
            )}
          </div>
        </div>

        {/* Relevance score */}
        <div className="flex flex-col items-end gap-1 min-w-[80px]">
          <span className="text-xs text-gray-400">Relevans</span>
          <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full ${getRelevanceColor(relevanceScore)} transition-all`}
              style={{ width: `${relevanceScore * 100}%` }}
            />
          </div>
          <span className="text-xs font-medium text-white">
            {Math.round(relevanceScore * 100)}%
          </span>
        </div>
      </div>

      {/* Snippet */}
      <p
        className="text-sm text-gray-300 mb-4 line-clamp-3"
        dangerouslySetInnerHTML={{ __html: highlightSnippet(snippet) }}
      />

      {/* Footer */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">ID: {result.id}</span>

        {result.url && (
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm text-blue-400 hover:text-blue-300 hover:bg-blue-900/20 rounded-md transition-colors"
          >
            Läs mer
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}
