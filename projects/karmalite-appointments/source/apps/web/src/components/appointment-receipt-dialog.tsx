"use client";

import { useRef } from "react";
import type { SupportedLocale } from "@jormall/contracts/locales";
import { formatServicePrice } from "./service-price";

export type ReceiptData = Readonly<{
  appointmentReference: string;
  branchName: string;
  customerName: string;
  customerPhone?: string | undefined;
  doctorName: string;
  endsAt: string;
  paymentDetails?:
    | Readonly<{
        amountMinor: number;
        currency: string;
        method: string;
        notes?: string | undefined;
        recordedAt: string;
        status: "PAID" | "PARTIAL" | "UNPAID" | "WAIVED";
      }>
    | undefined;
  postTreatmentInstructions?: string | null | undefined;
  preTreatmentInstructions?: string | null | undefined;
  roomName?: string | undefined;
  serviceCurrency: string;
  serviceName: string;
  servicePriceMinor: number | null;
  startsAt: string;
}>;

export function AppointmentReceiptDialog({
  closeLabel,
  data,
  label,
  locale,
}: Readonly<{
  closeLabel: string;
  data: ReceiptData;
  label: string;
  locale: SupportedLocale;
}>) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const isAr = locale === "ar";

  const totalMinor = data.servicePriceMinor ?? 0;
  const paidMinor = data.paymentDetails ? data.paymentDetails.amountMinor : 0;
  const balanceMinor = Math.max(0, totalMinor - paidMinor);

  const statusLabel = () => {
    const status = data.paymentDetails?.status ?? "UNPAID";
    switch (status) {
      case "PAID":
        return isAr ? "مدفوع بالكامل" : "Paid in Full";
      case "PARTIAL":
        return isAr ? "مدفوع جزئياً" : "Partially Paid";
      case "WAIVED":
        return isAr ? "معفى / مجاني" : "Waived / Complimentary";
      case "UNPAID":
      default:
        return isAr ? "غير مدفوع" : "Unpaid";
    }
  };

  const methodLabel = () => {
    const method = data.paymentDetails?.method;
    switch (method) {
      case "CASH":
        return isAr ? "نقداً" : "Cash";
      case "CARD":
        return isAr ? "بطاقة دفع إلكتروني" : "Card";
      case "TRANSFER":
        return isAr ? "تحويل بنكي / كليك" : "Bank Transfer / CliQ";
      case "INSURANCE":
        return isAr ? "تأمين" : "Insurance";
      default:
        return method ?? (isAr ? "غير محدد" : "Not specified");
    }
  };

  return (
    <>
      <button
        className="button button-secondary"
        onClick={() => dialogRef.current?.showModal()}
        type="button"
      >
        <span aria-hidden="true">🖨️</span> {label}
      </button>
      <dialog className="operation-dialog receipt-dialog" ref={dialogRef}>
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

        <div className="receipt-container" id="printable-receipt">
          <header className="receipt-header">
            <div className="receipt-clinic-badge">
              <span className="receipt-clinic-icon" aria-hidden="true">
                🏥
              </span>
              <div>
                <h3 className="receipt-branch-name">{data.branchName}</h3>
                <p className="receipt-subtitle">
                  {isAr ? "إيصال خدمة وبطاقة موعد" : "Service Receipt & Appointment Slip"}
                </p>
              </div>
            </div>
            <div className="receipt-ref-badge">
              <span className="receipt-ref-label">{isAr ? "رقم المرجع" : "Ref Code"}</span>
              <strong className="receipt-ref-code">{data.appointmentReference}</strong>
            </div>
          </header>

          <hr className="receipt-divider" />

          <div className="receipt-grid">
            <div>
              <span className="receipt-field-label">{isAr ? "المريض" : "Patient"}</span>
              <strong className="receipt-field-value">{data.customerName}</strong>
              {data.customerPhone ? (
                <span className="receipt-field-sub">{data.customerPhone}</span>
              ) : null}
            </div>
            <div>
              <span className="receipt-field-label">
                {isAr ? "الطبيب / الأخصائي" : "Doctor / Specialist"}
              </span>
              <strong className="receipt-field-value">{data.doctorName}</strong>
              {data.roomName ? (
                <span className="receipt-field-sub">
                  {isAr ? "الغرفة:" : "Room:"} {data.roomName}
                </span>
              ) : null}
            </div>
            <div>
              <span className="receipt-field-label">{isAr ? "وقت الموعد" : "Date & Time"}</span>
              <strong className="receipt-field-value">{data.startsAt}</strong>
            </div>
            <div>
              <span className="receipt-field-label">{isAr ? "حالة الدفع" : "Payment Status"}</span>
              <span
                className={`receipt-status-pill status-${(data.paymentDetails?.status ?? "UNPAID").toLowerCase()}`}
              >
                {statusLabel()}
              </span>
            </div>
          </div>

          <hr className="receipt-divider" />

          <table className="receipt-items-table">
            <thead>
              <tr>
                <th>{isAr ? "الخدمة" : "Service Description"}</th>
                <th className="text-end">{isAr ? "السعر" : "Price"}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>{data.serviceName}</strong>
                </td>
                <td className="text-end">
                  {formatServicePrice(locale, data.servicePriceMinor, data.serviceCurrency)}
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>{isAr ? "المجموع" : "Total"}</td>
                <td className="text-end">
                  {formatServicePrice(locale, totalMinor, data.serviceCurrency)}
                </td>
              </tr>
              {data.paymentDetails ? (
                <>
                  <tr>
                    <td>
                      {isAr ? "المبلغ المدفوع" : "Amount Paid"} ({methodLabel()})
                    </td>
                    <td className="text-end text-success">
                      {formatServicePrice(locale, paidMinor, data.paymentDetails.currency)}
                    </td>
                  </tr>
                  {balanceMinor > 0 ? (
                    <tr className="receipt-balance-row">
                      <td>{isAr ? "المبلغ المتبقي" : "Balance Due"}</td>
                      <td className="text-end text-danger">
                        {formatServicePrice(locale, balanceMinor, data.serviceCurrency)}
                      </td>
                    </tr>
                  ) : null}
                </>
              ) : (
                <tr className="receipt-balance-row">
                  <td>{isAr ? "المبلغ المستحق" : "Amount Due"}</td>
                  <td className="text-end text-danger">
                    {formatServicePrice(locale, totalMinor, data.serviceCurrency)}
                  </td>
                </tr>
              )}
            </tfoot>
          </table>

          {data.paymentDetails?.notes ? (
            <p className="receipt-payment-note">
              <strong>{isAr ? "ملاحظة الدفع: " : "Payment Note: "}</strong>
              {data.paymentDetails.notes}
            </p>
          ) : null}

          {data.postTreatmentInstructions ? (
            <div className="receipt-instructions">
              <h4>
                {isAr ? "تعليمات وتوصيات ما بعد الجلسة" : "Post-Treatment Instructions & Care"}
              </h4>
              <p>{data.postTreatmentInstructions}</p>
            </div>
          ) : null}

          <footer className="receipt-footer">
            <p className="receipt-thankyou">
              {isAr
                ? "شكراً لزيارتكم! نتمنى لكم دوام الصحة والعافية."
                : "Thank you for visiting! Wishing you health and wellness."}
            </p>
          </footer>
        </div>

        <div className="receipt-dialog-actions">
          <button
            className="button button-primary"
            onClick={() => {
              window.print();
            }}
            type="button"
          >
            <span aria-hidden="true">🖨️</span> {isAr ? "طباعة الإيصال الآن" : "Print Receipt Now"}
          </button>
          <button
            className="button button-secondary"
            onClick={() => dialogRef.current?.close()}
            type="button"
          >
            {closeLabel}
          </button>
        </div>
      </dialog>
    </>
  );
}
