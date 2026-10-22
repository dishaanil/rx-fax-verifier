import type { FillAction, Prescription, StockCheck } from '../types/prescription'
const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
export type ResolutionAction = 'SELECT_VALUE' | 'CORRECT' | 'CONFIRM' | 'MARK_UNREADABLE' | 'REQUEST_CLARIFICATION' | 'USE_PRESCRIBER_ANSWER' | 'ACKNOWLEDGE'
async function request(path: string, options?: RequestInit): Promise<unknown> {
  const response = await fetch(`${base}${path}`, options)
  if (response.status === 204) return null
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await response.json() : null
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `API request failed (${response.status}).`)
  if (!isJson) throw new Error('The prescription API is unavailable or returned a non-JSON response.')
  return body
}
function prescription(value: unknown): Prescription {
  const item = value as Prescription
  if (!item || typeof item.prescription_id !== 'string' || !item.fields || !Array.isArray(item.exceptions) || !item.source) throw new Error('API response does not match the prescription contract.')
  return item
}
export async function getPrescription(id: string): Promise<Prescription> {
  return prescription(await request(`/api/prescriptions/${encodeURIComponent(id)}`))
}
export async function getPrescriptions(): Promise<{ data: Prescription[]; live: boolean }> {
  try {
    const data = await request('/api/prescriptions')
    if (!Array.isArray(data)) throw new Error('Expected a prescription list.')
    const items = await Promise.all(data.map((item) => item?.fields ? prescription(item) :
      typeof item?.prescription_id === 'string' ? getPrescription(item.prescription_id) : Promise.reject(new Error('Queue entry has no prescription ID.'))))
    return { data: items, live: true }
  } catch {
    const response = await fetch('/rx_037.json')
    if (!response.ok) throw new Error('Unable to load the preview prescription.')
    return { data: [prescription(await response.json())], live: false }
  }
}
export async function intakePrescription(file: File): Promise<Prescription> {
  const body = new FormData(); body.append('file', file)
  return prescription(await request('/api/intake', { method: 'POST', body }))
}
export async function resolveException(id: string, exceptionId: string, action: ResolutionAction, value?: string): Promise<Prescription> {
  await request(`/api/exceptions/${encodeURIComponent(exceptionId)}/resolve`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(action === 'SELECT_VALUE' || action === 'CORRECT' ? { action, value } : { action }),
  })
  return getPrescription(id)
}
/** Starts a call to the prescriber; returns at once with the call in progress (poll for the result). */
export async function callPrescriber(exceptionId: string): Promise<Prescription> {
  return prescription(await request(`/api/exceptions/${encodeURIComponent(exceptionId)}/call`, { method: 'POST' }))
}
export async function approvePrescription(id: string): Promise<Prescription> {
  await request(`/api/prescriptions/${encodeURIComponent(id)}/approve`, { method: 'POST' })
  return getPrescription(id)
}
export async function rejectPrescription(id: string): Promise<Prescription> {
  await request(`/api/prescriptions/${encodeURIComponent(id)}/reject`, { method: 'POST' })
  return getPrescription(id)
}
export async function getStock(id: string): Promise<StockCheck> {
  return await request(`/api/prescriptions/${encodeURIComponent(id)}/stock`) as StockCheck
}
export async function fulfillPrescription(id: string, action: FillAction, pharmacy?: string): Promise<Prescription> {
  return prescription(await request(`/api/prescriptions/${encodeURIComponent(id)}/fulfill`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, pharmacy }),
  }))
}
export function prescriptionSourceUrl(id: string): string {
  return `${base}/api/prescriptions/${encodeURIComponent(id)}/source`
}
