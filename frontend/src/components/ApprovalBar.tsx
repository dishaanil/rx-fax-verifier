import type { Prescription } from '../types/prescription'
import { StatusBadge } from './StatusBadge'

export function ApprovalBar({ prescription, onApprove, apiReady }: { prescription: Prescription; onApprove: () => void; apiReady: boolean }) {
  const unresolvedCritical = prescription.exceptions.filter((item) => item.severity === 'CRITICAL').length
  const mayRequestApproval = prescription.status === 'READY_FOR_VERIFICATION'
  return (
    <footer className="approval-bar">
      <div>
        <StatusBadge status={prescription.status} />
        {prescription.status === 'REVIEW_REQUIRED' && <strong>NOT READY — {unresolvedCritical} decisions remain</strong>}
      </div>
      <button type="button" disabled={!mayRequestApproval || !apiReady} onClick={onApprove}>
        Request pharmacist approval
      </button>
    </footer>
  )
}
