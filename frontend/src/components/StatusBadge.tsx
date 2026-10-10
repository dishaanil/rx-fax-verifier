import type { PrescriptionStatus } from '../types/prescription'

const labels: Record<PrescriptionStatus, string> = {
  PROCESSING: 'PROCESSING',
  REVIEW_REQUIRED: 'NOT READY',
  UNPROCESSABLE: 'UNPROCESSABLE',
  AWAITING_CLARIFICATION: 'AWAITING CLARIFICATION',
  READY_FOR_VERIFICATION: 'READY FOR PHARMACIST VERIFICATION',
  APPROVED: '✓ APPROVED BY PHARMACIST',
  REJECTED: 'REJECTED',
}

export function StatusBadge({ status }: { status: PrescriptionStatus }) {
  const tone = status === 'APPROVED' || status === 'READY_FOR_VERIFICATION'
    ? 'success'
    : status === 'REVIEW_REQUIRED' || status === 'AWAITING_CLARIFICATION'
      ? 'danger'
      : 'muted'
  return <span className={`status status--${tone}`}>{labels[status]}</span>
}
