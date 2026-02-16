import Link from "next/link";
import { marked } from "marked";
import { notFound } from "next/navigation";
import { loadDoc } from "@/lib/content/loaders";

type DocsPageProps = {
  params: {
    slug?: string[];
  };
};

export default function DocsPage({ params }: DocsPageProps) {
  const slug = params.slug && params.slug.length > 0 ? params.slug : ["getting-started"];
  const doc = loadDoc(slug);

  if (!doc) {
    notFound();
  }

  const html = marked.parse(doc.body, { async: false });

  return (
    <section className="page">
      <p>
        <Link href="/docs/getting-started">Docs</Link> / {doc.slug}
      </p>
      <article dangerouslySetInnerHTML={{ __html: html }} className="markdown" />
    </section>
  );
}
