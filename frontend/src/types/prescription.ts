export type PrescriptionStatus =
  | 'PROCESSING'
  | 'REVIEW_REQUIRED'
  | 'UNPROCESSABLE'
  | 'AWAITING_CLARIFICATION'
  | 'READY_FOR_VERIFICATION'
  | 'APPROVED'
  | 'REJECTED'

export type FieldDecision =
  | 'EXTRACTED'
  | 'VERIFIED'
  | 'REVIEW_REQUIRED'
  | 'INVALID'
  | 'MISSING'
  | 'UNREADABLE'
  | 'HUMAN_VERIFIED'

export type Signal = { type: string; status: 'PASS' | 'FAIL' | 'WARNING' | 'AMBIGUOUS'; detail: string | null }
export type Read = { source: string; value: string | null }
export type Evidence = { page?: number | null; bbox?: [number, number, number, number] | null }

export type FieldResult = {
  raw_value: string | null
  normalized_value: string | null
  source_quality: 'CLEAR' | 'PARTIAL' | 'UNREADABLE'
  reads: Read[]
  evidence: Evidence | null
  signals: Signal[]
  candidates: string[]
  decision: FieldDecision
  reason: string | null
  resolution: unknown | null
}

export type Exception = {
  exception_id: string
  type: string
  field: string
  severity: string
  reason: string
  source_evidence: Evidence | null
  candidate_values: string[]
  required_action: string
}

export type Prescription = {
  prescription_id: string
  status: PrescriptionStatus
  source: { type: string; original_path: string; processed_path: string; sha256: string; untrusted_text?: string[] }
  fields: Record<string, FieldResult>
  exceptions: Exception[]
  clarifications: unknown[]
  approved_by: string | null
  audit_events: AuditEvent[]
}

/**
 * Backend-owned operational evidence. PRISM results are asynchronous and are
 * displayed here only after they have been persisted with the prescription.
 */
export type AuditEvent = {
  ts: string
  actor: string
  event: string
  exception_id?: string
  detail?: string
  data?: Record<string, string | number | boolean | null>
}
