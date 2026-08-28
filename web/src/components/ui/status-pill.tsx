import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const statusVariants = cva(
  "inline-flex min-h-[30px] items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1 text-xs font-normal tracking-[0.03em] before:size-1.5 before:shrink-0 before:rounded-full before:bg-current before:opacity-70",
  {
    variants: {
      tone: {
        active:
          "border-teal/40 bg-teal/10 text-teal before:opacity-100 before:shadow-[0_0_0_3px_rgba(0,173,181,0.10)]",
        completed: "border-ink bg-ink text-mist",
        pending: "border-slate/15 bg-mist text-slate",
        review: "border-slate/30 bg-paper text-ink",
        draft: "border-dashed border-slate/30 bg-transparent text-slate/70",
        failed:
          "border-wine/50 bg-[repeating-linear-gradient(-45deg,#fff,#fff_5px,#eee_5px,#eee_10px)] text-wine shadow-[inset_0_0_12px_rgba(116,48,62,0.10)]",
        neutral: "border-slate/15 bg-paper text-slate/55",
      },
    },
    defaultVariants: {
      tone: "neutral",
    },
  },
);

type StatusPillProps = HTMLAttributes<HTMLSpanElement> & VariantProps<typeof statusVariants>;

export function StatusPill({ className, tone, ...props }: StatusPillProps) {
  return <span className={cn(statusVariants({ tone }), className)} {...props} />;
}
