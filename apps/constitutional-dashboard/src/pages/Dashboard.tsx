import { useEffect, useState } from 'react';
import { StatusCard } from '../components/StatusCard';
import { LiveProgress } from '../components/LiveProgress';
import { SearchBox } from '../components/SearchBox';
import { BenchmarkChart } from '../components/BenchmarkChart';
import { Database, FileText, HardDrive, Server } from 'lucide-react';
import type { SystemStatus } from '../types';
import { API_BASE } from '../types';

interface CorpusStats {
  total_documents: number;
  collections: Record<string, number>;
  storage_size_mb: number;
  last_updated: string;
}

interface AdminStatus {
  pdf_cache_size_mb: number;
  pdf_cache_files: number;
}

export function Dashboard() {
  const [systemStatus, setSystemStatus] = useState<SystemStatus[]>([]);
  const [corpusStats, setCorpusStats] = useState<CorpusStats | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);

  useEffect(() => {
    // Function to check health of all services
    const checkHealth = async () => {
      const services = [
        { name: 'ChromaDB', endpoint: '/api/constitutional/health' },
        { name: 'Backend', endpoint: '/api/health' },
        { name: 'Ollama', endpoint: '/api/orchestrator/status' },
      ];

      const results = await Promise.all(
        services.map(async (service) => {
          const startTime = Date.now();
          try {
            const response = await fetch(`${API_BASE}${service.endpoint}`);
            const latency = Date.now() - startTime;

            return {
              name: service.name,
              status: response.ok ? 'online' : 'offline',
              latency,
              lastChecked: new Date().toISOString(),
            } as SystemStatus;
          } catch {
            return {
              name: service.name,
              status: 'offline',
              lastChecked: new Date().toISOString(),
            } as SystemStatus;
          }
        })
      );

      setSystemStatus(results);
    };

    // Fetch corpus stats and admin status
    const fetchStats = async () => {
      try {
        const [overviewRes, adminRes] = await Promise.all([
          fetch(`${API_BASE}/api/constitutional/stats/overview`),
          fetch(`${API_BASE}/api/constitutional/admin/status`),
        ]);

        if (overviewRes.ok) {
          const data = await overviewRes.json();
          setCorpusStats(data);
        }

        if (adminRes.ok) {
          const data = await adminRes.json();
          setAdminStatus(data);
        }
      } catch (err) {
        console.error('Failed to fetch stats:', err);
      }
    };

    // Initial checks
    checkHealth();
    fetchStats();

    // Refresh every 30 seconds
    const interval = setInterval(() => {
      checkHealth();
      fetchStats();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const formatNumber = (num: number) => num.toLocaleString('sv-SE');
  const mbToGb = (mb: number) => (mb / 1024).toFixed(1);

  return (
    <div className="space-y-8">
      {/* Corpus Overview Cards */}
      <section>
        <h2 className="text-2xl font-bold text-white mb-4">Corpus Översikt</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Total Documents */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center gap-3 mb-2">
              <FileText className="w-8 h-8 text-blue-500" />
              <span className="text-gray-400 text-sm">Totalt dokument</span>
            </div>
            <div className="text-3xl font-bold text-white">
              {corpusStats ? formatNumber(corpusStats.total_documents) : '---'}
            </div>
          </div>

          {/* Collections */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center gap-3 mb-2">
              <Database className="w-8 h-8 text-green-500" />
              <span className="text-gray-400 text-sm">Collections</span>
            </div>
            <div className="text-3xl font-bold text-white">
              {corpusStats ? Object.keys(corpusStats.collections).length : '---'}
            </div>
            {corpusStats && (
              <div className="mt-2 text-xs text-gray-500">
                {Object.entries(corpusStats.collections).map(([name, count]) => (
                  <div key={name} className="truncate">
                    {name}: {formatNumber(count)}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Storage */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center gap-3 mb-2">
              <HardDrive className="w-8 h-8 text-yellow-500" />
              <span className="text-gray-400 text-sm">ChromaDB</span>
            </div>
            <div className="text-3xl font-bold text-white">
              {corpusStats ? `${mbToGb(corpusStats.storage_size_mb)} GB` : '---'}
            </div>
          </div>

          {/* PDF Cache */}
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="flex items-center gap-3 mb-2">
              <Server className="w-8 h-8 text-purple-500" />
              <span className="text-gray-400 text-sm">PDF Cache</span>
            </div>
            <div className="text-3xl font-bold text-white">
              {adminStatus ? `${mbToGb(adminStatus.pdf_cache_size_mb)} GB` : '---'}
            </div>
            {adminStatus && (
              <div className="mt-2 text-xs text-gray-500">
                {formatNumber(adminStatus.pdf_cache_files)} filer
              </div>
            )}
          </div>
        </div>
      </section>

      {/* System Status Grid */}
      <section>
        <h2 className="text-2xl font-bold text-white mb-4">Systemstatus</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {systemStatus.map((status) => (
            <StatusCard key={status.name} status={status} />
          ))}
        </div>
      </section>

      {/* Live Harvest Progress */}
      <section>
        <LiveProgress />
      </section>

      {/* Search and Benchmarks Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quick Search */}
        <section>
          <SearchBox />
        </section>

        {/* Benchmark History */}
        <section>
          <BenchmarkChart />
        </section>
      </div>
    </div>
  );
}
