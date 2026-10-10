import { useState } from 'react'
import { approvePrescription, resolveException, sourceUrl } from '../api/prescriptions'
import { ApprovalBar } from '../components/ApprovalBar'
import { DocumentViewer } from '../components/DocumentViewer'
import { ExceptionPanel } from '../components/ExceptionPanel'
import { PrismEvidencePanel } from '../components/PrismEvidencePanel'
import { PrescriptionFields } from '../components/PrescriptionFields'
import { ReviewRequestDialog, type ReviewDraft } from '../components/ReviewRequestDialog'
import { ReviewHistory } from '../components/ReviewHistory'
import { StatusBadge } from '../components/StatusBadge'
import type { Prescription } from '../types/prescription'

export function PrescriptionReviewPage({ prescription, apiReady, imageUrl, onRefresh, onBack }: { prescription: Prescription; apiReady: boolean; imageUrl?: string; onRefresh: (value: Prescription) => void; onBack: () => void }) {
  const [selectedField, setSelectedField] = useState<string | null>(prescription.exceptions[0]?.field ?? null)
  const [candidate, setCandidate] = useState<string | undefined>()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [correction, setCorrection] = useState('')
  const [requestKind, setRequestKind] = useState<ReviewDraft['kind'] | null>(null)
  const [drafts, setDrafts] = useState<ReviewDraft[]>([])
  const documentUrl = imageUrl ?? sourceUrl(prescription.source.original_path)
  const field = selectedField ? prescription.fields[selectedField] : undefined
  const exception = prescription.exceptions.find((item) => item.field === selectedField)

  async function handleAction(action: string) {
    if (action === 'REQUEST_CLARIFICATION' || action === 'REJECT') {
      setRequestKind(action === 'REJECT' ? 'rejection' : 'clarification'); return
    }
    if (!exception || busy || !apiReady) return
    const value = action === 'CORRECT' ? correction.trim() : candidate ?? field?.normalized_value ?? field?.raw_value ?? undefined
    if (action !== 'MARK_UNREADABLE' && !value) { setError('Select a candidate or enter a corrected value first.'); return }
    setBusy(true)
    try {
      const next = await resolveException(prescription.prescription_id, exception.exception_id, action === 'MARK_UNREADABLE' ? 'MARK_UNREADABLE' : 'SELECT_VALUE', value)
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
      <PrismEvidencePanel prescriptionId={prescription.prescription_id} events={prescription.audit_events} />
      <ReviewHistory prescription={prescription} drafts={drafts} />
      {requestKind && <ReviewRequestDialog kind={requestKind} field={selectedField ?? 'prescription'} onClose={() => setRequestKind(null)} onSave={(draft) => setDrafts((old) => [...old, draft])} />}
    </main>
  )
}
