import { Button as BaseButton } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex min-h-10 cursor-pointer select-none items-center justify-center gap-2 rounded-[3px] border px-4 text-sm font-normal tracking-[0.02em] transition-[background-color,border-color,color,transform,box-shadow,opacity] duration-200 outline-none hover:-translate-y-px active:translate-y-0 focus-visible:ring-2 focus-visible:ring-slate/45 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:translate-y-0 disabled:border-line disabled:bg-mist/80 disabled:text-slate/40 disabled:shadow-none",
  {
    variants: {
      variant: {
        primary: "border-ink bg-ink text-mist shadow-hairline hover:border-slate hover:bg-slate",
        secondary:
          "border-slate/42 bg-paper text-slate hover:border-slate/60 hover:bg-mist/70 hover:text-ink",
        ghost: "border-transparent bg-transparent text-slate hover:bg-mist hover:text-ink",
        danger: "border-wine/35 bg-wine/6 text-wine hover:border-wine/50 hover:bg-wine/10",
      },
      size: {
        default: "h-10",
        small: "min-h-8 px-3 text-xs",
        icon: "size-10 px-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

type ButtonProps = ComponentProps<typeof BaseButton> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <BaseButton className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
