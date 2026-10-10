import type { FieldResult } from '../types/prescription'

const pretty = (key: string) => key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

export function FieldRow({ fieldKey, field, onSelect }: { fieldKey: string; field: FieldResult; onSelect: () => void }) {
  const isPass = field.decision === 'VERIFIED' || field.decision === 'HUMAN_VERIFIED'
  const state = isPass ? 'pass' : field.decision === 'REVIEW_REQUIRED' || field.decision === 'INVALID' ? 'critical' : 'warning'
  return (
    <button type="button" className={`field-row field-row--${state}`} onClick={onSelect}>
      <span className="field-row__label">{pretty(fieldKey)}</span>
      <span className="field-row__value">{field.normalized_value ?? field.raw_value ?? 'Not readable'}</span>
      <span className="field-row__state">{isPass ? 'Verified' : field.decision.replaceAll('_', ' ')}</span>
    </button>
  )
}
