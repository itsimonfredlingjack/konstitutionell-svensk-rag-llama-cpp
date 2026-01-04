import { useState, useEffect } from 'react';
import { X, ChevronDown } from 'lucide-react';
import type { SearchFilters, Municipality } from '../../types';
import { API_BASE } from '../../types';

interface FilterPanelProps {
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
}

const SOURCE_OPTIONS = [
  { value: '', label: 'Alla källor' },
  { value: 'riksdagen', label: 'Riksdagen' },
  { value: 'kommun', label: 'Kommun' },
  { value: 'myndighet', label: 'Myndighet' },
  { value: 'sou', label: 'SOU' },
  { value: 'prop', label: 'Proposition' },
];

const CATEGORY_OPTIONS = [
  { value: 'protokoll', label: 'Protokoll' },
  { value: 'beslut', label: 'Beslut' },
  { value: 'utredning', label: 'Utredning' },
  { value: 'motion', label: 'Motion' },
];

export default function FilterPanel({ filters, onFiltersChange }: FilterPanelProps) {
  const [municipalities, setMunicipalities] = useState<Municipality[]>([]);
  const [municipalitySearch, setMunicipalitySearch] = useState('');
  const [showMunicipalityDropdown, setShowMunicipalityDropdown] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  // Fetch municipalities on mount
  useEffect(() => {
    const fetchMunicipalities = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/municipalities`);
        if (response.ok) {
          const data = await response.json();
          setMunicipalities(data);
        }
      } catch (error) {
        console.error('Failed to fetch municipalities:', error);
      }
    };

    fetchMunicipalities();
  }, []);

  const handleSourceChange = (value: string) => {
    onFiltersChange({ ...filters, source: value || undefined });
  };

  const handleCategoryToggle = (value: string) => {
    const current = filters.category || [];
    const updated = current.includes(value)
      ? current.filter(c => c !== value)
      : [...current, value];
    onFiltersChange({ ...filters, category: updated.length > 0 ? updated : undefined });
  };

  const handleMunicipalitySelect = (municipality: Municipality) => {
    onFiltersChange({ ...filters, municipality: municipality.name });
    setMunicipalitySearch(municipality.name);
    setShowMunicipalityDropdown(false);
  };

  const handleDateChange = (field: 'date_from' | 'date_to', value: string) => {
    onFiltersChange({ ...filters, [field]: value || undefined });
  };

  const clearFilters = () => {
    onFiltersChange({});
    setMunicipalitySearch('');
  };

  const hasActiveFilters = filters.source ||
    (filters.category && filters.category.length > 0) ||
    filters.municipality ||
    filters.date_from ||
    filters.date_to;

  const filteredMunicipalities = municipalities.filter(m =>
    m.name.toLowerCase().includes(municipalitySearch.toLowerCase())
  );

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg">
      {/* Mobile accordion header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="lg:hidden w-full px-4 py-3 flex items-center justify-between text-white font-medium"
      >
        <span>Filter</span>
        <ChevronDown className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
      </button>

      {/* Filter content */}
      <div className={`p-4 space-y-4 ${!isExpanded ? 'hidden lg:block' : ''}`}>
        {/* Header with clear button */}
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Filtrera resultat</h3>
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="text-sm text-red-400 hover:text-red-300 flex items-center gap-1"
            >
              <X className="w-4 h-4" />
              Rensa
            </button>
          )}
        </div>

        {/* Source */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Källa
          </label>
          <select
            value={filters.source || ''}
            onChange={(e) => handleSourceChange(e.target.value)}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            {SOURCE_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Category (multi-select) */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Kategori
          </label>
          <div className="space-y-2">
            {CATEGORY_OPTIONS.map(option => (
              <label key={option.value} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={(filters.category || []).includes(option.value)}
                  onChange={() => handleCategoryToggle(option.value)}
                  className="w-4 h-4 bg-gray-700 border-gray-600 rounded text-blue-500 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-300">{option.label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Municipality autocomplete */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Kommun
          </label>
          <div className="relative">
            <input
              type="text"
              value={municipalitySearch}
              onChange={(e) => {
                setMunicipalitySearch(e.target.value);
                setShowMunicipalityDropdown(true);
                if (!e.target.value) {
                  onFiltersChange({ ...filters, municipality: undefined });
                }
              }}
              onFocus={() => setShowMunicipalityDropdown(true)}
              placeholder="Sök kommun..."
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />

            {showMunicipalityDropdown && municipalitySearch && filteredMunicipalities.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-gray-700 border border-gray-600 rounded-md shadow-lg max-h-48 overflow-y-auto">
                {filteredMunicipalities.slice(0, 10).map(municipality => (
                  <button
                    key={municipality.id}
                    onClick={() => handleMunicipalitySelect(municipality)}
                    className="w-full px-3 py-2 text-left text-white hover:bg-gray-600 transition-colors"
                  >
                    {municipality.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Date range */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Datumintervall
          </label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Från</label>
              <input
                type="date"
                value={filters.date_from || ''}
                onChange={(e) => handleDateChange('date_from', e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Till</label>
              <input
                type="date"
                value={filters.date_to || ''}
                onChange={(e) => handleDateChange('date_to', e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>
        </div>

        {/* Active filters summary */}
        {hasActiveFilters && (
          <div className="pt-4 border-t border-gray-700">
            <p className="text-xs text-gray-400">
              {[
                filters.source && `Källa: ${SOURCE_OPTIONS.find(o => o.value === filters.source)?.label}`,
                filters.category && filters.category.length > 0 && `${filters.category.length} kategori${filters.category.length > 1 ? 'er' : ''}`,
                filters.municipality && `Kommun: ${filters.municipality}`,
                (filters.date_from || filters.date_to) && 'Datumfilter aktiv'
              ].filter(Boolean).join(' • ')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
