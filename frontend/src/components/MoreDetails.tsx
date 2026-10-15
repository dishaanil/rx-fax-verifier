import type { Prescription } from '../types/prescription'

const PRISM_LABELS: Record<string, string> = {
  PRISM_TRACE_RECORDED: 'Model calls traced',
  PRISM_GUARDRAIL_FLAGGED: 'Guardrail flagged text on the fax',
  PRISM_EVALUATOR_COMPLETED: 'Evaluator finished',
}

const text = (value: unknown) => (value == null ? '—' : typeof value === 'string' ? value : JSON.stringify(value))
const time = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

/** Supporting evidence, collapsed by default: never needed to make the decision. */
export function MoreDetails({ prescription }: { prescription: Prescription }) {
  const untrusted = prescription.source.untrusted_text ?? []
  const prism = prescription.audit_events.filter((event) => event.event.startsWith('PRISM_'))
  return (
    <section className="more">
      {untrusted.length > 0 && <details className="more__item more__item--warning">
        <summary>Other text on the fax <span className="count">{untrusted.length}</span></summary>
        <p>Notes, stamps or instructions found on the page. They were treated as data only and never change a decision.</p>
        <ul className="quoted">{untrusted.map((line, index) => <li key={index}>{line}</li>)}</ul>
      </details>}
      <details className="more__item">
        <summary>Reliability checks (PRISM) <span className="count">{prism.length}</span></summary>
        {prism.length === 0
          ? <p>No PRISM evidence recorded for this prescription.</p>
          : <ul className="timeline">{prism.map((event, index) => <li key={index}><strong>{PRISM_LABELS[event.event] ?? event.event}</strong><span>{event.detail ?? 'Recorded'}</span></li>)}</ul>}
      </details>
      <details className="more__item">
        <summary>History <span className="count">{prescription.audit_events.length}</span></summary>
        <ul className="timeline">
          {prescription.audit_events.map((event, index) => (
            <li key={index}>
              <strong>{event.event.replaceAll('_', ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</strong>
              <span><time>{time(event.ts)}</time> · {event.actor.toLowerCase()}{event.detail ? ` · ${text(event.detail)}` : ''}</span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
