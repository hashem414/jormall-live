"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({
  children,
  confirmMessage,
  disabled = false,
  name,
  tone = "primary",
  value,
}: Readonly<{
  children: string;
  confirmMessage?: string | undefined;
  disabled?: boolean | undefined;
  name?: string | undefined;
  tone?: "danger" | "primary" | "secondary";
  value?: string | undefined;
}>) {
  const { pending } = useFormStatus();
  return (
    <button
      className={`button button-${tone}`}
      disabled={disabled || pending}
      name={name}
      onClick={(event) => {
        if (confirmMessage && !window.confirm(confirmMessage)) event.preventDefault();
      }}
      type="submit"
      value={value}
    >
      {children}
    </button>
  );
}
