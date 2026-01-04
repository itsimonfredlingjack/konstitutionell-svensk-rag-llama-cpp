import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';
import type { SearchResult, SearchFilters, SearchResponse } from '../types';
import { API_BASE } from '../types';
import SearchInput from '../components/search/SearchInput';
import FilterPanel from '../components/search/FilterPanel';
import ResultsList from '../components/search/ResultsList';

interface PaginationInfo {
  currentPage: number;
  totalPages: number;
  pageSize: number;
  totalResults: number;
}

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<SearchFilters>({});
  const [queryTimeMs, setQueryTimeMs] = useState(0);
  const [pagination, setPagination] = useState<PaginationInfo>({
    currentPage: 1,
    totalPages: 1,
    pageSize: 10,
    totalResults: 0,
  });
  const [sortBy, setSortBy] = useState<'relevance' | 'date_desc' | 'date_asc'>('relevance');

  const currentQuery = searchParams.get('q') || '';

  // Fetch search results
  const performSearch = async (query: string, page: number = 1) => {
    if (!query.trim()) {
      setResults([]);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const startTime = performance.now();

      const requestBody = {
        query: query.trim(),
        filters: filters,
        page: page,
        sort: sortBy,
        page_size: pagination.pageSize,
      };

      const response = await fetch(`${API_BASE}/api/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      const endTime = performance.now();
      const elapsed = Math.round(endTime - startTime);
      setQueryTimeMs(elapsed);

      if (!response.ok) {
        throw new Error(`Search failed with status ${response.status}`);
      }

      const data: SearchResponse = await response.json();

      setResults(data.results || []);
      setPagination(prev => ({
        ...prev,
        currentPage: page,
        totalResults: data.total || 0,
        totalPages: Math.ceil((data.total || 0) / prev.pageSize),
      }));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred during search';
      setError(errorMessage);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // Handle search input
  const handleSearch = (query: string) => {
    setSearchParams(query ? { q: query } : {});
    setPagination(prev => ({ ...prev, currentPage: 1 }));
    performSearch(query, 1);
  };

  // Handle filter changes
  const handleFiltersChange = (newFilters: SearchFilters) => {
    setFilters(newFilters);
    setPagination(prev => ({ ...prev, currentPage: 1 }));
    performSearch(currentQuery, 1);
  };

  // Handle pagination
  const handlePageChange = (page: number) => {
    performSearch(currentQuery, page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Handle sort change
  const handleSortChange = (newSort: 'relevance' | 'date_desc' | 'date_asc') => {
    setSortBy(newSort);
    setPagination(prev => ({ ...prev, currentPage: 1 }));
    performSearch(currentQuery, 1);
  };

  // Load initial search on mount if query present in URL
  useEffect(() => {
    if (currentQuery) {
      performSearch(currentQuery, 1);
    }
  }, []);

  return (
    <div className="space-y-6">
      {/* Search Header */}
      <div className="bg-gradient-to-r from-gray-800 to-gray-900 border border-gray-700 rounded-lg p-6 sm:p-8">
        <h1 className="text-3xl font-bold text-white mb-2">
          Sök myndighetsdokument
        </h1>
        <p className="text-gray-400 mb-6">
          Genomsök över 230 000 dokument från riksdagen, kommuner och myndigheter
        </p>

        {/* Search Input */}
        <SearchInput onSearch={handleSearch} loading={loading} />
      </div>

      {/* Error Alert */}
      {error && (
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-400">Sökfel</h3>
            <p className="text-sm text-red-300">{error}</p>
          </div>
        </div>
      )}

      {/* Main Content Grid */}
      {currentQuery && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar - Filters */}
          <aside className="lg:col-span-1">
            <FilterPanel
              filters={filters}
              onFiltersChange={handleFiltersChange}
            />
          </aside>

          {/* Main Content - Results */}
          <main className="lg:col-span-3 space-y-6">
            {/* Results Header with Sort */}
            {results.length > 0 && (
              <div className="flex items-center justify-between flex-wrap gap-4 bg-gray-800 border border-gray-700 rounded-lg p-4">
                <div className="text-sm text-gray-400">
                  Visar <span className="font-medium text-white">{results.length}</span> av{' '}
                  <span className="font-medium text-white">{pagination.totalResults.toLocaleString('sv-SE')}</span> resultat
                </div>

                <div className="flex items-center gap-3">
                  <label className="text-sm text-gray-400">Sortera:</label>
                  <select
                    value={sortBy}
                    onChange={(e) => handleSortChange(e.target.value as any)}
                    className="px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  >
                    <option value="relevance">Relevans</option>
                    <option value="date_desc">Nyast först</option>
                    <option value="date_asc">Äldst först</option>
                  </select>
                </div>

                {queryTimeMs > 0 && (
                  <div className="text-xs text-gray-500">
                    Svarstid: <span className="font-medium text-gray-400">{queryTimeMs}ms</span>
                  </div>
                )}
              </div>
            )}

            {/* Results List */}
            <ResultsList
              results={results}
              total={pagination.totalResults}
              queryTimeMs={queryTimeMs}
              query={currentQuery}
              loading={loading}
            />

            {/* Pagination */}
            {pagination.totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 pt-6">
                <button
                  onClick={() => handlePageChange(pagination.currentPage - 1)}
                  disabled={pagination.currentPage === 1 || loading}
                  className="p-2 rounded-md border border-gray-700 bg-gray-800 text-white hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>

                <div className="flex items-center gap-2">
                  {/* Page number inputs */}
                  {Array.from({ length: Math.min(5, pagination.totalPages) }).map((_, i) => {
                    let pageNum: number;

                    if (pagination.totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (pagination.currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (pagination.currentPage >= pagination.totalPages - 2) {
                      pageNum = pagination.totalPages - 4 + i;
                    } else {
                      pageNum = pagination.currentPage - 2 + i;
                    }

                    if (pageNum > 0 && pageNum <= pagination.totalPages) {
                      return (
                        <button
                          key={pageNum}
                          onClick={() => handlePageChange(pageNum)}
                          disabled={loading}
                          className={`px-3 py-2 rounded-md transition-colors ${
                            pagination.currentPage === pageNum
                              ? 'bg-blue-600 text-white'
                              : 'border border-gray-700 bg-gray-800 text-gray-300 hover:bg-gray-700'
                          } disabled:cursor-not-allowed`}
                        >
                          {pageNum}
                        </button>
                      );
                    }
                    return null;
                  })}
                </div>

                <button
                  onClick={() => handlePageChange(pagination.currentPage + 1)}
                  disabled={pagination.currentPage === pagination.totalPages || loading}
                  className="p-2 rounded-md border border-gray-700 bg-gray-800 text-white hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            )}

            {/* Results summary */}
            {results.length > 0 && (
              <div className="text-xs text-gray-500 text-center pt-4">
                Sida {pagination.currentPage} av {pagination.totalPages}
              </div>
            )}
          </main>
        </div>
      )}

      {/* Empty State - No Query */}
      {!currentQuery && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-12 text-center">
          <div className="max-w-md mx-auto">
            <h2 className="text-2xl font-semibold text-white mb-3">
              Börja din sökning
            </h2>
            <p className="text-gray-400 mb-4">
              Använd sökfältet ovan för att söka bland myndighetsdokument.
            </p>
            <div className="space-y-3 text-left">
              <div className="bg-gray-700/50 rounded-lg p-3">
                <p className="text-sm font-medium text-gray-300 mb-1">Exempelsökningar:</p>
                <ul className="text-sm text-gray-400 space-y-1">
                  <li>• Skattesystemet 2024</li>
                  <li>• Klimatpolitik propositioner</li>
                  <li>• Arbetsrätt lagändringar</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
