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
  source_evidence: (Evidence & { text?: string[] }) | null  // text: instruction-like lines found on the fax
  candidate_values: string[]
  required_action: string
}

export type Prescription = {
  prescription_id: string
  status: PrescriptionStatus
  source: { type: string; original_path: string; processed_path: string; sha256: string; untrusted_text?: string[] }
  fields: Record<string, FieldResult>
  exceptions: Exception[]
  clarifications: Clarification[]
  approved_by: string | null
  audit_events: AuditEvent[]
  fulfillment?: Fulfillment | null
}

export type StockStatus = 'IN_STOCK' | 'PARTIAL' | 'OUT_OF_STOCK' | 'NOT_STOCKED' | 'NOT_CHECKED'
export type FillAction = 'FILL' | 'PARTIAL_FILL' | 'ORDER' | 'TRANSFER'

/** Shelf stock for the verified drug, strength and quantity. Information only: never affects approval. */
export type StockCheck = {
  status: StockStatus
  message: string
  product: string | null
  location: string | null
  on_hand: number | null
  needed: number | null
  unit: string | null
  eta: string | null
  options: FillAction[]
}

/** The pharmacist's fill decision after approval. */
export type Fulfillment = {
  action: FillAction
  product: string | null
  unit: string | null
  location: string | null
  needed: number | null
  dispensed: number
  owed: number
  eta: string | null
  pharmacy: string | null
  by: string
  at: string
}

/** A request for the prescriber to clarify one exception: by any channel, or a phone call. */
export type Clarification = {
  exception_id: string
  status: 'REQUESTED' | 'RESOLVED' | CallStatus
  channel?: 'PHONE'
} & Partial<Omit<PhoneCall, 'exception_id' | 'status' | 'channel'>>

export type CallStatus = 'CALLING' | 'ANSWERED' | 'UNCLEAR' | 'FAILED'
export type CallTurn = { role: 'agent' | 'prescriber'; text: string }

/** A call to the prescriber. Its answer is evidence: only the pharmacist can apply it. */
export type PhoneCall = {
  exception_id: string
  status: CallStatus
  channel: 'PHONE'
  call_id: string
  simulated: boolean
  to_number: string
  prescriber: string
  field_label: string
  question: string
  started_at: string
  answer?: string | null
  summary?: string
  transcript?: CallTurn[]
  ended_at?: string
  applied?: boolean
  // Other values the prescriber said are wrong; exception_id is the issue opened for each (null if none was needed).
  corrections?: CallCorrection[]
}

export type CallCorrection = { field: string; value: string; quote: string; exception_id: string | null }

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
