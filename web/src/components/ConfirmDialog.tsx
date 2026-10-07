import { useEffect, useId, useRef, type FormEvent, type ReactNode } from 'react';

interface Props {
  open: boolean;
  title: string;
  /** The exact consequence. */
  children: ReactNode;
  /** Repeats the action, e.g. "Delete readings". */
  confirmLabel: string;
  busyLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** A modal `<dialog>` for a destructive action: names what will happen, then repeats the action on its button. */
export function ConfirmDialog({ open, title, children, confirmLabel, busyLabel, busy, onConfirm, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!busy) onConfirm();
  }

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <form className="dialog-form" onSubmit={submit} noValidate>
        <h2 id={titleId}>{title}</h2>
        {children}
        <div className="dialog-actions">
          <button type="button" className="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button button-danger" disabled={busy}>
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
