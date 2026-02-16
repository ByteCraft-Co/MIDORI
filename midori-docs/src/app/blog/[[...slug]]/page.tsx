import Link from "next/link";
import { marked } from "marked";
import { notFound } from "next/navigation";
import { loadBlogPost } from "@/lib/content/loaders";

type BlogPageProps = {
  params: {
    slug?: string[];
  };
};

export default function BlogPage({ params }: BlogPageProps) {
  const slug = params.slug && params.slug.length > 0 ? params.slug : ["launch-note"];
  const post = loadBlogPost(slug);

  if (!post) {
    notFound();
  }

  const html = marked.parse(post.body, { async: false });

  return (
    <section className="page">
      <p>
        <Link href="/blog/launch-note">Blog</Link> / {post.slug}
      </p>
      <article dangerouslySetInnerHTML={{ __html: html }} className="markdown" />
    </section>
  );
}
