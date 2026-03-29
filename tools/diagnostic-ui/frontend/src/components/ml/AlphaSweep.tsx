import { useAlphaSweep } from '../../hooks/useApi'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from 'recharts'

export default function AlphaSweep() {
  const { data, isLoading, error } = useAlphaSweep()

  if (isLoading) return <div className="text-gray-500 p-4">Computing alpha sweep...</div>
  if (error) return <div className="text-red-400 p-4">Error: {error.message}</div>
  if (!data) return null
  if ('error' in data) return <div className="text-yellow-400 p-4">{(data as { error: string }).error}</div>

  const chartData = data.alphas.map((alpha, i) => ({
    alpha,
    combined: data.combined_accuracy[i],
  }))

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">Alpha Sensitivity Sweep</h3>
      <p className="text-xs text-gray-500 mb-3">
        Combined accuracy at different form/content blend weights.
        alpha=1.0 is pure form, alpha=0.0 is pure content.
      </p>

      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Current Alpha</div>
          <div className="text-lg font-mono text-blue-400">{data.current_alpha}</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Optimal Alpha</div>
          <div className="text-lg font-mono text-green-400">{data.optimal_alpha}</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Form-Only Acc</div>
          <div className="text-lg font-mono text-green-400">{(data.form_accuracy * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Content-Only Acc</div>
          <div className="text-lg font-mono text-rose-400">{(data.content_accuracy * 100).toFixed(1)}%</div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ left: 20, right: 20, top: 10, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="alpha"
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            label={{ value: 'Alpha (form weight)', position: 'insideBottom', offset: -5, fill: '#9ca3af', fontSize: 11 }}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            domain={[0, 1]}
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
            formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, 'Combined Accuracy']}
            labelFormatter={(l: number) => `alpha=${l}`}
          />
          <ReferenceLine
            y={data.form_accuracy}
            stroke="#22c55e"
            strokeDasharray="5 5"
            label={{ value: 'Form only', fill: '#22c55e', fontSize: 10, position: 'right' }}
          />
          <ReferenceLine
            y={data.content_accuracy}
            stroke="#f43f5e"
            strokeDasharray="5 5"
            label={{ value: 'Content only', fill: '#f43f5e', fontSize: 10, position: 'right' }}
          />
          <ReferenceLine
            x={data.current_alpha}
            stroke="#60a5fa"
            strokeDasharray="3 3"
            label={{ value: 'Current', fill: '#60a5fa', fontSize: 10, position: 'top' }}
          />
          {data.optimal_alpha !== data.current_alpha && (
            <ReferenceLine
              x={data.optimal_alpha}
              stroke="#fbbf24"
              strokeDasharray="3 3"
              label={{ value: 'Optimal', fill: '#fbbf24', fontSize: 10, position: 'top' }}
            />
          )}
          <Line type="monotone" dataKey="combined" stroke="#818cf8" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
