import { useRef, useState } from 'react'
import { StatusBadge } from '../components/StatusBadge'
import { FINISHED, NEEDS_REVIEW, fieldValue, receivedAt } from '../lib/review'
import type { Prescription } from '../types/prescription'

const FILTERS = [
  { key: 'all', label: 'All', match: () => true },
  { key: 'review', label: 'Needs review', match: (rx: Prescription) => NEEDS_REVIEW.includes(rx.status) },
  { key: 'ready', label: 'Ready to approve', match: (rx: Prescription) => rx.status === 'READY_FOR_VERIFICATION' },
  { key: 'done', label: 'Done', match: (rx: Prescription) => FINISHED.includes(rx.status) },
] as const

export function IntakeQueuePage({ prescriptions, onOpen, onUpload, busy, live }: { prescriptions: Prescription[]; onOpen: (id: string) => void; onUpload: (file: File) => Promise<void>; busy: boolean; live: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('all')
  const [fileError, setFileError] = useState<string | null>(null)
  const active = FILTERS.find((item) => item.key === filter)!
  const visible = prescriptions.filter(active.match)

  function accept(file?: File) {
    if (!file || busy) return
    if (!file.type.startsWith('image/')) { setFileError('Choose a prescription image, such as PNG or JPEG.'); return }
    setFileError(null); void onUpload(file)
  }

  return (
    <main className="queue">
      <header className="queue__header">
        <div>
          <h1>Prescriptions</h1>
          <p className="muted">Upload a faxed prescription. Review anything uncertain against the fax, then approve.</p>
        </div>
      </header>

      <section
        className={`dropzone${dragging ? ' dropzone--active' : ''}${busy ? ' dropzone--busy' : ''}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files[0]) }}
      >
        {busy ? <span className="spinner" aria-hidden="true" /> : <span className="dropzone__icon" aria-hidden="true">↑</span>}
        <div>
          <strong>{busy ? 'Reading the fax…' : 'Drop a fax image here'}</strong>
          <span className="muted">{busy ? 'This takes a few seconds.' : 'PNG or JPEG'}</span>
        </div>
        <button type="button" className="button button--primary" disabled={busy} onClick={() => input.current?.click()}>Choose file</button>
        <input ref={input} type="file" accept="image/*" hidden disabled={busy} onChange={(event) => { accept(event.target.files?.[0]); event.target.value = '' }} />
      </section>
      {fileError && <p role="alert" className="banner banner--error">{fileError}</p>}
      {!live && <p className="note">Preview: showing a sample prescription. Start the prescription service to upload and review.</p>}

      <div className="tabs" role="group" aria-label="Filter prescriptions">
        {FILTERS.map((item) => (
          <button type="button" key={item.key} aria-pressed={filter === item.key} onClick={() => setFilter(item.key)}>
            {item.label} <span className="count">{prescriptions.filter(item.match).length}</span>
          </button>
        ))}
      </div>

      <section className="card table" aria-label="Prescription queue">
        <div className="table__head" aria-hidden="true"><span>Patient</span><span>Medication</span><span>Status</span><span>Open issues</span><span>Received</span></div>
        {visible.map((rx) => {
          const issues = rx.exceptions.length
          const medication = [rx.fields.drug, rx.fields.strength].map((field) => field && fieldValue(field)).filter(Boolean).join(' ')
          return (
            <button className="table__row" type="button" key={rx.prescription_id} onClick={() => onOpen(rx.prescription_id)}>
              <strong>{(rx.fields.patient && fieldValue(rx.fields.patient)) ?? 'Unknown patient'}</strong>
              <span>{medication || '—'}</span>
              <span><StatusBadge status={rx.status} /></span>
              <span className={issues ? 'issues' : 'muted'}>{issues ? `${issues} to resolve` : 'None'}</span>
              <span className="muted">{receivedAt(rx)}</span>
            </button>
          )
        })}
        {visible.length === 0 && <p className="table__empty">{prescriptions.length === 0 ? 'No prescriptions yet. Upload a fax to start.' : 'Nothing here.'}</p>}
      </section>
    </main>
  )
}
