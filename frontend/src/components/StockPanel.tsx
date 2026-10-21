import { useEffect, useState } from 'react'
import { getStock } from '../api/prescriptions'
import { FILL_LABELS } from '../lib/review'
import type { FillAction, Fulfillment, Prescription, StockCheck } from '../types/prescription'

const n = (value: number | null | undefined) => (value == null ? '—' : Number.isInteger(value) ? String(value) : value.toFixed(1))

const TONE: Record<StockCheck['status'], string> = {
  IN_STOCK: 'ok', PARTIAL: 'warn', OUT_OF_STOCK: 'danger', NOT_STOCKED: 'danger', NOT_CHECKED: 'muted',
}
const TITLE: Record<StockCheck['status'], string> = {
  IN_STOCK: 'In stock', PARTIAL: 'Not enough in stock', OUT_OF_STOCK: 'Out of stock', NOT_STOCKED: 'Not stocked here', NOT_CHECKED: 'Stock not checked',
}

/**
 * Before approval: where the medicine is and whether there's enough (information only).
 * After approval: the Fill step, with only the options the stock allows. Stock never rejects a prescription.
 */
export function StockPanel({ prescription, onFulfill, disabled }: {
  prescription: Prescription
  onFulfill: (action: FillAction, pharmacy?: string) => void
  disabled: boolean
}) {
  const [stock, setStock] = useState<StockCheck | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pharmacy, setPharmacy] = useState('')
  const approved = prescription.status === 'APPROVED'
  const done = prescription.fulfillment
  // Re-check whenever the values the lookup depends on, or the fill decision, change.
  const key = JSON.stringify([prescription.status, prescription.fulfillment?.at, ...['drug', 'strength', 'form', 'quantity']
    .map((name) => prescription.fields[name]?.normalized_value ?? prescription.fields[name]?.raw_value)])

  useEffect(() => {
    let cancelled = false
    getStock(prescription.prescription_id)
      .then((value) => { if (!cancelled) { setStock(value); setError(null) } })
      .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : 'Stock lookup failed.') })
    return () => { cancelled = true }
  }, [prescription.prescription_id, key])

  if (done) return <FillOutcome fulfillment={done} />
  if (error) return <p className="note">Stock lookup unavailable: {error}</p>
  if (!stock) return <p className="note">Checking stock…</p>

  const tone = TONE[stock.status]
  const owed = (stock.needed ?? 0) - (stock.on_hand ?? 0)
  return (
    <section className={`stock stock--${tone}${approved ? ' stock--fill' : ''}`} aria-label="Stock">
      <header className="stock__top">
        <span className={`stock__dot stock__dot--${tone}`} aria-hidden="true" />
        <h3>{approved ? `Fill · ${TITLE[stock.status].toLowerCase()}` : TITLE[stock.status]}</h3>
      </header>
      {stock.location && stock.status !== 'NOT_STOCKED' && <p className="stock__where">
        <span>Shelf</span> <strong>{stock.location}</strong>
      </p>}
      <p className="stock__line">{stock.message}</p>
      {stock.status === 'PARTIAL' && <p className="stock__line">{n(stock.on_hand)} on hand · {n(stock.needed)} needed · {n(owed)} short</p>}
      {!approved && stock.status !== 'NOT_CHECKED' && <p className="stock__hint">Stock doesn't affect approval. You'll choose how to fill it after approving.</p>}

      {approved && stock.options.length > 0 && <div className="stock__options">
        {stock.options.includes('FILL') && <button type="button" className="button button--primary" disabled={disabled} onClick={() => onFulfill('FILL')}>
          Mark filled · {n(stock.needed)} {stock.unit}
        </button>}
        {stock.options.includes('PARTIAL_FILL') && <button type="button" className="button button--primary" disabled={disabled} onClick={() => onFulfill('PARTIAL_FILL')}>
          Fill {n(stock.on_hand)} now, owe {n(owed)}
        </button>}
        {stock.options.includes('ORDER') && <button type="button" className="button button--secondary" disabled={disabled} onClick={() => onFulfill('ORDER')}>
          Order it · arrives {stock.eta}
        </button>}
        {stock.options.includes('TRANSFER') && <div className="stock__transfer">
          <input className="option__input" value={pharmacy} placeholder="Pharmacy name (optional)" aria-label="Pharmacy to send it to"
            onChange={(event) => setPharmacy(event.target.value)} disabled={disabled} />
          <button type="button" className="button button--secondary" disabled={disabled} onClick={() => onFulfill('TRANSFER', pharmacy)}>
            Send to another pharmacy
          </button>
        </div>}
      </div>}
    </section>
  )
}

function FillOutcome({ fulfillment: f }: { fulfillment: Fulfillment }) {
  const detail = {
    FILL: `${n(f.dispensed)} ${f.unit} picked from ${f.location}.`,
    PARTIAL_FILL: `${n(f.dispensed)} ${f.unit} picked from ${f.location}; ${n(f.owed)} owed, arriving ${f.eta}.`,
    ORDER: `${f.product ?? 'Stock'} ordered; arriving ${f.eta}. Fill when it comes in.`,
    TRANSFER: `Sent to ${f.pharmacy}. Let the patient know where to collect it.`,
  }[f.action]
  return (
    <section className="stock stock--ok stock--fill" aria-label="Fill">
      <header className="stock__top">
        <span className="stock__dot stock__dot--ok" aria-hidden="true" />
        <h3>{FILL_LABELS[f.action]}</h3>
      </header>
      <p className="stock__line">{detail}</p>
      <p className="stock__hint">Recorded by {f.by}.</p>
    </section>
  )
}
