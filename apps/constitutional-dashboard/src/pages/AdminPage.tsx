import { useEffect, useState, useRef } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  Download,
  Upload,
  Settings,
  Trash2,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle,
  Clock,
  Activity,
  Zap,
  Database,
} from 'lucide-react';
import { StatusCard } from '../components/StatusCard';
import type {
  EmbeddingJob,
  LogEntry,
  Workflow,
  CreateJobRequest,
} from '../types/admin';
import { API_BASE } from '../types/admin';

export function AdminPage() {
  // System Status
  const [systemStatus, setSystemStatus] = useState<any[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);

  // Harvest Control
  const [activeJob, setActiveJob] = useState<EmbeddingJob | null>(null);
  const [selectedSource, setSelectedSource] = useState<'Riksdagen' | 'Kommuner' | 'All'>('Riksdagen');
  const [rateLimit, setRateLimit] = useState(5);
  const [harvestLoading, setHarvestLoading] = useState(false);

  // Scraper Management
  const [scrapers, setScrapers] = useState<any[]>([]);
  const [scrapersLoading, setScrapersLoading] = useState(false);

  // Logs Viewer
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logFilter, setLogFilter] = useState<'ALL' | 'INFO' | 'WARNING' | 'ERROR'>('ALL');
  const [autoScroll, setAutoScroll] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // n8n Workflows
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowLoading, setWorkflowLoading] = useState(false);

  // Database Actions
  const [dbLoading, setDbLoading] = useState(false);
  const [dbMessage, setDbMessage] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // System Status Check
  useEffect(() => {
    const checkSystemStatus = async () => {
      setStatusLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/admin/status`);
        if (response.ok) {
          const data = await response.json();
          setSystemStatus([
            {
              name: 'Ollama',
              status: data.ollama?.online ? 'online' : 'offline',
              latency: data.ollama?.latency,
              lastChecked: new Date().toISOString(),
            },
            {
              name: 'ChromaDB',
              status: data.chromadb?.connected ? 'online' : 'offline',
              latency: data.chromadb?.latency,
              lastChecked: new Date().toISOString(),
            },
            {
              name: 'Backend API',
              status: data.api?.healthy ? 'online' : 'offline',
              latency: data.api?.latency,
              lastChecked: new Date().toISOString(),
            },
            {
              name: 'n8n',
              status: data.n8n?.online ? 'online' : 'offline',
              latency: data.n8n?.latency,
              lastChecked: new Date().toISOString(),
            },
          ]);
        }
      } catch (error) {
        console.error('Failed to fetch system status:', error);
      } finally {
        setStatusLoading(false);
      }
    };

    checkSystemStatus();
    const interval = setInterval(checkSystemStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch Harvest Jobs
  useEffect(() => {
    const fetchJobs = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/admin/harvest/jobs`);
        if (response.ok) {
          const data = await response.json();
          const active = data.jobs.find((j: EmbeddingJob) => j.status === 'running');
          setActiveJob(active || null);
        }
      } catch (error) {
        console.error('Failed to fetch harvest jobs:', error);
      }
    };

    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  // Fetch Logs
  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/admin/logs?limit=50`);
        if (response.ok) {
          const data = await response.json();
          setLogs(data.logs);
        }
      } catch (error) {
        console.error('Failed to fetch logs:', error);
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 2000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  // Fetch Workflows
  useEffect(() => {
    const fetchWorkflows = async () => {
      setWorkflowLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/admin/workflows`);
        if (response.ok) {
          const data = await response.json();
          setWorkflows(data.workflows);
        }
      } catch (error) {
        console.error('Failed to fetch workflows:', error);
      } finally {
        setWorkflowLoading(false);
      }
    };

    fetchWorkflows();
    const interval = setInterval(fetchWorkflows, 10000);
    return () => clearInterval(interval);
  }, []);

  // Fetch Scrapers
  useEffect(() => {
    const fetchScrapers = async () => {
      setScrapersLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/admin/scrapers`);
        if (response.ok) {
          const data = await response.json();
          setScrapers(data.scrapers);
        }
      } catch (error) {
        console.error('Failed to fetch scrapers:', error);
      } finally {
        setScrapersLoading(false);
      }
    };

    fetchScrapers();
    const interval = setInterval(fetchScrapers, 15000);
    return () => clearInterval(interval);
  }, []);

  // Harvest Actions
  const startHarvest = async () => {
    setHarvestLoading(true);
    try {
      const payload: CreateJobRequest = {
        source: selectedSource,
      };
      const response = await fetch(`${API_BASE}/api/admin/harvest/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        const data = await response.json();
        setActiveJob(data.job);
      }
    } catch (error) {
      console.error('Failed to start harvest:', error);
    } finally {
      setHarvestLoading(false);
    }
  };

  const stopHarvest = async () => {
    if (!activeJob) return;
    setHarvestLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/admin/harvest/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: activeJob.id }),
      });
      if (response.ok) {
        setActiveJob(null);
      }
    } catch (error) {
      console.error('Failed to stop harvest:', error);
    } finally {
      setHarvestLoading(false);
    }
  };

  const toggleScraper = async (scraperId: string, enabled: boolean) => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/scrapers/${scraperId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !enabled }),
      });
      if (response.ok) {
        setScrapers(
          scrapers.map((s) => (s.id === scraperId ? { ...s, enabled: !enabled } : s))
        );
      }
    } catch (error) {
      console.error('Failed to toggle scraper:', error);
    }
  };

  const triggerScraper = async (scraperId: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/scrapers/${scraperId}/trigger`, {
        method: 'POST',
      });
      if (response.ok) {
        const freshResponse = await fetch(`${API_BASE}/api/admin/scrapers`);
        if (freshResponse.ok) {
          const data = await freshResponse.json();
          setScrapers(data.scrapers);
        }
      }
    } catch (error) {
      console.error('Failed to trigger scraper:', error);
    }
  };

  const toggleWorkflow = async (workflowId: string, active: boolean) => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/workflows/${workflowId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: !active }),
      });
      if (response.ok) {
        setWorkflows(
          workflows.map((w) => (w.id === workflowId ? { ...w, active: !active } : w))
        );
      }
    } catch (error) {
      console.error('Failed to toggle workflow:', error);
    }
  };

  // Database Actions
  const reindexDatabase = async () => {
    setDbLoading(true);
    setDbMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/admin/database/reindex`, {
        method: 'POST',
      });
      if (response.ok) {
        setDbMessage({ type: 'success', message: 'Omindexering startad' });
      } else {
        setDbMessage({ type: 'error', message: 'Misslyckades att starta omindexering' });
      }
    } catch (error) {
      setDbMessage({ type: 'error', message: 'Fel: ' + String(error) });
    } finally {
      setDbLoading(false);
    }
  };

  const clearCache = async () => {
    setDbLoading(true);
    setDbMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/admin/database/clear-cache`, {
        method: 'POST',
      });
      if (response.ok) {
        setDbMessage({ type: 'success', message: 'Cache rensad' });
      } else {
        setDbMessage({ type: 'error', message: 'Misslyckades att rensa cache' });
      }
    } catch (error) {
      setDbMessage({ type: 'error', message: 'Fel: ' + String(error) });
    } finally {
      setDbLoading(false);
    }
  };

  const backupDatabase = async () => {
    setDbLoading(true);
    setDbMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/admin/database/backup`, {
        method: 'POST',
      });
      if (response.ok) {
        const data = await response.json();
        setDbMessage({ type: 'success', message: `Backup skapad: ${data.backup_path}` });
      } else {
        setDbMessage({ type: 'error', message: 'Misslyckades att skapa backup' });
      }
    } catch (error) {
      setDbMessage({ type: 'error', message: 'Fel: ' + String(error) });
    } finally {
      setDbLoading(false);
    }
  };

  const exportStatistics = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/database/statistics`);
      if (response.ok) {
        const data = await response.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `statistics-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        window.URL.revokeObjectURL(url);
        setDbMessage({ type: 'success', message: 'Statistik exporterad' });
      }
    } catch (error) {
      setDbMessage({ type: 'error', message: 'Fel: ' + String(error) });
    }
  };

  const filteredLogs = logs.filter((log) => logFilter === 'ALL' || log.level === logFilter);

  return (
    <div className="space-y-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-2">Admin Panel</h1>
        <p className="text-gray-400">Systemöversikt och styrning</p>
      </div>

      {/* System Status Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          <h2 className="text-2xl font-bold text-white">Systemstatus</h2>
        </div>
        {statusLoading ? (
          <div className="text-gray-400">Laddar systemstatus...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {systemStatus.map((status) => (
              <StatusCard key={status.name} status={status} />
            ))}
          </div>
        )}
      </section>

      {/* Harvest Control Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-yellow-400" />
          <h2 className="text-2xl font-bold text-white">Skördning (Harvest)</h2>
        </div>
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {/* Source Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Källa
              </label>
              <select
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value as any)}
                disabled={activeJob?.status === 'running'}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white disabled:opacity-50"
              >
                <option value="Riksdagen">Riksdagen (500K+ dokument)</option>
                <option value="Kommuner">Kommuner (omfattande skördning)</option>
                <option value="All">Alla källor</option>
              </select>
            </div>

            {/* Rate Limit */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Hastighetsgräns (req/s): {rateLimit}
              </label>
              <input
                type="range"
                min="1"
                max="20"
                value={rateLimit}
                onChange={(e) => setRateLimit(Number(e.target.value))}
                disabled={activeJob?.status === 'running'}
                className="w-full disabled:opacity-50"
              />
            </div>

            {/* Control Buttons */}
            <div className="flex items-end gap-2">
              {activeJob?.status === 'running' ? (
                <button
                  onClick={stopHarvest}
                  disabled={harvestLoading}
                  className="flex-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded flex items-center justify-center gap-2 transition-colors"
                >
                  <Pause className="w-4 h-4" />
                  Stoppa
                </button>
              ) : (
                <button
                  onClick={startHarvest}
                  disabled={harvestLoading}
                  className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 rounded flex items-center justify-center gap-2 transition-colors"
                >
                  <Play className="w-4 h-4" />
                  Starta
                </button>
              )}
            </div>
          </div>

          {/* Active Job Progress */}
          {activeJob && (
            <div className="bg-gray-700 rounded p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-white font-semibold">{activeJob.source}</h3>
                  <p className="text-sm text-gray-400">
                    {activeJob.progress}/{activeJob.total} dokument
                  </p>
                </div>
                <span
                  className={`px-3 py-1 rounded text-sm font-medium ${
                    activeJob.status === 'running'
                      ? 'bg-blue-600 text-white'
                      : activeJob.status === 'completed'
                        ? 'bg-green-600 text-white'
                        : 'bg-red-600 text-white'
                  }`}
                >
                  {activeJob.status === 'running' ? 'Pågår' : activeJob.status}
                </span>
              </div>
              <div className="w-full bg-gray-600 rounded-full h-2">
                <div
                  className="bg-green-500 h-2 rounded-full transition-all"
                  style={{ width: `${(activeJob.progress / activeJob.total) * 100}%` }}
                />
              </div>
              {activeJob.speed && (
                <p className="text-xs text-gray-400">
                  Hastighet: {activeJob.speed.toFixed(1)} dok/min
                </p>
              )}
              {activeJob.error && (
                <p className="text-xs text-red-400">Fel: {activeJob.error}</p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Scraper Management Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-purple-400" />
          <h2 className="text-2xl font-bold text-white">Skrapare (Scrapers)</h2>
        </div>
        <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-700 border-b border-gray-600">
                <tr>
                  <th className="px-6 py-3 text-left text-gray-300 font-semibold">Namn</th>
                  <th className="px-6 py-3 text-left text-gray-300 font-semibold">Status</th>
                  <th className="px-6 py-3 text-left text-gray-300 font-semibold">Senast körda</th>
                  <th className="px-6 py-3 text-center text-gray-300 font-semibold">Dokument</th>
                  <th className="px-6 py-3 text-center text-gray-300 font-semibold">Åtgärder</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {scrapersLoading ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-4 text-center text-gray-400">
                      Laddar skrapare...
                    </td>
                  </tr>
                ) : scrapers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-4 text-center text-gray-400">
                      Inga skrapare konfigurerade
                    </td>
                  </tr>
                ) : (
                  scrapers.map((scraper) => (
                    <tr key={scraper.id} className="hover:bg-gray-700 transition-colors">
                      <td className="px-6 py-4 text-white font-medium">{scraper.name}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          {scraper.enabled ? (
                            <CheckCircle className="w-4 h-4 text-green-500" />
                          ) : (
                            <AlertCircle className="w-4 h-4 text-gray-500" />
                          )}
                          <span className="text-gray-300">
                            {scraper.enabled ? 'Aktiverad' : 'Inaktiverad'}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-400 text-xs">
                        {scraper.last_run
                          ? new Date(scraper.last_run).toLocaleString('sv-SE')
                          : 'Aldrig'}
                      </td>
                      <td className="px-6 py-4 text-center text-gray-300">
                        {scraper.document_count || 0}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            onClick={() => toggleScraper(scraper.id, scraper.enabled)}
                            className="p-2 hover:bg-gray-600 rounded transition-colors text-gray-400 hover:text-white"
                            title={scraper.enabled ? 'Inaktivera' : 'Aktivera'}
                          >
                            {scraper.enabled ? (
                              <Eye className="w-4 h-4" />
                            ) : (
                              <EyeOff className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => triggerScraper(scraper.id)}
                            className="p-2 hover:bg-gray-600 rounded transition-colors text-gray-400 hover:text-white"
                            title="Kör nu"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Logs Viewer Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-cyan-400" />
            <h2 className="text-2xl font-bold text-white">Loggar</h2>
          </div>
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              autoScroll
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {autoScroll ? 'Auto-scroll på' : 'Auto-scroll av'}
          </button>
        </div>
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <div className="bg-gray-700 border-b border-gray-600 px-4 py-3 flex items-center gap-2">
            <label className="text-sm font-medium text-gray-300">Filter:</label>
            <select
              value={logFilter}
              onChange={(e) => setLogFilter(e.target.value as any)}
              className="bg-gray-600 border border-gray-500 rounded px-3 py-1 text-white text-sm"
            >
              <option value="ALL">Alla</option>
              <option value="INFO">Info</option>
              <option value="WARNING">Varning</option>
              <option value="ERROR">Fel</option>
            </select>
          </div>
          <div className="max-h-96 overflow-y-auto font-mono text-xs bg-gray-900">
            {filteredLogs.length === 0 ? (
              <div className="px-4 py-3 text-gray-500">Inga loggposter</div>
            ) : (
              filteredLogs.map((log, idx) => (
                <div
                  key={idx}
                  className={`px-4 py-2 border-b border-gray-800 ${
                    log.level === 'ERROR'
                      ? 'bg-red-950 text-red-300'
                      : log.level === 'WARNING'
                        ? 'bg-yellow-950 text-yellow-300'
                        : 'text-gray-300'
                  }`}
                >
                  <span className="text-gray-500">{new Date(log.timestamp).toLocaleTimeString('sv-SE')}</span>
                  {' '}
                  <span className="font-semibold">[{log.level}]</span>
                  {' '}
                  <span className="text-blue-400">{log.source}:</span>
                  {' '}
                  {log.message}
                  {log.details && (
                    <div className="ml-4 mt-1 text-gray-500 text-xs">{log.details}</div>
                  )}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </section>

      {/* Database Actions Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-green-400" />
          <h2 className="text-2xl font-bold text-white">Databasåtgärder</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <button
            onClick={reindexDatabase}
            disabled={dbLoading}
            className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 border border-gray-700 rounded-lg p-4 transition-colors flex flex-col items-center gap-3 text-white"
          >
            <RotateCcw className="w-6 h-6" />
            <span className="text-sm font-medium">Omindexera</span>
          </button>
          <button
            onClick={clearCache}
            disabled={dbLoading}
            className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 border border-gray-700 rounded-lg p-4 transition-colors flex flex-col items-center gap-3 text-white"
          >
            <Trash2 className="w-6 h-6" />
            <span className="text-sm font-medium">Rensa cache</span>
          </button>
          <button
            onClick={backupDatabase}
            disabled={dbLoading}
            className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 border border-gray-700 rounded-lg p-4 transition-colors flex flex-col items-center gap-3 text-white"
          >
            <Download className="w-6 h-6" />
            <span className="text-sm font-medium">Backup nu</span>
          </button>
          <button
            onClick={exportStatistics}
            disabled={dbLoading}
            className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 border border-gray-700 rounded-lg p-4 transition-colors flex flex-col items-center gap-3 text-white"
          >
            <Upload className="w-6 h-6" />
            <span className="text-sm font-medium">Exportera stats</span>
          </button>
        </div>
        {dbMessage && (
          <div
            className={`rounded-lg p-4 flex items-center gap-3 ${
              dbMessage.type === 'success'
                ? 'bg-green-950 border border-green-700 text-green-300'
                : 'bg-red-950 border border-red-700 text-red-300'
            }`}
          >
            {dbMessage.type === 'success' ? (
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
            )}
            {dbMessage.message}
          </div>
        )}
      </section>

      {/* n8n Workflows Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-orange-400" />
          <h2 className="text-2xl font-bold text-white">n8n Arbetsflöden</h2>
        </div>
        <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-700 border-b border-gray-600">
                <tr>
                  <th className="px-6 py-3 text-left text-gray-300 font-semibold">Namn</th>
                  <th className="px-6 py-3 text-left text-gray-300 font-semibold">Status</th>
                  <th className="px-6 py-3 text-left text-gray-300 font-semibold">Senaste körning</th>
                  <th className="px-6 py-3 text-center text-gray-300 font-semibold">Idag</th>
                  <th className="px-6 py-3 text-center text-gray-300 font-semibold">Fel</th>
                  <th className="px-6 py-3 text-center text-gray-300 font-semibold">Åtgärd</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {workflowLoading ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-4 text-center text-gray-400">
                      Laddar arbetsflöden...
                    </td>
                  </tr>
                ) : workflows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-4 text-center text-gray-400">
                      Inga arbetsflöden funna
                    </td>
                  </tr>
                ) : (
                  workflows.map((workflow) => (
                    <tr key={workflow.id} className="hover:bg-gray-700 transition-colors">
                      <td className="px-6 py-4 text-white font-medium">{workflow.name}</td>
                      <td className="px-6 py-4">
                        <span
                          className={`px-3 py-1 rounded text-xs font-medium ${
                            workflow.active
                              ? 'bg-green-600 text-white'
                              : 'bg-gray-600 text-gray-300'
                          }`}
                        >
                          {workflow.active ? 'Aktiv' : 'Inaktiv'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-gray-400 text-xs">
                        {workflow.last_run_at
                          ? new Date(workflow.last_run_at).toLocaleString('sv-SE')
                          : 'Aldrig'}
                        {workflow.last_run_status && (
                          <div className="mt-1">
                            {workflow.last_run_status === 'success' ? (
                              <CheckCircle className="w-3 h-3 text-green-500 inline mr-1" />
                            ) : workflow.last_run_status === 'error' ? (
                              <AlertCircle className="w-3 h-3 text-red-500 inline mr-1" />
                            ) : (
                              <Activity className="w-3 h-3 text-yellow-500 inline mr-1" />
                            )}
                            <span className="text-xs">{workflow.last_run_status}</span>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center text-gray-300">
                        {workflow.execution_count_today}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={workflow.error_count > 0 ? 'text-red-400' : 'text-gray-400'}>
                          {workflow.error_count}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <button
                          onClick={() => toggleWorkflow(workflow.id, workflow.active)}
                          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                            workflow.active
                              ? 'bg-red-600 hover:bg-red-700 text-white'
                              : 'bg-green-600 hover:bg-green-700 text-white'
                          }`}
                        >
                          {workflow.active ? 'Inaktivera' : 'Aktivera'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
