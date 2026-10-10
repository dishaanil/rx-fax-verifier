import type { AuditEvent } from '../types/prescription'

const eventLabel: Record<string, string> = {
  PRISM_TRACE_RECORDED: 'Trace recorded',
  PRISM_GUARDRAIL_FLAGGED: 'Guardrail flagged untrusted content',
  PRISM_EVALUATOR_COMPLETED: 'Evaluator evidence completed',
}

export function PrismEvidencePanel({ prescriptionId, events }: { prescriptionId: string; events: AuditEvent[] }) {
  const prismEvents = events.filter((event) => event.event.startsWith('PRISM_'))
  return (
    <aside className="prism-evidence" aria-label="PRISM reliability evidence">
      <div><strong>PRISM reliability evidence</strong><span>Session: {prescriptionId}</span></div>
      {prismEvents.length === 0
        ? <p>Awaiting backend trace, Guardrail, or Evaluator evidence. These checks never change approval authority in the browser.</p>
        : <ul>{prismEvents.map((event) => <li key={`${event.ts}-${event.event}`}><strong>{eventLabel[event.event] ?? event.event}</strong><span>{event.detail ?? 'Recorded by the backend.'}</span></li>)}</ul>}
    </aside>
  )
}
