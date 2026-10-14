import { STATUS_LABELS } from '../lib/review'
import type { PrescriptionStatus } from '../types/prescription'

const TONES: Record<PrescriptionStatus, string> = {
  PROCESSING: 'info',
  REVIEW_REQUIRED: 'warning',
  AWAITING_CLARIFICATION: 'warning',
  READY_FOR_VERIFICATION: 'ready',
  APPROVED: 'success',
  REJECTED: 'danger',
  UNPROCESSABLE: 'danger',
}

export function StatusBadge({ status }: { status: PrescriptionStatus }) {
  return <span className={`badge badge--${TONES[status]}`}>{STATUS_LABELS[status]}</span>
}
