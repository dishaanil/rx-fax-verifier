import { fieldLabel } from '../lib/review'
import type { PhoneCall } from '../types/prescription'

/** "Robert Hughes, MD" -> "Dr. Hughes" */
export function doctorName(prescriber: string): string {
  const last = prescriber.split(',')[0].trim().split(/\s+/).at(-1)
  return last ? `Dr. ${last}` : 'the prescriber'
}

const PhoneIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
  </svg>
)

/** The latest call about this issue: in progress, answered (pharmacist applies it) or not clarified. */
export function PrescriberCall({ call, disabled, onUse, onCallAgain, onReject }: {
  call: PhoneCall
  disabled: boolean
  onUse: () => void
  onCallAgain: () => void
  onReject: () => void
}) {
  const doctor = doctorName(call.prescriber)
  const tel = `tel:${call.to_number.replace(/[^\d+]/g, '')}`
  const state = call.status === 'CALLING' ? 'calling' : call.status === 'ANSWERED' ? 'answered' : 'unclear'
  const raised = (call.corrections ?? []).filter((c) => c.exception_id)

  return (
    <section className={`call call--${state}`} aria-live="polite">
      <header className="call__top">
        <span className="call__icon"><PhoneIcon /></span>
        <h3>
          {state === 'calling' && <>Calling {doctor}<span className="call__dots" aria-hidden="true" /></>}
          {state === 'answered' && <>{doctor} answered</>}
          {state === 'unclear' && <>Couldn't be clarified by phone</>}
        </h3>
        {call.simulated && <span className="chip call__sim" title="No phone call is placed. A model plays the prescriber.">Simulated</span>}
      </header>

      {state === 'calling' && <p className="call__line">
        {call.to_number} · AI assistant asking: <q>{call.question}</q>
      </p>}

      {state === 'answered' && <>
        <p className="call__answer"><span>{doctor} said</span> <strong>{call.answer}</strong></p>
        {call.summary && <p className="call__line">{call.summary}</p>}
        {call.applied
          ? <p className="call__line">You applied this answer.</p>
          : <div className="call__actions">
              <button type="button" className="button button--primary" disabled={disabled} onClick={onUse}>Use {call.answer}</button>
              <span className="call__hint">Check it against the fax before you use it.</span>
            </div>}
      </>}

      {state === 'unclear' && <>
        {call.summary && <p className="call__line">{call.summary}</p>}
        <p className="call__line">
          You decide: choose the value below, call {doctor} yourself at <a href={tel}>{call.to_number}</a>, or reject the prescription.
        </p>
        <div className="call__actions">
          <button type="button" className="button button--secondary" disabled={disabled} onClick={onCallAgain}>Call again</button>
          <button type="button" className="button button--quiet-danger" disabled={disabled} onClick={onReject}>Reject prescription</button>
        </div>
      </>}

      {raised.length > 0 && <div className="call__also">
        <strong>{doctor} also corrected</strong>
        <ul>{raised.map((c) => <li key={c.field}>{fieldLabel(c.field)}: <b>{c.value}</b> — added as an issue to review</li>)}</ul>
      </div>}

      <Transcript call={call} />

      {call.simulated && state !== 'calling' && <p className="call__note">Simulated call: no phone call was placed. The prescriber's replies come from a model.</p>}
    </section>
  )
}

/** Shown on an issue the prescriber raised during a call about something else. */
export function CorrectionSource({ call, value, quote }: { call: PhoneCall; value: string; quote: string }) {
  const doctor = doctorName(call.prescriber)
  return (
    <section className="call call--answered" aria-label="From the call">
      <header className="call__top">
        <span className="call__icon"><PhoneIcon /></span>
        <h3>{doctor} corrected this on the call</h3>
        {call.simulated && <span className="chip call__sim" title="No phone call is placed. A model plays the prescriber.">Simulated</span>}
      </header>
      <p className="call__answer"><span>{doctor} said</span> <strong>{value}</strong></p>
      {quote && <p className="call__line"><q>{quote}</q></p>}
      <p className="call__line">Nothing has been changed. Check the fax and, if needed, the patient, then choose below.</p>
      <Transcript call={call} />
    </section>
  )
}

function Transcript({ call }: { call: PhoneCall }) {
  if (!call.transcript?.length) return null
  const doctor = doctorName(call.prescriber)
  return (
    <details className="call__transcript">
      <summary>Show conversation <span className="count">{call.transcript.length}</span></summary>
      <ol className="transcript">
        {call.transcript.map((turn, index) => (
          <li key={index} className={`turn turn--${turn.role}`}>
            <small>{turn.role === 'agent' ? 'RxBridge assistant' : doctor}</small>
            <p>{turn.text}</p>
          </li>
        ))}
      </ol>
    </details>
  )
}
