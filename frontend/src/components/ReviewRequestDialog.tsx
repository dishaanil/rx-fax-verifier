import { useEffect, useRef, useState } from 'react'

export type ReviewDraft = { kind: 'clarification' | 'rejection'; field: string; note: string; createdAt: string }

export function ReviewRequestDialog({ kind, field, onClose, onSave }: { kind: ReviewDraft['kind']; field: string; onClose: () => void; onSave: (draft: ReviewDraft) => void }) {
  const [note, setNote] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close() }, [])
  return <dialog ref={dialog} className="request-dialog" aria-labelledby="request-title" onCancel={onClose}>
      <p className="eyebrow">Pharmacist action · {field.replaceAll('_', ' ')}</p>
      <h2 id="request-title">{kind === 'clarification' ? 'Request prescriber clarification' : 'Reject prescription'}</h2>
      <p>{kind === 'clarification' ? 'Describe what the prescriber needs to clarify. Their response must be accepted by a pharmacist before the order can proceed.' : 'Record why this prescription should be rejected.'}</p>
      <label>{kind === 'clarification' ? 'Question for the prescriber' : 'Rejection reason'}<textarea autoFocus rows={5} value={note} onChange={(event) => setNote(event.target.value)} placeholder={kind === 'clarification' ? 'Please confirm the drug name and intended strength…' : 'Document is a duplicate, misdirected, or unusable…'} /></label>
      <p className="draft-disclosure">Draft only: the backend has no submission contract for this action yet. Saving keeps a note in this screen; it does not contact anyone or change prescription status.</p>
      <div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button type="button" className="primary-button" disabled={!note.trim()} onClick={() => { onSave({ kind, field, note: note.trim(), createdAt: new Date().toISOString() }); onClose() }}>Save local draft</button></div>
  </dialog>
}
