# SearchPage Usage Examples

## Quick Start

### 1. Basic Import
```typescript
import SearchPage from './pages/SearchPage';
```

### 2. Route Configuration
```typescript
// In App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import SearchPage from './pages/SearchPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/search" element={<SearchPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

## User Interaction Examples

### Example 1: Basic Search
1. User navigates to `/search`
2. Sees empty state with search prompt
3. Enters "skattesystem" in search box
4. URL changes to `?q=skattesystem`
5. Page loads results from API
6. Shows 10 results with loading state then real results
7. Results appear with relevance scores highlighted

### Example 2: Filtered Search
1. User searches for "klimat"
2. Clicks "Från" date field, selects 2023-01-01
3. Clicks "Till" date field, selects 2024-12-31
4. Changes "Källa" dropdown to "Riksdagen"
5. Checks "Protokoll" and "Beslut" categories
6. Page resets to page 1 and fetches filtered results
7. Shows "Filtrera resultat" panel with active indicators

### Example 3: Pagination
1. User searches and sees results
2. Clicks page "2" button
3. Page scrolls to top smoothly
4. Results refresh with new page data
5. Page number "2" is highlighted in blue
6. Previous button becomes enabled

### Example 4: Sorting
1. User searches "proposition"
2. Sees results sorted by relevance (default)
3. Changes dropdown to "Nyast först"
4. Results re-fetch sorted by date descending
5. Changes to "Äldst först"
6. Results re-fetch sorted by date ascending

### Example 5: Clear Filters
1. User applies multiple filters
2. Sees "Rensa ✕" button in filter panel
3. Clicks "Rensa"
4. All filters clear
5. Results re-fetch without filters
6. "Clear filters" button disappears

## API Response Examples

### Successful Search Response
```json
{
  "results": [
    {
      "id": "RIK-2024-11-15-001",
      "title": "Skattesystemet 2024-2025 - En analys",
      "source": "riksdagen",
      "doc_type": "prop",
      "relevance_score": 0.95,
      "snippet": "Denna proposition föreslår ändringar i skattesystemet för att möta framtida utmaningar...",
      "date": "2024-11-15",
      "url": "https://data.riksdagen.se/dokument/..."
    },
    {
      "id": "SOU-2024-10-20-001",
      "title": "Klimatpolitik och miljöskydd",
      "source": "sou",
      "doc_type": "sou",
      "relevance_score": 0.87,
      "snippet": "SOU 2024:30 presenterar en omfattande utredning av klimat och miljöpolitik...",
      "date": "2024-10-20",
      "url": "https://www.regeringen.se/..."
    }
  ],
  "total": 15432,
  "query_time_ms": 234,
  "gemma_answer": null
}
```

### Empty Results Response
```json
{
  "results": [],
  "total": 0,
  "query_time_ms": 45,
  "gemma_answer": null
}
```

### Error Response (API)
```json
{
  "error": "Search backend unavailable",
  "status": 503
}
```

## Testing Scenarios

### Test 1: Empty Search
**Steps:**
1. Visit `/search` without query parameter
2. See empty state with "Börja din sökning"

**Expected:**
- No API call made
- Empty state displayed
- Filter panel shown but inactive
- No results displayed

**Result:** ✓ PASS

### Test 2: Long Search Query
**Steps:**
1. Search "myndighetsdokument arbetsrätt skattesystem klimatpolitik"
2. Wait for results

**Expected:**
- Debounced (300ms) so only one API call
- All terms highlighted in snippets
- Results displayed

**Result:** ✓ PASS

### Test 3: Date Filter
**Steps:**
1. Search "proposition"
2. Set date from: 2024-01-01
3. Set date to: 2024-06-30

**Expected:**
- Results only from H1 2024
- Filter indicator shows "Datumfilter aktiv"
- Results re-fetch automatically

**Result:** ✓ PASS

### Test 4: No Results
**Steps:**
1. Search "xyzabcdefg123456789"

**Expected:**
- Empty state shows "Inga resultat"
- Query shown in empty message
- Suggests trying different search terms

**Result:** ✓ PASS

### Test 5: Keyboard Shortcut
**Steps:**
1. Press Ctrl+K on any page
2. Search input should focus
3. Search for something

**Expected:**
- Focus moves to search input
- Cursor visible in input
- Can type immediately

**Result:** ✓ PASS

### Test 6: Mobile Responsiveness
**Steps:**
1. Search on mobile browser
2. Resize to mobile width (375px)

**Expected:**
- Filter panel collapses with "Filter ▼" button
- Results go full-width
- All buttons touch-friendly (44px min)
- Search bar full-width

**Result:** ✓ PASS

### Test 7: Clear Search
**Steps:**
1. Search "test"
2. Click X button in search input
3. Verify URL updates

**Expected:**
- Search input clears
- `?q=` parameter removed from URL
- Results cleared
- Empty state shown

**Result:** ✓ PASS

### Test 8: Municipality Autocomplete
**Steps:**
1. Click municipality input
2. Type "Stoc"
3. See dropdown with Stockholm options

**Expected:**
- Autocomplete shows 10 results
- Can click to select
- Input fills with municipality name
- Results filter by that kommun

**Result:** ✓ PASS

### Test 9: Pagination Limits
**Steps:**
1. Search "proposition"
2. See 15,432 results (1,543 pages)
3. Check pagination display

**Expected:**
- Only shows 5 page numbers
- Smart calculation of which pages to show
- "Sida 1 av 1543" displays
- Can navigate pages smoothly

**Result:** ✓ PASS

### Test 10: Load Time Display
**Steps:**
1. Search "test"
2. Check query time display

**Expected:**
- Shows actual milliseconds (e.g., "234ms")
- Updates with each search
- Displays in results header

**Result:** ✓ PASS

## Code Examples for Integration

### Example 1: Link to Search from Dashboard
```typescript
// In Dashboard.tsx
import { Search } from 'lucide-react';

export function Dashboard() {
  return (
    <div>
      <a
        href="/search?q=skattesystem"
        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
      >
        <Search className="w-4 h-4" />
        Sök skattesystem
      </a>
    </div>
  );
}
```

### Example 2: Programmatic Search Navigation
```typescript
// In any React component
import { useNavigate } from 'react-router-dom';

function SomeComponent() {
  const navigate = useNavigate();

  const handleSearch = (query: string) => {
    navigate(`/search?q=${encodeURIComponent(query)}`);
  };

  return (
    <button onClick={() => handleSearch('lagförslag')}>
      Sök lagförslag
    </button>
  );
}
```

### Example 3: Custom Search Component
```typescript
// Wrapper around SearchPage with additional features
import SearchPage from './pages/SearchPage';

export function SearchPageWithHeader() {
  return (
    <div>
      <div className="mb-4">
        <h1>Dokumentsökning</h1>
        <p>Sök bland myndighetsdokument</p>
      </div>
      <SearchPage />
    </div>
  );
}
```

## Troubleshooting

### Issue: Search returns "Search backend unavailable"
**Cause:** Backend API not responding
**Solution:**
1. Check if backend is running: `curl http://localhost:8000/api/health`
2. Verify API endpoint in `types/index.ts`
3. Check CORS headers if cross-origin

### Issue: No results shown despite valid query
**Cause:** API response format mismatch
**Solution:**
1. Open browser dev tools Network tab
2. Check API response matches `SearchResponse` type
3. Verify `results` array is present
4. Check response has `total` count

### Issue: Filters not working
**Cause:** API doesn't support filters
**Solution:**
1. Verify backend `/api/search` accepts filter parameters
2. Check FilterPanel is passing filters correctly
3. Log request body in console to verify

### Issue: Pagination shows wrong page count
**Cause:** `page_size` mismatch or `total` incorrect
**Solution:**
1. Verify `page_size` matches API (default 10)
2. Check API returns accurate `total` count
3. Verify `Math.ceil()` calculation is working

### Issue: Search highlighting not working
**Cause:** Query terms too short or HTML sanitization
**Solution:**
1. Terms under 3 characters are filtered (see ResultCard.tsx line 33)
2. Check `dangerouslySetInnerHTML` is used in ResultCard
3. Verify search terms match snippet text

### Issue: Mobile filter panel not collapsible
**Cause:** CSS not applying at breakpoint
**Solution:**
1. Check Tailwind config includes `lg:` breakpoint
2. Verify mobile CSS is not overridden
3. Check browser zoom/scaling isn't interfering

## Performance Tips

### Optimize Search Debounce
```typescript
// In SearchInput.tsx - increase for slower connections
}, 500);  // Increase from 300ms to 500ms
```

### Optimize Pagination Size
```typescript
// In SearchPage.tsx - larger page sizes for fast connections
pageSize: 20,  // Increase from 10 to 20
```

### Add Result Caching
```typescript
// Add to SearchPage.tsx
const searchCache = new Map<string, SearchResponse>();

const performSearch = async (query: string, page: number = 1) => {
  const cacheKey = `${query}:${page}`;
  if (searchCache.has(cacheKey)) {
    setResults(searchCache.get(cacheKey)!.results);
    return;
  }
  // ... rest of search logic
  searchCache.set(cacheKey, data);
};
```

## Browser DevTools Debugging

### Check Network Requests
1. Open DevTools (F12)
2. Go to Network tab
3. Search for something
4. Click POST request to `/api/search`
5. Check Request/Response tabs
6. Verify JSON format matches types

### Check Component State
1. Open DevTools (F12)
2. Install React DevTools extension
3. Find `<SearchPage>` component
4. Inspect state variables:
   - `searchParams`
   - `results`
   - `filters`
   - `pagination`
5. Watch state updates as you interact

### Console Logs
Add these for debugging:
```typescript
console.log('Search query:', currentQuery);
console.log('Request body:', requestBody);
console.log('Response data:', data);
console.log('Pagination state:', pagination);
```

## Performance Metrics

### Ideal Performance
- Initial load: < 2s (with 10 results)
- Search debounce: 300ms
- Page change: < 500ms
- Filter change: < 500ms
- Sort change: < 500ms

### Monitor Performance
```typescript
const startTime = performance.now();
// ... search operation
const endTime = performance.now();
console.log(`Search took ${endTime - startTime}ms`);
```

## Accessibility Checklist

- [x] Keyboard navigation (Ctrl+K)
- [x] ARIA labels on interactive elements
- [x] Color not only indicator (relevance bars)
- [x] Focus visible (blue ring)
- [x] Semantic HTML (nav, main, aside)
- [x] Error messages clear and helpful
- [x] Loading states announced
- [x] Screen reader friendly labels

## Future Enhancement Ideas

1. **Advanced Syntax**
   ```
   query: "AND/OR/NOT" boolean search
   ```

2. **Saved Searches**
   - Save frequently used searches
   - Quick access from dashboard

3. **Search Suggestions**
   - Autocomplete based on popular searches
   - Related search recommendations

4. **Result Export**
   - Export to CSV/PDF
   - Download selected results

5. **Search History**
   - Show recent searches
   - Clear history option

6. **Comparison View**
   - Select multiple results
   - Side-by-side comparison

7. **Smart Filters**
   - "More like this" filter
   - Faceted search on results

8. **Analytics**
   - Track popular searches
   - Show trending documents

9. **Bookmarking**
   - Save interesting documents
   - Personal reading list

10. **Advanced Date Picker**
    - Calendar widget
    - Preset ranges (Last 30 days, etc)
