import { FIELD_ORDER, FIELD_STATE_LABELS, fieldCounts, fieldLabel, fieldState, fieldValue, issueExplanation } from '../lib/review'
import type { Prescription } from '../types/prescription'

export function FieldList({ prescription, selected, onSelect }: { prescription: Prescription; selected: string | null; onSelect: (key: string) => void }) {
  const keys = Object.keys(prescription.fields).sort((a, b) => rank(a) - rank(b))
  const counts = fieldCounts(prescription)
  const summary = (['auto', 'human', 'review', 'unreadable', 'missing'] as const)
    .filter((state) => counts[state])
    .map((state) => `${counts[state]} ${FIELD_STATE_LABELS[state].toLowerCase()}`)
  return (
    <section className="card fields" aria-labelledby="fields-title">
      <header className="fields__header">
        <h2 id="fields-title">Prescription details</h2>
        <small>{summary.join(' · ')}</small>
      </header>
      <ul>
        {keys.map((key) => {
          const field = prescription.fields[key]
          const state = fieldState(field)
          const open = selected === key
          const issue = prescription.exceptions.find((item) => item.field === key)
          return (
            <li key={key}>
              <button type="button" className={`field field--${state}${open ? ' field--selected' : ''}`} aria-expanded={open} onClick={() => onSelect(key)}>
                <span className="field__label">{fieldLabel(key)}</span>
                <span className="field__value">{fieldValue(field) ?? <em>Not found</em>}</span>
                <span className={`dot dot--${state}`} title={FIELD_STATE_LABELS[state]} aria-label={FIELD_STATE_LABELS[state]} />
              </button>
              {open && <div className="field__detail">
                <p><strong>{FIELD_STATE_LABELS[state]}.</strong> {issue ? issueExplanation(issue, field).reason : field.reason}</p>
                {field.signals.length > 0 && <ul className="checks">
                  {field.signals.map((signal, index) => <li key={index} className={`check check--${signal.status.toLowerCase()}`}>{signal.detail ?? signal.type}</li>)}
                </ul>}
              </div>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function rank(key: string): number {
  const index = FIELD_ORDER.indexOf(key)
  return index === -1 ? FIELD_ORDER.length : index
}
