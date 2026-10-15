import type { Exception, FieldResult, Prescription, PrescriptionStatus } from '../types/prescription'

const FIELD_LABELS: Record<string, string> = {
  patient: 'Patient',
  patient_dob: 'Date of birth',
  drug: 'Drug',
  strength: 'Strength',
  form: 'Form',
  sig: 'Directions',
  quantity: 'Quantity',
  days_supply: 'Days supply',
  refills: 'Refills',
  prescriber: 'Prescriber',
  prescriber_identifier: 'Prescriber ID',
  date_written: 'Date written',
  signature_present: 'Signature',
  document: 'Document',
}

// Display order: the prescription as a pharmacist reads it.
export const FIELD_ORDER = Object.keys(FIELD_LABELS)

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export function issueQuestion(exception: Exception): string {
  if (exception.required_action === 'REJECT') return 'This fax was already received'
  return `What ${fieldLabel(exception.field).toLowerCase()} is written on the fax?`
}

export function readerLabel(source: string): string {
  return { primary: 'Reader 1', secondary: 'Reader 2', crossed_out: 'Crossed out' }[source] ?? source
}

export function fieldValue(field: FieldResult): string | null {
  return field.normalized_value ?? field.raw_value
}

export type FieldState = 'auto' | 'human' | 'review' | 'unreadable' | 'missing' | 'unchecked'

export function fieldState(field: FieldResult): FieldState {
  switch (field.decision) {
    case 'VERIFIED': return 'auto'
    case 'HUMAN_VERIFIED': return 'human'
    case 'REVIEW_REQUIRED':
    case 'INVALID': return 'review'
    case 'UNREADABLE': return 'unreadable'
    case 'MISSING': return 'missing'
    default: return 'unchecked'
  }
}

export const FIELD_STATE_LABELS: Record<FieldState, string> = {
  auto: 'Auto-verified',
  human: 'Verified by you',
  review: 'Needs review',
  unreadable: 'Unreadable',
  missing: 'Missing',
  unchecked: 'Not checked',
}

export function fieldCounts(prescription: Prescription): Record<FieldState, number> {
  const counts: Record<FieldState, number> = { auto: 0, human: 0, review: 0, unreadable: 0, missing: 0, unchecked: 0 }
  for (const field of Object.values(prescription.fields)) counts[fieldState(field)] += 1
  return counts
}

export const STATUS_LABELS: Record<PrescriptionStatus, string> = {
  PROCESSING: 'Processing',
  REVIEW_REQUIRED: 'Needs review',
  AWAITING_CLARIFICATION: 'Waiting on prescriber',
  READY_FOR_VERIFICATION: 'Ready to approve',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  UNPROCESSABLE: "Couldn't read",
}

export const NEEDS_REVIEW: PrescriptionStatus[] = ['REVIEW_REQUIRED', 'AWAITING_CLARIFICATION']
export const FINISHED: PrescriptionStatus[] = ['APPROVED', 'REJECTED', 'UNPROCESSABLE']

export type StepState = 'done' | 'current' | 'upcoming' | 'stopped'
export type Step = { label: string; detail: string; state: StepState }

/** The three review steps, derived only from the backend status (the backend owns every transition). */
export function reviewSteps(prescription: Prescription): Step[] {
  const { status } = prescription
  const open = prescription.exceptions.length
  const intake: Step = { label: 'Intake', detail: 'Fax read', state: 'done' }
  const issues: Step = { label: 'Resolve issues', detail: open ? `${open} left` : 'All resolved', state: 'done' }
  const approval: Step = { label: 'Pharmacist approval', detail: 'Not started', state: 'upcoming' }
  switch (status) {
    case 'PROCESSING':
      return [{ ...intake, detail: 'Reading fax…', state: 'current' }, { ...issues, detail: '', state: 'upcoming' }, { ...approval, detail: '' }]
    case 'UNPROCESSABLE':
      return [{ ...intake, detail: "Couldn't read", state: 'stopped' }, { ...issues, detail: '', state: 'upcoming' }, { ...approval, detail: '' }]
    case 'REVIEW_REQUIRED':
    case 'AWAITING_CLARIFICATION':
      return [intake, { ...issues, state: 'current' }, approval]
    case 'READY_FOR_VERIFICATION':
      return [intake, issues, { ...approval, detail: 'Your decision', state: 'current' }]
    case 'APPROVED':
      return [intake, issues, { ...approval, detail: 'Approved', state: 'done' }]
    case 'REJECTED':
      return [intake, { ...issues, state: open ? 'stopped' : 'done' }, { ...approval, detail: 'Rejected', state: 'stopped' }]
  }
}

export function clarificationRequested(prescription: Prescription, exceptionId: string): boolean {
  return prescription.clarifications.some((item) => {
    const record = item as { exception_id?: string; status?: string }
    return record.exception_id === exceptionId && record.status === 'REQUESTED'
  })
}

export function receivedAt(prescription: Prescription): string {
  const ts = prescription.audit_events[0]?.ts
  return ts ? new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'
}

const ISSUE_REASONS: Record<string, string> = {
  INVALID_STRENGTH: "This drug doesn't come in this strength, so it was probably misread.",
  IDENTIFIER_INVALID: 'This ID fails its check-digit test, so a digit may be misread.',
  POSSIBLE_QUANTITY_CONFLICT: "The quantity doesn't match the directions.",
  UNREADABLE_SOURCE: "This part of the fax couldn't be read.",
  PARTIAL_SOURCE: "Some characters couldn't be read.",
  MISSING_FIELD: "This is required, but it wasn't found on the fax.",
  PATIENT_IDENTITY_CONFLICT: "The patient's name or date of birth differs between two places on the fax.",
  UNVERIFIED_DRUG: "The drug name doesn't match a known drug.",
  AMBIGUOUS_DRUG: 'The drug name could be read as more than one drug.',
  UNSUPPORTED_SIG: "The directions use wording that couldn't be interpreted.",
  MISSING_EVIDENCE: "We couldn't find where this is written on the fax.",
  DUPLICATE_DOCUMENT: 'The same fax was uploaded before. Reject this copy.',
}

/** Plain-language reason, plus the specific failed check(s) when the backend gives them. */
export function issueExplanation(exception: Exception, field?: FieldResult): { reason: string; detail: string | null } {
  const failed = (field?.signals ?? []).filter((signal) => signal.status === 'FAIL' || signal.status === 'AMBIGUOUS')
  let reason = ISSUE_REASONS[exception.type]
  if (!reason && exception.type.startsWith('AMBIGUOUS_')) {
    reason = failed.some((signal) => signal.type === 'CROSS_PASS') ? 'The two readers read this differently.' : 'This is easy to misread.'
  }
  const details = failed.map((signal) => signal.detail).filter((detail): detail is string => Boolean(detail))
  return { reason: reason ?? exception.reason, detail: details.length ? details.join(' ') : null }
}
