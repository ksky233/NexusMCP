import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="page-enter grid min-h-[60vh] place-items-center text-center">
      <div>
        <p className="eyebrow">404 · Route not found</p>
        <h1 className="page-title">This control plane route does not exist.</h1>
        <p className="page-description mx-auto">
          Use the governed navigation instead of constructing internal URLs manually.
        </p>
        <Link
          className="mt-6 inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-strong"
          to="/"
        >
          Return to dashboard
        </Link>
      </div>
    </section>
  );
}
