import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { createAppQueryClient } from "@/app/query-client";
import { AppShell } from "@/layouts/app-shell";

afterEach(() => {
  vi.unstubAllEnvs();
});

test("keeps the local admin warning and accessible navigation visible", () => {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        Component: AppShell,
        children: [{ index: true, element: <p>Dashboard content</p> }],
      },
    ],
    { initialEntries: ["/"] },
  );

  render(<RouterProvider router={router} />);

  expect(screen.getByText("本地开发管理员 · 非生产级身份认证")).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "控制台导航" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "工具目录" })).toHaveAttribute("href", "/catalog");
});

test("opens and closes the accessible mobile navigation", async () => {
  const user = userEvent.setup();
  const router = createMemoryRouter(
    [
      {
        path: "/",
        Component: AppShell,
        children: [{ index: true, element: <p>Dashboard content</p> }],
      },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);

  await user.click(screen.getByRole("button", { name: "打开导航" }));
  expect(screen.getByRole("dialog", { name: "控制台导航" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "关闭导航" }));
  expect(screen.queryByRole("dialog", { name: "控制台导航" })).not.toBeInTheDocument();
});

test("shows the shared identity and reset confirmation in public demo mode", async () => {
  vi.stubEnv("VITE_PUBLIC_DEMO", "true");
  const user = userEvent.setup();
  const router = createMemoryRouter(
    [
      {
        path: "/",
        Component: AppShell,
        children: [{ index: true, element: <p>Dashboard content</p> }],
      },
    ],
    { initialEntries: ["/"] },
  );

  render(
    <QueryClientProvider client={createAppQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  expect(screen.getByText("公开演示身份 · public-demo-admin")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "重置演示工作区" }));
  expect(screen.getByRole("dialog", { name: "恢复演示初始状态？" })).toBeInTheDocument();
});
