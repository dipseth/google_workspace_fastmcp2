import { useWrapperLifecycle } from '../../hooks/useApi'

export default function WrapperLifecyclePanel() {
  const { data, isLoading, error } = useWrapperLifecycle()

  if (isLoading) return <div className="text-gray-400 text-xs p-4">Loading wrapper registry...</div>
  if (error) return <div className="text-red-400 text-xs p-4">Error: {error.message}</div>
  if (!data) return null

  if (data.error) return <div className="text-yellow-400 text-xs p-4">{data.error}</div>

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="text-xs text-gray-500 mb-3">
        {data.total_wrappers} registered wrapper{data.total_wrappers !== 1 ? 's' : ''}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-700">
              <th className="text-left p-1">Wrapper</th>
              <th className="text-left p-1">Domain</th>
              <th className="text-right p-1">Components</th>
              <th className="text-left p-1">Collection</th>
              <th className="text-left p-1">Mixins</th>
            </tr>
          </thead>
          <tbody>
            {data.wrappers.map((w, i) => (
              <tr key={i} className="border-b border-gray-800">
                <td className="p-1 text-gray-300 font-mono">{w.name}</td>
                <td className="p-1">
                  {w.domain ? (
                    <span className="text-blue-400">{w.domain}</span>
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
                <td className="p-1 text-right text-gray-200 font-mono">{w.components}</td>
                <td className="p-1 text-gray-400 truncate max-w-[200px]">{w.collection || '—'}</td>
                <td className="p-1 text-gray-500 truncate max-w-[300px]">
                  {w.mixins.length > 0 ? w.mixins.join(', ') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
