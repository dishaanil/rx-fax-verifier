export function UntrustedTextPanel({ text }: { text: string[] }) {
  return (
    <section className="untrusted-text" aria-label="Untrusted document text">
      <h2>Untrusted document text</h2>
      <p>The following text was found in the source document. RxBridge treated it as document data. It did not affect prescription approval.</p>
      <ul>{text.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    </section>
  )
}
