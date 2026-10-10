import type { FieldResult } from '../types/prescription'
import { FieldRow } from './FieldRow'

export function PrescriptionFields({ fields, selectedField, onSelect }: {
  fields: Record<string, FieldResult>
  selectedField: string | null
  onSelect: (fieldKey: string) => void
}) {
  const entries = Object.entries(fields)
  const verified = entries.filter(([, field]) => field.decision === 'VERIFIED' || field.decision === 'HUMAN_VERIFIED')
  const needsReview = entries.filter(([, field]) => field.decision !== 'VERIFIED' && field.decision !== 'HUMAN_VERIFIED')

  return (
    <section className="panel prescription-fields">
      <div className="panel__heading"><span>Structured draft</span><small>Policy-owned decisions</small></div>
      <div className="field-list">
        {needsReview.map(([key, field]) => <FieldRow key={key} fieldKey={key} field={field} onSelect={() => onSelect(key)} />)}
      </div>
      <details className="checks-passed">
        <summary>Checks passed ({verified.length})</summary>
        <div className="field-list">
          {verified.map(([key, field]) => <FieldRow key={key} fieldKey={key} field={field} onSelect={() => onSelect(key)} />)}
        </div>
      </details>
      {selectedField && <p className="selection-hint">Showing source evidence for {selectedField.replaceAll('_', ' ')}.</p>}
    </section>
  )
}
