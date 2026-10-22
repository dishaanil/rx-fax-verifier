import { useState } from 'react'
import type { ResolutionAction } from '../api/prescriptions'
import { clarificationRequested, correctionSource, fieldLabel, fieldValue, issueExplanation, issueQuestion, latestCall, readerLabel } from '../lib/review'
import type { Exception, Prescription } from '../types/prescription'
import { CorrectionSource, doctorName, PrescriberCall } from './PrescriberCall'
import { SourceCrop } from './SourceCrop'

const OTHER = '__other__'

export function IssuePanel({ prescription, exception, position, total, onMove, onResolve, onCall, onReject, disabled, documentUrl }: {
  prescription: Prescription
  exception: Exception
  position: number
  total: number
  onMove: (step: -1 | 1) => void
  onResolve: (action: ResolutionAction, value?: string) => void
  onCall: () => void
  onReject: () => void
  disabled: boolean
  documentUrl: string
}) {
  const [choice, setChoice] = useState<string | null>(null)
  const [other, setOther] = useState('')
  const field = prescription.fields[exception.field]
  const evidence = exception.source_evidence?.bbox ? exception.source_evidence : field?.evidence
  const options = [...new Set(exception.candidate_values)]
  const readings = field?.reads.filter((read) => read.value) ?? []
  const asked = clarificationRequested(prescription, exception.exception_id)
  const call = latestCall(prescription, exception.exception_id)
  const correction = correctionSource(prescription, exception.exception_id)
  const calling = call?.status === 'CALLING'
  const phone = prescription.fields.prescriber_phone ? fieldValue(prescription.fields.prescriber_phone) : null
  const prescriber = prescription.fields.prescriber ? fieldValue(prescription.fields.prescriber) : null
  const value = choice === OTHER ? other.trim() : choice
  const { reason, detail } = issueExplanation(exception, field)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!value) return
    onResolve(choice === OTHER ? 'CORRECT' : 'SELECT_VALUE', value)
  }

  return (
    <section className="card issue" aria-labelledby="issue-question">
      <header className="issue__top">
        <span className="eyebrow">Issue {position} of {total}</span>
        {total > 1 && <span className="issue__nav">
          <button type="button" className="icon-button" onClick={() => onMove(-1)} aria-label="Previous issue">‹</button>
          <button type="button" className="icon-button" onClick={() => onMove(1)} aria-label="Next issue">›</button>
        </span>}
      </header>
      <h2 id="issue-question">{issueQuestion(exception)}</h2>
      <p className="issue__reason">{reason}{detail && <small>{detail}</small>}</p>

      {evidence?.bbox && <SourceCrop bbox={evidence.bbox} documentUrl={documentUrl} />}

      {readings.length > 1 && <p className="issue__readings">
        <span>The readers saw</span>
        {readings.map((read) => <span key={`${read.source}-${read.value}`} className="chip"><small>{readerLabel(read.source)}</small> {read.value}</span>)}
      </p>}

      {correction && <CorrectionSource {...correction} />}

      {call && <PrescriberCall call={call} disabled={disabled || calling} onUse={() => onResolve('USE_PRESCRIBER_ANSWER')}
        onCallAgain={onCall} onReject={onReject} />}

      {exception.type === 'DOCUMENT_INSTRUCTION' ? (
        <>
          <ul className="quoted" aria-label="Text found on the fax">
            {(exception.source_evidence?.text ?? []).map((line) => <li key={line}>{line}</li>)}
          </ul>
          <div className="issue__actions">
            <button type="button" className="button button--danger" disabled={disabled} onClick={onReject}>Reject</button>
            <span className="issue__secondary">
              <button type="button" className="link-button" disabled={disabled} onClick={() => onResolve('ACKNOWLEDGE')}>Reviewed — not part of the prescription</button>
            </span>
          </div>
        </>
      ) : exception.required_action === 'REJECT' ? (
        <div className="issue__actions">
          <button type="button" className="button button--danger" disabled={disabled} onClick={onReject}>Reject duplicate</button>
        </div>
      ) : (
        <form onSubmit={submit}>
          {asked && <p className="note">You asked the prescriber to clarify. Enter the value here once they reply.</p>}
          <fieldset className="options" disabled={disabled}>
            <legend>{correction ? `Choose the correct ${fieldLabel(exception.field).toLowerCase()}` : 'Choose what the fax says'}</legend>
            {options.map((option) => (
              <label key={option} className={`option${choice === option ? ' option--selected' : ''}`}>
                <input type="radio" name="value" checked={choice === option} onChange={() => setChoice(option)} />
                <span>{option}</span>
                {correction && <small className="option__source">{option === correction.value ? `said by ${doctorName(correction.call.prescriber)}` : 'read from the fax'}</small>}
              </label>
            ))}
            <label className={`option option--other${choice === OTHER ? ' option--selected' : ''}`}>
              <input type="radio" name="value" checked={choice === OTHER} onChange={() => setChoice(OTHER)} />
              <span>{options.length ? 'Something else' : 'Enter the value'}</span>
              <input
                type="text"
                className="option__input"
                value={other}
                placeholder="Type exactly what is written"
                aria-label="Value written on the fax"
                onFocus={() => setChoice(OTHER)}
                onChange={(event) => setOther(event.target.value)}
              />
            </label>
          </fieldset>
          <div className="issue__actions">
            <button type="submit" className="button button--primary" disabled={disabled || !value}>Use this value</button>
            <span className="issue__secondary">
              <button type="button" className="link-button" disabled={disabled} onClick={() => onResolve('MARK_UNREADABLE')}>Can't read it</button>
              {phone && !call && <button type="button" className="link-button" disabled={disabled} onClick={onCall}
                title={`An AI assistant calls ${phone} and asks what was prescribed`}>Call {prescriber ? doctorName(prescriber) : 'prescriber'}</button>}
              {!phone && !asked && <button type="button" className="link-button" disabled={disabled} onClick={() => onResolve('REQUEST_CLARIFICATION')}>Ask prescriber</button>}
            </span>
          </div>
        </form>
      )}
    </section>
  )
}
