# SearchPage Integration Guide

## Overview
A complete full-featured search page for the Constitutional-AI dashboard has been created at:
```
src/pages/SearchPage.tsx
```

## Features Implemented

### 1. Full-Width Search Input
- Clear, prominent search box at the top with icon
- Debounced input (300ms) for performance
- Ctrl+K keyboard shortcut to focus
- Clear button to reset search
- URL-synced search query (reads from `?q=` parameter)

### 2. Left Sidebar Filter Panel
Uses existing `FilterPanel.tsx` component with:
- **Document Type Filters**: prop, mot, sou, bet, ds
- **Date Range Picker**: From/To date inputs
- **Source Filter**: Riksdagen, Kommun, Myndighet, SOU, Proposition
- **Category Filter**: Protokoll, Beslut, Utredning, Motion
- **Municipality Autocomplete**: Searchable dropdown with live data
- **Clear Filters Button**: Reset all active filters
- **Mobile Responsive**: Collapsible on small screens

### 3. Results List Display
Uses existing `ResultsList.tsx` and `ResultCard.tsx` components:
- **Document Title**: Highlighted in results list
- **Type Badge**: Color-coded by source
- **Relevance Score**: Visual bar + percentage
- **Date Display**: Formatted Swedish date (sv-SE)
- **Text Snippet**: With search term highlighting
- **External Link**: "Läs mer" button to original document
- **Loading States**: Skeleton loaders while fetching
- **Empty States**: Helpful messages when no results

### 4. Pagination
- Previous/Next buttons
- Numbered page buttons (max 5 visible)
- Smart page number calculation
- Smooth scroll to top on page change
- Disabled state during loading
- Page counter display

### 5. Sorting Options
- **Relevance**: Default sort (highest score first)
- **Date Descending**: Newest documents first
- **Date Ascending**: Oldest documents first
- Dropdown selector with real-time updates

### 6. Dark Theme Styling
- Gray-800/900 backgrounds matching existing dashboard
- Blue-500 focus and action colors
- Green/yellow/red relevance score indicators
- Consistent with existing component styling
- Responsive grid layout (1 col mobile, 4 col desktop)

### 7. Error Handling
- User-friendly error messages with alert icon
- API error status code handling
- Network error recovery
- Graceful degradation

### 8. Swedish Language UI
- All labels and messages in Swedish
- Date formatting with sv-SE locale
- "myndighetsdokument" terminology
- Localized number formatting (e.g., 230 000)

## API Integration

### Request Format
```typescript
POST /api/search
{
  query: string,           // Search query
  filters: SearchFilters,  // Optional filters
  page: number,            // 1-indexed page number
  sort: string,            // 'relevance' | 'date_desc' | 'date_asc'
  page_size: number        // Results per page (default 10)
}
```

### Response Format
```typescript
{
  results: SearchResult[],
  total: number,
  query_time_ms: number,
  gemma_answer?: GemmaAnswer
}
```

## Component Structure

```
SearchPage (src/pages/SearchPage.tsx)
├── Search Header (gradient background)
│   └── SearchInput (existing component)
├── Error Alert (if applicable)
└── Results Grid (on desktop: 1/4 + 3/4 layout)
    ├── Sidebar (col-span-1)
    │   └── FilterPanel (existing component)
    └── Main Content (col-span-3)
        ├── Results Header (with sort dropdown)
        ├── ResultsList (existing component)
        │   └── ResultCard[] (existing component)
        └── Pagination Controls
```

## State Management

### Component State
- `searchParams` - URL query parameters (via react-router)
- `results` - Array of SearchResult objects
- `loading` - Boolean for loading state
- `error` - String for error messages
- `filters` - Current active search filters
- `queryTimeMs` - Time taken for last search
- `pagination` - Pagination state object
- `sortBy` - Current sort order

### State Transitions
1. User enters search → `handleSearch()` → update URL + call `performSearch()`
2. `performSearch()` → sets loading → API call → updates results/pagination
3. User changes filters → reset to page 1 → `performSearch()`
4. User clicks page → smooth scroll + `performSearch()` with new page
5. User changes sort → reset to page 1 → `performSearch()`

## Integration Steps

### 1. Update App.tsx for Routing
If using React Router, add the search page route:

```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import SearchPage from './pages/SearchPage';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/search" element={<SearchPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

### 2. Update Layout.tsx Navigation
Add a Search link to the header navigation:

```typescript
<nav className="flex items-center gap-4">
  <a
    href="/search"
    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-700 text-white hover:bg-gray-600 transition-colors"
  >
    <Search className="w-4 h-4" />
    Search
  </a>
  <a
    href="/"
    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-700 text-white hover:bg-gray-600 transition-colors"
  >
    <LayoutDashboard className="w-4 h-4" />
    Dashboard
  </a>
</nav>
```

### 3. Verify Dependencies
Ensure these packages are installed:
```bash
npm list react-router-dom lucide-react
```

### 4. Testing
Start the dev server and test:
```bash
npm run dev
# Visit http://localhost:5173/search
```

## URL Parameters

The search page syncs with URL parameters:

```
# Basic search
/search?q=skattesystemet

# With filters (if needed - currently not in URL, but filterable via UI)
/search?q=lagförslag&sort=date_desc
```

## Performance Considerations

1. **Debounced Search**: 300ms delay prevents excessive API calls
2. **Pagination**: Only loads one page of results (10 per page default)
3. **Lazy Component Loading**: Results only render when query exists
4. **Memoized Imports**: Uses `import type` for zero-runtime imports
5. **Query Time Display**: Shows actual search latency (query_time_ms)

## Customization Points

### Change Page Size
Modify `pagination.pageSize` in initial state (line 26):
```typescript
pageSize: 20,  // More results per page
```

### Change Debounce Delay
In `SearchInput.tsx`, modify line 47:
```typescript
}, 300);  // 300ms debounce
```

### Add More Filters
Extend `FilterPanel.tsx` in `CATEGORY_OPTIONS` or `SOURCE_OPTIONS`

### Customize Styling
- Search header gradient: Line 163 (`from-gray-800 to-gray-900`)
- Grid layout: Line 211 (`grid-cols-1 lg:grid-cols-4`)
- Pagination size: Line 266 (`min-w-[80px]`)

## API Endpoint Required

The backend must provide:
```
POST /api/search
```

With support for:
- `query` - Full-text search
- `filters.sources[]` - Multiple source types
- `filters.doc_types[]` - Document type filtering
- `filters.date_from` / `filters.date_to` - Date range
- `filters.municipality` - Kommun filtering
- `sort` parameter with 'relevance', 'date_desc', 'date_asc'
- `page` and `page_size` for pagination

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari 14+, Android Chrome)

## Accessibility Features

- Semantic HTML (nav, main, aside sections)
- ARIA labels on buttons (`aria-label`)
- Keyboard navigation (Ctrl+K shortcut)
- Focus indicators on interactive elements
- Loading states for screen readers
- Semantic color usage (red for errors)

## Known Limitations

1. Date picker uses HTML5 input type="date" (browser-native UI)
2. Filters not persisted to URL (only search query)
3. "Load more" pagination (not infinite scroll)
4. Max 5 page numbers shown in pagination UI
5. Municipality autocomplete limited to 10 results

## Future Enhancements

- [ ] Add saved searches feature
- [ ] Advanced query syntax (AND, OR, NOT)
- [ ] Export results to CSV/PDF
- [ ] Search suggestions/autocomplete
- [ ] Bookmarking individual results
- [ ] Search history
- [ ] Filter presets
- [ ] Faceted search on results
- [ ] Results comparison view
- [ ] Persistent filter state in URL

## File Locations

- **SearchPage**: `src/pages/SearchPage.tsx` (294 lines)
- **SearchInput**: `src/components/search/SearchInput.tsx` (existing)
- **FilterPanel**: `src/components/search/FilterPanel.tsx` (existing)
- **ResultsList**: `src/components/search/ResultsList.tsx` (existing)
- **ResultCard**: `src/components/search/ResultCard.tsx` (existing)
- **Types**: `src/types/index.ts` (existing)

## Support

For issues or questions about the SearchPage:
1. Check the component comments (inline documentation)
2. Verify API endpoint is responding correctly
3. Check browser console for errors
4. Ensure all imported components exist
5. Verify TypeScript types match API response
