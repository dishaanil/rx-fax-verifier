export function ReviewActions({ disabled, canConfirm, canCorrect, onAction }: { disabled: boolean; canConfirm: boolean; canCorrect: boolean; onAction: (action: string) => void }) {
  return (
    <div className="review-actions">
      <button type="button" disabled={disabled || !canConfirm} onClick={() => onAction('CONFIRM')}>Confirm</button>
      <button type="button" disabled={disabled || !canCorrect} onClick={() => onAction('CORRECT')}>Correct</button>
      <button type="button" disabled={disabled} onClick={() => onAction('MARK_UNREADABLE')}>Mark unreadable</button>
      <button type="button" disabled title="Awaiting backend action contract">Request clarification</button>
      <button type="button" className="button--quiet" disabled title="Awaiting backend action contract">Reject draft</button>
    </div>
  )
}
