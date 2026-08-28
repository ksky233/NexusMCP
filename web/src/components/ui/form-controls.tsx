import type {
  HTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import { cn } from "@/lib/cn";

const controlClassName =
  "w-full rounded-[3px] border border-slate/30 bg-paper text-sm font-normal text-ink outline-none transition-[border-color,box-shadow,background-color] duration-200 placeholder:text-slate/40 hover:border-slate/45 focus:border-slate/70 focus:ring-3 focus:ring-slate/7 disabled:cursor-not-allowed disabled:bg-mist/65 disabled:text-slate/40 aria-invalid:border-wine/50 aria-invalid:shadow-[inset_0_0_9px_rgba(116,48,62,0.04)]";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(controlClassName, "h-[42px] px-3.5", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(controlClassName, "min-h-28 resize-y px-3.5 py-3 leading-6", className)}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(controlClassName, "h-[42px] px-3.5", className)} {...props} />;
}

export function FieldLabel({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn("mb-2 block text-xs font-normal text-slate", className)} {...props} />
  );
}

export function FieldHelp({
  className,
  error = false,
  ...props
}: HTMLAttributes<HTMLParagraphElement> & { error?: boolean }) {
  return (
    <p
      className={cn("mt-1.5 text-xs leading-5 text-slate/55", error && "text-wine", className)}
      {...props}
    />
  );
}
