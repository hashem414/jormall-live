"use client";

import { useEffect, useState } from "react";

type DoctorOption = Readonly<{ id: string; label: string }>;

export function DoctorScheduleControls({
  collapseLabel,
  doctors,
  expandLabel,
  selectLabel,
}: Readonly<{
  collapseLabel: string;
  doctors: readonly DoctorOption[];
  expandLabel: string;
  selectLabel: string;
}>) {
  const [selectedDoctor, setSelectedDoctor] = useState(doctors[0]?.id ?? "");

  useEffect(() => {
    for (const section of document.querySelectorAll<HTMLDetailsElement>(
      "details[data-doctor-schedule]",
    )) {
      const visible = !selectedDoctor || section.dataset.doctorId === selectedDoctor;
      section.dataset.mobileVisible = String(visible);
      if (visible) section.open = true;
    }
  }, [selectedDoctor]);

  function setAll(open: boolean) {
    for (const section of document.querySelectorAll<HTMLDetailsElement>(
      "details[data-doctor-schedule]",
    )) {
      section.open = open;
    }
  }

  if (doctors.length === 0) return null;
  return (
    <div className="doctor-schedule-controls">
      <label className="field doctor-mobile-selector">
        <span className="field-label">{selectLabel}</span>
        <select
          className="select"
          onChange={(event) => setSelectedDoctor(event.currentTarget.value)}
          value={selectedDoctor}
        >
          {doctors.map((doctor) => (
            <option key={doctor.id} value={doctor.id}>
              {doctor.label}
            </option>
          ))}
        </select>
      </label>
      <div className="doctor-desktop-controls row-actions">
        <button className="button button-secondary" onClick={() => setAll(true)} type="button">
          {expandLabel}
        </button>
        <button className="button button-secondary" onClick={() => setAll(false)} type="button">
          {collapseLabel}
        </button>
      </div>
    </div>
  );
}
