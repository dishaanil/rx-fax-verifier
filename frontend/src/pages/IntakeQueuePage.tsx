import type { Prescription } from '../types/prescription'
import { StatusBadge } from '../components/StatusBadge'
import { useRef, useState } from 'react'
import brandIcon from '../assets/rxbridge-icon.png'

export function IntakeQueuePage({ prescriptions, onOpen, onUpload, busy, live }: { prescriptions: Prescription[]; onOpen: (id: string) => void; onUpload: (file: File) => Promise<void>; busy: boolean; live: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [filter, setFilter] = useState('all')
  const [fileError, setFileError] = useState<string | null>(null)
  const ready = prescriptions.filter((item) => item.status === 'READY_FOR_VERIFICATION').length
  const review = prescriptions.filter((item) => ['REVIEW_REQUIRED', 'AWAITING_CLARIFICATION'].includes(item.status)).length
  const visible = prescriptions.filter((item) => filter === 'all' || (filter === 'ready' ? item.status === 'READY_FOR_VERIFICATION' : ['REVIEW_REQUIRED', 'AWAITING_CLARIFICATION'].includes(item.status)))
  function accept(file?: File) {
    if (!file || busy) return
    if (!file.type.startsWith('image/')) { setFileError('Choose a prescription image, such as PNG or JPEG.'); return }
    setFileError(null); void onUpload(file)
  }
  return (
    <main className="queue-page">
      <header className="page-header intake-hero"><div><p className="eyebrow">Prescription workspace</p><h1>From fax to a<br />verified draft.</h1><p>Upload a prescription. Inspect the evidence.<br />Keep pharmacist judgment at every decision.</p></div><img className="hero-mark" src={brandIcon} alt="" /></header>
      <div className="queue-metrics"><div><span>In queue</span><strong>{prescriptions.length}</strong></div><div><span>Needs a decision</span><strong>{review}</strong></div><div><span>Ready for verification</span><strong>{ready}</strong></div></div>
      <section className={`upload-card${dragging ? ' upload-card--dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files[0]) }}>
        <div className="upload-symbol" aria-hidden="true">↑</div><div><h2>{busy ? 'Uploading & extracting…' : 'Bring in a prescription'}</h2><p>Drop an image here or choose a file to start review.</p><small>Prescription images · PNG, JPEG and other supported image formats</small></div>
        <button type="button" className="primary-button" disabled={busy} onClick={() => input.current?.click()}>{busy ? 'Processing…' : 'Upload prescription'}</button>
        <input ref={input} id="prescription-upload" type="file" accept="image/*" hidden disabled={busy} onChange={(event) => { accept(event.target.files?.[0]); event.target.value = '' }} />
      </section>
      {fileError && <p role="alert" className="error-banner">{fileError}</p>}
      {!live && <p className="preview-banner"><span>Example preview</span> You’re viewing a sample prescription. Live upload and review require the prescription service.</p>}
      <div className="queue-toolbar"><div><p className="eyebrow">Intake queue</p><h2>Prescriptions</h2></div><div className="queue-filters" aria-label="Filter prescriptions">{[['all', 'All'], ['review', 'Needs review'], ['ready', 'Ready']].map(([key, label]) => <button type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label}</button>)}</div></div>
      <section className="queue-card">
        <div className="queue-head"><span>Patient</span><span>Status</span><span>Unresolved fields</span><span>Received</span></div>
        {visible.map((prescription) => (
          <button className="queue-row" type="button" key={prescription.prescription_id} onClick={() => onOpen(prescription.prescription_id)}>
            <strong>{prescription.fields.patient?.normalized_value ?? prescription.fields.patient?.raw_value ?? 'Identity needs review'}</strong>
            <StatusBadge status={prescription.status} />
            <span>{new Set(prescription.exceptions.filter((item) => item.severity === 'CRITICAL').map((item) => item.field)).size} decisions</span>
            <span>{prescription.audit_events[0]?.ts ? new Date(prescription.audit_events[0].ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
          </button>
        ))}
        {visible.length === 0 && <p className="empty-queue">{prescriptions.length === 0 ? 'No prescriptions yet. Upload an image to start.' : 'No prescriptions match this filter.'}</p>}
      </section>
    </main>
  )
}
