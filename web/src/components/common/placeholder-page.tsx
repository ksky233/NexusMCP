import { ArrowUpRight } from "lucide-react";

export function PlaceholderPage({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section aria-labelledby="placeholder-title" className="page-enter max-w-4xl">
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="placeholder-title" className="page-title">
        {title}
      </h1>
      <p className="page-description">{description}</p>
      <div className="mt-8 rounded-2xl border border-dashed border-line-strong bg-surface/65 p-8">
        <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent">
          <ArrowUpRight aria-hidden="true" className="size-5" />
        </span>
        <h2 className="mt-5 font-semibold text-ink">Route and application shell are ready</h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-ink-muted">
          W2 freezes navigation, API, cache and error boundaries. This route will consume its W1
          query contract in W3.
        </p>
      </div>
    </section>
  );
}
