import Link from "next/link";
import Image from "next/image";

const navItems = [
  { href: "/docs/getting-started", label: "Docs" },
  { href: "/roadmap", label: "Roadmap" },
  { href: "/changelog", label: "Changelog" },
  { href: "/playground", label: "Playground" },
  { href: "https://github.com/ByteCraft-Co/MIDORI", label: "GitHub" },
];

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <Link href="/" className="brand" aria-label="MIDORI home">
          <Image
            src="/brand/logo/midori-logo.png"
            alt="MIDORI logo"
            width={36}
            height={36}
            priority
          />
          <div>
            <p className="brand__name">MIDORI</p>
            <p className="brand__tag">Programming Language</p>
          </div>
        </Link>

        <nav aria-label="Primary">
          <ul className="site-nav">
            {navItems.map((item) => (
              <li key={item.href}>
                <Link href={item.href}>{item.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
