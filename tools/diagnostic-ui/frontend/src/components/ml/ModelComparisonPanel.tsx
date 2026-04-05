import { useModelComparison } from '../../hooks/useApi'

export default function ModelComparisonPanel() {
  const { data, isLoading, error } = useModelComparison()

  if (isLoading) return <div className="text-gray-400 text-xs p-4">Loading model comparison...</div>
  if (error) return <div className="text-red-400 text-xs p-4">Error: {error.message}</div>
  if (!data) return null

  const models = [
    { key: 'dual_head', label: 'DualHead MW', color: 'blue', data: data.dual_head },
    { key: 'unified_trn', label: 'UnifiedTRN', color: 'purple', data: data.unified_trn },
  ]

  const metricKeys = ['accuracy', 'mrr'] as const
  const meta = data.eval_meta

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      {/* Shared eval set banner */}
      {meta && (
        <div className="bg-amber-950/30 border border-amber-800/40 rounded-lg px-3 py-2 mb-4 text-xs">
          <div className="text-amber-400/80 font-medium mb-1">Both models evaluated on same data</div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-400">
            <span>
              <span className="text-gray-500">Eval set:</span>{' '}
              <span className="text-gray-200 font-mono">{meta.data_file}</span>
            </span>
            <span>
              <span className="text-gray-500">Features:</span> v{meta.feature_version}
            </span>
            <span>
              <span className="text-gray-500">Split:</span> {meta.split_ratio} (seed={meta.split_seed})
            </span>
            <span>
              <span className="text-gray-500">Candidates:</span>{' '}
              {meta.total_candidates.toLocaleString()} ({meta.total_positive} pos,{' '}
              <span className={meta.positive_ratio > 0.3 ? 'text-yellow-400' : 'text-gray-300'}>
                {(meta.positive_ratio * 100).toFixed(1)}%
              </span>)
            </span>
          </div>
        </div>
      )}

      {/* Side-by-side cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {models.map(({ key, label, color, data: mdata }) => (
          <div key={key} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className={`text-sm font-medium mb-3 text-${color}-400`}>{label}</div>
            {mdata?.error ? (
              <div className="text-red-400 text-xs">{mdata.error}</div>
            ) : mdata ? (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div className="text-center">
                    <div className="text-xs text-gray-500">Accuracy</div>
                    <div className="text-xl font-mono text-gray-100">
                      {(mdata.accuracy * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-gray-500">MRR</div>
                    <div className="text-xl font-mono text-gray-100">
                      {(mdata.mrr * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
                <div className="text-xs text-gray-500 space-y-1 mt-2">
                  <div>Groups: {mdata.n_groups}</div>
                  {mdata.model_type && <div>Type: {mdata.model_type}</div>}
                  {mdata.feature_version !== undefined && <div>Features: v{mdata.feature_version}</div>}
                  {mdata.total_params && <div>Params: {mdata.total_params.toLocaleString()}</div>}
                  {mdata.domain && (
                    <div>
                      Domain: <span className="text-cyan-400">{mdata.domain}</span>
                    </div>
                  )}
                  {mdata.checkpoint_file && (
                    <div>
                      Checkpoint: <span className="text-gray-300 font-mono">{mdata.checkpoint_file}</span>
                    </div>
                  )}
                  {mdata.data_version && mdata.data_version !== 'unknown' && (
                    <div>
                      Trained on: <span className="text-gray-300 font-mono">{mdata.data_version}</span>
                    </div>
                  )}
                  {mdata.pool_acc !== undefined && <div>Pool acc: {(mdata.pool_acc * 100).toFixed(1)}%</div>}
                  {mdata.halt_acc !== undefined && mdata.halt_acc > 0 && (
                    <div>Halt acc: {(mdata.halt_acc * 100).toFixed(1)}%</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-gray-500 text-xs">Not available</div>
            )}
          </div>
        ))}
      </div>

      {/* Bar comparison */}
      {data.dual_head && data.unified_trn && !data.dual_head.error && !data.unified_trn.error && (
        <div className="bg-gray-800 rounded p-3">
          <div className="text-xs text-gray-500 mb-2">Metric Comparison</div>
          {metricKeys.map((metric) => {
            const dh = data.dual_head?.[metric] ?? 0
            const uni = data.unified_trn?.[metric] ?? 0
            const max = Math.max(dh, uni, 0.01)
            return (
              <div key={metric} className="mb-2">
                <div className="text-xs text-gray-400 mb-1 capitalize">{metric}</div>
                <div className="flex gap-1 items-center">
                  <div className="w-16 text-xs text-gray-500 text-right">DualHead</div>
                  <div className="flex-1 bg-gray-700 rounded h-4 overflow-hidden">
                    <div
                      className="bg-blue-600 h-full rounded"
                      style={{ width: `${(dh / max) * 100}%` }}
                    />
                  </div>
                  <div className="w-14 text-xs font-mono text-gray-300 text-right">
                    {(dh * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="flex gap-1 items-center mt-1">
                  <div className="w-16 text-xs text-gray-500 text-right">Unified</div>
                  <div className="flex-1 bg-gray-700 rounded h-4 overflow-hidden">
                    <div
                      className="bg-purple-600 h-full rounded"
                      style={{ width: `${(uni / max) * 100}%` }}
                    />
                  </div>
                  <div className="w-14 text-xs font-mono text-gray-300 text-right">
                    {(uni * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
