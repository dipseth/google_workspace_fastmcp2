import { useState } from 'react'
import { useSlotRoutingTest } from '../../hooks/useApi'

const POOL_COLORS: Record<string, string> = {
  buttons: '#3b82f6',
  content_texts: '#9ca3af',
  grid_items: '#f59e0b',
  chips: '#8b5cf6',
  carousel_cards: '#06b6d4',
}

const POOL_TEXT: Record<string, string> = {
  buttons: 'text-blue-400',
  content_texts: 'text-gray-300',
  grid_items: 'text-amber-400',
  chips: 'text-violet-400',
  carousel_cards: 'text-cyan-400',
}

const PRESETS: Record<string, string[]> = {
  'Mixed actions + status': [
    'Restart Server', 'View Logs', 'API Gateway: Online', 'CPU: 45%', 'Deploy to Production',
  ],
  'Chips + text': [
    'Python', 'JavaScript', 'Bug', 'Feature', 'The build completed successfully.',
  ],
  'Grid items + buttons': [
    'web-server-01', 'db-primary', 'cache-node', 'Delete All', 'Refresh',
  ],
  'All types mixed': [
    'Submit Form', 'Status: Active', 'High Priority', 'Step 1: Configure', 'Alice Johnson',
  ],
}

export default function SlotRoutingTest() {
  const [inputText, setInputText] = useState('')
  const { mutate, data, isPending, error } = useSlotRoutingTest()

  const handleSubmit = () => {
    const items = inputText.split('\n').map(s => s.trim()).filter(Boolean)
    if (items.length === 0) return
    mutate({ content_items: items })
  }

  const handlePreset = (items: string[]) => {
    setInputText(items.join('\n'))
    mutate({ content_items: items })
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">Slot Routing Tester</h3>
      <p className="text-xs text-gray-500 mb-3">
        Enter content items (one per line) to see which pool the slot assigner predicts for each.
      </p>

      {/* Presets */}
      <div className="flex flex-wrap gap-2 mb-3">
        {Object.entries(PRESETS).map(([label, items]) => (
          <button
            key={label}
            onClick={() => handlePreset(items)}
            className="text-xs px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded transition-colors"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex gap-2 mb-4">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Restart Server&#10;API Gateway: Online&#10;CPU: 45%&#10;Deploy&#10;Bug"
          className="flex-1 bg-gray-800 text-gray-200 text-sm font-mono rounded p-2 border border-gray-700 focus:border-blue-500 focus:outline-none resize-y min-h-[80px]"
          rows={4}
        />
        <button
          onClick={handleSubmit}
          disabled={isPending || !inputText.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded font-medium transition-colors self-start"
        >
          {isPending ? 'Routing...' : 'Test'}
        </button>
      </div>

      {error && <div className="text-red-400 text-xs mb-2">Error: {error.message}</div>}

      {/* Results */}
      {data && data.items && (
        <div>
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Routing Results</h4>
          <div className="space-y-2">
            {data.items.map((item, i) => (
              <div key={i} className="bg-gray-800/50 rounded p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-mono text-gray-200">{item.content_text}</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded ${POOL_TEXT[item.predicted_pool] || 'text-gray-400'}`}
                    style={{ backgroundColor: (POOL_COLORS[item.predicted_pool] || '#666') + '30' }}>
                    {item.predicted_pool} ({(item.confidence * 100).toFixed(0)}%)
                  </span>
                </div>
                {/* Score bars */}
                <div className="space-y-0.5">
                  {data.pool_names.map((pool) => {
                    const score = item.pool_scores[pool] || 0
                    const isPred = pool === item.predicted_pool
                    return (
                      <div key={pool} className="flex items-center gap-2 text-xs">
                        <span className={`w-24 text-right ${isPred ? (POOL_TEXT[pool] || 'text-gray-300') : 'text-gray-600'}`}>
                          {pool}
                        </span>
                        <div className="flex-1 bg-gray-900 rounded h-3 overflow-hidden">
                          <div
                            className="h-full rounded transition-all"
                            style={{
                              width: `${score * 100}%`,
                              backgroundColor: isPred ? (POOL_COLORS[pool] || '#666') : '#4b5563',
                              opacity: isPred ? 1 : 0.4,
                            }}
                          />
                        </div>
                        <span className={`font-mono w-12 text-right ${isPred ? 'text-gray-200' : 'text-gray-600'}`}>
                          {(score * 100).toFixed(1)}%
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
