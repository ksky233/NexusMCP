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

  expect(
    screen.getByText("Local Development Admin · Not Production Authentication"),
  ).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Control plane" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Tool Catalog" })).toHaveAttribute("href", "/catalog");
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

  await user.click(screen.getByRole("button", { name: "Open navigation" }));
  expect(screen.getByRole("dialog", { name: "Control plane navigation" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Close navigation" }));
  expect(
    screen.queryByRole("dialog", { name: "Control plane navigation" }),
  ).not.toBeInTheDocument();
});
