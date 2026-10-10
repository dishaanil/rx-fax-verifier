import type { Prescription } from '../types/prescription'
import { StatusBadge } from '../components/StatusBadge'

export function IntakeQueuePage({ prescriptions, onOpen, onUpload, busy, live }: { prescriptions: Prescription[]; onOpen: (id: string) => void; onUpload: (file: File) => Promise<void>; busy: boolean; live: boolean }) {
  return (
    <main className="queue-page">
      <header className="page-header"><p className="eyebrow">RxBridge</p><h1>Prescription intake</h1><p>Evidence-first review queue. Policy, not the interface, decides what can proceed.</p></header>
      <section className="upload-card">
        <label htmlFor="prescription-upload">{busy ? 'Uploading / processing…' : 'Upload a prescription image'}</label>
        <input id="prescription-upload" type="file" accept="image/*" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onUpload(file); event.target.value = '' }} />
        {!live && <p className="fixture-note">Example preview — live API unavailable. Upload requires the prescription service.</p>}
      </section>
      <section className="queue-card">
        <div className="queue-head"><span>Patient</span><span>Status</span><span>Unresolved fields</span><span>Received</span></div>
        {prescriptions.map((prescription) => (
          <button className="queue-row" type="button" key={prescription.prescription_id} onClick={() => onOpen(prescription.prescription_id)}>
            <strong>{prescription.fields.patient?.normalized_value ?? prescription.fields.patient?.raw_value ?? 'Identity needs review'}</strong>
            <StatusBadge status={prescription.status} />
            <span>{prescription.exceptions.length}</span>
            <span>{prescription.audit_events[0]?.ts ? new Date(prescription.audit_events[0].ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
          </button>
        ))}
        {prescriptions.length === 0 && <p className="empty-queue">No prescriptions yet. Upload an image to start.</p>}
      </section>
    </main>
  )
}
