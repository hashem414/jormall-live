"use client";

export function PrintScheduleButton({ label }: Readonly<{ label: string }>) {
  return (
    <button
      className="button button-secondary"
      onClick={() => {
        window.print();
      }}
      type="button"
    >
      <span aria-hidden="true">🖨️</span> {label}
    </button>
  );
}
