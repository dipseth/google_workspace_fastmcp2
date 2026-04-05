import { useCandidatePoolAnalysis } from '../../hooks/useApi'

export default function CandidatePoolPanel() {
  const { data, isLoading, error } = useCandidatePoolAnalysis()

  if (isLoading) return <div className="text-gray-400 text-xs p-4">Analyzing candidate pools...</div>
  if (error) return <div className="text-red-400 text-xs p-4">Error: {error.message}</div>
  if (!data) return null

  const maxCount = Math.max(...data.pools.map((p) => p.count), 1)

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="text-xs text-gray-500 mb-3">
        {data.total_candidates} candidates across {data.n_pools} pools ({data.n_groups} groups)
      </div>

      {/* Pool bars */}
      <div className="space-y-2 mb-4">
        {data.pools.map((p) => {
          const barColor = p.avg_positive_rate > 0.3 ? 'bg-green-600' : p.avg_positive_rate > 0.1 ? 'bg-yellow-600' : 'bg-gray-600'
          return (
            <div key={p.pool} className="flex items-center gap-2">
              <div className="w-28 text-xs text-gray-300 text-right truncate font-mono">{p.pool}</div>
              <div className="flex-1 bg-gray-700 rounded h-5 overflow-hidden relative">
                <div
                  className={`${barColor} h-full rounded`}
                  style={{ width: `${(p.count / maxCount) * 100}%` }}
                />
                <div className="absolute inset-0 flex items-center px-2 text-xs text-gray-200">
                  {p.count} ({p.percentage}%)
                </div>
              </div>
              <div className="w-16 text-xs text-gray-500 text-right">
                +{(p.avg_positive_rate * 100).toFixed(0)}%
              </div>
            </div>
          )
        })}
      </div>

      {/* Detail table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-700">
              <th className="text-left p-1">Pool</th>
              <th className="text-right p-1">Count</th>
              <th className="text-right p-1">% of Total</th>
              <th className="text-right p-1">Pos. Rate</th>
            </tr>
          </thead>
          <tbody>
            {data.pools.map((p) => (
              <tr key={p.pool} className="border-b border-gray-800">
                <td className="p-1 text-gray-300 font-mono">{p.pool}</td>
                <td className="p-1 text-right text-gray-200 font-mono">{p.count}</td>
                <td className="p-1 text-right text-gray-400">{p.percentage}%</td>
                <td className="p-1 text-right text-gray-400">{(p.avg_positive_rate * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
