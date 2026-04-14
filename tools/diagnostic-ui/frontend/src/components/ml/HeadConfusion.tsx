import { useHeadConfusion } from '../../hooks/useApi'
import type { HeadConfusionData } from '../../types'

function ConfusionGrid({ data, title, accentColor }: { data: HeadConfusionData; title: string; accentColor: string }) {
  const { labels, matrix } = data
  const maxVal = Math.max(1, ...matrix.flat())

  return (
    <div>
      <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">{title}</h4>
      <p className="text-xs text-gray-500 mb-2">
        Accuracy: <span className={`font-mono ${accentColor}`}>{(data.accuracy * 100).toFixed(1)}%</span>
        {' '}({data.n_groups} groups)
      </p>
      <div className="overflow-x-auto">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="p-1 text-gray-500 text-right">Pred \ Exp</th>
              {labels.map((l) => (
                <th key={l} className="p-1 text-gray-400 text-center min-w-[60px] truncate max-w-[80px]" title={l}>
                  {l.length > 10 ? l.slice(0, 8) + '..' : l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((rowLabel, i) => (
              <tr key={rowLabel}>
                <td className="p-1 text-gray-400 text-right truncate max-w-[80px]" title={rowLabel}>
                  {rowLabel.length > 10 ? rowLabel.slice(0, 8) + '..' : rowLabel}
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

export default function HeadConfusion() {
  const { data, isLoading, error } = useHeadConfusion()

  if (isLoading) return <div className="text-gray-500 p-4">Computing confusion matrices...</div>
  if (error) return <div className="text-red-400 p-4">Error: {error.message}</div>
  if (!data) return null

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">Per-Head Confusion Matrix</h3>
      <p className="text-xs text-gray-500 mb-3">
        Where each head makes mistakes. Diagonal (green) = correct, off-diagonal (red) = errors.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ConfusionGrid data={data.form_head} title="Form Head" accentColor="text-green-400" />
        <ConfusionGrid data={data.content_head} title="Content Head" accentColor="text-rose-400" />
      </div>
    </div>
  )
}
