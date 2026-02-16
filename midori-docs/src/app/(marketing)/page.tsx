import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <p>MIDORI LANGUAGE</p>
        <h1>Build fast, safe systems with a language that stays readable.</h1>
        <p>
          MIDORI is an LLVM-backed language with safety-first defaults, explicit semantics,
          and a practical compiler pipeline designed for long-term engineering work.
        </p>
        <div className="hero__actions">
          <Link className="btn btn--primary" href="/docs/getting-started">
            Start with Docs
          </Link>
          <Link className="btn btn--ghost" href="https://github.com/ByteCraft-Co/MIDORI">
            View Compiler Repo
          </Link>
        </div>
      </section>

      <section className="section">
        <div className="card-grid">
          <article className="card">
            <h3>Language Reference</h3>
            <p>Track syntax, typing, ownership, and safety behavior with versioned specs.</p>
          </article>
          <article className="card">
            <h3>Compiler Internals</h3>
            <p>Understand lexer, parser, typechecker, MIR, borrow pass, and LLVM emission.</p>
          </article>
          <article className="card">
            <h3>Release Discipline</h3>
            <p>Follow changelog-driven releases tied directly to compiler tags.</p>
          </article>
        </div>
      </section>
    </>
  );
}
