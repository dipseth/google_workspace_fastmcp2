import { useState } from 'react'
import { useSearchEvaluation } from '../../hooks/useApi'

export default function SearchEvalPanel() {
  const { data, isLoading, error } = useSearchEvaluation()
  const [showFailuresOnly, setShowFailuresOnly] = useState(false)
  const [sortBy, setSortBy] = useState<'rr' | 'name' | 'candidates'>('rr')

  if (isLoading) return <div className="text-gray-400 text-xs p-4">Evaluating search pipeline...</div>
  if (error) return <div className="text-red-400 text-xs p-4">Error: {error.message}</div>
  if (!data) return null

  const metrics = data.metrics
  let groups = [...data.per_group]

  if (showFailuresOnly) groups = groups.filter((g) => !g.top_is_correct)
  if (sortBy === 'rr') groups.sort((a, b) => a.reciprocal_rank - b.reciprocal_rank)
  else if (sortBy === 'candidates') groups.sort((a, b) => b.n_candidates - a.n_candidates)
  else groups.sort((a, b) => a.query_name.localeCompare(b.query_name))

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      {/* Aggregate metrics */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4">
        {['precision@1', 'precision@3', 'precision@5', 'recall@5', 'recall@10', 'mrr'].map((key) => (
          <div key={key} className="bg-gray-800 rounded p-2 text-center">
            <div className="text-xs text-gray-500 uppercase">{key}</div>
            <div className="text-lg font-mono text-gray-100">
              {metrics[key] !== undefined ? `${(metrics[key] * 100).toFixed(1)}%` : 'N/A'}
            </div>
          </div>
        ))}
      </div>

      <div className="text-xs text-gray-500 mb-3">
        {data.n_groups} validation groups evaluated
      </div>

      {/* Controls */}
      <div className="flex gap-3 mb-3 items-center text-xs">
        <label className="text-gray-400 flex items-center gap-1">
          <input
            type="checkbox"
            checked={showFailuresOnly}
            onChange={() => setShowFailuresOnly(!showFailuresOnly)}
            className="accent-red-500"
          />
          Failures only
        </label>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className="bg-gray-800 text-gray-300 rounded px-2 py-1 text-xs border border-gray-700"
        >
          <option value="rr">Sort by RR (ascending)</option>
          <option value="name">Sort by name</option>
          <option value="candidates">Sort by # candidates</option>
        </select>
      </div>

      {/* Per-group table */}
      <div className="overflow-x-auto max-h-80 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="text-gray-500 border-b border-gray-700">
              <th className="text-left p-1">Query</th>
              <th className="text-right p-1">#Cands</th>
              <th className="text-right p-1">#Pos</th>
              <th className="text-right p-1">RR</th>
              <th className="text-center p-1">Top OK?</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g, i) => (
              <tr
                key={i}
                className={`border-b border-gray-800 ${!g.top_is_correct ? 'bg-red-950/30' : ''}`}
              >
                <td className="p-1 text-gray-300 truncate max-w-[200px]">{g.query_name}</td>
                <td className="p-1 text-right text-gray-400">{g.n_candidates}</td>
                <td className="p-1 text-right text-gray-400">{g.n_positive}</td>
                <td className="p-1 text-right font-mono text-gray-200">{g.reciprocal_rank.toFixed(3)}</td>
                <td className="p-1 text-center">
                  {g.top_is_correct ? (
                    <span className="text-green-400">Y</span>
                  ) : (
                    <span className="text-red-400">N</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
