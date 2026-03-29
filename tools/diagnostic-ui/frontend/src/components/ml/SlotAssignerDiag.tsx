import { useSlotAssignerInfo, useSlotAssignerConfusion } from '../../hooks/useApi'
import type { SlotAssignerConfusion } from '../../types'

const POOL_COLORS: Record<string, string> = {
  buttons: 'text-blue-400',
  content_texts: 'text-gray-300',
  grid_items: 'text-amber-400',
  chips: 'text-violet-400',
  carousel_cards: 'text-cyan-400',
}

const POOL_BG: Record<string, string> = {
  buttons: 'bg-blue-500/20',
  content_texts: 'bg-gray-500/20',
  grid_items: 'bg-amber-500/20',
  chips: 'bg-violet-500/20',
  carousel_cards: 'bg-cyan-500/20',
}

function Stat({ label, value, color = 'text-gray-200' }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-gray-800 rounded p-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-lg font-mono ${color}`}>{typeof value === 'number' ? value.toFixed(value >= 1 ? 0 : 4) : value}</div>
    </div>
  )
}

function ConfusionMatrix({ data }: { data: SlotAssignerConfusion }) {
  const { labels, matrix } = data
  const maxVal = Math.max(1, ...matrix.flat())

  return (
    <div>
      <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Pool Confusion Matrix</h4>
      <p className="text-xs text-gray-500 mb-2">
        Accuracy: <span className="font-mono text-green-400">{(data.accuracy * 100).toFixed(1)}%</span>
        {' '}({data.n_items} unique items)
      </p>
      <div className="overflow-x-auto">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="p-1 text-gray-500 text-right">Pred \ Exp</th>
              {labels.map((l) => (
                <th key={l} className={`p-1 text-center min-w-[70px] truncate max-w-[90px] ${POOL_COLORS[l] || 'text-gray-400'}`} title={l}>
                  {l.replace('_', '\u200B_')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((rowLabel, i) => (
              <tr key={rowLabel}>
                <td className={`p-1 text-right truncate max-w-[90px] ${POOL_COLORS[rowLabel] || 'text-gray-400'}`} title={rowLabel}>
                  {rowLabel.replace('_', '\u200B_')}
                </td>
                {matrix[i].map((val, j) => {
                  const isDiag = i === j
                  const intensity = val / maxVal
                  const bg = isDiag
                    ? `rgba(34, 197, 94, ${Math.max(0.1, intensity * 0.8)})`
                    : val > 0
                      ? `rgba(239, 68, 68, ${Math.max(0.15, intensity * 0.7)})`
                      : 'transparent'
                  return (
                    <td
                      key={j}
                      className="p-1 text-center font-mono border border-gray-800"
                      style={{ backgroundColor: bg }}
                      title={`Predicted: ${rowLabel}, Expected: ${labels[j]}, Count: ${val}`}
                    >
                      {val > 0 ? val : ''}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MisclassifiedTable({ items }: { items: SlotAssignerConfusion['misclassified'] }) {
  if (items.length === 0) return <p className="text-xs text-gray-500 mt-2">No misclassifications!</p>

  return (
    <div className="mt-4">
      <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">
        Misclassified Items ({items.length})
      </h4>
      <div className="max-h-60 overflow-y-auto">
        <table className="text-xs w-full">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left p-1">Content</th>
              <th className="text-left p-1">Expected</th>
              <th className="text-left p-1">Predicted</th>
              <th className="text-left p-1">Source</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="p-1 font-mono text-gray-300 max-w-[200px] truncate" title={item.content_text}>
                  {item.content_text}
                </td>
                <td className={`p-1 ${POOL_COLORS[item.expected] || 'text-gray-400'}`}>
                  {item.expected}
                </td>
                <td className={`p-1 ${POOL_COLORS[item.predicted] || 'text-gray-400'}`}>
                  {item.predicted}
                </td>
                <td className="p-1 text-gray-500">{item.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function SlotAssignerDiag() {
  const { data: info, isLoading: infoLoading, error: infoError } = useSlotAssignerInfo()
  const { data: confusion, isLoading: confLoading, error: confError } = useSlotAssignerConfusion()

  const isLoading = infoLoading || confLoading
  const error = infoError || confError

  if (isLoading) return <div className="text-gray-500 p-4">Loading slot assigner diagnostics...</div>
  if (error) return <div className="text-red-400 p-4">Error: {error.message}</div>
  if (!info) return <div className="text-gray-500 p-4">No slot assigner checkpoint found.</div>

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">Slot Assigner — Model Info & Accuracy</h3>
      <p className="text-xs text-gray-500 mb-3">
        SlotAffinityNet: direct content→pool classifier. Routes supply_map items to the correct pool before card building.
      </p>

      {/* Model stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <Stat label="Val Accuracy" value={`${(info.val_accuracy * 100).toFixed(1)}%`} color="text-green-400" />
        <Stat label="Train Accuracy" value={`${(info.train_acc * 100).toFixed(1)}%`} color="text-blue-400" />
        <Stat label="Epoch" value={info.epoch} />
        <Stat label="Parameters" value={info.n_params.toLocaleString()} />
        <Stat label="Architecture" value={`${info.content_dim}→${info.hidden_dim}→${info.n_pools}`} />
      </div>

      {/* Per-pool accuracy bars */}
      <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Per-Pool Validation Accuracy</h4>
      <div className="space-y-1 mb-4">
        {Object.entries(info.val_per_pool).map(([pool, acc]) => (
          <div key={pool} className="flex items-center gap-2 text-xs">
            <span className={`w-28 text-right ${POOL_COLORS[pool] || 'text-gray-400'}`}>{pool}</span>
            <div className="flex-1 bg-gray-800 rounded h-4 overflow-hidden">
              <div
                className={`h-full rounded ${POOL_BG[pool] || 'bg-gray-600'}`}
                style={{
                  width: `${(acc as number) * 100}%`,
                  backgroundColor: (acc as number) >= 0.8 ? '#22c55e80' : (acc as number) >= 0.5 ? '#eab30880' : '#ef444480',
                }}
              />
            </div>
            <span className="font-mono w-14 text-right">{((acc as number) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>

      {/* Data stats */}
      {info.data_stats && (
        <div className="mb-4">
          <h4 className="text-xs text-gray-400 mb-1 uppercase tracking-wider">Training Data</h4>
          <p className="text-xs text-gray-500">
            {info.data_stats.total_pairs.toLocaleString()} pairs
            ({info.data_stats.positive} positive, {info.data_stats.negative} negative)
          </p>
        </div>
      )}

      {/* Confusion matrix */}
      {confusion && !('error' in confusion) && (
        <>
          <ConfusionMatrix data={confusion} />
          <MisclassifiedTable items={confusion.misclassified} />
        </>
      )}
    </div>
  )
}
