import { useTrainingLoss } from '../../hooks/useApi'

export default function TrainingLossPanel() {
  const { data, isLoading, error } = useTrainingLoss()

  if (isLoading) return <div className="text-gray-400 text-xs p-4">Loading training loss curves...</div>
  if (error) return <div className="text-red-400 text-xs p-4">Error: {error.message}</div>
  if (!data) return null

  const models = [
    { key: 'dual_head', label: 'DualHead MW', color: 'blue', data: data.dual_head },
    { key: 'unified_trn', label: 'UnifiedTRN', color: 'purple', data: data.unified_trn },
  ] as const

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {models.map(({ key, label, color, data: mdata }) => (
          <div key={key} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className={`text-sm font-medium mb-3 text-${color}-400`}>{label}</div>
            {!mdata?.available ? (
              <div className="text-gray-500 text-xs">Loss curves not available in checkpoint</div>
            ) : (
              <div>
                <div className="text-xs text-gray-500 mb-2">
                  {mdata.n_epochs} epochs · best @ epoch {mdata.best_epoch}
                </div>
                {/* Loss chart - simple ASCII-style bars */}
                <div className="mb-3">
                  <div className="text-xs text-gray-400 mb-1">Loss (train / val)</div>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {mdata.train_losses.map((tl, i) => {
                      const vl = mdata.val_losses[i] ?? tl
                      const maxLoss = Math.max(...mdata.train_losses, ...mdata.val_losses, 0.01)
                      return (
                        <div key={i} className="flex items-center gap-1 text-xs">
                          <div className="w-6 text-gray-600 text-right">{i + 1}</div>
                          <div className="flex-1 flex gap-0.5">
                            <div
                              className={`bg-${color}-600 h-2 rounded`}
                              style={{ width: `${(tl / maxLoss) * 100}%` }}
                              title={`Train: ${tl.toFixed(4)}`}
                            />
                          </div>
                          <div className="flex-1 flex gap-0.5">
                            <div
                              className={`bg-${color}-400 h-2 rounded opacity-60`}
                              style={{ width: `${(vl / maxLoss) * 100}%` }}
                              title={`Val: ${vl.toFixed(4)}`}
                            />
                          </div>
                          <div className="w-20 text-gray-500 text-right font-mono">
                            {tl.toFixed(3)} / {vl.toFixed(3)}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
                {/* Accuracy chart */}
                {mdata.train_accs.length > 0 && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Accuracy (train / val)</div>
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {mdata.train_accs.map((ta, i) => {
                        const va = mdata.val_accs[i] ?? ta
                        return (
                          <div key={i} className="flex items-center gap-1 text-xs">
                            <div className="w-6 text-gray-600 text-right">{i + 1}</div>
                            <div className="flex-1 bg-gray-700 rounded h-3 overflow-hidden">
                              <div
                                className="bg-green-600 h-full rounded"
                                style={{ width: `${ta * 100}%` }}
                                title={`Train: ${(ta * 100).toFixed(1)}%`}
                              />
                            </div>
                            <div className="flex-1 bg-gray-700 rounded h-3 overflow-hidden">
                              <div
                                className="bg-green-400 h-full rounded opacity-70"
                                style={{ width: `${va * 100}%` }}
                                title={`Val: ${(va * 100).toFixed(1)}%`}
                              />
                            </div>
                            <div className="w-24 text-gray-500 text-right font-mono">
                              {(ta * 100).toFixed(1)} / {(va * 100).toFixed(1)}%
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
