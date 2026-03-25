import { useState } from 'react'
import { useContentAccuracyDetail } from '../../hooks/useApi'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export default function ContentAccuracyDetail() {
  const { data, isLoading, error } = useContentAccuracyDetail()
  const [showFailuresOnly, setShowFailuresOnly] = useState(false)

  if (isLoading) return <div className="text-gray-500 p-4">Computing content accuracy detail...</div>
  if (error) return <div className="text-red-400 p-4">Error: {error.message}</div>
  if (!data) return null

  // Build histogram chart data
  const maxRank = Math.max(data.form_rank_histogram.length, data.content_rank_histogram.length)
  const histData = Array.from({ length: Math.min(maxRank, 10) }, (_, i) => ({
    rank: `Rank ${i + 1}`,
    form: data.form_rank_histogram[i] || 0,
    content: data.content_rank_histogram[i] || 0,
  }))

  // Filter groups for table
  const filteredGroups = showFailuresOnly
    ? data.groups.filter((g) => (g.content_rank !== null && g.content_rank > 1) || g.form_rank > 1)
    : data.groups

  // Sort by content_rank descending (worst first)
  const sortedGroups = [...filteredGroups].sort((a, b) => {
    const ar = a.content_rank ?? 0
    const br = b.content_rank ?? 0
    return br - ar
  })

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">Content Accuracy Detail</h3>
      <p className="text-xs text-gray-500 mb-3">
        Per-head rank distribution and per-group breakdown.
      </p>

      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Form Top-1</div>
          <div className="text-lg font-mono text-green-400">{(data.form_top1 * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Content Top-1</div>
          <div className="text-lg font-mono text-rose-400">{(data.content_top1 * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Form MRR</div>
          <div className="text-lg font-mono text-green-400">{data.form_mrr.toFixed(3)}</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Content MRR</div>
          <div className="text-lg font-mono text-rose-400">{data.content_mrr.toFixed(3)}</div>
        </div>
      </div>

      <div className="mb-4">
        <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Rank Distribution</h4>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={histData} margin={{ left: 20 }}>
            <XAxis dataKey="rank" tick={{ fill: '#9ca3af', fontSize: 10 }} />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }} />
            <Legend />
            <Bar dataKey="form" fill="#22c55e" name="Form Head" />
            <Bar dataKey="content" fill="#f43f5e" name="Content Head" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <div className="flex items-center gap-3 mb-2">
          <label className="text-xs text-gray-400 flex items-center gap-1">
            <input
              type="checkbox"
              checked={showFailuresOnly}
              onChange={(e) => setShowFailuresOnly(e.target.checked)}
              className="rounded"
            />
            Show failures only
          </label>
          <span className="text-xs text-gray-500">{sortedGroups.length} groups shown</span>
        </div>
        <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-900">
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left p-1">#</th>
                <th className="text-left p-1">Group</th>
                <th className="text-center p-1">Cands</th>
                <th className="text-center p-1">Form Rank</th>
                <th className="text-center p-1">Content Rank</th>
                <th className="text-center p-1">Form Margin</th>
                <th className="text-center p-1">Content Margin</th>
                <th className="text-center p-1">Agreement</th>
              </tr>
            </thead>
            <tbody>
              {sortedGroups.slice(0, 100).map((g, idx) => {
                const formOk = g.form_rank === 1
                const contentOk = g.content_rank === 1
                const agree = formOk === contentOk
                return (
                  <tr key={g.name} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="p-1 text-gray-600">{idx + 1}</td>
                    <td className="p-1 text-gray-300 font-mono">{g.name}</td>
                    <td className="p-1 text-center text-gray-400">{g.n_candidates}</td>
                    <td className={`p-1 text-center font-mono ${formOk ? 'text-green-400' : 'text-red-400'}`}>
                      {g.form_rank}
                    </td>
                    <td className={`p-1 text-center font-mono ${g.content_rank === null ? 'text-gray-600' : contentOk ? 'text-green-400' : 'text-red-400'}`}>
                      {g.content_rank ?? '-'}
                    </td>
                    <td className={`p-1 text-center font-mono ${(g.form_margin ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {g.form_margin?.toFixed(3) ?? '-'}
                    </td>
                    <td className={`p-1 text-center font-mono ${(g.content_margin ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {g.content_margin?.toFixed(3) ?? '-'}
                    </td>
                    <td className="p-1 text-center">
                      {g.content_rank === null ? '-' : agree ? <span className="text-green-400">Y</span> : <span className="text-yellow-400">N</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
