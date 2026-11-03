"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { z } from "zod";

import { createAppointmentAction } from "../app/[locale]/actions";
import { formatServicePrice } from "./service-price";
import { SubmitButton } from "./submit-button";

const weekdayNames = [
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
] as const;

type AppointmentOptions = Readonly<{
  branches: readonly Readonly<{
    hoursRules: readonly Readonly<{
      endMinuteLocal: number;
      startMinuteLocal: number;
      weekday: string;
    }>[];
    id: string;
    nameAr: string;
    nameEn: string;
    timezone: string;
  }>[];
  customers: readonly PatientOption[];
  providers: readonly Readonly<{
    branchIds: readonly string[];
    displayNameAr: string;
    displayNameEn: string;
    id: string;
    serviceIds: readonly string[];
  }>[];
  services: readonly Readonly<{
    branchIds: readonly string[];
    branchConfigurations: readonly Readonly<{
      branchId: string;
      bufferAfterMins: number;
      bufferBeforeMins: number;
      durationMins: number | null;
      priceMinor: number | null;
    }>[];
    currency: string;
    defaultDurationMins: number;
    defaultPriceMinor: number | null;
    id: string;
    nameAr: string;
    nameEn: string;
    postTreatmentInstructionsAr: string | null;
    postTreatmentInstructionsEn: string | null;
    preTreatmentInstructionsAr: string | null;
    preTreatmentInstructionsEn: string | null;
    resourceRequirements: readonly Readonly<{
      branchId: string;
      quantity: number;
      resourceGroup: Readonly<{ nameAr: string; nameEn: string }>;
    }>[];
  }>[];
  rooms: readonly Readonly<{
    branchId: string;
    id: string;
    nameAr: string;
    nameEn: string;
    serviceIds: readonly string[];
  }>[];
}>;

type PatientOption = Readonly<{
  contacts?: readonly Readonly<{ kind: string; originalValue: string }>[];
  displayName: string;
  id: string;
  referenceCode?: string;
}>;

const slotsSchema = z.object({
  slots: z.array(
    z.object({
      endsAt: z.string(),
      providerId: z.string(),
      resourceIdsByGroup: z.record(z.string(), z.array(z.string())),
      startsAt: z.string(),
      startsAtLocal: z.string(),
      timezone: z.string(),
    }),
  ),
});

const patientSearchSchema = z.object({
  rows: z.array(
    z.object({
      contacts: z
        .array(z.object({ kind: z.enum(["EMAIL", "PHONE"]), originalValue: z.string() }))
        .default([]),
      displayName: z.string(),
      id: z.string(),
      referenceCode: z.string(),
    }),
  ),
});
const createdPatientSchema = z.object({
  patient: z.object({
    contacts: z.array(z.object({ kind: z.enum(["EMAIL", "PHONE"]), originalValue: z.string() })),
    displayName: z.string(),
    id: z.string(),
    referenceCode: z.string(),
  }),
});
const safetyIndicatorSchema = z.object({
  allergyInformationAvailable: z.boolean(),
  conditionInformationAvailable: z.boolean(),
  healthInformationNotProvided: z.boolean(),
});

type Slot = z.infer<typeof slotsSchema>["slots"][number];
type AvailabilityState = "idle" | "loading" | "error" | "empty" | "closed" | "past";

export function AppointmentWizard({
  canConfirmAppointment,
  canCreateCustomer,
  canReadPatientHealth,
  canWritePatientHealth,
  idempotencyKey,
  initialBranchId,
  initialDate,
  initialPatientId,
  initialProviderId,
  initialServiceId: propInitialServiceId,
  initialStartsAtLocal,
  locale,
  options,
}: Readonly<{
  canConfirmAppointment: boolean;
  canCreateCustomer: boolean;
  canReadPatientHealth: boolean;
  canWritePatientHealth: boolean;
  idempotencyKey: string;
  initialBranchId?: string | undefined;
  initialDate?: string | undefined;
  initialPatientId?: string | undefined;
  initialProviderId?: string | undefined;
  initialServiceId?: string | undefined;
  initialStartsAtLocal?: string | undefined;
  locale: "ar" | "en";
  options: AppointmentOptions;
}>) {
  const selectedInitialBranchId = options.branches.some(({ id }) => id === initialBranchId)
    ? (initialBranchId ?? "")
    : (options.branches[0]?.id ?? "");
  const requestedInitialProvider = options.providers.find(
    ({ branchIds, id }) => id === initialProviderId && branchIds.includes(selectedInitialBranchId),
  );
  const matchingPropService = propInitialServiceId
    ? options.services.find(
        ({ branchIds, id }) =>
          id === propInitialServiceId && branchIds.includes(selectedInitialBranchId),
      )
    : undefined;
  const initialServiceId =
    matchingPropService?.id ??
    options.services.find(
      ({ branchIds, id }) =>
        branchIds.includes(selectedInitialBranchId) &&
        (!requestedInitialProvider || requestedInitialProvider.serviceIds.includes(id)),
    )?.id ??
    "";
  const selectedInitialProviderId = options.providers.some(
    ({ branchIds, id, serviceIds }) =>
      id === initialProviderId &&
      branchIds.includes(selectedInitialBranchId) &&
      serviceIds.includes(initialServiceId),
  )
    ? (initialProviderId ?? "")
    : (options.providers.find(
        ({ branchIds, serviceIds }) =>
          branchIds.includes(selectedInitialBranchId) && serviceIds.includes(initialServiceId),
      )?.id ?? "");
  const initialCustomerId = options.customers.some(({ id }) => id === initialPatientId)
    ? (initialPatientId ?? "")
    : (options.customers[0]?.id ?? "");
  const initialCustomerSearch = patientOptionValue(
    options.customers.find(({ id }) => id === initialCustomerId),
  );
  const [customerMode, setCustomerMode] = useState<"existing" | "new">("existing");
  const [customerSearch, setCustomerSearch] = useState(initialCustomerSearch);
  const [patientResults, setPatientResults] = useState<readonly PatientOption[]>(options.customers);
  const [addedPatients, setAddedPatients] = useState<readonly PatientOption[]>([]);
  const [customerId, setCustomerId] = useState(initialCustomerId);
  const [safetyIndicators, setSafetyIndicators] = useState<Readonly<{
    allergyInformationAvailable: boolean;
    conditionInformationAvailable: boolean;
    healthInformationNotProvided: boolean;
    patientId: string;
  }> | null>(null);
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [newCustomerEmail, setNewCustomerEmail] = useState("");
  const [newAllergyState, setNewAllergyState] = useState("NOT_PROVIDED");
  const [newAllergyDetails, setNewAllergyDetails] = useState("");
  const [newMedicalConditionState, setNewMedicalConditionState] = useState("NOT_PROVIDED");
  const [newMedicalConditionDetails, setNewMedicalConditionDetails] = useState("");
  const [newHealthConsentConfirmed, setNewHealthConsentConfirmed] = useState(false);
  const [patientCreateState, setPatientCreateState] = useState<
    "idle" | "loading" | "error" | "created"
  >("idle");
  const [doctorPreference, setDoctorPreference] = useState<"any" | "specific">("specific");
  const [roomId, setRoomId] = useState("");
  const [branchId, setBranchId] = useState(selectedInitialBranchId);
  const [serviceId, setServiceId] = useState(initialServiceId);
  const [providerId, setProviderId] = useState(selectedInitialProviderId);
  const [date, setDate] = useState(initialDate ?? "");
  const [startsAtLocal, setStartsAtLocal] = useState(initialStartsAtLocal ?? "");
  const [slots, setSlots] = useState<readonly Slot[]>([]);
  const [availabilityState, setAvailabilityState] = useState<AvailabilityState>("idle");
  const [currentInstant, setCurrentInstant] = useState(() => new Date());
  const patientListId = useId();
  const labels = wizardLabels[locale];
  const knownPatients = useMemo(() => {
    const patients = new Map<string, PatientOption>();
    for (const patient of [...addedPatients, ...options.customers, ...patientResults]) {
      patients.set(patient.id, patient);
    }
    return [...patients.values()];
  }, [addedPatients, options.customers, patientResults]);
  const selectedPatient = knownPatients.find(({ id }) => id === customerId);
  const visibleCustomers =
    customerSearch.trim().length < 2 || customerSearch === patientOptionValue(selectedPatient)
      ? knownPatients
      : patientResults;
  const availableServices = options.services.filter(({ branchIds }) =>
    branchIds.includes(branchId),
  );
  const availableProviders = options.providers.filter(
    ({ branchIds, serviceIds }) => branchIds.includes(branchId) && serviceIds.includes(serviceId),
  );
  const selectedBranch = options.branches.find(({ id }) => id === branchId);
  const minimumDate = localDateInTimeZone(currentInstant, selectedBranch?.timezone ?? "Asia/Amman");
  const selectedService = options.services.find(({ id }) => id === serviceId);
  const selectedServiceBranch = selectedService?.branchConfigurations.find(
    (configuration) => configuration.branchId === branchId,
  );
  const selectedDuration =
    selectedServiceBranch?.durationMins ?? selectedService?.defaultDurationMins ?? 0;
  const compatibleRooms = options.rooms.filter(
    (room) => room.branchId === branchId && room.serviceIds.includes(serviceId),
  );
  const selectedSlot = slots.find(
    (slot) => slot.startsAtLocal === startsAtLocal && slot.providerId === providerId,
  );
  const availableRoomIds = useMemo(
    () => new Set(Object.values(selectedSlot?.resourceIdsByGroup ?? {}).flat()),
    [selectedSlot],
  );
  const availableRooms = compatibleRooms.filter(({ id }) => availableRoomIds.has(id));
  const selectedRequirements =
    selectedService?.resourceRequirements.filter(
      (requirement) => requirement.branchId === branchId,
    ) ?? [];
  const selectedHours = workingHoursForDate(selectedBranch?.hoursRules ?? [], date);
  const dateIsPast = date !== "" && date < minimumDate;
  const dateIsOpen = date !== "" && !dateIsPast && selectedHours.length > 0;

  const selectedSlotIsFuture =
    selectedSlot !== undefined &&
    new Date(selectedSlot.startsAt).getTime() > currentInstant.getTime();
  const newPatientReady =
    branchId !== "" &&
    newCustomerName.trim().length >= 2 &&
    newCustomerPhone.trim().length >= 7 &&
    (newAllergyState !== "PROVIDED" || newAllergyDetails.trim().length > 0) &&
    (newMedicalConditionState !== "PROVIDED" || newMedicalConditionDetails.trim().length > 0) &&
    (!requiresConsent(newAllergyState, newMedicalConditionState) || newHealthConsentConfirmed);
  const patientIsValid = customerMode === "existing" && customerId !== "";
  const canSubmit =
    patientIsValid &&
    branchId !== "" &&
    serviceId !== "" &&
    providerId !== "" &&
    startsAtLocal !== "" &&
    selectedSlotIsFuture &&
    (compatibleRooms.length === 0 || roomId !== "");

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentInstant(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const query = customerSearch.trim();
    if (query.length < 2) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void fetch(`/api/patients/search?q=${encodeURIComponent(query)}`, {
        signal: controller.signal,
      })
        .then(async (response) => patientSearchSchema.safeParse(await response.json()))
        .then((parsed) => {
          if (parsed.success) setPatientResults(parsed.data.rows);
        })
        .catch((error: unknown) => {
          if (!(error instanceof DOMException && error.name === "AbortError")) {
            setPatientResults([]);
          }
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [customerSearch, options.customers]);

  useEffect(() => {
    if (!canReadPatientHealth || customerMode !== "existing" || !customerId) return;
    const controller = new AbortController();
    void fetch(`/api/patients/${encodeURIComponent(customerId)}/safety-indicators`, {
      signal: controller.signal,
    })
      .then(async (response) => safetyIndicatorSchema.safeParse(await response.json()))
      .then((parsed) => {
        if (parsed.success) setSafetyIndicators({ ...parsed.data, patientId: customerId });
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setSafetyIndicators(null);
      });
    return () => controller.abort();
  }, [canReadPatientHealth, customerId, customerMode]);

  function clearAvailability(): void {
    setDate("");
    setSlots([]);
    setStartsAtLocal("");
    setRoomId("");
    setAvailabilityState("idle");
  }

  function selectBranch(nextBranchId: string): void {
    const nextService = options.services.find(({ branchIds }) => branchIds.includes(nextBranchId));
    const nextProvider = options.providers.find(
      ({ branchIds, serviceIds }) =>
        branchIds.includes(nextBranchId) && serviceIds.includes(nextService?.id ?? ""),
    );
    setBranchId(nextBranchId);
    setServiceId(nextService?.id ?? "");
    setProviderId(nextProvider?.id ?? "");
    clearAvailability();
  }

  function selectService(nextServiceId: string): void {
    setServiceId(nextServiceId);
    setProviderId(
      options.providers.find(
        ({ branchIds, serviceIds }) =>
          branchIds.includes(branchId) && serviceIds.includes(nextServiceId),
      )?.id ?? "",
    );
    clearAvailability();
  }

  async function addPatient(): Promise<void> {
    if (!canCreateCustomer || !newPatientReady) {
      setPatientCreateState("error");
      return;
    }
    setPatientCreateState("loading");
    try {
      const response = await fetch("/api/patients", {
        body: JSON.stringify({
          ...(newAllergyDetails.trim() ? { allergyDetails: newAllergyDetails.trim() } : {}),
          allergyState: newAllergyState,
          displayName: newCustomerName.trim(),
          ...(newCustomerEmail.trim() ? { emailOriginal: newCustomerEmail.trim() } : {}),
          healthConsentConfirmed: newHealthConsentConfirmed,
          ...(newMedicalConditionDetails.trim()
            ? { medicalConditionDetails: newMedicalConditionDetails.trim() }
            : {}),
          medicalConditionState: newMedicalConditionState,
          phoneOriginal: newCustomerPhone.trim(),
          preferredBranchId: branchId,
          preferredLocale: locale,
        }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      const parsed = createdPatientSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) {
        setPatientCreateState("error");
        return;
      }
      const patient = parsed.data.patient;
      setAddedPatients((current) => [patient, ...current]);
      setPatientResults((current) => [patient, ...current]);
      setCustomerId(patient.id);
      setCustomerSearch(patientOptionValue(patient));
      setCustomerMode("existing");
      setPatientCreateState("created");
    } catch {
      setPatientCreateState("error");
    }
  }

  async function findAvailability(): Promise<void> {
    if (!date || !branchId || !serviceId || (doctorPreference === "specific" && !providerId))
      return;
    const requestedAt = new Date();
    setCurrentInstant(requestedAt);
    const currentMinimumDate = localDateInTimeZone(
      requestedAt,
      selectedBranch?.timezone ?? "Asia/Amman",
    );
    if (date < currentMinimumDate) {
      setAvailabilityState("past");
      setSlots([]);
      return;
    }
    if (!dateIsOpen) {
      setAvailabilityState("closed");
      setSlots([]);
      return;
    }
    setAvailabilityState("loading");
    setStartsAtLocal("");
    try {
      const query = new URLSearchParams({
        branchId,
        endsOn: date,
        serviceId,
        startsOn: date,
      });
      if (doctorPreference === "specific") query.set("providerId", providerId);
      if (customerMode === "existing" && customerId) query.set("customerId", customerId);
      const response = await fetch(`/api/appointments/availability?${query.toString()}`);
      const parsed = slotsSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) {
        setAvailabilityState("error");
        setSlots([]);
        return;
      }
      setSlots(parsed.data.slots);
      setAvailabilityState(parsed.data.slots.length === 0 ? "empty" : "idle");
    } catch {
      setAvailabilityState("error");
      setSlots([]);
    }
  }

  return (
    <form action={createAppointmentAction} className="appointment-wizard">
      <input name="locale" type="hidden" value={locale} />
      <input name="idempotencyKey" type="hidden" value={idempotencyKey} />
      <input name="customerMode" type="hidden" value={customerMode} />
      <input
        name="customerId"
        type="hidden"
        value={customerMode === "existing" ? customerId : ""}
      />
      <input name="branchId" type="hidden" value={branchId} />
      <input name="serviceId" type="hidden" value={serviceId} />
      <input name="providerId" type="hidden" value={providerId} />
      <input name="roomId" type="hidden" value={roomId} />
      <input name="startsAtLocal" type="hidden" value={startsAtLocal} />
      <fieldset className="wizard-step">
        <legend>{labels.create}</legend>
        <div className="wizard-section-grid">
          <section className="wizard-section">
            <h3>{labels.steps[0]}</h3>
            <div className="form-stack">
              {canCreateCustomer ? (
                <div className="segmented-control" role="group" aria-label={labels.customerMode}>
                  <button
                    aria-pressed={customerMode === "existing"}
                    className="button button-secondary"
                    onClick={() => setCustomerMode("existing")}
                    type="button"
                  >
                    {labels.existingCustomer}
                  </button>
                  <button
                    aria-pressed={customerMode === "new"}
                    className="button button-secondary"
                    onClick={() => {
                      setCustomerMode("new");
                      setPatientCreateState("idle");
                    }}
                    type="button"
                  >
                    {labels.newCustomer}
                  </button>
                </div>
              ) : null}
              {customerMode === "existing" ? (
                <>
                  <PatientCombobox
                    inputId={patientListId}
                    label={labels.customer}
                    onChange={(query) => {
                      setCustomerSearch(query);
                      const selected = visibleCustomers.find(
                        (patient) => patientOptionValue(patient) === query,
                      );
                      setCustomerId(selected?.id ?? "");
                    }}
                    onSelect={(patient) => {
                      setCustomerId(patient.id);
                      setCustomerSearch(patientOptionValue(patient));
                    }}
                    options={visibleCustomers}
                    value={customerSearch}
                  />
                  {patientCreateState === "created" ? (
                    <p className="inline-alert" role="status">
                      {labels.patientAdded}
                    </p>
                  ) : null}
                  {selectedPatient ? (
                    <dl className="details-list" aria-label={labels.patientSummary}>
                      <ReviewItem
                        label={labels.patientId}
                        value={selectedPatient.referenceCode ?? selectedPatient.id}
                      />
                      <ReviewItem label={labels.customerName} value={selectedPatient.displayName} />
                      <ReviewItem
                        label={labels.customerPhone}
                        value={
                          selectedPatient.contacts?.find(({ kind }) => kind === "PHONE")
                            ?.originalValue ?? "—"
                        }
                      />
                      <ReviewItem
                        label={labels.customerEmail}
                        value={
                          selectedPatient.contacts?.find(({ kind }) => kind === "EMAIL")
                            ?.originalValue ?? "—"
                        }
                      />
                    </dl>
                  ) : null}
                  {safetyIndicators?.patientId === customerId ? (
                    <div className="inline-alert" role="status">
                      <p>
                        {safetyIndicators.allergyInformationAvailable
                          ? labels.allergyAvailable
                          : labels.allergyNotAvailable}
                      </p>
                      <p>
                        {safetyIndicators.conditionInformationAvailable
                          ? labels.conditionAvailable
                          : labels.conditionNotAvailable}
                      </p>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="form-grid">
                  <label className="field">
                    <span className="field-label">{labels.customerName}</span>
                    <input
                      className="input"
                      name="newCustomerName"
                      onChange={(event) => setNewCustomerName(event.currentTarget.value)}
                      required
                      value={newCustomerName}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">{labels.customerPhone}</span>
                    <input
                      className="input"
                      dir="ltr"
                      inputMode="tel"
                      name="newCustomerPhone"
                      onChange={(event) => setNewCustomerPhone(event.currentTarget.value)}
                      required
                      type="tel"
                      value={newCustomerPhone}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">{labels.customerEmail}</span>
                    <input
                      className="input"
                      name="newCustomerEmail"
                      onChange={(event) => setNewCustomerEmail(event.currentTarget.value)}
                      type="email"
                      value={newCustomerEmail}
                    />
                  </label>
                  {canWritePatientHealth ? (
                    <>
                      <label className="field">
                        <span className="field-label">{labels.allergyState}</span>
                        <select
                          className="select"
                          name="newAllergyState"
                          onChange={(event) => setNewAllergyState(event.currentTarget.value)}
                          value={newAllergyState}
                        >
                          {healthOptions(locale).map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      {newAllergyState === "PROVIDED" ? (
                        <label className="field">
                          <span className="field-label">{labels.allergyDetails}</span>
                          <textarea
                            className="textarea"
                            name="newAllergyDetails"
                            onChange={(event) => setNewAllergyDetails(event.currentTarget.value)}
                            required
                            value={newAllergyDetails}
                          />
                        </label>
                      ) : null}
                      <label className="field">
                        <span className="field-label">{labels.conditionState}</span>
                        <select
                          className="select"
                          name="newMedicalConditionState"
                          onChange={(event) =>
                            setNewMedicalConditionState(event.currentTarget.value)
                          }
                          value={newMedicalConditionState}
                        >
                          {healthOptions(locale).map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      {newMedicalConditionState === "PROVIDED" ? (
                        <label className="field">
                          <span className="field-label">{labels.conditionDetails}</span>
                          <textarea
                            className="textarea"
                            name="newMedicalConditionDetails"
                            onChange={(event) =>
                              setNewMedicalConditionDetails(event.currentTarget.value)
                            }
                            required
                            value={newMedicalConditionDetails}
                          />
                        </label>
                      ) : null}
                      {requiresConsent(newAllergyState, newMedicalConditionState) ? (
                        <label className="checkbox-line">
                          <input
                            checked={newHealthConsentConfirmed}
                            name="newHealthConsentConfirmed"
                            onChange={(event) =>
                              setNewHealthConsentConfirmed(event.currentTarget.checked)
                            }
                            required
                            type="checkbox"
                          />{" "}
                          <span>{labels.healthConsent}</span>
                        </label>
                      ) : (
                        <input name="newHealthConsentConfirmed" type="hidden" value="off" />
                      )}
                    </>
                  ) : (
                    <>
                      <input name="newAllergyState" type="hidden" value="NOT_PROVIDED" />
                      <input name="newMedicalConditionState" type="hidden" value="NOT_PROVIDED" />
                      <input name="newHealthConsentConfirmed" type="hidden" value="off" />
                    </>
                  )}
                  <div className="button-row wizard-add-patient">
                    <button
                      className="button"
                      disabled={patientCreateState === "loading" || !newPatientReady}
                      onClick={() => void addPatient()}
                      type="button"
                    >
                      {patientCreateState === "loading" ? labels.addingPatient : labels.addPatient}
                    </button>
                  </div>
                  <p aria-live="polite" className="availability-feedback">
                    {patientCreateState === "error"
                      ? labels.patientAddError
                      : patientCreateState === "created"
                        ? labels.patientAdded
                        : ""}
                  </p>
                </div>
              )}
              {customerMode === "existing" ? (
                <>
                  <input name="newCustomerName" type="hidden" value="" />
                  <input name="newCustomerPhone" type="hidden" value="" />
                  <input name="newCustomerEmail" type="hidden" value="" />
                  <input name="newAllergyState" type="hidden" value="NOT_PROVIDED" />
                  <input name="newMedicalConditionState" type="hidden" value="NOT_PROVIDED" />
                  <input name="newHealthConsentConfirmed" type="hidden" value="off" />
                </>
              ) : null}
            </div>
          </section>
          <section className="wizard-section">
            <h3>{labels.steps[1]}</h3>
            <div className="form-stack">
              <ChoiceSelect
                label={labels.branch}
                onChange={selectBranch}
                options={options.branches.map((branch) => ({
                  id: branch.id,
                  label: locale === "ar" ? branch.nameAr : branch.nameEn,
                }))}
                value={branchId}
              />
              <ChoiceSelect
                label={labels.service}
                onChange={selectService}
                options={availableServices.map((service) => ({
                  id: service.id,
                  label: locale === "ar" ? service.nameAr : service.nameEn,
                }))}
                value={serviceId}
              />
              {selectedService ? (
                <dl className="details-list">
                  <ReviewItem
                    label={labels.duration}
                    value={`${selectedDuration} ${labels.minutes}`}
                  />
                  <ReviewItem
                    label={labels.price}
                    value={formatServicePrice(
                      locale,
                      selectedService.defaultPriceMinor,
                      selectedService.currency,
                    )}
                  />
                </dl>
              ) : null}
            </div>
          </section>
          <section className="wizard-section">
            <h3>{labels.steps[2]}</h3>
            <div className="form-stack">
              <div className="segmented-control" role="group" aria-label={labels.doctorChoice}>
                <button
                  aria-pressed={doctorPreference === "specific"}
                  className="button button-secondary"
                  onClick={() => setDoctorPreference("specific")}
                  type="button"
                >
                  {labels.specificDoctor}
                </button>
                <button
                  aria-pressed={doctorPreference === "any"}
                  className="button button-secondary"
                  onClick={() => {
                    setDoctorPreference("any");
                    setProviderId("");
                    clearAvailability();
                  }}
                  type="button"
                >
                  {labels.anyDoctor}
                </button>
              </div>
              {doctorPreference === "specific" ? (
                <ChoiceSelect
                  label={labels.provider}
                  onChange={(value) => {
                    setProviderId(value);
                    clearAvailability();
                  }}
                  options={availableProviders.map((provider) => ({
                    id: provider.id,
                    label: locale === "ar" ? provider.displayNameAr : provider.displayNameEn,
                  }))}
                  value={providerId}
                />
              ) : (
                <p className="field-hint">{labels.anyDoctorHint}</p>
              )}
              {availableProviders.length === 0 ? (
                <p className="inline-alert" role="alert">
                  {labels.providerSetupRequired}
                </p>
              ) : null}
            </div>
          </section>
          <section className="wizard-section">
            <h3>{labels.steps[3]}</h3>
            <div className="form-stack">
              <label className="field">
                <span className="field-label">{labels.date}</span>
                <input
                  className="input"
                  onChange={(event) => {
                    const nextDate = event.currentTarget.value;
                    setDate(nextDate);
                    setSlots([]);
                    setStartsAtLocal("");
                    setAvailabilityState(
                      nextDate && nextDate < minimumDate
                        ? "past"
                        : nextDate &&
                            workingHoursForDate(selectedBranch?.hoursRules ?? [], nextDate)
                              .length === 0
                          ? "closed"
                          : "idle",
                    );
                  }}
                  required
                  min={minimumDate}
                  type="date"
                  value={date}
                />
              </label>
              {dateIsOpen ? (
                <p className="field-hint">
                  {labels.branchHours}: {selectedHours.map(formatHours).join(", ")}
                </p>
              ) : null}
              <button
                className="button button-secondary"
                disabled={!date || !dateIsOpen || availabilityState === "loading"}
                onClick={() => void findAvailability()}
                type="button"
              >
                {availabilityState === "loading" ? labels.searching : labels.findTimes}
              </button>
              <p aria-live="polite" className="availability-feedback">
                {availabilityState === "error"
                  ? labels.availabilityError
                  : availabilityState === "empty"
                    ? labels.noTimes
                    : availabilityState === "closed"
                      ? labels.closedDay
                      : availabilityState === "past"
                        ? labels.pastDate
                        : ""}
              </p>
              {slots.length > 0 ? (
                <SlotPicker
                  label={labels.time}
                  onSelect={(slot) => {
                    setStartsAtLocal(slot.startsAtLocal);
                    setProviderId(slot.providerId);
                    const ids = new Set(Object.values(slot.resourceIdsByGroup).flat());
                    setRoomId(compatibleRooms.find(({ id }) => ids.has(id))?.id ?? "");
                  }}
                  selectedKey={startsAtLocal && providerId ? `${providerId}|${startsAtLocal}` : ""}
                  slots={slots}
                />
              ) : null}
            </div>
          </section>
          <section className="wizard-section">
            <h3>{labels.steps[4]}</h3>
            <div className="form-stack">
              <p className="field-hint">{labels.resourcesAutomatic}</p>
              {availableRooms.length === 0 ? (
                <p className="inline-alert" role="alert">
                  {labels.noCompatibleRooms}
                </p>
              ) : (
                <ChoiceSelect
                  label={labels.room}
                  onChange={setRoomId}
                  options={availableRooms.map((room) => ({
                    id: room.id,
                    label: locale === "ar" ? room.nameAr : room.nameEn,
                  }))}
                  value={roomId}
                />
              )}
              {selectedRequirements.length === 0 ? (
                <p className="muted">{labels.noResourceRequirement}</p>
              ) : (
                <ul className="history-list">
                  {selectedRequirements.map((requirement) => (
                    <li key={`${requirement.branchId}:${requirement.resourceGroup.nameEn}`}>
                      {locale === "ar"
                        ? requirement.resourceGroup.nameAr
                        : requirement.resourceGroup.nameEn}{" "}
                      × {requirement.quantity}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
          <section className="wizard-section wizard-section-review">
            <h3>{labels.steps[5]}</h3>
            <dl className="details-list">
              <ReviewItem
                label={labels.customer}
                value={
                  customerMode === "new"
                    ? newCustomerName
                    : optionLabel(options.customers, customerId, "displayName")
                }
              />
              <ReviewItem
                label={labels.branch}
                value={bilingualLabel(options.branches, branchId, locale)}
              />
              <ReviewItem
                label={labels.service}
                value={bilingualLabel(options.services, serviceId, locale)}
              />
              <ReviewItem
                label={labels.provider}
                value={providerLabel(options.providers, providerId, locale)}
              />
              <ReviewItem label={labels.dateAndTime} value={startsAtLocal.replace("T", " ")} />
              <ReviewItem
                label={labels.endTime}
                value={appointmentEndLabel(startsAtLocal, selectedDuration)}
              />
              <ReviewItem
                label={labels.duration}
                value={selectedService ? `${selectedDuration} ${labels.minutes}` : "-"}
              />
              <ReviewItem
                label={labels.preparationBuffer}
                value={`${selectedServiceBranch?.bufferBeforeMins ?? 0} ${labels.minutes}`}
              />
              <ReviewItem
                label={labels.cleanupBuffer}
                value={`${selectedServiceBranch?.bufferAfterMins ?? 0} ${labels.minutes}`}
              />
              <ReviewItem
                label={labels.price}
                value={
                  selectedService
                    ? formatServicePrice(
                        locale,
                        selectedService.defaultPriceMinor,
                        selectedService.currency,
                      )
                    : "-"
                }
              />
              <ReviewItem
                label={labels.resources}
                value={bilingualLabel(options.rooms, roomId, locale)}
              />
              <ReviewItem label={labels.bookingSource} value={labels.staffBooking} />
              {customerMode === "existing" && safetyIndicators?.patientId === customerId ? (
                <ReviewItem
                  label={labels.safetyWarning}
                  value={
                    [
                      safetyIndicators.allergyInformationAvailable ? labels.allergyAvailable : "",
                      safetyIndicators.conditionInformationAvailable
                        ? labels.conditionAvailable
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" ") || labels.noSafetyWarning
                  }
                />
              ) : null}
              <ReviewItem
                label={labels.instructions}
                value={
                  (locale === "ar"
                    ? selectedService?.preTreatmentInstructionsAr
                    : selectedService?.preTreatmentInstructionsEn) ?? "-"
                }
              />
            </dl>
          </section>
        </div>
      </fieldset>
      <div className="wizard-actions">
        {customerMode === "new" ? (
          <p className="inline-alert" role="status">
            {labels.addPatientBeforeBooking}
          </p>
        ) : null}
        <div className="button-row">
          <SubmitButton disabled={!canSubmit} name="initialStatus" tone="secondary" value="PENDING">
            {labels.createPending}
          </SubmitButton>
          {canConfirmAppointment ? (
            <SubmitButton disabled={!canSubmit} name="initialStatus" value="CONFIRMED">
              {labels.createConfirmed}
            </SubmitButton>
          ) : null}
        </div>
      </div>
    </form>
  );
}

function workingHoursForDate(
  rules: readonly Readonly<{ endMinuteLocal: number; startMinuteLocal: number; weekday: string }>[],
  date: string,
) {
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(date)) return [];
  const weekday = weekdayNames[new Date(`${date}T00:00:00Z`).getUTCDay()];
  return rules.filter((rule) => rule.weekday === weekday);
}

function localDateInTimeZone(instant: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: timezone,
    year: "numeric",
  }).formatToParts(instant);
  const value = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function patientOptionValue(patient: PatientOption | undefined): string {
  if (!patient) return "";
  return patient.referenceCode
    ? `${patient.displayName} — ${patient.referenceCode}`
    : patient.displayName;
}

function requiresConsent(allergyState: string, conditionState: string): boolean {
  return [allergyState, conditionState].some(
    (state) => state === "PROVIDED" || state === "NONE_REPORTED",
  );
}

function appointmentEndLabel(startsAtLocal: string, durationMins: number): string {
  if (!startsAtLocal || durationMins <= 0) return "—";
  const start = new Date(`${startsAtLocal}:00Z`);
  return new Date(start.getTime() + durationMins * 60_000)
    .toISOString()
    .slice(0, 16)
    .replace("T", " ");
}

function healthOptions(locale: "ar" | "en") {
  return locale === "ar"
    ? [
        { label: "لم يتم تقديم المعلومات", value: "NOT_PROVIDED" },
        { label: "لا توجد معلومات معروفة", value: "NONE_REPORTED" },
        { label: "تم تقديم المعلومات", value: "PROVIDED" },
        { label: "رفض المريض تقديم المعلومات", value: "DECLINED" },
      ]
    : [
        { label: "Not yet provided", value: "NOT_PROVIDED" },
        { label: "None reported", value: "NONE_REPORTED" },
        { label: "Information provided", value: "PROVIDED" },
        { label: "Patient declined to provide", value: "DECLINED" },
      ];
}

function formatHours(rule: Readonly<{ endMinuteLocal: number; startMinuteLocal: number }>): string {
  return `${minuteLabel(rule.startMinuteLocal)}–${minuteLabel(rule.endMinuteLocal)}`;
}

function minuteLabel(minute: number): string {
  return `${Math.floor(minute / 60)
    .toString()
    .padStart(2, "0")}:${(minute % 60).toString().padStart(2, "0")}`;
}

function SlotPicker({
  label,
  onSelect,
  selectedKey,
  slots,
}: Readonly<{
  label: string;
  onSelect: (slot: Slot) => void;
  selectedKey: string;
  slots: readonly Slot[];
}>) {
  // Group slots by provider so staff can see who the slot belongs to
  const grouped = new Map<string, readonly Slot[]>();
  for (const slot of slots) {
    const prev = grouped.get(slot.providerId) ?? [];
    grouped.set(slot.providerId, [...prev, slot]);
  }
  const singleProvider = grouped.size === 1;
  return (
    <fieldset className="choice-fieldset slot-picker-fieldset">
      <legend className="field-label">{label}</legend>
      {[...grouped.entries()].map(([providerId, providerSlots]) => (
        <div key={providerId} className="slot-picker-group">
          {!singleProvider ? (
            <p className="slot-picker-provider-label">{providerSlots[0]?.timezone ?? providerId}</p>
          ) : null}
          <div className="slot-picker-grid" role="group">
            {providerSlots.map((slot) => {
              const key = `${slot.providerId}|${slot.startsAtLocal}`;
              const isSelected = key === selectedKey;
              return (
                <button
                  aria-pressed={isSelected}
                  className={`slot-chip${isSelected ? " slot-chip--selected" : ""}`}
                  key={key}
                  onClick={() => onSelect(slot)}
                  title={slot.startsAtLocal.slice(11)}
                  type="button"
                >
                  {slot.startsAtLocal.slice(11)}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </fieldset>
  );
}

function ChoiceSelect({
  label,
  onChange,
  options,
  value,
}: Readonly<{
  label: string;
  onChange: (value: string) => void;
  options: readonly Readonly<{ id: string; label: string }>[];
  value: string;
}>) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select
        className="select"
        onChange={(event) => onChange(event.currentTarget.value)}
        required
        value={value}
      >
        {options.length === 0 ? <option value="">—</option> : null}
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function PatientCombobox({
  inputId,
  label,
  onChange,
  onSelect,
  options,
  value,
}: Readonly<{
  inputId: string;
  label: string;
  onChange: (value: string) => void;
  onSelect: (patient: PatientOption) => void;
  options: readonly PatientOption[];
  value: string;
}>) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const visibleOptions = options.slice(0, 25);
  const listboxId = `${inputId}-options`;

  function selectPatient(patient: PatientOption): void {
    onSelect(patient);
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
          onChange(event.currentTarget.value);
          setActiveIndex(0);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
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
        role="combobox"
        type="search"
        value={value}
      />
      {isOpen && visibleOptions.length > 0 ? (
        <div className="patient-combobox-options" id={listboxId} role="listbox">
          {visibleOptions.map((patient, index) => (
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
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ReviewItem({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function optionLabel<T extends Readonly<{ id: string }>, K extends keyof T>(
  options: readonly T[],
  id: string,
  key: K,
): string {
  const value = options.find((option) => option.id === id)?.[key];
  return typeof value === "string" ? value : "—";
}

function bilingualLabel(
  options: readonly Readonly<{ id: string; nameAr: string; nameEn: string }>[],
  id: string,
  locale: "ar" | "en",
): string {
  return optionLabel(options, id, locale === "ar" ? "nameAr" : "nameEn");
}

function providerLabel(
  options: readonly Readonly<{ displayNameAr: string; displayNameEn: string; id: string }>[],
  id: string,
  locale: "ar" | "en",
): string {
  return optionLabel(options, id, locale === "ar" ? "displayNameAr" : "displayNameEn");
}

const wizardLabels = {
  ar: {
    addPatient: "إضافة المريض",
    addPatientBeforeBooking: "أضف المريض أولاً، ثم اختر الموعد المتاح لإكمال الحجز.",
    addingPatient: "جارٍ إضافة المريض…",
    bookingSource: "مصدر الحجز",
    cleanupBuffer: "فاصل التنظيف",
    endTime: "وقت الانتهاء",
    allergyDetails: "تفاصيل الحساسية",
    allergyState: "حالة معلومات الحساسية",
    anyDoctor: "أي طبيب مؤهل متاح",
    anyDoctorHint: "سيحدد النظام طبيباً مؤهلاً ومتوفراً عند اختيار الوقت.",
    conditionDetails: "تفاصيل الحالات الصحية المعروفة",
    conditionState: "حالة معلومات الحالات الصحية",
    createConfirmed: "إنشاء وتأكيد",
    createPending: "إنشاء كقيد الانتظار",
    customerEmail: "البريد الإلكتروني",
    doctorChoice: "اختيار الطبيب",
    healthConsent: "أكد المريض موافقته على تسجيل معلومات السلامة هذه.",
    allergyAvailable: "معلومات الحساسية متوفرة.",
    allergyNotAvailable: "لا تتوفر تفاصيل حساسية.",
    conditionAvailable: "معلومات الحالة الصحية متوفرة.",
    conditionNotAvailable: "لا تتوفر تفاصيل حالة صحية.",
    noCompatibleRooms: "لا توجد غرف متوافقة ومهيأة لهذه الخدمة.",
    noSafetyWarning: "لا يوجد مؤشر سلامة متوفر.",
    patientId: "رقم المريض",
    patientAddError: "تعذرت إضافة المريض. تحقق من البيانات أو ابحث عن رقم هاتف مسجل مسبقاً.",
    patientAdded: "تمت إضافة المريض واختياره للموعد.",
    patientSummary: "بيانات المريض المحدد",
    preparationBuffer: "فاصل التحضير",
    room: "الغرفة",
    safetyWarning: "مؤشر سلامة المريض",
    specificDoctor: "طبيب محدد",
    staffBooking: "حجز يدوي بواسطة الموظف",
    availabilityError: "تعذر تحميل الأوقات المتاحة. يرجى المحاولة مرة أخرى.",
    branch: "الفرع",
    branchHours: "ساعات عمل الفرع",
    chooseTime: "اختر وقتاً",
    closedDay: "الفرع مغلق في هذا اليوم. اختر يوماً آخر.",
    create: "إنشاء الموعد",
    customer: "المريض",
    customerMode: "اختيار مريض موجود أو إضافة مريض جديد",
    customerName: "اسم المريض",
    customerPhone: "رقم الهاتف",
    date: "التاريخ",
    dateAndTime: "التاريخ والوقت",
    duration: "المدة",
    instructions: "التعليمات",
    minutes: "دقيقة",
    noResourceRequirement: "لا توجد متطلبات غرف أو معدات مهيأة لهذه الخدمة.",
    price: "السعر",
    resources: "الموارد",
    resourcesAutomatic: "سيعيّن النظام غرف العلاج والمعدات المتاحة تلقائياً عند إنشاء الموعد.",
    existingCustomer: "مريض موجود",
    findTimes: "البحث عن الأوقات المتاحة",
    newCustomer: "إضافة مريض جديد",
    next: "التالي",
    noTimes: "لا توجد أوقات متاحة لهذا الاختيار. جرّب يوماً أو طبيباً آخر.",
    pastDate: "لا يمكن حجز تاريخ أو وقت مضى. اختر اليوم أو تاريخاً مستقبلياً.",
    previous: "السابق",
    progress: "خطوات إنشاء الموعد",
    provider: "الطبيب",
    providerSetupRequired: "لا يوجد طبيب مهيأ لهذا الفرع والخدمة.",
    searchCustomer: "البحث عن مريض أو اختياره",
    searching: "جارٍ البحث…",
    service: "الخدمة",
    steps: ["المريض", "الخدمة والفرع", "الطبيب", "التاريخ والوقت", "الغرفة", "المراجعة"],
    time: "الوقت المتاح",
  },
  en: {
    addPatient: "Add patient",
    addPatientBeforeBooking:
      "Add the patient first, then choose an available time to complete the booking.",
    addingPatient: "Adding patient…",
    bookingSource: "Booking source",
    cleanupBuffer: "Cleanup buffer",
    endTime: "End time",
    allergyDetails: "Allergy details",
    allergyState: "Allergy information state",
    anyDoctor: "Any available qualified doctor",
    anyDoctorHint: "The system will select a qualified, available doctor with the time.",
    conditionDetails: "Known health-condition details",
    conditionState: "Health-condition information state",
    createConfirmed: "Create & Confirm",
    createPending: "Create as Pending",
    customerEmail: "Email address",
    doctorChoice: "Doctor selection",
    healthConsent: "The patient authorized staff to record this safety information.",
    allergyAvailable: "Allergy information available.",
    allergyNotAvailable: "No allergy details available.",
    conditionAvailable: "Medical-condition information available.",
    conditionNotAvailable: "No condition details available.",
    noCompatibleRooms: "No compatible rooms are configured for this service.",
    noSafetyWarning: "No safety indicator is available.",
    patientId: "Patient ID",
    patientAddError:
      "The patient could not be added. Check the details or search for an existing phone number.",
    patientAdded: "The patient was added and selected for this appointment.",
    patientSummary: "Selected patient details",
    preparationBuffer: "Preparation buffer",
    room: "Room",
    safetyWarning: "Patient safety indicator",
    specificDoctor: "Specific doctor",
    staffBooking: "Staff manual booking",
    availabilityError: "Available times could not be loaded. Please try again.",
    branch: "Branch",
    branchHours: "Branch working hours",
    chooseTime: "Choose a time",
    closedDay: "The branch is closed on this day. Choose another day.",
    create: "Create appointment",
    customer: "Patient",
    customerMode: "Choose an existing patient or add a new patient",
    customerName: "Patient name",
    customerPhone: "Phone number",
    date: "Date",
    dateAndTime: "Date and time",
    duration: "Duration",
    instructions: "Instructions",
    minutes: "minutes",
    noResourceRequirement:
      "No treatment-room or equipment requirement is configured for this service.",
    price: "Price",
    resources: "Resources",
    resourcesAutomatic:
      "Available treatment rooms and equipment will be assigned automatically when the appointment is created.",
    existingCustomer: "Existing patient",
    findTimes: "Find available times",
    newCustomer: "Add new patient",
    next: "Next",
    noTimes: "No times are available for this selection. Try another day or doctor.",
    pastDate: "Past dates and times cannot be booked. Choose today or a future date.",
    previous: "Previous",
    progress: "Appointment creation steps",
    provider: "Doctor",
    providerSetupRequired: "No doctor is configured for this branch and service.",
    searchCustomer: "Search or select patient",
    searching: "Searching…",
    service: "Service",
    steps: ["Patient", "Service & Branch", "Doctor", "Date & Time", "Room", "Review"],
    time: "Available time",
  },
} as const;
