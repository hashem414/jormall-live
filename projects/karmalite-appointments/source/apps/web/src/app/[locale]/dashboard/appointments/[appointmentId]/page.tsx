import { randomUUID } from "node:crypto";

import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { AppointmentStatus } from "@jormall/db/generated/enums";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  AppointmentReceiptDialog,
  type ReceiptData,
} from "../../../../../components/appointment-receipt-dialog";
import { AppointmentInventoryConsumptionSection } from "../../../../../components/appointment-inventory-consumption";
import { Feedback } from "../../../../../components/feedback";
import { formatServicePrice } from "../../../../../components/service-price";
import { SubmitButton } from "../../../../../components/submit-button";
import { MessageTimeline } from "../../../../../components/message-timeline";
import { OperationDialog } from "../../../../../components/operation-dialog";
import { phaseOneMessages } from "../../../../../messages/phase-one";
import { phaseTwoLabel, phaseTwoMessages } from "../../../../../messages/phase-two";
import {
  communicationRepository,
  crmAppointmentRepository,
  identityRepository,
  operationalWorkflowsRepository,
  requireTenantAccess,
} from "../../../../../server/identity";
import {
  addAppointmentNoteAction,
  callAppointmentToRoomAction,
  changeAppointmentRoomAction,
  changeAppointmentServiceAction,
  recordAppointmentPaymentAction,
  rescheduleAppointmentAction,
  resendRoomMessageAction,
  startAppointmentServiceAction,
  transitionAppointmentAction,
} from "../../../actions";

function parsePaymentNote(notes: readonly { body: string; createdAt: Date }[] = []) {
  for (const note of notes) {
    const match = note.body.match(/<!--DATA:(\{.*?\})-->/s);
    if (match?.[1]) {
      try {
        const parsed = JSON.parse(match[1]);
        if (parsed.type === "PAYMENT_RECEIPT") {
          return {
            amountMinor: Number(parsed.amountMinor) || 0,
            currency: String(parsed.currency || "JOD"),
            method: String(parsed.method || "CASH"),
            notes: typeof parsed.notes === "string" ? parsed.notes : undefined,
            recordedAt: note.createdAt.toISOString(),
            status: (parsed.status as "PAID" | "PARTIAL" | "UNPAID" | "WAIVED") || "PAID",
          };
        }
      } catch {
        // ignore parse error
      }
    }
  }
  return undefined;
}

export default async function AppointmentPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/appointments/[appointmentId]">) {
  const { appointmentId, locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([requireTenantAccess(locale), searchParams]);
  const appointment = await crmAppointmentRepository.getAppointment(access, appointmentId);
  const resource = { branchId: appointment.branchId, staffProfileId: appointment.providerId };
  const canReadInventory = canAccessResource(access, "inventory.items.read", resource);
  const canReadConsumption = canAccessResource(access, "inventory.consumption.read", resource);
  const canAdjustConsumption = canAccessResource(access, "inventory.consumption.adjust", resource);
  const inventoryContext =
    canReadInventory || canReadConsumption || canAdjustConsumption
      ? await operationalWorkflowsRepository.getAppointmentInventoryContext(
          access,
          appointmentId,
          appointment.serviceId,
        )
      : { batches: [], consumptions: [], locations: [], requirements: [], reservations: [] };
  const canReschedule = canAccessResource(access, "appointment.reschedule", resource);
  const canClaimRoom = canAccessResource(access, "room.occupancy.claim", resource);
  const canReleaseRoom = canAccessResource(access, "room.occupancy.release", resource);
  const canCancel = canAccessResource(access, "appointment.cancel", resource) && canReleaseRoom;
  const canConfirm = canAccessResource(access, "appointment.confirm", resource);
  const canCheckIn = canAccessResource(access, "appointment.checkIn", resource);
  const canCall = canAccessResource(access, "appointment.callToRoom", resource) && canClaimRoom;
  const canStart = canAccessResource(access, "appointment.startService", resource) && canClaimRoom;
  const canChangeService =
    appointment.status === AppointmentStatus.IN_PROGRESS &&
    canAccessResource(access, "appointment.startService", resource) &&
    canAccessResource(access, "services.read", resource);
  const canComplete = canAccessResource(access, "appointment.complete", resource) && canReleaseRoom;
  const canNoShow = canAccessResource(access, "appointment.noShow", resource) && canReleaseRoom;
  const canChangeRoom =
    canAccessResource(access, "room.assignment.change", resource) && canClaimRoom && canReleaseRoom;
  const canReadOperational =
    canAccessResource(access, "appointment_records.read", resource) &&
    canAccessResource(access, "patients.doctor_notes.read", resource);
  const canWriteOperational =
    canAccessResource(access, "appointment_records.write", resource) &&
    canAccessResource(access, "patients.doctor_notes.write", resource);
  const canReadMessages = canAccessResource(access, "messages.read", resource);
  const canReadHealth = canAccessResource(access, "patients.health.read", resource);
  const canReadAudit = canAccessResource(access, "audit.read", resource);
  const messageTimeline = canReadMessages
    ? await communicationRepository.listAppointmentMessages(access, appointment.id)
    : [];
  const operational = canReadOperational
    ? await crmAppointmentRepository.getAppointmentOperationalDetail(access, appointment.id)
    : null;
  const healthIndicators = canReadHealth
    ? await crmAppointmentRepository.getPatientSafetyIndicators(access, appointment.customer.id)
    : null;
  const auditEvents = canReadAudit
    ? await crmAppointmentRepository.listAppointmentAudit(access, appointment.id)
    : [];
  const operationalRooms = canAccessResource(access, "resources.read")
    ? await crmAppointmentRepository.listOperationalRooms(access, {
        branchId: appointment.branchId,
        serviceId: appointment.serviceId,
      })
    : [];
  const availableRooms = operationalRooms.filter(
    (room) => room.status === "ACTIVE" && room.availableCapacity > 0,
  );
  const changeableServices = canChangeService
    ? (await identityRepository.listServices(access)).filter(
        (service) =>
          service.id !== appointment.serviceId &&
          appointment.provider.services.some(({ serviceId }) => serviceId === service.id) &&
          service.branches.some(
            ({ branchId, isEnabled }) => branchId === appointment.branchId && isEnabled,
          ) &&
          (appointment.actualRoom ?? appointment.room)?.compatibleServices.some(
            ({ serviceId }) => serviceId === service.id,
          ),
      )
    : [];
  const appointmentDay = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: appointment.timezone,
    year: "numeric",
  }).format(appointment.startsAt);
  const doctorDayAppointments =
    appointment.status === AppointmentStatus.COMPLETED
      ? await crmAppointmentRepository.listAppointments(access, {
          branchId: appointment.branchId,
          day: appointmentDay,
          providerId: appointment.providerId,
        })
      : [];
  const nextCheckedIn = doctorDayAppointments.find(
    ({ status }) => status === AppointmentStatus.CHECKED_IN,
  );
  const nextRooms = nextCheckedIn
    ? availableRooms.filter(({ serviceIds }) => serviceIds.includes(nextCheckedIn.serviceId))
    : [];
  const phaseOne = phaseOneMessages[locale];
  const messages = phaseTwoMessages[locale];
  const localStart = localInputValue(appointment.startsAt, appointment.timezone);

  const paymentDetails = parsePaymentNote(operational?.notes);
  const totalMinor = appointment.service.defaultPriceMinor ?? 0;
  const paidMinor = paymentDetails ? paymentDetails.amountMinor : 0;
  const balanceMinor = Math.max(0, totalMinor - paidMinor);

  const followUpDate = new Date(appointment.startsAt.getTime() + 14 * 24 * 60 * 60 * 1000);
  const followUpDay = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: appointment.timezone,
    year: "numeric",
  }).format(followUpDate);

  const receiptData: ReceiptData = {
    appointmentReference: appointment.referenceCode,
    branchName: locale === "ar" ? appointment.branch.nameAr : appointment.branch.nameEn,
    customerName: appointment.customer.displayName,
    customerPhone: appointment.customer.contacts.find(({ kind }) => kind === "PHONE")
      ?.originalValue,
    doctorName:
      locale === "ar" ? appointment.provider.displayNameAr : appointment.provider.displayNameEn,
    endsAt: appointment.endsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
      timeZone: appointment.timezone,
    }),
    paymentDetails,
    postTreatmentInstructions:
      locale === "ar"
        ? appointment.service.postTreatmentInstructionsAr
        : appointment.service.postTreatmentInstructionsEn,
    preTreatmentInstructions:
      locale === "ar"
        ? appointment.service.preTreatmentInstructionsAr
        : appointment.service.preTreatmentInstructionsEn,
    roomName:
      (appointment.actualRoom ?? appointment.room)
        ? locale === "ar"
          ? (appointment.actualRoom ?? appointment.room)?.nameAr
          : (appointment.actualRoom ?? appointment.room)?.nameEn
        : undefined,
    serviceCurrency: appointment.service.currency,
    serviceName: locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn,
    servicePriceMinor: appointment.service.defaultPriceMinor,
    startsAt: appointment.startsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
      timeZone: appointment.timezone,
    }),
  };

  return (
    <section className="page-stack" aria-labelledby="appointment-title">
      <div className="split-heading">
        <div>
          <p className="eyebrow">{messages.appointment}</p>
          <h1 id="appointment-title">{appointment.customer.displayName}</h1>
          <p className="muted">
            {appointment.referenceCode} · {phaseTwoLabel(locale, appointment.status)} ·{" "}
            {appointment.startsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
              timeZone: appointment.timezone,
            })}
          </p>
        </div>
        <div className="row-actions">
          <Link
            className="button button-primary"
            href={`/${locale}/schedule/calendar?patient=${appointment.customer.id}&serviceId=${appointment.service.id}&providerId=${appointment.provider.id}&branchId=${appointment.branchId}&day=${followUpDay}&create=true#create-appointment-title`}
          >
            📅 {messages.bookFollowUp}
          </Link>
          <AppointmentReceiptDialog
            closeLabel={locale === "ar" ? "إغلاق" : "Close"}
            data={receiptData}
            label={messages.printReceipt}
            locale={locale}
          />
        </div>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <nav
        className="workspace-tabs"
        aria-label={locale === "ar" ? "أقسام تفاصيل الموعد" : "Appointment detail sections"}
      >
        <a href="#summary">{locale === "ar" ? "الملخص" : "Summary"}</a>
        <a href="#billing">{locale === "ar" ? "الفاتورة والدفع" : "Billing & Payment"}</a>
        <a href="#customer">{locale === "ar" ? "المريض" : "Patient"}</a>
        <a href="#service">{locale === "ar" ? "الخدمة والتعليمات" : "Service & Instructions"}</a>
        <a href="#provider-resources">{locale === "ar" ? "الطبيب والغرفة" : "Doctor & Room"}</a>
        <a href="#communications">{locale === "ar" ? "الاتصالات" : "Communications"}</a>
        <a href="#history">{locale === "ar" ? "السجل" : "History"}</a>
        {canReadOperational ? (
          <a href="#doctor-notes">{locale === "ar" ? "ملاحظات الطبيب" : "Doctor Notes"}</a>
        ) : null}
        {canReadAudit ? (
          <a href="#appointment-audit">{locale === "ar" ? "التدقيق" : "Audit"}</a>
        ) : null}
      </nav>
      <section className="panel" id="summary" aria-label={messages.appointment}>
        <dl className="details-list">
          <div>
            <dt>{locale === "ar" ? "المرجع" : "Reference"}</dt>
            <dd>{appointment.referenceCode}</dd>
          </div>
          <div>
            <dt>{phaseOne.branch}</dt>
            <dd>{locale === "ar" ? appointment.branch.nameAr : appointment.branch.nameEn}</dd>
          </div>
          <div>
            <dt>{phaseOne.service}</dt>
            <dd>{locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}</dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "الطبيب" : "Doctor"}</dt>
            <dd>
              {locale === "ar"
                ? appointment.provider.displayNameAr
                : appointment.provider.displayNameEn}
            </dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "الغرفة" : "Room"}</dt>
            <dd>
              {(appointment.actualRoom ?? appointment.room)
                ? locale === "ar"
                  ? (appointment.actualRoom ?? appointment.room)?.nameAr
                  : (appointment.actualRoom ?? appointment.room)?.nameEn
                : "—"}
            </dd>
          </div>
          <div>
            <dt>{messages.endTime}</dt>
            <dd>
              {appointment.endsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                timeZone: appointment.timezone,
              })}
            </dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "وقت تجهيز الغرفة" : "Room ready at"}</dt>
            <dd>
              {appointment.calledAt
                ? appointment.calledAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                    timeZone: appointment.timezone,
                  })
                : "—"}
            </dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "بدء الخدمة" : "Service started"}</dt>
            <dd>
              {appointment.serviceStartedAt
                ? appointment.serviceStartedAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                    timeZone: appointment.timezone,
                  })
                : "—"}
            </dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "المدة الفعلية" : "Actual duration"}</dt>
            <dd>
              {appointment.actualDurationMins === null
                ? "—"
                : `${appointment.actualDurationMins} ${locale === "ar" ? "دقيقة" : "min"}`}
            </dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "مصدر الحجز" : "Booking source"}</dt>
            <dd>{appointment.source.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt>{locale === "ar" ? "أنشأه" : "Created by"}</dt>
            <dd>{appointment.createdBy?.name ?? "-"}</dd>
          </div>
          <div>
            <dt>{messages.paymentStatus}</dt>
            <dd>
              <span
                className={`status-pill status-${(paymentDetails?.status ?? "UNPAID").toLowerCase()}`}
              >
                {paymentDetails
                  ? paymentDetails.status === "PAID"
                    ? messages.paid
                    : paymentDetails.status === "PARTIAL"
                      ? messages.partial
                      : messages.waived
                  : messages.unpaid}
              </span>
              {" · "}
              {formatServicePrice(
                locale,
                appointment.service.defaultPriceMinor,
                appointment.service.currency,
              )}
            </dd>
          </div>
        </dl>
      </section>
      <section className="panel page-stack" id="billing" aria-labelledby="billing-title">
        <div className="split-heading">
          <div>
            <p className="eyebrow">
              {locale === "ar" ? "المحاسبة والإيصالات" : "Accounting & Receipts"}
            </p>
            <h2 id="billing-title">{locale === "ar" ? "الفاتورة والدفع" : "Billing & Payment"}</h2>
          </div>
          <div className="row-actions">
            {canWriteOperational ? (
              <OperationDialog
                closeLabel={locale === "ar" ? "إغلاق" : "Close"}
                label={messages.recordPayment}
              >
                <form action={recordAppointmentPaymentAction} className="form-grid">
                  <input name="locale" type="hidden" value={locale} />
                  <input name="appointmentId" type="hidden" value={appointment.id} />
                  <input name="currency" type="hidden" value={appointment.service.currency} />

                  <label className="field">
                    <span className="field-label">{messages.paymentStatus}</span>
                    <select className="select" defaultValue="PAID" name="status" required>
                      <option value="PAID">{messages.paid}</option>
                      <option value="PARTIAL">{messages.partial}</option>
                      <option value="WAIVED">{messages.waived}</option>
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">{messages.paymentMethod}</span>
                    <select className="select" defaultValue="CASH" name="method" required>
                      <option value="CASH">{messages.cash}</option>
                      <option value="CARD">{messages.card}</option>
                      <option value="TRANSFER">{messages.transfer}</option>
                      <option value="INSURANCE">{messages.insurance}</option>
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">
                      {messages.amountPaid} ({appointment.service.currency})
                    </span>
                    <input
                      className="input"
                      defaultValue={appointment.service.defaultPriceMinor ?? 0}
                      min={0}
                      name="amountMinor"
                      required
                      type="number"
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">
                      {locale === "ar"
                        ? "رقم المرجع / الإيصال (اختياري)"
                        : "Reference / Receipt # (Optional)"}
                    </span>
                    <input className="input" name="reference" placeholder="e.g. TX-98432" />
                  </label>

                  <label className="field">
                    <span className="field-label">{messages.paymentNotes}</span>
                    <input
                      className="input"
                      name="notes"
                      placeholder={locale === "ar" ? "ملاحظات الدفع..." : "Payment notes..."}
                    />
                  </label>

                  <SubmitButton>{messages.recordPayment}</SubmitButton>
                </form>
              </OperationDialog>
            ) : null}
            <AppointmentReceiptDialog
              closeLabel={locale === "ar" ? "إغلاق" : "Close"}
              data={receiptData}
              label={messages.printReceipt}
              locale={locale}
            />
          </div>
        </div>

        <dl className="details-list">
          <div>
            <dt>{locale === "ar" ? "سعر الخدمة" : "Service fee"}</dt>
            <dd>{formatServicePrice(locale, totalMinor, appointment.service.currency)}</dd>
          </div>
          <div>
            <dt>{messages.paymentStatus}</dt>
            <dd>
              <strong
                className={`status-pill status-${(paymentDetails?.status ?? "UNPAID").toLowerCase()}`}
              >
                {paymentDetails
                  ? paymentDetails.status === "PAID"
                    ? messages.paid
                    : paymentDetails.status === "PARTIAL"
                      ? messages.partial
                      : messages.waived
                  : messages.unpaid}
              </strong>
            </dd>
          </div>
          <div>
            <dt>{messages.amountPaid}</dt>
            <dd className="text-success">
              {formatServicePrice(
                locale,
                paidMinor,
                paymentDetails?.currency ?? appointment.service.currency,
              )}
            </dd>
          </div>
          <div>
            <dt>{messages.balanceDue}</dt>
            <dd className={balanceMinor > 0 ? "text-danger" : ""}>
              {formatServicePrice(locale, balanceMinor, appointment.service.currency)}
            </dd>
          </div>
          {paymentDetails ? (
            <>
              <div>
                <dt>{messages.paymentMethod}</dt>
                <dd>{paymentDetails.method}</dd>
              </div>
              <div>
                <dt>{locale === "ar" ? "تاريخ تسجيل الدفع" : "Recorded at"}</dt>
                <dd>
                  {new Date(paymentDetails.recordedAt).toLocaleString(
                    locale === "ar" ? "ar-JO" : "en-JO",
                    { timeZone: appointment.timezone },
                  )}
                </dd>
              </div>
              {paymentDetails.notes ? (
                <div>
                  <dt>{messages.paymentNotes}</dt>
                  <dd>{paymentDetails.notes}</dd>
                </div>
              ) : null}
            </>
          ) : null}
        </dl>
      </section>
      <section className="panel" id="customer">
        <h2>{locale === "ar" ? "المريض" : "Patient"}</h2>
        <p>
          <a href={`/${locale}/customers/${appointment.customer.id}`}>
            {appointment.customer.displayName}
          </a>
        </p>
        <p className="muted">
          {appointment.customer.contacts.map(({ originalValue }) => originalValue).join(", ") ||
            (locale === "ar" ? "لا توجد وسيلة اتصال" : "No contact method")}
        </p>
        {healthIndicators ? (
          <ul>
            <li>
              {healthIndicators.allergyInformationAvailable
                ? locale === "ar"
                  ? "معلومات الحساسية متوفرة"
                  : "Allergy information available"
                : locale === "ar"
                  ? "لا تظهر تفاصيل الحساسية هنا"
                  : "Allergy details are not shown here"}
            </li>
            <li>
              {healthIndicators.conditionInformationAvailable
                ? locale === "ar"
                  ? "معلومات الحالة الصحية متوفرة"
                  : "Medical-condition information available"
                : locale === "ar"
                  ? "لا تظهر تفاصيل الحالة الصحية هنا"
                  : "Condition details are not shown here"}
            </li>
          </ul>
        ) : null}
      </section>
      <section className="panel" id="service">
        <h2>{locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}</h2>
        <h3>{locale === "ar" ? "تعليمات ما قبل الخدمة" : "Pre-treatment instructions"}</h3>
        <p>
          {(locale === "ar"
            ? appointment.service.preTreatmentInstructionsAr
            : appointment.service.preTreatmentInstructionsEn) ?? "-"}
        </p>
        <h3>{locale === "ar" ? "تعليمات ما بعد الخدمة" : "Post-treatment instructions"}</h3>
        <p>
          {(locale === "ar"
            ? appointment.service.postTreatmentInstructionsAr
            : appointment.service.postTreatmentInstructionsEn) ?? "-"}
        </p>
      </section>
      <section className="panel" id="provider-resources">
        <h2>{locale === "ar" ? "الطبيب والغرفة" : "Doctor & Room"}</h2>
        <p>
          {locale === "ar"
            ? appointment.provider.displayNameAr
            : appointment.provider.displayNameEn}
        </p>
        <ul>
          {appointment.resourceReservations.map(({ resource }) => (
            <li key={resource.nameEn}>
              {locale === "ar" ? resource.nameAr : resource.nameEn} · {resource.status}
            </li>
          ))}
        </ul>
        {appointment.roomOccupancies.length > 0 ? (
          <dl className="details-list">
            {appointment.roomOccupancies.map((occupancy) => (
              <div key={occupancy.id}>
                <dt>{locale === "ar" ? "إشغال الغرفة" : "Room occupancy"}</dt>
                <dd>
                  {locale === "ar" ? occupancy.resource.nameAr : occupancy.resource.nameEn} ·{" "}
                  {occupancy.releasedAt
                    ? locale === "ar"
                      ? "تم التحرير"
                      : "Released"
                    : locale === "ar"
                      ? "مشغولة الآن"
                      : "Currently occupied"}
                  {" · "}
                  {occupancy.claimedAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                    timeZone: appointment.timezone,
                  })}
                  {" · "}
                  {occupancy.claimedBy.name}
                  {occupancy.releasedAt && occupancy.releasedBy
                    ? ` · ${occupancy.releasedBy.name}`
                    : ""}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </section>
      {canReschedule &&
      (appointment.status === AppointmentStatus.PENDING ||
        appointment.status === AppointmentStatus.CONFIRMED) ? (
        <form action={rescheduleAppointmentAction} className="panel inline-form">
          <input name="locale" type="hidden" value={locale} />
          <input name="appointmentId" type="hidden" value={appointment.id} />
          <input name="expectedVersion" type="hidden" value={appointment.version} />
          <input name="idempotencyKey" type="hidden" value={randomUUID()} />
          <label className="field">
            <span className="field-label">{messages.reschedule}</span>
            <input
              className="input"
              defaultValue={localStart}
              name="startsAtLocal"
              required
              type="datetime-local"
            />
          </label>
          <SubmitButton tone="secondary">{messages.reschedule}</SubmitButton>
        </form>
      ) : null}
      <section className="panel page-stack" aria-labelledby="appointment-actions-title">
        <h2 id="appointment-actions-title">
          {locale === "ar" ? "إجراءات الموعد" : "Appointment actions"}
        </h2>
        <div className="row-actions">
          {appointment.status === AppointmentStatus.PENDING && canConfirm ? (
            <TransitionButton
              appointment={appointment}
              label={locale === "ar" ? "تأكيد" : "Confirm"}
              locale={locale}
              status={AppointmentStatus.CONFIRMED}
            />
          ) : null}
          {appointment.status === AppointmentStatus.CONFIRMED && canCheckIn ? (
            <TransitionButton
              appointment={appointment}
              label={messages.checkIn}
              locale={locale}
              status={AppointmentStatus.CHECKED_IN}
            />
          ) : null}
          {appointment.status === AppointmentStatus.CHECKED_IN && canCall ? (
            <form action={callAppointmentToRoomAction} className="inline-form">
              <OperationHidden appointment={appointment} locale={locale} />
              <label className="field">
                <span className="field-label">{locale === "ar" ? "الغرفة" : "Room"}</span>
                <select className="select" name="roomId" required>
                  <option value="">{locale === "ar" ? "اختر الغرفة" : "Select room"}</option>
                  {availableRooms.map((room) => (
                    <option key={room.id} value={room.id}>
                      {locale === "ar" ? room.nameAr : room.nameEn} ({room.availableCapacity})
                    </option>
                  ))}
                </select>
              </label>
              <SubmitButton disabled={availableRooms.length === 0}>
                {locale === "ar" ? "استدعاء إلى الغرفة" : "Call to Room"}
              </SubmitButton>
            </form>
          ) : null}
          {appointment.status === AppointmentStatus.CALLED && canStart ? (
            <form action={startAppointmentServiceAction}>
              <OperationHidden appointment={appointment} locale={locale} />
              <SubmitButton>{locale === "ar" ? "بدء الخدمة" : "Start Service"}</SubmitButton>
            </form>
          ) : null}
          {appointment.status === AppointmentStatus.IN_PROGRESS && canChangeService ? (
            <OperationDialog
              closeLabel={locale === "ar" ? "إغلاق" : "Close"}
              label={locale === "ar" ? "تغيير الخدمة" : "Change Service"}
            >
              <form action={changeAppointmentServiceAction} className="form-grid">
                <OperationHidden appointment={appointment} locale={locale} />
                <label className="field">
                  <span className="field-label">
                    {locale === "ar" ? "الخدمة الجديدة" : "New service"}
                  </span>
                  <select className="select" name="serviceId" required>
                    <option value="">{locale === "ar" ? "اختر خدمة" : "Select a service"}</option>
                    {changeableServices.map((service) => (
                      <option key={service.id} value={service.id}>
                        {locale === "ar" ? service.nameAr : service.nameEn}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="field-label">
                    {locale === "ar" ? "سبب التغيير (اختياري)" : "Reason for change (optional)"}
                  </span>
                  <input className="input" maxLength={500} name="reason" />
                </label>
                <p className="field-hint">
                  {locale === "ar"
                    ? "سيتم التحقق من صلاحية الطبيب والغرفة والموارد وتحديث متطلبات المخزون."
                    : "Doctor, room, resources, and inventory requirements will be revalidated."}
                </p>
                <SubmitButton disabled={changeableServices.length === 0}>
                  {locale === "ar" ? "حفظ الخدمة" : "Save Service"}
                </SubmitButton>
              </form>
            </OperationDialog>
          ) : null}
          {appointment.status === AppointmentStatus.CALLED && canChangeRoom ? (
            <form action={changeAppointmentRoomAction} className="inline-form">
              <OperationHidden appointment={appointment} locale={locale} />
              <select
                aria-label={locale === "ar" ? "الغرفة الجديدة" : "New room"}
                className="select"
                name="roomId"
                required
              >
                <option value="">{locale === "ar" ? "غيّر الغرفة" : "Change Room"}</option>
                {availableRooms
                  .filter((room) => room.id !== appointment.actualRoomId)
                  .map((room) => (
                    <option key={room.id} value={room.id}>
                      {locale === "ar" ? room.nameAr : room.nameEn} ({room.availableCapacity})
                    </option>
                  ))}
              </select>
              <SubmitButton tone="secondary">
                {locale === "ar" ? "تغيير الغرفة" : "Change Room"}
              </SubmitButton>
            </form>
          ) : null}
          {appointment.status === AppointmentStatus.CALLED && canCall ? (
            <form action={resendRoomMessageAction}>
              <OperationHidden appointment={appointment} locale={locale} />
              <SubmitButton tone="secondary">
                {locale === "ar" ? "إرسال رسالة الغرفة مرة أخرى" : "Send Room Message Again"}
              </SubmitButton>
            </form>
          ) : null}
          {appointment.status === AppointmentStatus.CONFIRMED && canNoShow ? (
            <TransitionButton
              appointment={appointment}
              label={messages.markNoShow}
              locale={locale}
              reasonOptional
              status={AppointmentStatus.NO_SHOW}
            />
          ) : null}
        </div>
        {appointment.status === AppointmentStatus.COMPLETED && canReadConsumption ? (
          <div className="panel callout-panel">
            <h3>
              {locale === "ar" ? "الخطوات التالية بعد إتمام الخدمة" : "Post-Completion Next Steps"}
            </h3>
            <p className="muted">
              {locale === "ar"
                ? "يمكنك الآن تحصيل الدفعة، طباعة الإيصال والتعليمات، أو جدولة موعد المتابعة القادم للمريض."
                : "You can now record payment, print the receipt & instructions, or schedule the patient's next visit."}
            </p>
            <div className="row-actions">
              <Link
                className="button button-primary"
                href={`/${locale}/schedule/calendar?patient=${appointment.customer.id}&serviceId=${appointment.service.id}&providerId=${appointment.provider.id}&branchId=${appointment.branchId}&day=${followUpDay}&create=true#create-appointment-title`}
              >
                📅 {messages.bookFollowUp}
              </Link>
              <AppointmentReceiptDialog
                closeLabel={locale === "ar" ? "إغلاق" : "Close"}
                data={receiptData}
                label={messages.printReceipt}
                locale={locale}
              />
            </div>
          </div>
        ) : null}
        {appointment.status === AppointmentStatus.COMPLETED ? (
          <AppointmentInventoryConsumptionSection
            consumptions={inventoryContext.consumptions}
            isReadonly
            locale={locale}
            requirements={inventoryContext.requirements}
          />
        ) : null}
        {appointment.status === AppointmentStatus.CALLED && canReadInventory ? (
          <AppointmentInventoryConsumptionSection
            isReadonly
            locale={locale}
            requirements={inventoryContext.requirements}
          />
        ) : null}
        {appointment.status === AppointmentStatus.IN_PROGRESS && canComplete ? (
          <form action={transitionAppointmentAction} className="form-grid">
            <TransitionHidden
              appointment={appointment}
              locale={locale}
              status={AppointmentStatus.COMPLETED}
            />
            {canAdjustConsumption ? (
              <AppointmentInventoryConsumptionSection
                batches={inventoryContext.batches}
                locale={locale}
                locations={inventoryContext.locations}
                requirements={inventoryContext.requirements}
              />
            ) : null}
            {canWriteOperational ? (
              <>
                <label className="field">
                  <span className="field-label">{messages.recordSummary}</span>
                  <input className="input" name="recordSummary" maxLength={5000} required />
                </label>
                <label className="field">
                  <span className="field-label">{messages.recordDetails}</span>
                  <textarea className="input textarea" name="recordDetails" maxLength={10000} />
                </label>
              </>
            ) : null}
            <div className="form-actions">
              <SubmitButton>{messages.complete}</SubmitButton>
            </div>
          </form>
        ) : null}
        {canCancel &&
        (appointment.status === AppointmentStatus.PENDING ||
          appointment.status === AppointmentStatus.CONFIRMED ||
          appointment.status === AppointmentStatus.CHECKED_IN ||
          appointment.status === AppointmentStatus.CALLED ||
          appointment.status === AppointmentStatus.IN_PROGRESS) ? (
          <OperationDialog closeLabel={locale === "ar" ? "إغلاق" : "Close"} label={messages.cancel}>
            <form action={transitionAppointmentAction} className="form-grid">
              <TransitionHidden
                appointment={appointment}
                locale={locale}
                status={AppointmentStatus.CANCELLED}
              />
              <label className="field">
                <span className="field-label">
                  {locale === "ar" ? "سبب الإلغاء" : "Cancellation reason"}
                </span>
                <input className="input" name="reason" required />
              </label>
              {canWriteOperational ? (
                <label className="field">
                  <span className="field-label">
                    {locale === "ar" ? "ملاحظة داخلية اختيارية" : "Optional internal note"}
                  </span>
                  <textarea className="textarea" maxLength={10000} name="internalNote" rows={2} />
                </label>
              ) : null}
              <label className="field">
                <span className="field-label">
                  {locale === "ar" ? "إشعار المريض" : "Patient notification"}
                </span>
                <select className="select" defaultValue="SEND" name="notificationChoice">
                  <option value="SEND">
                    {locale === "ar" ? "إرسال إشعار (محاكاة)" : "Send notification (simulated)"}
                  </option>
                  <option value="SKIP">{locale === "ar" ? "عدم الإرسال" : "Do not send"}</option>
                </select>
              </label>
              <SubmitButton tone="danger">{messages.cancel}</SubmitButton>
            </form>
          </OperationDialog>
        ) : null}
      </section>
      {nextCheckedIn &&
      nextRooms.length > 0 &&
      canAccessResource(access, "doctor.queue.next", {
        branchId: nextCheckedIn.branchId,
        staffProfileId: nextCheckedIn.providerId,
      }) &&
      canAccessResource(access, "appointment.callToRoom", {
        branchId: nextCheckedIn.branchId,
        staffProfileId: nextCheckedIn.providerId,
      }) &&
      canAccessResource(access, "room.occupancy.claim", {
        branchId: nextCheckedIn.branchId,
        staffProfileId: nextCheckedIn.providerId,
      }) ? (
        <form action={callAppointmentToRoomAction} className="panel inline-form">
          <OperationHidden appointment={nextCheckedIn} locale={locale} />
          <input name="asNext" type="hidden" value="true" />
          <label className="field">
            <span className="field-label">
              {locale === "ar" ? "الموعد التالي" : "Call Next Appointment"}
            </span>
            <select className="select" name="roomId" required>
              <option value="">{locale === "ar" ? "اختر الغرفة" : "Select room"}</option>
              {nextRooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {locale === "ar" ? room.nameAr : room.nameEn}
                </option>
              ))}
            </select>
          </label>
          <SubmitButton>
            {locale === "ar" ? "استدعاء الموعد التالي" : "Call Next Appointment"}
          </SubmitButton>
        </form>
      ) : null}
      {operational ? (
        <section className="panel page-stack" id="doctor-notes" aria-labelledby="operations-title">
          <h2 id="operations-title">
            {locale === "ar" ? "التشغيل الداخلي" : "Internal operations"}
          </h2>
          {operational.record ? (
            <article>
              <h3>{messages.recordSummary}</h3>
              <p>{operational.record.summary}</p>
              {operational.record.details ? (
                <p className="muted">{operational.record.details}</p>
              ) : null}
            </article>
          ) : null}
          <div>
            <h3>{messages.internalNote}</h3>
            <ul className="note-list">
              {operational.notes.map((note) => (
                <li key={note.id}>
                  <strong>{note.author.name}</strong>
                  <span>{note.body}</span>
                </li>
              ))}
            </ul>
          </div>
          {canWriteOperational ? (
            <form action={addAppointmentNoteAction} className="form-stack">
              <input name="locale" type="hidden" value={locale} />
              <input name="appointmentId" type="hidden" value={appointment.id} />
              <label className="field">
                <span className="field-label">{messages.internalNote}</span>
                <textarea className="input textarea" name="body" required />
              </label>
              <div>
                <SubmitButton tone="secondary">
                  {locale === "ar" ? "إضافة ملاحظة" : "Add note"}
                </SubmitButton>
              </div>
            </form>
          ) : null}
        </section>
      ) : null}
      <section className="panel" id="history" aria-labelledby="history-title">
        <h2 id="history-title">{locale === "ar" ? "سجل الحالة" : "Status history"}</h2>
        <ul className="history-list">
          {appointment.history.map((entry) => (
            <li key={entry.id}>
              <strong>{historyEntryLabel(locale, entry)}</strong>{" "}
              <small>
                {entry.createdAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO")} ·{" "}
                {entry.actor?.name ?? (locale === "ar" ? "النظام" : "System")} ·{" "}
                {entry.transitionSource.replaceAll("_", " ")}
                {entry.reason && entry.eventType === "STATUS_CHANGED" ? ` · ${entry.reason}` : ""}
              </small>
            </li>
          ))}
        </ul>
      </section>
      {canReadMessages ? (
        <div id="communications">
          {appointment.operationalEvents.length > 0 ? (
            <section className="panel" aria-labelledby="operational-events-title">
              <h2 id="operational-events-title">
                {locale === "ar" ? "أحداث التشغيل" : "Operational events"}
              </h2>
              <ol className="history-list">
                {appointment.operationalEvents.map((event) => (
                  <li key={`${event.eventType}:${event.createdAt.toISOString()}`}>
                    <strong>{event.eventType.replaceAll("_", " ")}</strong>
                    <small>
                      {event.createdAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO")} ·{" "}
                      {event.status === "PROCESSED"
                        ? locale === "ar"
                          ? "تمت المحاكاة"
                          : "Simulated"
                        : locale === "ar"
                          ? "في قائمة الانتظار"
                          : "Queued"}
                    </small>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          <MessageTimeline locale={locale} messages={messageTimeline} />
        </div>
      ) : null}
      {canReadAudit ? (
        <section
          className="panel page-stack"
          id="appointment-audit"
          aria-labelledby="appointment-audit-title"
        >
          <h2 id="appointment-audit-title">
            {locale === "ar" ? "سجل تدقيق الموعد" : "Appointment audit"}
          </h2>
          {auditEvents.length ? (
            <ol className="history-list">
              {auditEvents.map((event) => (
                <li key={event.id}>
                  <strong>{event.action}</strong>
                  <small>
                    {event.createdAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO")} ·{" "}
                    {event.actor?.name ?? "System"}
                  </small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">
              {locale === "ar" ? "لا يوجد نشاط تدقيق." : "No audit activity."}
            </p>
          )}
        </section>
      ) : null}
    </section>
  );
}

function TransitionButton({
  appointment,
  label,
  locale,
  reasonOptional,
  reasonRequired,
  status,
}: Readonly<{
  appointment: { id: string; version: number };
  label: string;
  locale: "ar" | "en";
  reasonOptional?: boolean;
  reasonRequired?: boolean;
  status: AppointmentStatus;
}>) {
  if (reasonRequired || reasonOptional) {
    return (
      <OperationDialog closeLabel={locale === "ar" ? "إغلاق" : "Close"} label={label}>
        <form action={transitionAppointmentAction} className="form-grid">
          <TransitionHidden appointment={appointment} locale={locale} status={status} />
          <p>
            {locale === "ar"
              ? "أكد الإجراء قبل حفظ حالة الموعد."
              : "Confirm this action before saving the appointment status."}
          </p>
          <label className="field" htmlFor={`reason-${status}`}>
            <span className="field-label">
              {locale === "ar" ? "سبب اختياري" : "Optional reason"}
            </span>
            <input
              className="input"
              id={`reason-${status}`}
              name="reason"
              required={reasonRequired}
            />
          </label>
          <SubmitButton tone="secondary">{label}</SubmitButton>
        </form>
      </OperationDialog>
    );
  }
  return (
    <form action={transitionAppointmentAction}>
      <TransitionHidden appointment={appointment} locale={locale} status={status} />
      <SubmitButton tone="secondary">{label}</SubmitButton>
    </form>
  );
}

function TransitionHidden({
  appointment,
  locale,
  status,
}: Readonly<{
  appointment: { id: string; version: number };
  locale: "ar" | "en";
  status: AppointmentStatus;
}>) {
  return (
    <>
      <input name="locale" type="hidden" value={locale} />
      <input name="appointmentId" type="hidden" value={appointment.id} />
      <input name="expectedVersion" type="hidden" value={appointment.version} />
      <input name="idempotencyKey" type="hidden" value={randomUUID()} />
      <input name="toStatus" type="hidden" value={status} />
    </>
  );
}

function OperationHidden({
  appointment,
  locale,
}: Readonly<{
  appointment: { id: string; version: number };
  locale: "ar" | "en";
}>) {
  return (
    <>
      <input name="locale" type="hidden" value={locale} />
      <input name="appointmentId" type="hidden" value={appointment.id} />
      <input name="expectedVersion" type="hidden" value={appointment.version} />
      <input name="idempotencyKey" type="hidden" value={randomUUID()} />
    </>
  );
}

function localInputValue(date: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
    hourCycle: "h23",
    minute: "2-digit",
    month: "2-digit",
    timeZone: timezone,
    year: "numeric",
  })
    .formatToParts(date)
    .filter((part) => part.type !== "literal");
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}T${value.hour === "24" ? "00" : value.hour}:${value.minute}`;
}

function historyEntryLabel(
  locale: "ar" | "en",
  entry: Readonly<{
    eventType: string;
    fromStatus: AppointmentStatus | null;
    toStatus: AppointmentStatus;
  }>,
): string {
  if (entry.eventType === "STATUS_CHANGED") {
    return `${entry.fromStatus ? `${phaseTwoLabel(locale, entry.fromStatus)} → ` : ""}${phaseTwoLabel(locale, entry.toStatus)}`;
  }
  const labels: Readonly<Record<string, readonly [string, string]>> = {
    CREATED: ["Created", "تم الإنشاء"],
    DOCTOR_CHANGED: ["Doctor Changed", "تم تغيير الطبيب"],
    SERVICE_CHANGED: ["Service Changed", "تم تغيير الخدمة"],
    RESCHEDULED: ["Rescheduled", "تمت إعادة الجدولة"],
    ROOM_CHANGED: ["Room Changed", "تم تغيير الغرفة"],
  };
  const label = labels[entry.eventType];
  return label ? label[locale === "ar" ? 1 : 0] : entry.eventType.replaceAll("_", " ");
}
