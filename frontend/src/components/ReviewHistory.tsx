import type { Prescription } from '../types/prescription'
import type { ReviewDraft } from './ReviewRequestDialog'

function valueText(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export function ReviewHistory({ prescription, drafts }: { prescription: Prescription; drafts: ReviewDraft[] }) {
  const resolved = Object.entries(prescription.fields).filter(([, field]) => field.resolution)
  return <section className="review-history">
    <details><summary>Review history & evidence <span>{prescription.audit_events.length} events</span></summary>
      {prescription.approved_by && <p>Approved by pharmacist: <strong>{valueText(prescription.approved_by)}</strong></p>}
      {resolved.map(([key, field]) => <div className="history-item" key={key}><strong>{key.replaceAll('_', ' ')} resolution</strong><p>{valueText(field.resolution)}</p></div>)}
      {prescription.clarifications.map((item, index) => <div className="history-item" key={index}><strong>Prescriber clarification · pharmacist acceptance required</strong><p>{valueText(item)}</p></div>)}
      <ol className="audit-list">{prescription.audit_events.map((event, index) => <li key={`${event.ts}-${index}`}><time>{new Date(event.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time><div><strong>{event.event.replaceAll('_', ' ').toLowerCase()}</strong><span>{event.actor}{event.detail ? ` · ${event.detail}` : ''}</span></div></li>)}</ol>
    </details>
    {drafts.length > 0 && <div className="local-drafts"><h3>Unsubmitted local drafts</h3>{drafts.map((draft, index) => <p key={index}><strong>{draft.kind === 'clarification' ? 'Clarification' : 'Rejection'} · {draft.field}: </strong>{draft.note}</p>)}<small>These notes are cleared when you leave this review screen.</small></div>}
  </section>
}
