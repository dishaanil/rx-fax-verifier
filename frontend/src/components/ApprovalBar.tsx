import type { Prescription } from '../types/prescription'
import { StatusBadge } from './StatusBadge'

export function ApprovalBar({ prescription, onApprove, onReject, apiReady }: { prescription: Prescription; onApprove: () => void; onReject: () => void; apiReady: boolean }) {
  const unresolvedCritical = prescription.exceptions.filter((item) => item.severity === 'CRITICAL').length
  const mayRequestApproval = prescription.status === 'READY_FOR_VERIFICATION'
  const mayReject = !['APPROVED', 'REJECTED'].includes(prescription.status)
  return (
    <footer className="approval-bar">
      <div>
        <StatusBadge status={prescription.status} />
        {prescription.status === 'REVIEW_REQUIRED' && <strong>NOT READY — {unresolvedCritical} decisions remain</strong>}
      </div>
      <button type="button" disabled={!mayRequestApproval || !apiReady} onClick={onApprove}>
        Approve as pharmacist
      </button>
      {mayReject && <button type="button" className="button--quiet" disabled={!apiReady} onClick={onReject}>Reject prescription</button>}
    </footer>
  )
}
