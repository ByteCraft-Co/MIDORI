import Link from "next/link";

export default function NotFound() {
  return (
    <section className="page">
      <h1>Not Found</h1>
      <p>The page you requested does not exist in this version of MIDORI docs.</p>
      <Link className="btn btn--primary" href="/docs/getting-started">
        Go to Docs
      </Link>
    </section>
  );
}
