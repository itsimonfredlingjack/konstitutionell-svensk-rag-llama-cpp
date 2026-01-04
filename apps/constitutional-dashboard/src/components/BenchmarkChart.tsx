import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { BenchmarkData } from '../types';
import { TrendingUp } from 'lucide-react';

// Mock data for now - replace with real API when available
const mockData: BenchmarkData[] = [
  { date: '2024-12-10', queriesPerDay: 120, avgLatency: 250, accuracy: 92 },
  { date: '2024-12-11', queriesPerDay: 145, avgLatency: 230, accuracy: 94 },
  { date: '2024-12-12', queriesPerDay: 180, avgLatency: 210, accuracy: 93 },
  { date: '2024-12-13', queriesPerDay: 210, avgLatency: 195, accuracy: 95 },
  { date: '2024-12-14', queriesPerDay: 195, avgLatency: 200, accuracy: 94 },
  { date: '2024-12-15', queriesPerDay: 230, avgLatency: 185, accuracy: 96 },
  { date: '2024-12-16', queriesPerDay: 250, avgLatency: 175, accuracy: 95 },
];

export function BenchmarkChart() {
  const data = mockData;

  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
        <TrendingUp className="w-6 h-6" />
        Prestandahistorik (7 dagar)
      </h2>

      {data && data.length > 0 && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="date"
              stroke="#9CA3AF"
              tick={{ fill: '#9CA3AF' }}
              tickFormatter={(value) => new Date(value).toLocaleDateString('sv-SE', { month: 'short', day: 'numeric' })}
            />
            <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: '1px solid #374151',
                borderRadius: '0.5rem',
                color: '#fff',
              }}
              labelFormatter={(value) => new Date(value).toLocaleDateString('sv-SE')}
            />
            <Legend wrapperStyle={{ color: '#9CA3AF' }} />
            <Line
              type="monotone"
              dataKey="queriesPerDay"
              name="Sökningar/dag"
              stroke="#3B82F6"
              strokeWidth={2}
              dot={{ fill: '#3B82F6' }}
            />
            <Line
              type="monotone"
              dataKey="avgLatency"
              name="Snitt-latens (ms)"
              stroke="#10B981"
              strokeWidth={2}
              dot={{ fill: '#10B981' }}
            />
            <Line
              type="monotone"
              dataKey="accuracy"
              name="Träffsäkerhet (%)"
              stroke="#F59E0B"
              strokeWidth={2}
              dot={{ fill: '#F59E0B' }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {data && data.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          Ingen benchmarkdata tillgänglig
        </div>
      )}
    </div>
  );
}
