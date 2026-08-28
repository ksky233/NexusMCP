import { render, screen } from "@testing-library/react";
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
