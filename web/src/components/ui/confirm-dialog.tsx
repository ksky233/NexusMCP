import { Dialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ConfirmDialog({
  open,
  onOpenChange,
  eyebrow = "Confirm action",
  title,
  description,
  confirmLabel,
  onConfirm,
  danger = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  eyebrow?: string;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  danger?: boolean;
}) {
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-ink/28 backdrop-blur-[1px] transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
        <Dialog.Viewport className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4">
          <Dialog.Popup className="w-full max-w-lg rounded-[6px] border border-slate/30 bg-paper shadow-overlay transition-[opacity,transform] duration-200 data-[ending-style]:scale-[0.98] data-[ending-style]:opacity-0 data-[starting-style]:scale-[0.98] data-[starting-style]:opacity-0">
            <div className="p-6 sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="component-label">{eyebrow}</p>
                  <Dialog.Title className="mt-2 text-xl font-normal text-ink">{title}</Dialog.Title>
                </div>
                <Dialog.Close
                  aria-label="Close dialog"
                  className="grid size-9 cursor-pointer place-items-center rounded-[3px] border border-transparent text-slate/55 outline-none hover:border-slate/20 hover:bg-mist focus-visible:ring-2 focus-visible:ring-slate/45"
                >
                  <X aria-hidden="true" className="size-4" />
                </Dialog.Close>
              </div>
              <Dialog.Description className="mt-4 text-sm leading-7 text-slate/70">
                {description}
              </Dialog.Description>
              <div className="mt-7 flex justify-end gap-3 border-t border-slate/15 pt-5">
                <Dialog.Close render={<Button variant="secondary" />}>Cancel</Dialog.Close>
                <Button onClick={onConfirm} variant={danger ? "danger" : "primary"}>
                  {confirmLabel}
                </Button>
              </div>
            </div>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
