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
      <div className="hairline-divider my-10" />
      <div className="panel border-dashed p-8 sm:p-10">
        <ArrowUpRight aria-hidden="true" className="size-5 stroke-[1.35] text-slate/55" />
        <p className="component-label mt-7">Implementation boundary</p>
        <h2 className="mt-3 text-lg font-light text-ink">Route and application shell are ready</h2>
        <p className="mt-3 max-w-xl text-sm leading-7 text-slate/65">
          W2 freezes navigation, API, cache and error boundaries. This route will consume its W1
          query contract in W3.
        </p>
      </div>
    </section>
  );
}
