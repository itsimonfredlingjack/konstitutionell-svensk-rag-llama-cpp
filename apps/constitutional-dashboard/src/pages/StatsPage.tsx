import { useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  Database,
  TrendingUp,
  FileText,
  HardDrive,
  Loader2,
  Calendar,
} from 'lucide-react';

interface OverviewStats {
  totalDocuments: number;
  documentsThisWeek: number;
  totalSources: number;
  databaseSize: string;
}

interface DocumentTypeData {
  name: string;
  count: number;
  label: string;
}

interface TimelineData {
  date: string;
  documents: number;
}

interface CollectionStats {
  name: string;
  documents: number;
  percentage: number;
}

interface SourceStat {
  source: string;
  documents: number;
  lastUpdated: string;
  status: 'online' | 'syncing' | 'offline';
}

interface StorageStats {
  chromatdb_size: string;
  pdf_cache_size: string;
  total_storage: string;
}

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'];

export function StatsPage() {
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [docTypes, setDocTypes] = useState<DocumentTypeData[]>([]);
  const [timeline, setTimeline] = useState<TimelineData[]>([]);
  const [collections, setCollections] = useState<CollectionStats[]>([]);
  const [sources, setSources] = useState<SourceStat[]>([]);
  const [storage, setStorage] = useState<StorageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAllStats = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch overview stats
        const overviewRes = await fetch(
          'http://localhost:8000/api/stats/overview'
        );
        if (overviewRes.ok) {
          setOverview(await overviewRes.json());
        }

        // Fetch document types
        const typesRes = await fetch(
          'http://localhost:8000/api/stats/documents-by-type'
        );
        if (typesRes.ok) {
          const data = await typesRes.json();
          setDocTypes(data);
        }

        // Fetch timeline data
        const timelineRes = await fetch(
          'http://localhost:8000/api/stats/timeline'
        );
        if (timelineRes.ok) {
          const data = await timelineRes.json();
          setTimeline(data);
        }

        // Mock data for collections (update when API available)
        setCollections([
          { name: 'riksdag_documents_p1', documents: 230000, percentage: 43 },
          {
            name: 'swedish_gov_docs',
            documents: 305000,
            percentage: 57,
          },
        ]);

        // Mock data for sources (update when API available)
        setSources([
          {
            source: 'Riksdagen',
            documents: 230000,
            lastUpdated: '2025-12-15T14:30:00Z',
            status: 'online',
          },
          {
            source: 'Regeringskansliet',
            documents: 85000,
            lastUpdated: '2025-12-15T12:15:00Z',
            status: 'online',
          },
          {
            source: 'Domstolar',
            documents: 125000,
            lastUpdated: '2025-12-14T18:45:00Z',
            status: 'syncing',
          },
          {
            source: 'Kommuner',
            documents: 95000,
            lastUpdated: '2025-12-13T09:00:00Z',
            status: 'online',
          },
        ]);

        // Mock storage stats (update when API available)
        setStorage({
          chromatdb_size: '1.2 GB',
          pdf_cache_size: '3.8 GB',
          total_storage: '5.0 GB',
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        setError(message);
        console.error('Failed to fetch stats:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAllStats();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 animate-spin text-blue-500" />
          <p className="text-gray-400">Laddar statistik...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {error && (
        <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 text-red-400">
          <p className="font-semibold">Fel vid inladdning av statistik</p>
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {/* Overview Cards */}
      <section>
        <h2 className="text-2xl font-bold text-white mb-4">Överblick</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Total Documents */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-400 text-sm mb-2">
                  Totalt indexerade dokument
                </p>
                <p className="text-3xl font-bold text-white">
                  {overview
                    ? (overview.totalDocuments / 1000).toFixed(0)
                    : '0'}
                  K
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  {overview?.totalDocuments.toLocaleString('sv-SE') ||
                    '0'}{' '}
                  dokument
                </p>
              </div>
              <FileText className="w-8 h-8 text-blue-500" />
            </div>
          </div>

          {/* Documents This Week */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-400 text-sm mb-2">
                  Tillagda denna vecka
                </p>
                <p className="text-3xl font-bold text-white">
                  {overview ? (overview.documentsThisWeek / 1000).toFixed(1) : '0'}{' '}
                  K
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  {overview?.documentsThisWeek.toLocaleString('sv-SE') || '0'}{' '}
                  dokument
                </p>
              </div>
              <Calendar className="w-8 h-8 text-green-500" />
            </div>
          </div>

          {/* Total Sources */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-400 text-sm mb-2">
                  Myndigheter & källor
                </p>
                <p className="text-3xl font-bold text-white">
                  {overview?.totalSources || '0'}
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  aktiva källor
                </p>
              </div>
              <TrendingUp className="w-8 h-8 text-yellow-500" />
            </div>
          </div>

          {/* Database Size */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-400 text-sm mb-2">
                  Databaskapacitet
                </p>
                <p className="text-3xl font-bold text-white">
                  {overview?.databaseSize || '0'}
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  ChromaDB
                </p>
              </div>
              <Database className="w-8 h-8 text-purple-500" />
            </div>
          </div>
        </div>
      </section>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Document Distribution Chart */}
        <section className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" />
            Dokumentfördelning efter typ
          </h3>

          {docTypes.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={docTypes}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="label"
                  stroke="#9CA3AF"
                  tick={{ fill: '#9CA3AF', fontSize: 12 }}
                />
                <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '0.5rem',
                    color: '#fff',
                  }}
                  formatter={(value: any) => value.toLocaleString('sv-SE')}
                />
                <Bar
                  dataKey="count"
                  fill="#3B82F6"
                  radius={[8, 8, 0, 0]}
                  name="Dokument"
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-12 text-gray-500">
              Ingen dokumentdata tillgänglig
            </div>
          )}
        </section>

        {/* Collection Breakdown Pie Chart */}
        <section className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <Database className="w-5 h-5 text-purple-500" />
            Samlingsfördelning
          </h3>

          {collections.length > 0 ? (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={collections}
                    dataKey="documents"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={(entry) => `${entry.percentage}%`}
                  >
                    {collections.map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={COLORS[index % COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: any) =>
                      value.toLocaleString('sv-SE')
                    }
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-4 space-y-2 w-full">
                {collections.map((col, idx) => (
                  <div
                    key={col.name}
                    className="flex items-center justify-between text-sm"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{
                          backgroundColor:
                            COLORS[idx % COLORS.length],
                        }}
                      />
                      <span className="text-gray-300">{col.name}</span>
                    </div>
                    <span className="text-white font-semibold">
                      {col.documents.toLocaleString('sv-SE')} ({col.percentage}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              Ingen samlingsdata tillgänglig
            </div>
          )}
        </section>
      </div>

      {/* Timeline Chart */}
      <section className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-green-500" />
          Dokumentinladdning (senaste 30 dagarna)
        </h3>

        {timeline.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                stroke="#9CA3AF"
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                tickFormatter={(value) =>
                  new Date(value).toLocaleDateString('sv-SE', {
                    month: 'short',
                    day: 'numeric',
                  })
                }
              />
              <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '0.5rem',
                  color: '#fff',
                }}
                formatter={(value: any) =>
                  value.toLocaleString('sv-SE')
                }
                labelFormatter={(value) =>
                  new Date(value).toLocaleDateString('sv-SE')
                }
              />
              <Legend wrapperStyle={{ color: '#9CA3AF' }} />
              <Line
                type="monotone"
                dataKey="documents"
                name="Dokument tillagda"
                stroke="#10B981"
                strokeWidth={2}
                dot={{ fill: '#10B981', r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-center py-12 text-gray-500">
            Ingen tidsseriedata tillgänglig
          </div>
        )}
      </section>

      {/* Source Statistics Table */}
      <section className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <Database className="w-5 h-5 text-blue-500" />
          Källöversikt
        </h3>

        {sources.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-300">
                    Källa
                  </th>
                  <th className="px-4 py-3 text-right text-sm font-semibold text-gray-300">
                    Dokument
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-300">
                    Senast uppdaterad
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-300">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr
                    key={source.source}
                    className="border-b border-gray-700 hover:bg-gray-700/50 transition-colors"
                  >
                    <td className="px-4 py-3 text-sm text-white font-medium">
                      {source.source}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-300">
                      {source.documents.toLocaleString('sv-SE')}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-400">
                      {new Date(source.lastUpdated).toLocaleString(
                        'sv-SE'
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span
                        className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold ${
                          source.status === 'online'
                            ? 'bg-green-900/30 text-green-400'
                            : source.status === 'syncing'
                              ? 'bg-yellow-900/30 text-yellow-400'
                              : 'bg-red-900/30 text-red-400'
                        }`}
                      >
                        <span
                          className={`inline-block w-2 h-2 rounded-full ${
                            source.status === 'online'
                              ? 'bg-green-500'
                              : source.status === 'syncing'
                                ? 'bg-yellow-500'
                                : 'bg-red-500'
                          }`}
                        />
                        {source.status === 'online'
                          ? 'Online'
                          : source.status === 'syncing'
                            ? 'Synkroniseras'
                            : 'Offline'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12 text-gray-500">
            Ingen källdata tillgänglig
          </div>
        )}
      </section>

      {/* Storage Statistics */}
      <section className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <HardDrive className="w-5 h-5 text-orange-500" />
          Lagringsstatistik
        </h3>

        {storage ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gray-700/50 rounded-lg p-4 border border-gray-600">
              <p className="text-gray-400 text-sm mb-2">ChromaDB</p>
              <p className="text-2xl font-bold text-white">
                {storage.chromatdb_size}
              </p>
              <p className="text-xs text-gray-500 mt-2">
                Vektordatabaskälla
              </p>
            </div>

            <div className="bg-gray-700/50 rounded-lg p-4 border border-gray-600">
              <p className="text-gray-400 text-sm mb-2">
                PDF-cacheminne
              </p>
              <p className="text-2xl font-bold text-white">
                {storage.pdf_cache_size}
              </p>
              <p className="text-xs text-gray-500 mt-2">
                Lokalt lagrade PDFs
              </p>
            </div>

            <div className="bg-gray-700/50 rounded-lg p-4 border border-gray-600">
              <p className="text-gray-400 text-sm mb-2">
                Total lagring
              </p>
              <p className="text-2xl font-bold text-white">
                {storage.total_storage}
              </p>
              <p className="text-xs text-gray-500 mt-2">
                Sammanlagd storlek
              </p>
            </div>
          </div>
        ) : (
          <div className="text-center py-12 text-gray-500">
            Ingen lagringsdata tillgänglig
          </div>
        )}
      </section>
    </div>
  );
}
