"use client";

import { useId, useMemo, useRef, useState } from "react";

export type PatientFormOption = Readonly<{
  displayName: string;
  id: string;
  referenceCode?: string | null | undefined;
}>;

export function PatientFormCombobox({
  label,
  locale,
  name = "customerId",
  options,
}: Readonly<{
  label: string;
  locale: "ar" | "en";
  name?: string | undefined;
  options: readonly PatientFormOption[];
}>) {
  const inputId = useId();
  const listboxId = `${inputId}-options`;
  const inputReference = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const visibleOptions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase(locale === "ar" ? "ar-JO" : "en-JO");
    return options
      .filter((patient) => {
        if (!normalized) return true;
        return [patient.displayName, patient.referenceCode ?? ""].some((value) =>
          value.toLocaleLowerCase(locale === "ar" ? "ar-JO" : "en-JO").includes(normalized),
        );
      })
      .slice(0, 25);
  }, [locale, options, query]);
  const text =
    locale === "ar"
      ? {
          noResults: "لا يوجد مريض مطابق.",
          placeholder: "ابحث باسم المريض أو الرقم المرجعي",
          required: "اختر مريضاً من نتائج البحث.",
        }
      : {
          noResults: "No matching patient found.",
          placeholder: "Search by patient name or reference",
          required: "Select a patient from the search results.",
        };

  function selectPatient(patient: PatientFormOption): void {
    setSelectedId(patient.id);
    setQuery(
      patient.referenceCode
        ? `${patient.displayName} — ${patient.referenceCode}`
        : patient.displayName,
    );
    inputReference.current?.setCustomValidity("");
    setIsOpen(false);
    setActiveIndex(0);
  }

  return (
    <div
      className="field patient-combobox"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false);
      }}
    >
      <label className="field-label" htmlFor={inputId}>
        {label}
      </label>
      <input name={name} type="hidden" value={selectedId} />
      <input
        aria-activedescendant={
          isOpen && visibleOptions[activeIndex]
            ? `${inputId}-option-${visibleOptions[activeIndex].id}`
            : undefined
        }
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={isOpen}
        autoComplete="off"
        className="input"
        id={inputId}
        onChange={(event) => {
          setQuery(event.currentTarget.value);
          setSelectedId("");
          event.currentTarget.setCustomValidity(text.required);
          setActiveIndex(0);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
        onInvalid={(event) => event.currentTarget.setCustomValidity(text.required)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setIsOpen(true);
            setActiveIndex((index) => Math.min(index + 1, visibleOptions.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex((index) => Math.max(index - 1, 0));
          } else if (event.key === "Enter" && isOpen && visibleOptions[activeIndex]) {
            event.preventDefault();
            selectPatient(visibleOptions[activeIndex]);
          } else if (event.key === "Escape") {
            setIsOpen(false);
          }
        }}
        placeholder={text.placeholder}
        ref={inputReference}
        required
        role="combobox"
        type="search"
        value={query}
      />
      {isOpen ? (
        <div className="patient-combobox-options" id={listboxId} role="listbox">
          {visibleOptions.length ? (
            visibleOptions.map((patient, index) => (
              <button
                aria-selected={index === activeIndex}
                className="patient-combobox-option"
                id={`${inputId}-option-${patient.id}`}
                key={patient.id}
                onClick={() => selectPatient(patient)}
                onMouseDown={(event) => event.preventDefault()}
                role="option"
                type="button"
              >
                <span>{patient.displayName}</span>
                {patient.referenceCode ? <small>{patient.referenceCode}</small> : null}
              </button>
            ))
          ) : (
            <p className="patient-combobox-empty">{text.noResults}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
