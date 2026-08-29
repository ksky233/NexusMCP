import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pagination } from "@/components/ui/pagination";
import { StatusPill } from "@/components/ui/status-pill";

test("status pill keeps semantic text alongside its visual tone", () => {
  render(<StatusPill tone="active">Running</StatusPill>);

  const status = screen.getByText("Running");
  expect(status).toHaveClass("text-teal");
  expect(status).toHaveTextContent("Running");
});

test("pagination keeps a bounded window around the current page", async () => {
  const user = userEvent.setup();
  const onPageChange = vi.fn();
  render(<Pagination onPageChange={onPageChange} page={6} totalPages={10} />);

  expect(screen.getByRole("button", { name: "4" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "8" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "6" })).toHaveAttribute("aria-current", "page");
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(onPageChange).toHaveBeenCalledWith(7);
});

test("confirm dialog exposes an accessible decision boundary", async () => {
  const user = userEvent.setup();
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ConfirmDialog
      confirmLabel="Disable upstream"
      danger
      description="New tool calls will no longer resolve through this upstream."
      onConfirm={onConfirm}
      onOpenChange={onOpenChange}
      open
      title="Disable this upstream?"
    />,
  );

  expect(screen.getByRole("dialog", { name: "Disable this upstream?" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Disable upstream" }));
  expect(onConfirm).toHaveBeenCalledOnce();
});
