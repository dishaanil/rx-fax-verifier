import type { Exception, FieldResult } from '../types/prescription'
import { CandidateSelector } from './CandidateSelector'
import { ReviewActions } from './ReviewActions'
import { SourceCrop } from './SourceCrop'

export function ExceptionPanel({ exception, field, selectedCandidate, onCandidate, onAction, apiReady, correction, onCorrection, documentUrl }: {
  exception?: Exception
  field?: FieldResult
  selectedCandidate?: string
  onCandidate: (value: string) => void
  onAction: (action: string) => void
  apiReady: boolean
  correction: string
  onCorrection: (value: string) => void
  documentUrl: string
}) {
  if (!exception || !field) {
    return <section className="panel exception-panel"><div className="panel__heading"><span>Review action</span></div><p>{exception?.reason ?? field?.reason ?? 'Select a field to inspect its evidence.'}</p>{exception?.required_action === 'REJECT' && <ReviewActions disabled={!apiReady} rejectOnly onAction={onAction} />}{field?.signals.map((signal, index) => <p key={index}>{signal.type}: {signal.detail ?? signal.status}</p>)}</section>
  }
  const cropEvidence = exception.source_evidence?.bbox
    ? { page: exception.source_evidence.page ?? field.evidence?.page ?? 1, bbox: exception.source_evidence.bbox }
    : field.evidence?.bbox
      ? { page: field.evidence.page ?? 1, bbox: field.evidence.bbox }
      : null
  return (
    <section className="panel exception-panel">
      <div className="panel__heading"><span>Decision required</span><small>{exception.severity}</small></div>
      <h2>{exception.field.replaceAll('_', ' ')}</h2>
      <p className="exception-reason">{exception.reason}</p>
      {cropEvidence ? <SourceCrop evidence={cropEvidence} documentUrl={documentUrl} /> : <p className="fixture-note">No source crop is available for this exception.</p>}
      <div className="reads">
        <strong>Competing reads</strong>
        {field.reads.map((read) => <span key={`${read.source}-${read.value}`}>{read.source}: {read.value ?? 'No reading'}</span>)}
      </div>
      {exception.required_action === 'REJECT' ? <ReviewActions disabled={!apiReady} rejectOnly onAction={onAction} /> : <>
        <CandidateSelector values={exception.candidate_values} selectedValue={selectedCandidate} onChange={onCandidate} />
        <label className="correction-label">Corrected value<input value={correction} disabled={!apiReady} onChange={(event) => onCorrection(event.target.value)} placeholder="Enter the value supported by the source" /></label>
        <ReviewActions disabled={!apiReady} canSelect={Boolean(selectedCandidate)} canConfirm={Boolean(field.normalized_value ?? field.raw_value)} canCorrect={Boolean(correction.trim())} onAction={onAction} />
      </>}
      <p className="fixture-note">The backend validates each pharmacist action and returns the resulting prescription state.</p>
      {!apiReady && <p className="fixture-note">Fixture preview: resolution is disabled until the policy API is connected. The backend revalidates every action.</p>}
    </section>
  )
}
