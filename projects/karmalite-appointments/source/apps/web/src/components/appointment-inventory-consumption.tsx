"use client";

import { useState } from "react";

export type ServiceInventoryRequirementItem = {
  id: string;
  itemId: string;
  expectedQuantity: unknown;
  unitOfMeasure: string;
  isRequired: boolean;
  reservationMode: string;
  item: {
    id: string;
    name: string;
    unitOfMeasure?: string;
  };
};

export type InventoryBatchOption = {
  id: string;
  itemId: string;
  batchNumber: string;
  expiryDate: Date | string | null;
  quantity: unknown;
};

export type InventoryLocationOption = {
  id: string;
  name: string;
  isDefault?: boolean;
};

export type RecordedConsumptionItem = {
  id: string;
  itemId: string;
  expectedQuantity: unknown;
  actualQuantity: unknown;
  unitOfMeasure: string;
  isReconciliationRequired?: boolean;
  reconciliationNote?: string | null;
  item: { name: string };
  batch?: { batchNumber: string } | null;
  location?: { name: string } | null;
};

interface Props {
  requirements: readonly ServiceInventoryRequirementItem[];
  batches?: readonly InventoryBatchOption[];
  locations?: readonly InventoryLocationOption[];
  locale: "ar" | "en";
  isReadonly?: boolean;
  consumptions?: readonly RecordedConsumptionItem[];
}

export function AppointmentInventoryConsumptionSection({
  requirements,
  batches = [],
  locations = [],
  locale,
  isReadonly = false,
  consumptions = [],
}: Readonly<Props>) {
  const isAr = locale === "ar";
  const defaultLoc = locations.find((l) => l.isDefault) ?? locations[0];

  const [items, setItems] = useState(() =>
    requirements.map((req) => {
      const itemBatches = batches.filter((b) => b.itemId === req.itemId);
      const recommendedBatch = itemBatches[0];
      return {
        actualQuantity: Number(req.expectedQuantity),
        batchId: recommendedBatch?.id ?? "",
        expectedQuantity: Number(req.expectedQuantity),
        itemId: req.itemId,
        locationId: defaultLoc?.id ?? "",
        name: req.item.name,
        reconciliationNote: "",
        unitOfMeasure: req.unitOfMeasure || req.item.unitOfMeasure || "unit",
      };
    }),
  );

  const serialized = JSON.stringify(
    items.map((i) => ({
      actualQuantity: i.actualQuantity,
      batchId: i.batchId || undefined,
      expectedQuantity: i.expectedQuantity,
      itemId: i.itemId,
      locationId: i.locationId || undefined,
      reconciliationNote: i.reconciliationNote || undefined,
      unitOfMeasure: i.unitOfMeasure,
    })),
  );

  if (isReadonly) {
    if (consumptions && consumptions.length > 0) {
      return (
        <div className="panel" style={{ marginTop: "1rem" }}>
          <h3>{isAr ? "المواد المستهلكة في الموعد" : "Consumed Inventory Items"}</h3>
          <div className="table-wrapper" style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ width: "100%", textAlign: "start" }}>
              <thead>
                <tr>
                  <th>{isAr ? "الصنف" : "Item"}</th>
                  <th>{isAr ? "المتوقع" : "Expected"}</th>
                  <th>{isAr ? "الفعلي" : "Actual"}</th>
                  <th>{isAr ? "التشغيلة" : "Batch"}</th>
                  <th>{isAr ? "الموقع" : "Location"}</th>
                  <th>{isAr ? "ملاحظة" : "Note"}</th>
                </tr>
              </thead>
              <tbody>
                {consumptions.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.item.name}</strong>
                    </td>
                    <td>
                      {String(c.expectedQuantity)} {c.unitOfMeasure}
                    </td>
                    <td>
                      {String(c.actualQuantity)} {c.unitOfMeasure}
                    </td>
                    <td>{c.batch?.batchNumber ?? "—"}</td>
                    <td>{c.location?.name ?? "—"}</td>
                    <td>
                      {c.isReconciliationRequired ? (
                        <span className="status status-warning" style={{ display: "inline-block" }}>
                          {isAr ? "يتطلب تسوية" : "Reconciliation"}
                        </span>
                      ) : null}
                      {c.reconciliationNote ? ` ${c.reconciliationNote}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
    }

    if (requirements.length === 0) {
      return null;
    }

    return (
      <div className="panel" style={{ marginTop: "0.5rem" }}>
        <h4>{isAr ? "المواد المتوقعة للخدمة" : "Expected Service Materials"}</h4>
        <ul style={{ listStyle: "disc", paddingInlineStart: "1.5rem", margin: "0.5rem 0" }}>
          {requirements.map((req) => (
            <li key={req.id}>
              <strong>{req.item.name}</strong>: {String(req.expectedQuantity)} {req.unitOfMeasure}{" "}
              {req.reservationMode === "RESERVE_ON_CONFIRMATION" ? (
                <span className="status" style={{ fontSize: "0.75rem" }}>
                  {isAr ? "محجوز عند التأكيد" : "Reserved"}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (requirements.length === 0) {
    return null;
  }

  return (
    <div
      className="panel"
      style={{
        border: "1px solid var(--border-color, #e2e8f0)",
        padding: "1rem",
        borderRadius: "8px",
        margin: "0.75rem 0",
      }}
    >
      <h3 style={{ margin: "0 0 0.5rem 0", fontSize: "1rem" }}>
        {isAr ? "المواد المستخدمة (المخزون)" : "Items Used (Inventory)"}
      </h3>
      <p style={{ margin: "0 0 0.75rem 0", fontSize: "0.85rem", opacity: 0.8 }}>
        {isAr
          ? "راجع الكميات الفعلية المستخدمة في الخدمة قبل إنهاء الموعد."
          : "Verify actual materials consumed during the service before completion."}
      </p>
      <input name="consumptions" type="hidden" value={serialized} />
      <div className="page-stack" style={{ gap: "0.75rem" }}>
        {items.map((item, idx) => {
          const itemBatches = batches.filter((b) => b.itemId === item.itemId);
          return (
            <div
              key={item.itemId}
              style={{
                background: "var(--surface-muted, #f8fafc)",
                border: "1px solid var(--border-color, #e2e8f0)",
                borderRadius: "6px",
                padding: "0.75rem",
              }}
            >
              <div
                style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}
              >
                <strong>{item.name}</strong>
                <span style={{ fontSize: "0.85rem", opacity: 0.8 }}>
                  {isAr ? "المتوقع:" : "Expected:"} {item.expectedQuantity} {item.unitOfMeasure}
                </span>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                  gap: "0.5rem",
                }}
              >
                <label className="field" style={{ margin: 0 }}>
                  <span className="field-label" style={{ fontSize: "0.8rem" }}>
                    {isAr ? "الكمية الفعلية" : "Actual Qty"} ({item.unitOfMeasure})
                  </span>
                  <input
                    className="input"
                    min="0"
                    onChange={(e) => {
                      const val = Number(e.target.value);
                      setItems((prev) =>
                        prev.map((it, i) => (i === idx ? { ...it, actualQuantity: val } : it)),
                      );
                    }}
                    step="any"
                    type="number"
                    value={item.actualQuantity}
                  />
                </label>

                {itemBatches.length > 0 ? (
                  <label className="field" style={{ margin: 0 }}>
                    <span className="field-label" style={{ fontSize: "0.8rem" }}>
                      {isAr ? "التشغيلة (FEFO)" : "Batch (FEFO)"}
                    </span>
                    <select
                      className="select"
                      onChange={(e) => {
                        const val = e.target.value;
                        setItems((prev) =>
                          prev.map((it, i) => (i === idx ? { ...it, batchId: val } : it)),
                        );
                      }}
                      value={item.batchId}
                    >
                      <option value="">{isAr ? "-- بدون تحديد --" : "-- Select batch --"}</option>
                      {itemBatches.map((b) => {
                        const exp = b.expiryDate ? new Date(b.expiryDate).toLocaleDateString() : "";
                        return (
                          <option key={b.id} value={b.id}>
                            {b.batchNumber} {exp ? `(Exp: ${exp})` : ""} [{String(b.quantity)}]
                          </option>
                        );
                      })}
                    </select>
                  </label>
                ) : null}

                {locations.length > 1 ? (
                  <label className="field" style={{ margin: 0 }}>
                    <span className="field-label" style={{ fontSize: "0.8rem" }}>
                      {isAr ? "موقع الصرف" : "Dispense Location"}
                    </span>
                    <select
                      className="select"
                      onChange={(e) => {
                        const val = e.target.value;
                        setItems((prev) =>
                          prev.map((it, i) => (i === idx ? { ...it, locationId: val } : it)),
                        );
                      }}
                      value={item.locationId}
                    >
                      {locations.map((loc) => (
                        <option key={loc.id} value={loc.id}>
                          {loc.name}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>

              {item.actualQuantity !== item.expectedQuantity ? (
                <div style={{ marginTop: "0.5rem" }}>
                  <label className="field" style={{ margin: 0 }}>
                    <span className="field-label" style={{ fontSize: "0.8rem" }}>
                      {isAr ? "سبب فرق الكمية (تسوية)" : "Variance Reason (Reconciliation Note)"}
                    </span>
                    <input
                      className="input"
                      onChange={(e) => {
                        const val = e.target.value;
                        setItems((prev) =>
                          prev.map((it, i) =>
                            i === idx ? { ...it, reconciliationNote: val } : it,
                          ),
                        );
                      }}
                      placeholder={
                        isAr ? "سبب التباين في الاستهلاك..." : "Reason for difference..."
                      }
                      type="text"
                      value={item.reconciliationNote}
                    />
                  </label>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
