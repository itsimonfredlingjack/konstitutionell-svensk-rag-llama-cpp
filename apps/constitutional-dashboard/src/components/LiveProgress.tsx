import { useWebSocket } from '../hooks/useWebSocket';
import type { HarvestProgress } from '../types';
import { Activity, AlertCircle } from 'lucide-react';

const WS_URL = typeof window !== 'undefined'
  ? `ws://${window.location.hostname}:8000/ws/harvest`
  : 'ws://localhost:8000/ws/harvest';

export function LiveProgress() {
  const { data, connected, error } = useWebSocket<HarvestProgress>(WS_URL);

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-6 h-6" />
          Pågående Harvest
        </h2>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
          <span className="text-xs text-gray-400">
            {connected ? 'Ansluten' : 'Frånkopplad'}
          </span>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/20 border border-red-700 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-sm text-red-400">{error}</span>
        </div>
      )}

      {data ? (
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-400">Källa</span>
              <span className="text-white font-medium">{data.currentSource}</span>
            </div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-400">Bearbetade dokument</span>
              <span className="text-white font-medium">
                {data.documentsProcessed.toLocaleString('sv-SE')}
                {data.totalDocuments && ` / ${data.totalDocuments.toLocaleString('sv-SE')}`}
              </span>
            </div>
          </div>

          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-400">Framsteg</span>
              <span className="text-white font-medium">{data.progress.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-3 overflow-hidden">
              <div
                className="bg-blue-500 h-full transition-all duration-500 rounded-full"
                style={{ width: `${Math.min(data.progress, 100)}%` }}
              />
            </div>
          </div>

          {data.eta && (
            <div className="pt-3 border-t border-gray-700">
              <span className="text-sm text-gray-400">Uppskattad tid kvar: </span>
              <span className="text-sm text-white font-medium">{data.eta}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          {connected ? 'Väntar på data...' : 'Ansluter till WebSocket...'}
        </div>
      )}
    </div>
  );
}
