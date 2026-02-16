export default function PlaygroundPage() {
  return (
    <section className="page">
      <h1>Playground</h1>
      <p>
        Web playground is planned. For now, use the MIDORI CLI locally to run `.mdr` files
        and validate compiler behavior end-to-end.
      </p>
      <div className="code-block">
        <p>midori run examples/hello.mdr</p>
      </div>
    </section>
  );
}
