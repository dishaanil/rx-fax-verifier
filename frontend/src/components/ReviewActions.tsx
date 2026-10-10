export function ReviewActions({ disabled, canSelect, canConfirm, canCorrect, rejectOnly = false, onAction }: { disabled: boolean; canSelect?: boolean; canConfirm?: boolean; canCorrect?: boolean; rejectOnly?: boolean; onAction: (action: string) => void }) {
  return (
    <div className="review-actions">
      {rejectOnly ? <button type="button" className="button--quiet" disabled={disabled} onClick={() => onAction('REJECT')}>Reject prescription</button> : <>
        <button type="button" disabled={disabled || !canSelect} onClick={() => onAction('SELECT_VALUE')}>Use selected candidate</button>
        <button type="button" disabled={disabled || !canConfirm} onClick={() => onAction('CONFIRM')}>Confirm</button>
        <button type="button" disabled={disabled || !canCorrect} onClick={() => onAction('CORRECT')}>Correct</button>
        <button type="button" disabled={disabled} onClick={() => onAction('MARK_UNREADABLE')}>Mark unreadable</button>
        <button type="button" disabled={disabled} onClick={() => onAction('REQUEST_CLARIFICATION')}>Request clarification</button>
        <button type="button" className="button--quiet" disabled={disabled} onClick={() => onAction('REJECT')}>Reject prescription</button>
      </>}
    </div>
  )
}
