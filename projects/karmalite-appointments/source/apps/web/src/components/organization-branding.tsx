import type { CSSProperties } from "react";

function initials(name: string): string {
  const words = name.trim().split(/\s+/u).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => Array.from(word)[0] ?? "")
    .join("")
    .toLocaleUpperCase();
}

function safeLogoUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  if (value === "/api/workspace/logo") return value;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export function JorMallBrand({ compact = false }: Readonly<{ compact?: boolean }>) {
  return (
    <span className={compact ? "jormall-lockup is-compact" : "jormall-lockup"}>
      <span className="jormall-signal" aria-hidden="true">
        <span className="jormall-signal-ring ring-one" />
        <span className="jormall-signal-ring ring-two" />
        <span className="jormall-signal-ring ring-three" />
        <span className="jormall-signal-dot" />
      </span>
      <span className="jormall-wordmark">JorMall</span>
    </span>
  );
}

export function OrganizationLogo({
  logoUrl,
  name,
}: Readonly<{ logoUrl: string | null | undefined; name: string }>) {
  const resolvedLogoUrl = safeLogoUrl(logoUrl);
  const style: CSSProperties | undefined = resolvedLogoUrl
    ? { backgroundImage: `url(${JSON.stringify(resolvedLogoUrl)})` }
    : undefined;

  return (
    <span
      aria-hidden="true"
      className={resolvedLogoUrl ? "organization-logo has-image" : "organization-logo"}
      style={style}
    >
      {resolvedLogoUrl ? null : initials(name)}
    </span>
  );
}
