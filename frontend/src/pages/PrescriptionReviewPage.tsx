import { useState } from 'react'
import { approvePrescription, prescriptionSourceUrl, rejectPrescription, resolveException, type ResolutionAction } from '../api/prescriptions'
import { DecisionCard } from '../components/DecisionCard'
import { DocumentViewer } from '../components/DocumentViewer'
import { FieldList } from '../components/FieldList'
import { IssuePanel } from '../components/IssuePanel'
import { MoreDetails } from '../components/MoreDetails'
import { StatusBadge } from '../components/StatusBadge'
import { Stepper } from '../components/Stepper'
import { FINISHED, fieldLabel, fieldValue } from '../lib/review'
import type { Prescription } from '../types/prescription'

export function PrescriptionReviewPage({ prescription, apiReady, onRefresh, onBack }: { prescription: Prescription; apiReady: boolean; onRefresh: (value: Prescription) => void; onBack: () => void }) {
  const { exceptions, fields, status } = prescription
  const [issueId, setIssueId] = useState<string | null>(exceptions[0]?.exception_id ?? null)
  const [selectedField, setSelectedField] = useState<string | null>(exceptions[0]?.field ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const documentUrl = prescriptionSourceUrl(prescription.prescription_id)

  const issueIndex = Math.max(0, exceptions.findIndex((item) => item.exception_id === issueId))
  const issue = exceptions[issueIndex]
  const locked = !apiReady || status === 'PROCESSING' || FINISHED.includes(status)
  const field = selectedField ? fields[selectedField] : undefined
  const issueEvidence = issue && issue.field === selectedField && issue.source_evidence?.bbox ? issue.source_evidence : null
  const patient = fields.patient ? fieldValue(fields.patient) : null
  const medication = [fields.drug, fields.strength].map((item) => item && fieldValue(item)).filter(Boolean).join(' ')

  async function run(action: () => Promise<Prescription>, failure: string) {
    if (busy) return
    setBusy(true)
    try {
      const next = await action()
      onRefresh(next); setError(null)
      setIssueId(next.exceptions[0]?.exception_id ?? null)
      setSelectedField(next.exceptions[0]?.field ?? null)
    } catch (caught) { setError(caught instanceof Error ? caught.message : failure) }
    finally { setBusy(false) }
  }

  function resolve(action: ResolutionAction, value?: string) {
    if (issue) void run(() => resolveException(prescription.prescription_id, issue.exception_id, action, value), 'That decision could not be saved.')
  }

  function reject() {
    if (window.confirm('Reject this prescription? Nothing will be dispensed from this fax.')) {
      void run(() => rejectPrescription(prescription.prescription_id), 'The prescription could not be rejected.')
    }
  }

  function selectField(key: string) {
    setSelectedField(key)
    const match = exceptions.find((item) => item.field === key)
    if (match) setIssueId(match.exception_id)
  }

  function move(step: -1 | 1) {
    const next = exceptions[(issueIndex + step + exceptions.length) % exceptions.length]
    setIssueId(next.exception_id); setSelectedField(next.field)
  }

  return (
    <main className="review">
      <header className="review__header">
        <button type="button" className="link-button back" onClick={onBack}>← All prescriptions</button>
        <div className="review__title">
          <h1>{patient ?? 'Unknown patient'}</h1>
          <p>{medication || 'Medication not read yet'} <span className="muted">· {prescription.prescription_id}</span></p>
        </div>
        <StatusBadge status={status} />
        {!FINISHED.includes(status) && apiReady && <button type="button" className="button button--quiet-danger" disabled={busy} onClick={reject}>Reject prescription</button>}
      </header>

      <Stepper prescription={prescription} />
      {error && <p className="banner banner--error" role="alert">{error}</p>}
      {busy && <p className="banner" role="status">Saving and re-checking…</p>}

      <div className="review__grid">
        <DocumentViewer documentPath={documentUrl} evidence={issueEvidence ?? field?.evidence} label={selectedField ? fieldLabel(selectedField).toLowerCase() : undefined} />
        <div className="review__side">
          {issue && !FINISHED.includes(status)
            ? <IssuePanel key={issue.exception_id} prescription={prescription} exception={issue} position={issueIndex + 1} total={exceptions.length}
                onMove={move} onResolve={resolve} onReject={() => void run(() => rejectPrescription(prescription.prescription_id), 'The prescription could not be rejected.')}
                disabled={busy || locked} documentUrl={documentUrl} />
            : <DecisionCard prescription={prescription} disabled={busy || !apiReady} onApprove={() => void run(() => approvePrescription(prescription.prescription_id), 'Approval was not permitted.')} />}
          {issue && !FINISHED.includes(status) && (
            // Approval stays visible but disabled while issues remain (DESIGN.md §13).
            <button type="button" className="button button--primary button--wide" disabled>
              Approve as pharmacist · {exceptions.length} {exceptions.length === 1 ? 'issue' : 'issues'} left
            </button>
          )}
          {!apiReady && <p className="note">Preview only: connect the prescription service to make decisions.</p>}
          <FieldList prescription={prescription} selected={selectedField} onSelect={selectField} />
          <MoreDetails prescription={prescription} />
        </div>
      </div>
    </main>
  )
}
