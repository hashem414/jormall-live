"use client";

import type { ReactNode } from "react";
import { useRef } from "react";

export function OperationDialog({
  children,
  closeLabel,
  label,
}: Readonly<{ children: ReactNode; closeLabel: string; label: string }>) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  return (
    <>
      <button
        className="button button-secondary"
        onClick={() => dialogRef.current?.showModal()}
        type="button"
      >
        {label}
      </button>
      <dialog className="operation-dialog" ref={dialogRef}>
        <div className="operation-dialog-heading">
          <h2>{label}</h2>
          <button
            aria-label={closeLabel}
            className="drawer-close"
            onClick={() => dialogRef.current?.close()}
            type="button"
          >
            {closeLabel}
          </button>
        </div>
        {children}
      </dialog>
    </>
  );
}
