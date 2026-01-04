import { useState, useEffect, useRef } from 'react';
import { Search, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

interface SearchInputProps {
  onSearch: (query: string) => void;
  loading?: boolean;
}

export default function SearchInput({ onSearch, loading }: SearchInputProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get('q') || '');
  const debounceTimer = useRef<NodeJS.Timeout>();

  // Read initial query from URL
  useEffect(() => {
    const urlQuery = searchParams.get('q');
    if (urlQuery) {
      setQuery(urlQuery);
      onSearch(urlQuery);
    }
  }, []);

  // Debounced search (300ms)
  useEffect(() => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }

    debounceTimer.current = setTimeout(() => {
      if (query.trim()) {
        onSearch(query.trim());
        // Update URL params
        setSearchParams(prev => {
          const newParams = new URLSearchParams(prev);
          newParams.set('q', query.trim());
          return newParams;
        });
      } else if (!query.trim() && searchParams.has('q')) {
        // Clear URL param if query is empty
        setSearchParams(prev => {
          const newParams = new URLSearchParams(prev);
          newParams.delete('q');
          return newParams;
        });
      }
    }, 300);

    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, [query]);

  // Ctrl+K to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('search-input')?.focus();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleClear = () => {
    setQuery('');
    setSearchParams(prev => {
      const newParams = new URLSearchParams(prev);
      newParams.delete('q');
      return newParams;
    });
  };

  return (
    <div className="w-full">
      <div className="relative">
        <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-6 h-6 text-gray-400" />

        <input
          id="search-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Sök i myndighetsdokument..."
          className="w-full px-6 py-4 pl-16 pr-12 text-lg bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white placeholder-gray-400 transition-all"
          disabled={loading}
        />

        {query && (
          <button
            onClick={handleClear}
            className="absolute right-4 top-1/2 -translate-y-1/2 p-1.5 hover:bg-gray-700 rounded-full transition-colors"
            aria-label="Clear search"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        )}
      </div>

      <div className="mt-2 text-sm text-gray-500">
        Tryck <kbd className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-gray-400 font-mono text-xs">Ctrl+K</kbd> för att fokusera sökfältet
      </div>
    </div>
  );
}
