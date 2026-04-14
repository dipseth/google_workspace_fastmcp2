import { useUnifiedModelInfo, useUnifiedHaltAnalysis } from '../../hooks/useApi'

const COMPONENT_COLORS: Record<string, string> = {
  structural_enc: '#3b82f6',
  content_enc: '#f59e0b',
  backbone: '#8b5cf6',
  form_head: '#22c55e',
  content_head: '#f43f5e',
  pool_head: '#06b6d4',
  halt_head: '#f97316',
}

function Stat({ label, value, color = 'text-gray-200', sub }: { label: string; value: string | number; color?: string; sub?: string }) {
  return (
    <div className="bg-gray-800 rounded p-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-lg font-mono ${color}`}>{typeof value === 'number' ? (value < 2 ? (value * 100).toFixed(1) + '%' : value.toLocaleString()) : value}</div>
      {sub && <div className="text-xs text-gray-600">{sub}</div>}
    </div>
  )
}

function ComparisonBar({ label, unified, standalone, color }: { label: string; unified: number; standalone: number; color: string }) {
  const delta = unified - standalone
  const deltaStr = delta > 0 ? `+${(delta * 100).toFixed(1)}%` : `${(delta * 100).toFixed(1)}%`
  return (
    <div className="flex items-center gap-2 text-xs mb-1">
      <span className="w-24 text-right text-gray-400">{label}</span>
      <div className="flex-1 flex gap-1">
        <div className="flex-1 bg-gray-800 rounded h-5 overflow-hidden relative">
          <div className="absolute inset-0 flex items-center px-1 text-gray-500 text-[10px]">standalone</div>
          <div className="h-full rounded" style={{ width: `${standalone * 100}%`, backgroundColor: color, opacity: 0.3 }} />
        </div>
        <div className="flex-1 bg-gray-800 rounded h-5 overflow-hidden relative">
          <div className="absolute inset-0 flex items-center px-1 text-gray-300 text-[10px]">unified</div>
          <div className="h-full rounded" style={{ width: `${unified * 100}%`, backgroundColor: color, opacity: 0.8 }} />
        </div>
      </div>
      <span className={`font-mono w-16 text-right ${delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>{deltaStr}</span>
    </div>
  )
}

export default function UnifiedTRNDiag() {
  const { data: info, isLoading: infoLoading, error: infoError } = useUnifiedModelInfo()
  const { data: halt, isLoading: haltLoading, error: haltError } = useUnifiedHaltAnalysis()

  if (infoLoading) return <div className="text-gray-500 p-4">Loading UnifiedTRN diagnostics...</div>
  if (infoError) return <div className="text-red-400 p-4">Error: {infoError.message}</div>
  if (!info || 'error' in info) return <div className="text-gray-500 p-4">No UnifiedTRN checkpoint found.</div>

  const comp = info.comparison

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-1">UnifiedTRN — Model Info & Comparison</h3>
        <p className="text-xs text-gray-500 mb-3">
          Single 28.7K-param network replacing DualHeadScorerMW + SlotAffinityNet.
          4 heads: form (ranking), content (ranking), pool (classification), halt (convergence).
        </p>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Stat label="Form Top-1" value={info.val_form_top1} color="text-green-400" />
        <Stat label="Content Top-1" value={info.val_content_top1} color="text-rose-400" />
        <Stat label="Pool Acc" value={info.val_pool_acc} color="text-cyan-400" />
        <Stat label="Halt Acc" value={info.val_halt_acc} color="text-orange-400" />
        <Stat label="Epoch" value={info.epoch} />
        <Stat label="Parameters" value={info.total_params} sub={`vs ${comp.combined_standalone_params.toLocaleString()} standalone`} />
      </div>

      {/* Comparison with standalone models */}
      <div>
        <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Unified vs Standalone</h4>
        <ComparisonBar label="Form Top-1" unified={info.val_form_top1} standalone={comp.dual_head.form_top1} color="#22c55e" />
        <ComparisonBar label="Content Top-1" unified={info.val_content_top1} standalone={comp.dual_head.content_top1} color="#f43f5e" />
        <ComparisonBar label="Pool Acc" unified={info.val_pool_acc} standalone={comp.slot_affinity.pool_acc} color="#06b6d4" />
      </div>

      {/* Component param breakdown */}
      <div>
        <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Parameter Breakdown</h4>
        <div className="space-y-1">
          {Object.entries(info.component_params).map(([name, count]) => {
            const pct = (count as number) / info.total_params
            return (
              <div key={name} className="flex items-center gap-2 text-xs">
                <span className="w-28 text-right text-gray-400">{name}</span>
                <div className="flex-1 bg-gray-800 rounded h-4 overflow-hidden">
                  <div className="h-full rounded" style={{
                    width: `${pct * 100}%`,
                    backgroundColor: COMPONENT_COLORS[name] || '#6b7280',
                  }} />
                </div>
                <span className="font-mono w-20 text-right text-gray-400">{(count as number).toLocaleString()} ({(pct * 100).toFixed(1)}%)</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Loss weights */}
      <div>
        <h4 className="text-xs text-gray-400 mb-1 uppercase tracking-wider">Loss Weights</h4>
        <div className="flex gap-3 text-xs">
          {Object.entries(info.loss_weights).map(([k, v]) => (
            <span key={k} className="text-gray-500">
              {k.replace('w_', '')}: <span className="text-gray-300 font-mono">{v as number}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Halt head analysis */}
      {halt && !('error' in halt) && !haltLoading && (
        <div>
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Halt Head Analysis</h4>
          <p className="text-xs text-gray-500 mb-2">
            When the model is correct, halt_prob should be high (green). When wrong, low (red).
          </p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <Stat label="Mean Halt (Correct)" value={halt.mean_halt_correct} color="text-green-400" />
            <Stat label="Mean Halt (Wrong)" value={halt.mean_halt_wrong} color="text-red-400" />
            <Stat label="Correct Groups" value={`${halt.n_correct}/${halt.n_groups}`} />
            <Stat label="Separation" value={(halt.mean_halt_correct - halt.mean_halt_wrong).toFixed(3)} color={halt.mean_halt_correct > halt.mean_halt_wrong ? 'text-green-400' : 'text-red-400'} />
          </div>

          {/* Halt probability histogram */}
          <div className="flex gap-0.5 items-end h-24 mb-2">
            {halt.correct_histogram.map((count, i) => {
              const wrongCount = halt.wrong_histogram[i] || 0
              const maxBin = Math.max(1, ...halt.correct_histogram, ...halt.wrong_histogram)
              const correctH = (count / maxBin) * 100
              const wrongH = (wrongCount / maxBin) * 100
              return (
                <div key={i} className="flex-1 flex flex-col items-center justify-end gap-0" title={`${halt.bin_edges[i]}-${halt.bin_edges[i + 1]}: ${count} correct, ${wrongCount} wrong`}>
                  <div className="w-full bg-green-500/60 rounded-t" style={{ height: `${correctH}%` }} />
                  <div className="w-full bg-red-500/60 rounded-b" style={{ height: `${wrongH}%` }} />
                </div>
              )
            })}
          </div>
          <div className="flex justify-between text-[10px] text-gray-600 mb-3">
            <span>0.0</span><span>halt_prob →</span><span>1.0</span>
          </div>

          {/* Threshold sweep table */}
          <h4 className="text-xs text-gray-400 mb-1 uppercase tracking-wider">Threshold Sweep</h4>
          <div className="max-h-40 overflow-y-auto">
            <table className="text-xs w-full">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left p-1">Threshold</th>
                  <th className="text-right p-1">Precision</th>
                  <th className="text-right p-1">Recall</th>
                  <th className="text-right p-1">Accuracy</th>
                  <th className="text-right p-1">Would Halt</th>
                </tr>
              </thead>
              <tbody>
                {halt.threshold_sweep.filter((_, i) => i % 2 === 0).map((t) => (
                  <tr key={t.threshold} className={`border-b border-gray-800/50 ${t.threshold === 0.7 ? 'bg-blue-900/20' : ''}`}>
                    <td className="p-1 font-mono">{t.threshold.toFixed(2)} {t.threshold === 0.7 ? '←' : ''}</td>
                    <td className="p-1 text-right font-mono">{(t.precision * 100).toFixed(1)}%</td>
                    <td className="p-1 text-right font-mono">{(t.recall * 100).toFixed(1)}%</td>
                    <td className="p-1 text-right font-mono">{(t.accuracy * 100).toFixed(1)}%</td>
                    <td className="p-1 text-right font-mono text-gray-500">{t.would_halt}/{halt.n_groups}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {haltLoading && <div className="text-gray-500 text-xs">Loading halt analysis...</div>}
      {haltError && <div className="text-red-400 text-xs">Halt analysis error: {haltError.message}</div>}
    </div>
  )
}
