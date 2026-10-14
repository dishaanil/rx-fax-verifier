import { fieldLabel, fieldValue } from '../lib/review'
import type { Prescription } from '../types/prescription'

const SUMMARY = ['patient', 'patient_dob', 'drug', 'strength', 'form', 'sig', 'quantity', 'refills', 'prescriber']

/** Step 3, and what follows it. Shown only when no issue is open. */
export function DecisionCard({ prescription, onApprove, disabled }: { prescription: Prescription; onApprove: () => void; disabled: boolean }) {
  const { status } = prescription
  if (status === 'PROCESSING') {
    return <section className="card outcome"><span className="spinner" aria-hidden="true" /><h2>Reading the fax…</h2><p>Fields appear here in a few seconds.</p></section>
  }
  if (status === 'UNPROCESSABLE') {
    return <section className="card outcome outcome--danger"><h2>This fax couldn't be read</h2><p>It may not be a prescription, or it holds more than one. Ask the prescriber to resend it.</p></section>
  }
  if (status === 'REJECTED') {
    return <section className="card outcome outcome--danger"><h2>Prescription rejected</h2><p>Nothing will be dispensed from this fax.</p></section>
  }
  const rows = SUMMARY.filter((key) => prescription.fields[key])
  const approved = status === 'APPROVED'
  return (
    <section className={`card decision${approved ? ' decision--approved' : ''}`}>
      <span className="eyebrow">{approved ? 'Approved' : 'Final check'}</span>
      <h2>{approved ? `Approved by ${prescription.approved_by ?? 'pharmacist'}` : 'Everything checks out'}</h2>
      {!approved && <p>Read the prescription once more against the fax, then approve it.</p>}
      <dl className="summary">
        {rows.map((key) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{fieldValue(prescription.fields[key]) ?? '—'}</dd></div>)}
      </dl>
      {!approved && <button type="button" className="button button--primary button--wide" disabled={disabled} onClick={onApprove}>Approve as pharmacist</button>}
    </section>
  )
}
