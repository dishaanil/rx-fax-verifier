export function ReviewActions({ disabled, canConfirm, canCorrect, onAction }: { disabled: boolean; canConfirm: boolean; canCorrect: boolean; onAction: (action: string) => void }) {
  return (
    <div className="review-actions">
      <button type="button" disabled={disabled || !canConfirm} onClick={() => onAction('CONFIRM')}>Confirm</button>
      <button type="button" disabled={disabled || !canCorrect} onClick={() => onAction('CORRECT')}>Correct</button>
      <button type="button" disabled={disabled} onClick={() => onAction('MARK_UNREADABLE')}>Mark unreadable</button>
      <button type="button" onClick={() => onAction('REQUEST_CLARIFICATION')}>Request clarification</button>
      <button type="button" className="button--quiet" onClick={() => onAction('REJECT')}>Reject draft</button>
    </div>
  )
}
