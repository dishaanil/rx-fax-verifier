import { reviewSteps } from '../lib/review'
import type { Prescription } from '../types/prescription'

const MARKS = { done: '✓', stopped: '✕' } as const

export function Stepper({ prescription }: { prescription: Prescription }) {
  return (
    <ol className="stepper" aria-label="Review progress">
      {reviewSteps(prescription).map((step, index) => (
        <li key={step.label} className={`step step--${step.state}`} aria-current={step.state === 'current' ? 'step' : undefined}>
          <span className="step__mark" aria-hidden="true">{step.state === 'done' || step.state === 'stopped' ? MARKS[step.state] : index + 1}</span>
          <span className="step__text"><strong>{step.label}</strong>{step.detail && <small>{step.detail}</small>}</span>
        </li>
      ))}
    </ol>
  )
}
