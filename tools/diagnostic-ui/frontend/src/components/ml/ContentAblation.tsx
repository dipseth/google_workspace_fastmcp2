import { useContentAblation } from '../../hooks/useApi'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const FEATURE_COLORS: Record<string, string> = {
  sim_c_mean: '#3b82f6', sim_c_max: '#2563eb', sim_c_std: '#60a5fa', sim_c_coverage: '#93c5fd',
  sim_i_mean: '#8b5cf6', sim_i_max: '#7c3aed', sim_i_std: '#a78bfa', sim_i_coverage: '#c4b5fd',
  sim_relationships: '#93c5fd',
  is_parent: '#22c55e', is_child: '#4ade80', is_sibling: '#86efac',
  depth_ratio: '#f59e0b', n_shared_ancestors: '#fbbf24',
  sim_content: '#f43f5e', content_density: '#fb7185', content_form_alignment: '#fda4af',
}

const SHORT_NAMES: Record<string, string> = {
  sim_c_mean: 'c_mean', sim_c_max: 'c_max', sim_c_std: 'c_std', sim_c_coverage: 'c_cov',
  sim_i_mean: 'i_mean', sim_i_max: 'i_max', sim_i_std: 'i_std', sim_i_coverage: 'i_cov',
  sim_relationships: 'sim_r',
  is_parent: 'is_parent', is_child: 'is_child', is_sibling: 'is_sibling',
  depth_ratio: 'depth_ratio', n_shared_ancestors: 'shared_anc',
  sim_content: 'sim_content', content_density: 'content_dens', content_form_alignment: 'content_align',
}

function AblationChart({ data, title }: { data: { name: string; fullName: string; value: number }[]; title: string }) {
  return (
    <div>
      <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">{title}</h4>
      <ResponsiveContainer width="100%" height={420}>
        <BarChart data={data} layout="vertical" margin={{ left: 80 }}>
          <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 10 }} />
          <YAxis dataKey="name" type="category" tick={{ fill: '#9ca3af', fontSize: 10 }} width={80} />
          <Tooltip
            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
            formatter={(v: number, _: string, props: { payload: { fullName: string } }) => [
              `${(v * 100).toFixed(2)}%`, props.payload.fullName,
            ]}
          />
          <Bar dataKey="value">
            {data.map((entry) => (
              <Cell key={entry.name} fill={FEATURE_COLORS[entry.fullName] || '#6b7280'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function ContentAblation() {
  const { data, isLoading, error } = useContentAblation()

  if (isLoading) return <div className="text-gray-500 p-4">Computing per-head ablation...</div>
  if (error) return <div className="text-red-400 p-4">Error: {error.message}</div>
  if (!data) return null

  const makeData = (values: number[]) =>
    data.feature_names.map((name, i) => ({
      name: SHORT_NAMES[name] || name,
      fullName: name,
      value: values[i],
    }))

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">Content-Specific Ablation</h3>
      <p className="text-xs text-gray-500 mb-3">
        Per-head accuracy drop when zeroing each feature independently.
      </p>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Baseline Form</div>
          <div className="text-lg font-mono text-green-400">{(data.baseline_form * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Baseline Content</div>
          <div className="text-lg font-mono text-rose-400">{(data.baseline_content * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs text-gray-500">Baseline Combined</div>
          <div className="text-lg font-mono text-blue-400">{(data.baseline_combined * 100).toFixed(1)}%</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AblationChart data={makeData(data.form_ablation)} title="Form Head Ablation" />
        <AblationChart data={makeData(data.content_ablation)} title="Content Head Ablation" />
        <AblationChart data={makeData(data.combined_ablation)} title="Combined Ablation" />
      </div>
    </div>
  )
}
