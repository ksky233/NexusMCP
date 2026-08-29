import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="page-enter grid min-h-[60vh] place-items-center text-center">
      <div>
        <p className="eyebrow">404 · 页面不存在</p>
        <h1 className="page-title">未找到对应的控制台页面</h1>
        <p className="page-description mx-auto">
          请通过左侧治理导航访问功能，不要手动拼接内部地址。
        </p>
        <Link
          className="mt-7 inline-flex h-10 items-center rounded-[3px] border border-ink bg-ink px-4 text-sm font-normal text-mist transition-colors hover:border-slate hover:bg-slate focus-visible:ring-2 focus-visible:ring-slate/45 focus-visible:ring-offset-2 focus-visible:outline-none"
          to="/"
        >
          返回系统概览
        </Link>
      </div>
    </section>
  );
}
