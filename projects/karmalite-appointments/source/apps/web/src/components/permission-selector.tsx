"use client";

import { useId, useSyncExternalStore } from "react";

type PermissionOption = Readonly<{
  code: string;
  id: string;
  label: string;
}>;

type PermissionSection = Readonly<{
  description?: string;
  key: string;
  label: string;
  permissions: readonly PermissionOption[];
}>;

const subscribeToHydration = () => () => undefined;
const clientHydrationSnapshot = () => true;
const serverHydrationSnapshot = () => false;

export function PermissionSelector({
  clearAllLabel,
  initialPermissionCodes = [],
  legend,
  sections,
  selectAllLabel,
}: Readonly<{
  clearAllLabel: string;
  initialPermissionCodes?: readonly string[];
  legend: string;
  sections: readonly PermissionSection[];
  selectAllLabel: string;
}>) {
  const groupId = useId();
  const availableCodes = sections.flatMap(({ permissions }) => permissions.map(({ code }) => code));
  const initialSelectedCodes = new Set(
    initialPermissionCodes.filter((code) => availableCodes.includes(code)),
  );
  const isHydrated = useSyncExternalStore(
    subscribeToHydration,
    clientHydrationSnapshot,
    serverHydrationSnapshot,
  );

  function setAll(source: HTMLButtonElement, checked: boolean) {
    const checkboxes = source
      .closest("fieldset")
      ?.querySelectorAll<HTMLInputElement>('input[name="permissionCodes"]');
    checkboxes?.forEach((checkbox) => {
      checkbox.defaultChecked = checked;
      checkbox.checked = checked;
    });
  }

  return (
    <fieldset className="permission-grid">
      <legend>{legend}</legend>
      <div className="permission-selection-actions">
        <button
          aria-controls={groupId}
          className="button button-secondary"
          disabled={!isHydrated}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setAll(event.currentTarget, true);
          }}
          type="button"
        >
          {selectAllLabel}
        </button>
        <button
          aria-controls={groupId}
          className="button button-secondary"
          disabled={!isHydrated}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setAll(event.currentTarget, false);
          }}
          type="button"
        >
          {clearAllLabel}
        </button>
      </div>
      <div className="permission-sections" id={groupId}>
        {sections.map((section) => (
          <section className="permission-section" key={section.key}>
            <h3>{section.label}</h3>
            {section.description ? <p>{section.description}</p> : null}
            <div className="permission-options">
              {section.permissions.map((permission) => (
                <label className="check-field" key={permission.id}>
                  <input
                    defaultChecked={initialSelectedCodes.has(permission.code)}
                    name="permissionCodes"
                    type="checkbox"
                    value={permission.code}
                  />
                  <span>{permission.label}</span>
                </label>
              ))}
            </div>
          </section>
        ))}
      </div>
    </fieldset>
  );
}
