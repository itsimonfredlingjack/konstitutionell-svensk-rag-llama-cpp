import { CheckCircle, XCircle, Clock } from 'lucide-react';
import type { SystemStatus } from '../types';

interface StatusCardProps {
  status: SystemStatus;
}

export function StatusCard({ status }: StatusCardProps) {
  const isOnline = status.status === 'online';

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-white mb-2">{status.name}</h3>
          <div className="flex items-center gap-2 mb-3">
            {isOnline ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <XCircle className="w-5 h-5 text-red-500" />
            )}
            <span className={`text-sm font-medium ${isOnline ? 'text-green-500' : 'text-red-500'}`}>
              {isOnline ? 'Online' : 'Offline'}
            </span>
          </div>
          {status.latency !== undefined && (
            <div className="flex items-center gap-2 text-gray-400 text-sm">
              <Clock className="w-4 h-4" />
              <span>{status.latency}ms</span>
            </div>
          )}
        </div>
      </div>
      <div className="mt-4 pt-4 border-t border-gray-700">
        <p className="text-xs text-gray-500">
          Senast kontrollerad: {new Date(status.lastChecked).toLocaleString('sv-SE')}
        </p>
      </div>
    </div>
  );
}
