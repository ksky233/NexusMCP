import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const normalizedTotal = Math.max(totalPages, 1);
  const windowSize = Math.min(normalizedTotal, 5);
  const windowStart = Math.min(Math.max(page - 2, 1), normalizedTotal - windowSize + 1);
  const visiblePages = Array.from({ length: windowSize }, (_, index) => windowStart + index);
  return (
    <nav aria-label="Pagination" className="flex items-center gap-1">
      <Button
        aria-label="Previous page"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        size="small"
        variant="secondary"
      >
        <ChevronLeft aria-hidden="true" className="size-3.5" />
      </Button>
      {visiblePages.map((pageNumber) => (
        <Button
          aria-current={pageNumber === page ? "page" : undefined}
          className="min-w-8 px-2"
          key={pageNumber}
          onClick={() => onPageChange(pageNumber)}
          size="small"
          variant={pageNumber === page ? "primary" : "secondary"}
        >
          {pageNumber}
        </Button>
      ))}
      <Button
        aria-label="Next page"
        disabled={page >= normalizedTotal}
        onClick={() => onPageChange(page + 1)}
        size="small"
        variant="secondary"
      >
        <ChevronRight aria-hidden="true" className="size-3.5" />
      </Button>
    </nav>
  );
}
