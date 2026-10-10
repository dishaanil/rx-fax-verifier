export function CandidateSelector({ values, selectedValue, onChange }: { values: string[]; selectedValue?: string; onChange: (value: string) => void }) {
  return (
    <fieldset className="candidate-selector">
      <legend>Candidate values</legend>
      {values.map((value) => (
        <label key={value}>
          <input type="radio" name="candidate" value={value} checked={selectedValue === value} onChange={() => onChange(value)} />
          {value}
        </label>
      ))}
    </fieldset>
  )
}
