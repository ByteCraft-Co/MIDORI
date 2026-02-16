export default function RoadmapPage() {
  return (
    <section className="page">
      <h1>Roadmap</h1>
      <div className="card-grid">
        <article className="card">
          <h3>Compiler Stabilization</h3>
          <p>Expand borrow-check diagnostics, match lowering, and trait/generic semantics.</p>
        </article>
        <article className="card">
          <h3>Tooling</h3>
          <p>Ship language server, formatter hardening, and improved REPL ergonomics.</p>
        </article>
        <article className="card">
          <h3>Ecosystem</h3>
          <p>Define package manager contracts and standard library support guarantees.</p>
        </article>
      </div>
    </section>
  );
}
