import { useState } from 'react'
import { approvePrescription, prescriptionSourceUrl, rejectPrescription, resolveException, type ResolutionAction } from '../api/prescriptions'
import { ApprovalBar } from '../components/ApprovalBar'
import { DocumentViewer } from '../components/DocumentViewer'
import { ExceptionPanel } from '../components/ExceptionPanel'
import { PrismEvidencePanel } from '../components/PrismEvidencePanel'
import { PrescriptionFields } from '../components/PrescriptionFields'
import { ReviewHistory } from '../components/ReviewHistory'
import { StatusBadge } from '../components/StatusBadge'
import { UntrustedTextPanel } from '../components/UntrustedTextPanel'
import type { Prescription } from '../types/prescription'

export function PrescriptionReviewPage({ prescription, apiReady, onRefresh, onBack }: { prescription: Prescription; apiReady: boolean; onRefresh: (value: Prescription) => void; onBack: () => void }) {
  const [selectedField, setSelectedField] = useState<string | null>(prescription.exceptions[0]?.field ?? null)
  const [candidate, setCandidate] = useState<string | undefined>()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [correction, setCorrection] = useState('')
  const documentUrl = prescriptionSourceUrl(prescription.prescription_id)
  const field = selectedField ? prescription.fields[selectedField] : undefined
  const exception = prescription.exceptions.find((item) => item.field === selectedField)

  async function handleAction(action: string) {
    if (busy || !apiReady) return
    if (action === 'REJECT') {
      setBusy(true)
      try { onRefresh(await rejectPrescription(prescription.prescription_id)); setError(null) }
      catch (caught) { setError(caught instanceof Error ? caught.message : 'Prescription could not be rejected.') }
      finally { setBusy(false) }
      return
    }
    if (!exception) return
    const value = action === 'CORRECT' ? correction.trim() : action === 'SELECT_VALUE' ? candidate : undefined
    if ((action === 'CORRECT' || action === 'SELECT_VALUE') && !value) { setError(action === 'CORRECT' ? 'Enter a corrected value first.' : 'Select a candidate first.'); return }
    setBusy(true)
    try {
      const next = await resolveException(prescription.prescription_id, exception.exception_id, action as ResolutionAction, value)
      onRefresh(next); setCandidate(undefined); setCorrection(''); setError(null)
      setSelectedField(next.exceptions[0]?.field ?? selectedField)
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to resolve exception.') }
    finally { setBusy(false) }
  }

  async function handleApprove() {
    if (busy || !apiReady || prescription.status !== 'READY_FOR_VERIFICATION') return
    setBusy(true)
    try { onRefresh(await approvePrescription(prescription.prescription_id)); setError(null) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Approval was not permitted.') }
    finally { setBusy(false) }
  }

  return (
    <main className="review-page">
      <header className="review-header"><button type="button" className="back" onClick={onBack}>← Intake queue</button><div><p className="eyebrow">Prescription {prescription.prescription_id}</p><h1>Pharmacist review</h1><p className="review-subtitle">Check the source. Resolve the exceptions. Verify the prescription.</p></div><StatusBadge status={prescription.status} /></header>
      <div className="workflow-strip"><span className="complete">1 · Intake</span><span className="active">2 · Evidence review</span><span className={prescription.status === 'APPROVED' ? 'complete' : ''}>3 · Pharmacist approval</span></div>
      {error && <p className="error-banner" role="alert">{error}</p>}
      {(busy || prescription.status === 'PROCESSING') && <p role="status">{busy ? 'Saving and revalidating…' : 'Extracting prescription fields…'}</p>}
      <div className="review-grid">
        <DocumentViewer documentPath={documentUrl} evidence={field?.evidence} />
        <PrescriptionFields fields={prescription.fields} selectedField={selectedField} onSelect={(key) => { setSelectedField(key); setCandidate(undefined); setCorrection(''); setError(null) }} />
        <ExceptionPanel exception={exception} field={field} selectedCandidate={candidate} onCandidate={setCandidate} onAction={handleAction} apiReady={apiReady && !busy && !['PROCESSING', 'APPROVED', 'REJECTED', 'UNPROCESSABLE'].includes(prescription.status)} correction={correction} onCorrection={setCorrection} documentUrl={documentUrl} />
      </div>
      <ApprovalBar prescription={prescription} onApprove={handleApprove} apiReady={apiReady && !busy} />
      {prescription.source.untrusted_text?.length ? <UntrustedTextPanel text={prescription.source.untrusted_text} /> : null}
      <PrismEvidencePanel prescriptionId={prescription.prescription_id} events={prescription.audit_events} />
      <ReviewHistory prescription={prescription} />
    </main>
  )
}
