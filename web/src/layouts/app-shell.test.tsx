import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { expect, test } from "vitest";

import { AppShell } from "@/layouts/app-shell";

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
