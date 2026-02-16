import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <p>MIDORI Docs Platform</p>
        <div className="site-footer__links">
          <Link href="/docs/getting-started">Documentation</Link>
          <Link href="/about">About</Link>
          <Link href="https://github.com/ByteCraft-Co/MIDORI">Source</Link>
        </div>
      </div>
    </footer>
  );
}
