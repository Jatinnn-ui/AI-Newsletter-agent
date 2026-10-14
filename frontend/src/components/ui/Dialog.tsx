import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button, IconButton } from "./Button";
import { cx } from "./cx";

/**
 * Modal built on the native <dialog> element: showModal() provides focus containment,
 * Escape handling, inert background and focus return to the opener.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className={cx(
        "m-auto w-[min(440px,calc(100vw-32px))] rounded-[12px] border border-line bg-surface p-0 text-fg shadow-[0_24px_64px_-16px_rgba(0,0,0,0.6)] backdrop:bg-black/60",
        className,
      )}
    >
      {open && (
        <div className="fade-in">
          <div className="flex items-start gap-3 px-5 pt-5">
            <div className="min-w-0 flex-1">
              <h2 id="dialog-title" className="text-[16px] font-medium">
                {title}
              </h2>
              {description && <div className="mt-1.5 text-[13px] text-fg-2">{description}</div>}
            </div>
            <IconButton icon={X} label="Close dialog" onClick={onClose} className="-mt-1 -mr-2" />
          </div>
          {children && <div className="px-5 pt-4">{children}</div>}
          <div className="mt-5 flex flex-wrap justify-end gap-2 border-t border-line-subtle px-5 py-3">{footer}</div>
        </div>
      )}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Keep running",
  destructive,
  loading,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button size="sm" variant="ghost" onClick={onClose} autoFocus>
            {cancelLabel}
          </Button>
          <Button size="sm" variant={destructive ? "danger" : "primary"} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
