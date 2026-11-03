import { randomUUID } from "node:crypto";

import type React from "react";

import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../../components/feedback";
import { OperationDialog } from "../../../../../components/operation-dialog";
import { SubmitButton } from "../../../../../components/submit-button";
import {
  operationalWorkflowsRepository,
  requirePageCollectionPermission,
} from "../../../../../server/identity";
import {
  adjustInventoryStockAction,
  approveInventoryOrderAction,
  approveInventoryProposalAction,
  createInventoryItemDirectAction,
  createInventoryLocationAction,
  createInventoryOrderAction,
  createInventoryProposalAction,
  createInventorySupplierAction,
  markInventoryOrderedAction,
  receiveInventoryOrderAction,
  rejectInventoryOrderAction,
  reviewInventoryProposalAction,
  transferInventoryStockAction,
  updateInventoryItemAction,
} from "../../../actions";

const categories = [
  "MATERIAL",
  "CONSUMABLE",
  "SKINCARE_PRODUCT",
  "CLEANING_MATERIAL",
  "EQUIPMENT_SUPPLY",
  "RETAIL_PRODUCT",
  "OTHER",
] as const;

// ─── Label helpers ────────────────────────────────────────────────────────────

function categoryLabel(cat: string, isAr: boolean): string {
  const labels: Record<string, [string, string]> = {
    CLEANING_MATERIAL: ["مواد تنظيف", "Cleaning"],
    CONSUMABLE: ["مستهلكات", "Consumable"],
    EQUIPMENT_SUPPLY: ["معدات ومستلزمات", "Equipment"],
    MATERIAL: ["مواد خام", "Material"],
    OTHER: ["أخرى", "Other"],
    RETAIL_PRODUCT: ["منتج للبيع", "Retail"],
    SKINCARE_PRODUCT: ["منتج عناية", "Skincare"],
  };
  const pair = labels[cat];
  if (!pair) return cat;
  return isAr ? pair[0] : pair[1];
}

function healthLabel(health: string, isAr: boolean): string {
  if (isAr) {
    switch (health) {
      case "HEALTHY":
        return "جيد";
      case "LOW_STOCK":
        return "منخفض";
      case "OUT_OF_STOCK":
        return "نفد";
      default:
        return health;
    }
  }
  switch (health) {
    case "HEALTHY":
      return "Healthy";
    case "LOW_STOCK":
      return "Low Stock";
    case "OUT_OF_STOCK":
      return "Out of Stock";
    default:
      return health;
  }
}

function healthStyle(health: string): React.CSSProperties {
  switch (health) {
    case "OUT_OF_STOCK":
      return { background: "#fee2e2", color: "#b91c1c", fontWeight: 700 };
    case "LOW_STOCK":
      return { background: "#fef3c7", color: "#92400e", fontWeight: 700 };
    default:
      return { background: "#e5f6ed", color: "#2e7a53" };
  }
}

function expiryAlertLabel(alert: string, isAr: boolean): string {
  if (isAr) {
    switch (alert) {
      case "EXPIRED":
        return "منتهي الصلاحية";
      case "CRITICAL_7_DAYS":
        return "ينتهي خلال 7 أيام";
      case "WARNING_30_DAYS":
        return "ينتهي خلال 30 يوم";
      case "NOTICE_60_DAYS":
        return "ينتهي خلال 60 يوم";
      case "INFO_90_DAYS":
        return "ينتهي خلال 90 يوم";
      case "GOOD":
        return "صالح";
      case "NO_EXPIRY":
        return "—";
      default:
        return alert;
    }
  }
  switch (alert) {
    case "EXPIRED":
      return "Expired";
    case "CRITICAL_7_DAYS":
      return "Expires in 7 days";
    case "WARNING_30_DAYS":
      return "Expires in 30 days";
    case "NOTICE_60_DAYS":
      return "Expires in 60 days";
    case "INFO_90_DAYS":
      return "Expires in 90 days";
    case "GOOD":
      return "Good";
    case "NO_EXPIRY":
      return "—";
    default:
      return alert;
  }
}

function expiryAlertStyle(alert: string): React.CSSProperties {
  switch (alert) {
    case "EXPIRED":
      return { background: "#fee2e2", color: "#b91c1c", fontWeight: 700 };
    case "CRITICAL_7_DAYS":
      return { background: "#fee2e2", color: "#b91c1c" };
    case "WARNING_30_DAYS":
      return { background: "#ffedd5", color: "#c2410c" };
    case "NOTICE_60_DAYS":
      return { background: "#fef3c7", color: "#92400e" };
    case "INFO_90_DAYS":
      return { background: "#e0f2fe", color: "#0369a1" };
    default:
      return { background: "#e5f6ed", color: "#2e7a53" };
  }
}

function movementTypeLabel(type: string, isAr: boolean): string {
  if (isAr) {
    switch (type) {
      case "PURCHASE_RECEIPT":
        return "استلام";
      case "APPOINTMENT_CONSUMPTION":
        return "استهلاك موعد";
      case "MANUAL_CORRECTION":
        return "تصحيح يدوي";
      case "ADJUSTMENT":
        return "تعديل";
      case "TRANSFER_IN":
        return "نقل وارد";
      case "TRANSFER_OUT":
        return "نقل صادر";
      case "EXPIRED":
        return "منتهي صلاحية";
      case "DAMAGED":
        return "تالف";
      case "LOST":
        return "مفقود";
      case "SPILLED":
        return "هدر/مسكوب";
      case "RETURN_TO_SUPPLIER":
        return "إرجاع للمورد";
      case "RESERVATION":
        return "حجز";
      case "RESERVATION_RELEASE":
        return "إلغاء حجز";
      default:
        return type;
    }
  }
  switch (type) {
    case "PURCHASE_RECEIPT":
      return "Received";
    case "APPOINTMENT_CONSUMPTION":
      return "Appointment Use";
    case "MANUAL_CORRECTION":
      return "Manual Correction";
    case "ADJUSTMENT":
      return "Adjustment";
    case "TRANSFER_IN":
      return "Transfer In";
    case "TRANSFER_OUT":
      return "Transfer Out";
    case "EXPIRED":
      return "Expired";
    case "DAMAGED":
      return "Damaged";
    case "LOST":
      return "Lost";
    case "SPILLED":
      return "Spilled/Waste";
    case "RETURN_TO_SUPPLIER":
      return "Return to Supplier";
    case "RESERVATION":
      return "Reserved";
    case "RESERVATION_RELEASE":
      return "Reservation Released";
    default:
      return type;
  }
}

function proposalStatusLabel(status: string, isAr: boolean): string {
  if (isAr) {
    switch (status) {
      case "PENDING_APPROVAL":
        return "بانتظار الموافقة";
      case "APPROVED":
        return "موافق عليه";
      case "REJECTED":
        return "مرفوض";
      case "MORE_INFO_REQUIRED":
        return "يحتاج معلومات";
      default:
        return status;
    }
  }
  switch (status) {
    case "PENDING_APPROVAL":
      return "Pending Approval";
    case "APPROVED":
      return "Approved";
    case "REJECTED":
      return "Rejected";
    case "MORE_INFO_REQUIRED":
      return "More Info Needed";
    default:
      return status;
  }
}

function orderStatusLabel(status: string, isAr: boolean): string {
  if (isAr) {
    switch (status) {
      case "PENDING_APPROVAL":
        return "بانتظار الموافقة";
      case "REQUESTED":
        return "مطلوب";
      case "APPROVED":
        return "موافق عليه";
      case "ORDERED":
        return "قيد الشحن";
      case "PARTIALLY_RECEIVED":
        return "استلام جزئي";
      case "RECEIVED":
        return "مستلم";
      case "REJECTED":
        return "مرفوض";
      default:
        return status;
    }
  }
  switch (status) {
    case "PENDING_APPROVAL":
      return "Pending Approval";
    case "REQUESTED":
      return "Requested";
    case "APPROVED":
      return "Approved";
    case "ORDERED":
      return "In Transit";
    case "PARTIALLY_RECEIVED":
      return "Partially Received";
    case "RECEIVED":
      return "Received";
    case "REJECTED":
      return "Rejected";
    default:
      return status;
  }
}

export default async function InventoryPage({
  params,
  searchParams,
}: PageProps<"/[locale]/business/inventory">) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  const access = await requirePageCollectionPermission(locale, "inventory.items.read");

  const [inventoryData, branches] = await Promise.all([
    operationalWorkflowsRepository.listInventory(access),
    operationalWorkflowsRepository.listInventoryBranches(access),
  ]);

  const {
    batches,
    items: allItems,
    locations,
    movements,
    orders,
    overview,
    proposals,
    suppliers,
  } = inventoryData;
  const defaultBranch = branches[0];
  const inventoryResource = {
    ...(defaultBranch ? { branchId: defaultBranch.id } : {}),
    ...(access.staffProfileId ? { staffProfileId: access.staffProfileId } : {}),
  };

  // Support prompt tabs: Overview, Items, Requests, Orders, Receiving, Movements
  // (with backwards compatibility aliases: approvals -> requests, incoming -> receiving)
  let rawTab = typeof query.tab === "string" ? query.tab : "overview";
  if (rawTab === "approvals") rawTab = "requests";
  if (rawTab === "incoming") rawTab = "receiving";

  const validTabs = ["overview", "items", "requests", "orders", "receiving", "movements"] as const;
  const tab = validTabs.includes(rawTab as (typeof validTabs)[number])
    ? (rawTab as (typeof validTabs)[number])
    : "overview";

  // Server-side search filter on Items tab (?q=)
  const searchQuery =
    tab === "items" && typeof query.q === "string" ? query.q.trim().toLowerCase() : "";
  const items = searchQuery
    ? allItems.filter(
        (item) =>
          item.name.toLowerCase().includes(searchQuery) ||
          (item.sku !== null &&
            item.sku !== undefined &&
            item.sku.toLowerCase().includes(searchQuery)) ||
          categoryLabel(item.category, false).toLowerCase().includes(searchQuery),
      )
    : allItems;

  const canManageItems = canAccessResource(access, "inventory.items.manage", inventoryResource);
  const canPropose = canAccessResource(access, "inventory.itemProposal.create", inventoryResource);
  const canApproveProposal = canAccessResource(
    access,
    "inventory.itemProposal.approve",
    inventoryResource,
  );
  const canOrder = canAccessResource(access, "inventory.orderRequest.create", inventoryResource);
  const canApproveOrder = canAccessResource(
    access,
    "inventory.orderRequest.approve",
    inventoryResource,
  );
  const canMarkOrdered = canAccessResource(
    access,
    "inventory.order.markOrdered",
    inventoryResource,
  );
  const canReceive = canAccessResource(access, "inventory.order.receive", inventoryResource);
  const canSupplier = canAccessResource(access, "inventory.supplier.read", inventoryResource);
  const canCost = canAccessResource(access, "inventory.cost.read", inventoryResource);
  const canAdjust = canAccessResource(access, "inventory.stock.adjust", inventoryResource);
  const canTransfer = canAccessResource(access, "inventory.stock.transfer", inventoryResource);

  const isAr = locale === "ar";
  const t = isAr
    ? {
        actions: "الإجراءات",
        adjustStock: "تعديل المخزون",
        allLocations: "جميع المواقع",
        approve: "موافقة",
        approvals: "الطلبات والموافقات",
        attention: "يحتاج انتباه",
        available: "المتوفر",
        batches: "التشغيلات",
        category: "التصنيف",
        cost: "التكلفة",
        createItem: "إضافة صنف جديد",
        createLocation: "إضافة موقع تخزين",
        createSupplier: "إضافة مورد",
        empty: "لا توجد سجلات في هذا القسم.",
        eta: "الوصول المتوقع",
        expiringSoon: "قريب الانتهاء",
        heading: "المخزون",
        incomingOrders: "الطلبات الواردة",
        items: "الأصناف",
        location: "الموقع",
        lowStock: "مخزون منخفض",
        markOrdered: "تسجيل كطلب مورّد",
        minimum: "الحد الأدنى",
        movements: "سجل الحركات",
        nearestExpiry: "أقرب انتهاء",
        needsAttention: "أصناف بحاجة لانتباه فوري",
        onHand: "الموجود",
        orders: "طلبات التوريد",
        ordersInTransit: "طلبات قيد الشحن",
        outOfStock: "نفد المخزون",
        overview: "نظرة عامة",
        overdue: "متأخر عن الموعد",
        pendingRequests: "طلبات معلقة",
        placeOrder: "طلب توريد",
        projectedShortage: "عجز متوقع",
        receive: "استلام",
        receiving: "الاستلام",
        reject: "رفض",
        remaining: "المتبقي",
        price: "السعر (د.أ.)",
        requestItem: "اقتراح صنف جديد",
        requests: "طلبات الأصناف",
        reserved: "محجوز",
        searchPlaceholder: "ابحث بالاسم أو SKU أو التصنيف...",
        status: "الحالة",
        supplier: "المورد",
        transfer: "نقل مخزون",
        upcomingDemand: "استهلاك المواعيد القادمة",
        urgency: "الأولوية",
      }
    : {
        actions: "Actions",
        adjustStock: "Adjust Stock",
        allLocations: "All Locations",
        approve: "Approve",
        approvals: "Requests & Approvals",
        attention: "Attention",
        available: "Available",
        batches: "Batches",
        category: "Category",
        cost: "Cost",
        createItem: "Create Item",
        createLocation: "Add Location",
        createSupplier: "Add Supplier",
        empty: "No records in this section.",
        eta: "Expected Arrival",
        expiringSoon: "Expiring Soon",
        heading: "Inventory",
        incomingOrders: "Incoming Orders",
        items: "Items",
        location: "Location",
        lowStock: "Low Stock",
        markOrdered: "Mark Ordered",
        minimum: "Min",
        movements: "Movements",
        nearestExpiry: "Nearest Expiry",
        needsAttention: "Items Requiring Immediate Attention",
        onHand: "On Hand",
        orders: "Orders",
        ordersInTransit: "Orders In Transit",
        outOfStock: "Out of Stock",
        overview: "Overview",
        overdue: "Overdue",
        pendingRequests: "Pending Requests",
        placeOrder: "Place Order",
        projectedShortage: "Projected Shortage",
        receive: "Receive",
        receiving: "Receiving",
        reject: "Reject",
        remaining: "Remaining",
        price: "Price (JOD)",
        requestItem: "Request New Item",
        requests: "Requests",
        reserved: "Reserved",
        searchPlaceholder: "Search by name, SKU, or category...",
        status: "Status",
        supplier: "Supplier",
        transfer: "Transfer Stock",
        upcomingDemand: "Upcoming Appointment Demand",
        urgency: "Urgency",
      };

  const nav = [
    ["overview", t.overview],
    ["items", t.items],
    ["requests", t.requests],
    ["orders", t.orders],
    ["receiving", t.receiving],
    ["movements", t.movements],
  ] as const;

  return (
    <section className="inventory-workspace page-stack">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div>
          <p className="eyebrow">Business</p>
          <h1>{t.heading}</h1>
        </div>
        <div className="row-actions">
          {canPropose ? (
            <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.requestItem}>
              <form action={createInventoryProposalAction} className="form-grid">
                <input name="locale" type="hidden" value={locale} />
                {defaultBranch ? (
                  <input name="branchId" type="hidden" value={defaultBranch.id} />
                ) : null}
                <Field
                  label={isAr ? "اسم الصنف المقترح" : "Proposed item name"}
                  name="proposedName"
                />
                <label className="field">
                  <span className="field-label">{t.category}</span>
                  <select className="select" name="category">
                    {categories.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <Field
                  label={isAr ? "الوحدة (مثال: حبة، مل)" : "Unit of measure"}
                  name="unitOfMeasure"
                />
                <Field
                  label={isAr ? "الكمية المقترحة" : "Suggested quantity"}
                  name="suggestedQuantity"
                  type="number"
                />
                <Field
                  label={isAr ? "سبب الحاجة (اختياري)" : "Reason needed (Optional)"}
                  name="reasonNeeded"
                  required={false}
                />
                <label className="field">
                  <span className="field-label">{isAr ? "ملاحظة إضافية" : "Note (Optional)"}</span>
                  <textarea className="textarea" name="note" rows={2} />
                </label>
                <label className="inventory-checkbox-line">
                  <input name="urgent" type="checkbox" /> {isAr ? "عاجل" : "Urgent"}
                </label>
                <SubmitButton>{t.requestItem}</SubmitButton>
              </form>
            </OperationDialog>
          ) : null}

          {canManageItems && defaultBranch ? (
            <>
              <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.createItem}>
                <form action={createInventoryItemDirectAction} className="form-grid">
                  <input name="locale" type="hidden" value={locale} />
                  <input name="branchId" type="hidden" value={defaultBranch.id} />
                  <Field label={isAr ? "اسم الصنف" : "Item name"} name="name" />
                  <label className="field">
                    <span className="field-label">{t.category}</span>
                    <select className="select" name="category">
                      {categories.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    label={isAr ? "رمز المخزون (SKU)" : "SKU (internal item code)"}
                    name="sku"
                    required={false}
                  />
                  <Field label={isAr ? "الوحدة" : "Unit of measure"} name="unitOfMeasure" />
                  <Field
                    label={isAr ? "الحد الأدنى للمخزون" : "Minimum stock"}
                    name="minimumStock"
                    type="number"
                    value="0"
                  />
                  <Field
                    label={isAr ? "كمية إعادة الطلب" : "Reorder quantity"}
                    name="reorderQuantity"
                    required={false}
                    type="number"
                    value="0"
                  />
                  <Field
                    label={isAr ? "الكمية الابتدائية (اختياري)" : "Initial quantity (Optional)"}
                    name="currentStock"
                    required={false}
                    type="number"
                    value="0"
                  />
                  {canCost ? (
                    <Field
                      label={isAr ? "سعر الوحدة (د.أ.)" : "Unit price (JOD)"}
                      name="unitPrice"
                      required={false}
                      type="number"
                      min="0"
                      step="0.01"
                    />
                  ) : null}
                  {suppliers.length > 0 ? (
                    <label className="field">
                      <span className="field-label">{t.supplier}</span>
                      <select className="select" name="defaultSupplierId">
                        <option value="">{isAr ? "-- بدون مورد افتراضي --" : "-- None --"}</option>
                        {suppliers.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <div className="inventory-checkbox-group">
                    <label className="inventory-checkbox-line">
                      <input name="batchTrackingEnabled" type="checkbox" />{" "}
                      {isAr ? "تتبع التشغيلات (Batches)" : "Batch tracking"}
                    </label>
                    <label className="inventory-checkbox-line">
                      <input name="expiryTrackingEnabled" type="checkbox" />{" "}
                      {isAr ? "تتبع تاريخ الصلاحية" : "Expiry tracking"}
                    </label>
                  </div>
                  <Field label={isAr ? "ملاحظات" : "Notes"} name="notes" required={false} />
                  <SubmitButton>{t.createItem}</SubmitButton>
                </form>
              </OperationDialog>

              <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.createLocation}>
                <form action={createInventoryLocationAction} className="form-grid">
                  <input name="locale" type="hidden" value={locale} />
                  <input name="branchId" type="hidden" value={defaultBranch.id} />
                  <Field
                    label={
                      isAr ? "اسم الموقع (مثال: المستودع الرئيسي، خزانة العيادة)" : "Location name"
                    }
                    name="name"
                  />
                  <Field
                    label={isAr ? "الوصف أو الرمز" : "Description / Code"}
                    name="code"
                    required={false}
                  />
                  <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <input name="isDefault" type="checkbox" />{" "}
                    {isAr ? "موقع افتراضي للفرع" : "Default location"}
                  </label>
                  <SubmitButton>{t.createLocation}</SubmitButton>
                </form>
              </OperationDialog>
            </>
          ) : null}
        </div>
      </div>

      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />

      <nav aria-label={t.heading} className="workspace-tabs">
        {nav.map(([key, label]) => (
          <Link
            aria-current={tab === key ? "page" : undefined}
            href={`/${locale}/business/inventory?tab=${key}`}
            key={key}
          >
            {label}
          </Link>
        ))}
      </nav>

      {/* ─────────────────────────────────────────────────────────────────
          TAB 1: OVERVIEW
      ───────────────────────────────────────────────────────────────── */}
      {tab === "overview" ? (
        <div className="page-stack" style={{ gap: "1.5rem" }}>
          {/* KPI cards — uses inventory-kpi-grid (no hero offset) */}
          <div className="inventory-kpi-grid">
            <article
              className="inventory-kpi-card"
              data-tone={overview.lowStockCount > 0 ? "attention" : undefined}
            >
              <span>{t.lowStock}</span>
              <strong>{overview.lowStockCount}</strong>
              <small>{isAr ? "أصناف قاربت النفاد" : "Below minimum"}</small>
            </article>
            <article
              className="inventory-kpi-card"
              data-tone={overview.outOfStockCount > 0 ? "attention" : undefined}
            >
              <span>{t.outOfStock}</span>
              <strong>{overview.outOfStockCount}</strong>
              <small>{isAr ? "رصيد صفر" : "Zero quantity"}</small>
            </article>
            <article
              className="inventory-kpi-card"
              data-tone={overview.expiringSoonCount > 0 ? "attention" : undefined}
            >
              <span>{t.expiringSoon}</span>
              <strong>{overview.expiringSoonCount}</strong>
              <small>{isAr ? "خلال 90 يوماً" : "Within 90 days"}</small>
            </article>
            <article className="inventory-kpi-card">
              <span>{t.pendingRequests}</span>
              <strong>{overview.pendingRequestsCount}</strong>
              <small>{isAr ? "بانتظار الموافقة" : "Awaiting approval"}</small>
            </article>
            <article className="inventory-kpi-card">
              <span>{t.ordersInTransit}</span>
              <strong>{overview.ordersInTransitCount}</strong>
              <small>{isAr ? "طلبات قيد الشحن" : "Shipped / Placed"}</small>
            </article>
            <article
              className="inventory-kpi-card"
              data-tone={overview.projectedShortagesCount > 0 ? "attention" : undefined}
            >
              <span>{t.projectedShortage}</span>
              <strong>{overview.projectedShortagesCount}</strong>
              <small>{isAr ? "عجز لمواعيد قادمة" : "Upcoming shortage"}</small>
            </article>
          </div>

          {/* Section: Needs Attention — urgency-tiered cards */}
          <section className="panel">
            <h2 style={{ marginBottom: "1rem" }}>{t.needsAttention}</h2>
            {overview.needsAttention.length === 0 ? (
              <p className="muted">
                {isAr
                  ? "جميع الأصناف بمستويات مخزون آمنة."
                  : "All items are in healthy stock levels."}
              </p>
            ) : (
              <div className="card-grid">
                {overview.needsAttention.map((item) => {
                  const urgency =
                    item.health === "OUT_OF_STOCK" ? "out" : item.isShortage ? "shortage" : "low";
                  return (
                    <article className="inv-attention-card" data-urgency={urgency} key={item.id}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: "0.5rem",
                        }}
                      >
                        <h2>{item.name}</h2>
                        <span className="status" style={healthStyle(item.health)}>
                          {healthLabel(item.health, isAr)}
                        </span>
                      </div>
                      <p>
                        {t.available}:{" "}
                        <strong>
                          {item.availableStock} {item.unitOfMeasure}
                        </strong>{" "}
                        - {t.minimum}: {String(item.minimumStock)}
                      </p>
                      {item.isShortage ? (
                        <p style={{ color: "#b91c1c", fontSize: "0.85rem", fontWeight: 600 }}>
                          ⚡ {t.projectedShortage}: −{item.projectedShortage} {item.unitOfMeasure}
                        </p>
                      ) : null}
                      {item.upcomingDemand > 0 ? (
                        <p style={{ fontSize: "0.85rem", opacity: 0.8 }}>
                          {t.upcomingDemand}: {item.upcomingDemand} {item.unitOfMeasure}
                        </p>
                      ) : null}
                      {canOrder ? (
                        <Link
                          className="button button-secondary"
                          href={`/${locale}/business/inventory?tab=orders&preselectItem=${item.id}`}
                          style={{ marginTop: "0.25rem", fontSize: "0.8rem" }}
                        >
                          {t.placeOrder}
                        </Link>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          {/* Section: Upcoming Appointment Demand */}
          <section className="panel">
            <h2>{t.upcomingDemand}</h2>
            {overview.upcomingDemandItems.length === 0 ? (
              <p className="muted">
                {isAr
                  ? "لا يوجد استهلاك متوقع للمواعيد القادمة حالياً."
                  : "No upcoming appointment inventory consumption forecasted."}
              </p>
            ) : (
              <div className="table-wrapper" style={{ overflowX: "auto" }}>
                <table className="data-table" style={{ width: "100%", textAlign: "start" }}>
                  <thead>
                    <tr>
                      <th>{t.items}</th>
                      <th>{t.available}</th>
                      <th>{t.upcomingDemand}</th>
                      <th>{isAr ? "الرصيد المتوقع" : "Projected Stock"}</th>
                      <th>{t.status}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.upcomingDemandItems.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.name}</strong>
                        </td>
                        <td>
                          {item.availableStock} {item.unitOfMeasure}
                        </td>
                        <td>
                          {item.upcomingDemand} {item.unitOfMeasure}
                        </td>
                        <td
                          style={{
                            color: item.projectedStock < 0 ? "#b91c1c" : "inherit",
                            fontWeight: "bold",
                          }}
                        >
                          {item.projectedStock} {item.unitOfMeasure}
                        </td>
                        <td>
                          {item.isShortage ? (
                            <span
                              className="status status-danger"
                              style={{ background: "#fee2e2", color: "#b91c1c" }}
                            >
                              {t.projectedShortage} ({item.projectedShortage})
                            </span>
                          ) : (
                            <span className="status">{item.health}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Section: Incoming Orders */}
          <section className="panel">
            <h2>{t.incomingOrders}</h2>
            {overview.incomingOrders.length === 0 ? (
              <p className="muted">
                {isAr ? "لا توجد طلبات توريد واردة حالياً." : "No incoming orders in transit."}
              </p>
            ) : (
              <div className="card-grid">
                {overview.incomingOrders.map((order) => (
                  <article className="record-card" key={order.id}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span className="status">{order.status}</span>
                      {order.isOverdue ? (
                        <span
                          className="status status-danger"
                          style={{ background: "#fee2e2", color: "#b91c1c" }}
                        >
                          {t.overdue}
                        </span>
                      ) : null}
                    </div>
                    <h2>{order.item.name}</h2>
                    <p>
                      {isAr ? "الكمية المطلوبة:" : "Quantity:"}{" "}
                      {String(order.orderedQuantity ?? order.requestedQuantity)}
                    </p>
                    {order.expectedArrivalAt ? (
                      <p>
                        {t.eta}:{" "}
                        {new Date(order.expectedArrivalAt).toLocaleString(isAr ? "ar-JO" : "en-JO")}
                      </p>
                    ) : null}
                    {canReceive ? (
                      <Link
                        className="button button-secondary"
                        href={`/${locale}/business/inventory?tab=receiving&order=${order.id}`}
                        style={{ marginTop: "0.5rem" }}
                      >
                        {t.receive}
                      </Link>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      ) : null}

      {/* ─────────────────────────────────────────────────────────────────
          TAB 2: ITEMS
      ───────────────────────────────────────────────────────────────── */}
      {tab === "items" ? (
        <div className="page-stack" style={{ gap: "1rem" }}>
          {/* Search bar */}
          <form action={`/${locale}/business/inventory`} className="inv-search-row" method="get">
            <input name="tab" type="hidden" value="items" />
            <div className="inv-search-input">
              <input
                autoComplete="off"
                defaultValue={searchQuery}
                name="q"
                placeholder={t.searchPlaceholder}
                type="search"
              />
            </div>
            {searchQuery ? (
              <Link
                className="button button-secondary"
                href={`/${locale}/business/inventory?tab=items`}
                style={{ fontSize: "0.8rem", minHeight: "38px" }}
              >
                {isAr ? "مسح البحث" : "Clear"}
              </Link>
            ) : null}
            <span style={{ color: "var(--product-muted)", fontSize: "0.8rem" }}>
              {searchQuery
                ? isAr
                  ? `${items.length} نتيجة`
                  : `${items.length} result${items.length !== 1 ? "s" : ""}`
                : isAr
                  ? `${allItems.length} صنف`
                  : `${allItems.length} item${allItems.length !== 1 ? "s" : ""}`}
            </span>
          </form>

          {items.length === 0 ? (
            <p className="panel">
              {searchQuery
                ? isAr
                  ? `لا توجد نتائج لـ "${searchQuery}"`
                  : `No results for "${searchQuery}"`
                : t.empty}
            </p>
          ) : (
            <div className="table-wrapper" style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ width: "100%", textAlign: "start" }}>
                <thead>
                  <tr>
                    <th>{t.items}</th>
                    <th>{t.category}</th>
                    {canCost ? <th>{t.price}</th> : null}
                    <th>{t.onHand}</th>
                    <th>{t.reserved}</th>
                    <th>{t.available}</th>
                    <th>{t.minimum}</th>
                    <th>{t.nearestExpiry}</th>
                    <th>{t.status}</th>
                    <th>{t.actions}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const expiryBadge = item.nearestExpiryAlert ? (
                      <span
                        className="status"
                        style={{
                          ...expiryAlertStyle(item.nearestExpiryAlert),
                          fontSize: "0.75rem",
                          display: "inline-block",
                        }}
                      >
                        {item.nearestExpiry
                          ? new Date(item.nearestExpiry).toLocaleDateString()
                          : ""}{" "}
                        {expiryAlertLabel(item.nearestExpiryAlert, isAr)}
                      </span>
                    ) : item.nearestExpiry ? (
                      new Date(item.nearestExpiry).toLocaleDateString()
                    ) : (
                      "—"
                    );

                    return (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.name}</strong>
                          {item.sku ? (
                            <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>SKU: {item.sku}</div>
                          ) : null}
                        </td>
                        <td>
                          <span className="inv-cat-badge" data-cat={item.category}>
                            {categoryLabel(item.category, isAr)}
                          </span>
                        </td>
                        {canCost ? (
                          <td>
                            {item.unitPrice === null || item.unitPrice === undefined
                              ? "—"
                              : `${Number(item.unitPrice).toFixed(2)} ${isAr ? "د.أ." : "JOD"}`}
                          </td>
                        ) : null}
                        <td>
                          {item.currentStockNumber} {item.unitOfMeasure}
                        </td>
                        <td>{String(item.reservedQuantity)}</td>
                        <td>
                          <strong>{item.availableStock}</strong> {item.unitOfMeasure}
                        </td>
                        <td>{String(item.minimumStock)}</td>
                        <td>{expiryBadge}</td>
                        <td>
                          {item.isShortage ? (
                            <span
                              className="status"
                              style={{ background: "#fee2e2", color: "#b91c1c" }}
                            >
                              ⚡ {t.projectedShortage}
                            </span>
                          ) : (
                            <span className="status" style={healthStyle(item.health)}>
                              {healthLabel(item.health, isAr)}
                            </span>
                          )}
                        </td>
                        <td>
                          <div className="row-actions" style={{ gap: "0.25rem" }}>
                            {canOrder ? (
                              <OperationDialog
                                closeLabel={isAr ? "إغلاق" : "Close"}
                                label={t.placeOrder}
                              >
                                <form action={createInventoryOrderAction} className="form-grid">
                                  <input name="locale" type="hidden" value={locale} />
                                  <input name="branchId" type="hidden" value={item.branchId} />
                                  <input name="itemId" type="hidden" value={item.id} />
                                  <p>
                                    <strong>{item.name}</strong> ({t.available}:{" "}
                                    {item.availableStock} {item.unitOfMeasure})
                                  </p>
                                  <Field
                                    label={isAr ? "الكمية المطلوبة" : "Requested quantity"}
                                    name="quantity"
                                    type="number"
                                  />
                                  <Field label={isAr ? "السبب" : "Reason"} name="reason" />
                                  <label className="field">
                                    <span className="field-label">{t.urgency}</span>
                                    <select className="select" name="urgency">
                                      <option value="NORMAL">{isAr ? "عادي" : "Normal"}</option>
                                      <option value="URGENT">{isAr ? "عاجل" : "Urgent"}</option>
                                    </select>
                                  </label>
                                  <Field
                                    label={isAr ? "ملاحظة (اختياري)" : "Note (Optional)"}
                                    name="note"
                                    required={false}
                                  />
                                  <SubmitButton>{t.placeOrder}</SubmitButton>
                                </form>
                              </OperationDialog>
                            ) : null}

                            {canAdjust && locations.length > 0 ? (
                              <OperationDialog
                                closeLabel={isAr ? "إغلاق" : "Close"}
                                label={t.adjustStock}
                              >
                                <form action={adjustInventoryStockAction} className="form-grid">
                                  <input name="locale" type="hidden" value={locale} />
                                  <input name="branchId" type="hidden" value={item.branchId} />
                                  <input name="itemId" type="hidden" value={item.id} />
                                  <p>
                                    <strong>{item.name}</strong>
                                  </p>
                                  <label className="field">
                                    <span className="field-label">{t.location}</span>
                                    <select className="select" name="locationId">
                                      {locations.map((loc) => (
                                        <option key={loc.id} value={loc.id}>
                                          {loc.name}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  {batches.filter((b) => b.itemId === item.id).length > 0 ? (
                                    <label className="field">
                                      <span className="field-label">{t.batches}</span>
                                      <select className="select" name="batchId">
                                        <option value="">
                                          {isAr ? "-- بدون تشغيلة --" : "-- No batch --"}
                                        </option>
                                        {batches
                                          .filter((b) => b.itemId === item.id)
                                          .map((b) => (
                                            <option key={b.id} value={b.id}>
                                              {b.batchNumber} (Qty: {String(b.quantity)})
                                            </option>
                                          ))}
                                      </select>
                                    </label>
                                  ) : null}
                                  <label className="field">
                                    <span className="field-label">
                                      {isAr ? "نوع التعديل" : "Adjustment Reason"}
                                    </span>
                                    <select className="select" name="movementType">
                                      <option value="EXPIRED">
                                        {isAr ? "منتهي الصلاحية" : "Expired"}
                                      </option>
                                      <option value="DAMAGED">{isAr ? "تالف" : "Damaged"}</option>
                                      <option value="LOST">{isAr ? "مفقود" : "Lost"}</option>
                                      <option value="SPILLED">
                                        {isAr ? "مسكوب / هدر" : "Spilled"}
                                      </option>
                                      <option value="RETURN_TO_SUPPLIER">
                                        {isAr ? "إرجاع للمورد" : "Returned to Supplier"}
                                      </option>
                                      <option value="MANUAL_CORRECTION">
                                        {isAr ? "تصحيح يدوي" : "Manual Correction"}
                                      </option>
                                    </select>
                                  </label>
                                  <Field
                                    label={isAr ? "الكمية" : "Quantity Change"}
                                    name="quantityChange"
                                    type="number"
                                  />
                                  <Field label={isAr ? "سبب التعديل" : "Reason"} name="reason" />
                                  <SubmitButton>{t.adjustStock}</SubmitButton>
                                </form>
                              </OperationDialog>
                            ) : null}

                            {canTransfer && locations.length > 1 ? (
                              <OperationDialog
                                closeLabel={isAr ? "إغلاق" : "Close"}
                                label={t.transfer}
                              >
                                <form action={transferInventoryStockAction} className="form-grid">
                                  <input name="locale" type="hidden" value={locale} />
                                  <input name="branchId" type="hidden" value={item.branchId} />
                                  <input name="itemId" type="hidden" value={item.id} />
                                  <p>
                                    <strong>{item.name}</strong>
                                  </p>
                                  <label className="field">
                                    <span className="field-label">
                                      {isAr ? "من موقع" : "From Location"}
                                    </span>
                                    <select className="select" name="fromLocationId">
                                      {locations.map((loc) => (
                                        <option key={loc.id} value={loc.id}>
                                          {loc.name}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label className="field">
                                    <span className="field-label">
                                      {isAr ? "إلى موقع" : "To Location"}
                                    </span>
                                    <select className="select" name="toLocationId">
                                      {locations.map((loc) => (
                                        <option key={loc.id} value={loc.id}>
                                          {loc.name}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  {batches.filter((b) => b.itemId === item.id).length > 0 ? (
                                    <label className="field">
                                      <span className="field-label">{t.batches}</span>
                                      <select className="select" name="batchId">
                                        <option value="">
                                          {isAr ? "-- بدون تشغيلة --" : "-- No batch --"}
                                        </option>
                                        {batches
                                          .filter((b) => b.itemId === item.id)
                                          .map((b) => (
                                            <option key={b.id} value={b.id}>
                                              {b.batchNumber} (Qty: {String(b.quantity)})
                                            </option>
                                          ))}
                                      </select>
                                    </label>
                                  ) : null}
                                  <Field
                                    label={isAr ? "الكمية" : "Quantity"}
                                    name="quantity"
                                    type="number"
                                  />
                                  <Field label={isAr ? "السبب" : "Reason"} name="reason" />
                                  <SubmitButton>{t.transfer}</SubmitButton>
                                </form>
                              </OperationDialog>
                            ) : null}

                            {canManageItems ? (
                              <OperationDialog
                                closeLabel={isAr ? "إغلاق" : "Close"}
                                label={isAr ? "تعديل" : "Edit"}
                              >
                                <form action={updateInventoryItemAction} className="form-grid">
                                  <input name="locale" type="hidden" value={locale} />
                                  <input name="id" type="hidden" value={item.id} />
                                  <input
                                    name="expectedVersion"
                                    type="hidden"
                                    value={item.version}
                                  />
                                  <Field
                                    label={isAr ? "اسم الصنف" : "Item name"}
                                    name="name"
                                    value={item.name}
                                  />
                                  <Field
                                    label={isAr ? "كود الصنف / SKU" : "SKU"}
                                    name="sku"
                                    required={false}
                                    value={item.sku ?? ""}
                                  />
                                  <Field
                                    label={isAr ? "الوحدة" : "Unit of measure"}
                                    name="unitOfMeasure"
                                    value={item.unitOfMeasure}
                                  />
                                  <Field
                                    label={isAr ? "الحد الأدنى" : "Minimum stock"}
                                    name="minimumStock"
                                    type="number"
                                    value={String(item.minimumStock)}
                                  />
                                  <Field
                                    label={isAr ? "كمية إعادة الطلب" : "Reorder quantity"}
                                    name="reorderQuantity"
                                    required={false}
                                    type="number"
                                    value={String(item.reorderQuantity)}
                                  />
                                  <Field
                                    label={isAr ? "ملاحظات" : "Notes"}
                                    name="notes"
                                    required={false}
                                    value={item.notes ?? ""}
                                  />
                                  <SubmitButton>
                                    {isAr ? "حفظ التعديلات" : "Save Changes"}
                                  </SubmitButton>
                                </form>
                              </OperationDialog>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {/* ─────────────────────────────────────────────────────────────────
          TAB 3: REQUESTS (ITEM PROPOSALS)
      ───────────────────────────────────────────────────────────────── */}
      {tab === "requests" ? (
        <div className="page-stack" style={{ gap: "1.5rem" }}>
          {proposals.length === 0 ? (
            <p className="panel">{t.empty}</p>
          ) : (
            <div className="card-grid">
              {proposals.map((proposal) => (
                <article className="record-card" key={proposal.id}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                    <span className="status">{proposalStatusLabel(proposal.status, isAr)}</span>
                    {proposal.urgent ? (
                      <span className="status" style={{ background: "#fee2e2", color: "#b91c1c" }}>
                        {isAr ? "عاجل" : "Urgent"}
                      </span>
                    ) : null}
                  </div>
                  <h2>{proposal.proposedName}</h2>
                  <p>
                    <span className="inv-cat-badge" data-cat={proposal.category}>
                      {categoryLabel(proposal.category, isAr)}
                    </span>{" "}
                    - {String(proposal.suggestedQuantity)} {proposal.unitOfMeasure}
                  </p>
                  {proposal.reasonNeeded ? (
                    <p style={{ opacity: 0.85 }}>{proposal.reasonNeeded}</p>
                  ) : null}
                  {proposal.note ? (
                    <p style={{ fontSize: "0.85rem", opacity: 0.7 }}>
                      {isAr ? "ملاحظة:" : "Note:"} {proposal.note}
                    </p>
                  ) : null}
                  {proposal.reviewNote ? (
                    <p style={{ fontSize: "0.85rem", color: "var(--product-blue, #2c72b0)" }}>
                      {isAr ? "ملاحظة المراجعة:" : "Review note:"} {proposal.reviewNote}
                    </p>
                  ) : null}

                  {canApproveProposal && proposal.status === "PENDING_APPROVAL" ? (
                    <div className="page-stack" style={{ marginTop: "0.75rem", gap: "0.5rem" }}>
                      <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.approve}>
                        <form action={approveInventoryProposalAction} className="form-grid">
                          <input name="locale" type="hidden" value={locale} />
                          <input name="id" type="hidden" value={proposal.id} />
                          <input name="expectedVersion" type="hidden" value={proposal.version} />
                          <Field
                            label={isAr ? "الاسم النهائي للصنف" : "Final item name"}
                            name="name"
                            value={proposal.proposedName}
                          />
                          <Field
                            label={isAr ? "الحد الأدنى للمخزون" : "Minimum stock"}
                            name="minimumStock"
                            type="number"
                            value="0"
                          />
                          <Field
                            label={isAr ? "كمية إعادة الطلب" : "Reorder quantity"}
                            name="reorderQuantity"
                            required={false}
                            type="number"
                            value="0"
                          />
                          <Field
                            label={isAr ? "رمز المخزون (SKU)" : "SKU (internal item code)"}
                            name="sku"
                            required={false}
                          />
                          {canSupplier ? (
                            <>
                              <Field
                                label={isAr ? "اسم المورد" : "Supplier name"}
                                name="supplierName"
                                required={false}
                              />
                              <Field
                                label={isAr ? "هاتف المورد" : "Supplier phone"}
                                name="supplierPhone"
                                required={false}
                              />
                            </>
                          ) : null}
                          {canCost ? (
                            <Field
                              label={isAr ? "سعر الوحدة (د.أ.)" : "Unit price (JOD)"}
                              name="unitPrice"
                              required={false}
                              type="number"
                              min="0"
                              step="0.01"
                            />
                          ) : null}
                          <div className="inventory-checkbox-group">
                            <label className="inventory-checkbox-line">
                              <input name="batchTrackingEnabled" type="checkbox" />{" "}
                              {isAr ? "تتبع التشغيلات" : "Batch tracking"}
                            </label>
                            <label className="inventory-checkbox-line">
                              <input name="expiryTrackingEnabled" type="checkbox" />{" "}
                              {isAr ? "تتبع تاريخ الصلاحية" : "Expiry tracking"}
                            </label>
                          </div>
                          <SubmitButton>{t.approve}</SubmitButton>
                        </form>
                      </OperationDialog>

                      <OperationDialog
                        closeLabel={isAr ? "إغلاق" : "Close"}
                        label={isAr ? "مراجعة / رفض" : "Review / Reject"}
                      >
                        <form action={reviewInventoryProposalAction} className="form-grid">
                          <input name="locale" type="hidden" value={locale} />
                          <input name="id" type="hidden" value={proposal.id} />
                          <input name="expectedVersion" type="hidden" value={proposal.version} />
                          <label className="field">
                            <span className="field-label">{isAr ? "القرار" : "Decision"}</span>
                            <select className="select" name="status">
                              <option value="MORE_INFO_REQUIRED">
                                {isAr ? "معلومات إضافية مطلوبة" : "More information required"}
                              </option>
                              <option value="REJECTED">{isAr ? "رفض" : "Reject"}</option>
                            </select>
                          </label>
                          <Field
                            label={isAr ? "سبب القرار (اختياري)" : "Decision reason (optional)"}
                            name="reason"
                            required={false}
                          />
                          <SubmitButton>{isAr ? "إرسال القرار" : "Submit Decision"}</SubmitButton>
                        </form>
                      </OperationDialog>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* ─────────────────────────────────────────────────────────────────
          TAB 4: ORDERS (ORDER REQUESTS)
      ───────────────────────────────────────────────────────────────── */}
      {tab === "orders" ? (
        <div className="page-stack" style={{ gap: "1.5rem" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "0.5rem",
            }}
          >
            {canOrder && items.length > 0 ? (
              <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.placeOrder}>
                <form action={createInventoryOrderAction} className="form-grid">
                  <input name="locale" type="hidden" value={locale} />
                  {defaultBranch ? (
                    <input name="branchId" type="hidden" value={defaultBranch.id} />
                  ) : null}
                  <label className="field">
                    <span className="field-label">{t.items}</span>
                    <select
                      className="select"
                      defaultValue={
                        typeof query.preselectItem === "string" ? query.preselectItem : undefined
                      }
                      name="itemId"
                    >
                      {items.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name} ({t.available}: {item.availableStock} {item.unitOfMeasure})
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    label={isAr ? "الكمية المطلوبة" : "Requested quantity"}
                    name="quantity"
                    type="number"
                  />
                  <Field label={isAr ? "السبب" : "Reason"} name="reason" />
                  <label className="field">
                    <span className="field-label">{t.urgency}</span>
                    <select className="select" name="urgency">
                      <option value="NORMAL">NORMAL</option>
                      <option value="URGENT">URGENT</option>
                    </select>
                  </label>
                  <Field
                    label={isAr ? "ملاحظة (اختياري)" : "Note (Optional)"}
                    name="note"
                    required={false}
                  />
                  <SubmitButton>{t.placeOrder}</SubmitButton>
                </form>
              </OperationDialog>
            ) : null}

            {canSupplier && canManageItems ? (
              <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.createSupplier}>
                <form action={createInventorySupplierAction} className="form-grid">
                  <input name="locale" type="hidden" value={locale} />
                  <Field label={isAr ? "اسم المورد" : "Supplier name"} name="name" />
                  <Field label={isAr ? "رقم الهاتف" : "Phone"} name="phone" />
                  <Field
                    label={isAr ? "البريد الإلكتروني (اختياري)" : "Email (Optional)"}
                    name="email"
                    required={false}
                    type="email"
                  />
                  <Field label={isAr ? "ملاحظات" : "Notes"} name="notes" required={false} />
                  <SubmitButton>{t.createSupplier}</SubmitButton>
                </form>
              </OperationDialog>
            ) : null}
          </div>

          {orders.length === 0 ? (
            <p className="panel">{t.empty}</p>
          ) : (
            <div className="card-grid">
              {orders.map((order) => (
                <article className="record-card" key={order.id}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span className="status">{order.status}</span>
                    <span className="status">{order.urgency}</span>
                  </div>
                  <h2>{order.item.name}</h2>
                  <p>
                    {isAr ? "الكمية المطلوبة:" : "Requested:"}{" "}
                    <strong>{String(order.requestedQuantity)}</strong>
                  </p>
                  <p style={{ opacity: 0.85 }}>{order.reason}</p>
                  {order.expectedArrivalAt ? (
                    <p style={{ fontSize: "0.85rem", color: "var(--color-primary, #0284c7)" }}>
                      {t.eta}:{" "}
                      {new Date(order.expectedArrivalAt).toLocaleString(isAr ? "ar-JO" : "en-JO")}
                    </p>
                  ) : null}
                  {canSupplier && order.supplierName ? (
                    <p style={{ fontSize: "0.85rem", opacity: 0.8 }}>
                      {t.supplier}: {order.supplierName}
                    </p>
                  ) : null}
                  {canCost && order.item.unitPrice ? (
                    <p style={{ fontSize: "0.85rem", opacity: 0.8 }}>
                      {t.cost}:{" "}
                      {String(Number(order.requestedQuantity) * Number(order.item.unitPrice))} JOD
                    </p>
                  ) : null}

                  {canApproveOrder && order.status === "PENDING_APPROVAL" ? (
                    <div className="row-actions" style={{ marginTop: "0.75rem" }}>
                      <form action={approveInventoryOrderAction}>
                        <input name="locale" type="hidden" value={locale} />
                        <input name="id" type="hidden" value={order.id} />
                        <input name="expectedVersion" type="hidden" value={order.version} />
                        <SubmitButton>{t.approve}</SubmitButton>
                      </form>
                      <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.reject}>
                        <form action={rejectInventoryOrderAction} className="form-grid">
                          <input name="locale" type="hidden" value={locale} />
                          <input name="id" type="hidden" value={order.id} />
                          <input name="expectedVersion" type="hidden" value={order.version} />
                          <Field label={isAr ? "سبب الرفض" : "Rejection reason"} name="reason" />
                          <SubmitButton>{t.reject}</SubmitButton>
                        </form>
                      </OperationDialog>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* ─────────────────────────────────────────────────────────────────
          TAB 5: RECEIVING
      ───────────────────────────────────────────────────────────────── */}
      {tab === "receiving" ? (
        <div className="page-stack" style={{ gap: "1.5rem" }}>
          {orders.filter((o) => ["APPROVED", "ORDERED", "PARTIALLY_RECEIVED"].includes(o.status))
            .length === 0 ? (
            <p className="panel">{t.empty}</p>
          ) : (
            <div className="card-grid">
              {orders
                .filter((o) => ["APPROVED", "ORDERED", "PARTIALLY_RECEIVED"].includes(o.status))
                .map((order) => {
                  const orderedQty = Number(order.orderedQuantity ?? order.requestedQuantity);
                  const receivedQty = Number(order.receivedQuantity ?? 0);
                  const remainingQty = Math.max(0, orderedQty - receivedQty);
                  const receivedPct =
                    orderedQty > 0 ? Math.min(100, (receivedQty / orderedQty) * 100) : 0;
                  const isOverdue = order.expectedArrivalAt
                    ? new Date(order.expectedArrivalAt) < new Date()
                    : false;
                  const isComplete = remainingQty === 0;

                  return (
                    <article className="record-card" key={order.id}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span className="status">{orderStatusLabel(order.status, isAr)}</span>
                        {isOverdue && order.status === "ORDERED" ? (
                          <span
                            className="status"
                            style={{ background: "#fee2e2", color: "#b91c1c" }}
                          >
                            {t.overdue}
                          </span>
                        ) : null}
                      </div>
                      <h2>{order.item.name}</h2>

                      {/* Receiving progress bar */}
                      <div className="inv-progress-wrap">
                        <div className="inv-progress-label">
                          <span>
                            {isAr ? "المستلم" : "Received"}: <strong>{receivedQty}</strong> /{" "}
                            {orderedQty}
                          </span>
                          <span>
                            {Math.round(receivedPct)}%{" "}
                            {isComplete
                              ? isAr
                                ? "مكتمل"
                                : "Complete"
                              : `- ${isAr ? "المتبقي" : "Remaining"}: ${remainingQty}`}
                          </span>
                        </div>
                        <div className="inv-progress-bar">
                          <div
                            className="inv-progress-fill"
                            data-complete={isComplete ? "true" : undefined}
                            data-overdue={isOverdue && !isComplete ? "true" : undefined}
                            style={{ width: `${receivedPct}%` }}
                          />
                        </div>
                      </div>

                      {order.expectedArrivalAt ? (
                        <p
                          style={{ fontSize: "0.85rem", color: isOverdue ? "#b91c1c" : "inherit" }}
                        >
                          {t.eta}:{" "}
                          {new Date(order.expectedArrivalAt).toLocaleString(
                            isAr ? "ar-JO" : "en-JO",
                          )}
                        </p>
                      ) : null}

                      {/* Mark Ordered action */}
                      {canMarkOrdered && order.status === "APPROVED" ? (
                        <OperationDialog
                          closeLabel={isAr ? "إغلاق" : "Close"}
                          label={t.markOrdered}
                        >
                          <form action={markInventoryOrderedAction} className="form-grid">
                            <input name="locale" type="hidden" value={locale} />
                            <input name="id" type="hidden" value={order.id} />
                            <input name="expectedVersion" type="hidden" value={order.version} />
                            <Field
                              label={isAr ? "الكمية المطلوبة من المورد" : "Ordered quantity"}
                              name="orderedQuantity"
                              type="number"
                              value={String(orderedQty)}
                            />
                            <Field
                              label={isAr ? "اسم المورد" : "Supplier name"}
                              name="supplierName"
                              value={order.supplierName ?? ""}
                            />
                            <Field
                              label={isAr ? "تاريخ الطلب" : "Order date"}
                              name="orderedAt"
                              type="datetime-local"
                              value={new Date().toISOString().slice(0, 16)}
                            />
                            <Field
                              label={
                                isAr ? "مدة التوصيل المتوقعة (قيمة)" : "Expected delivery value"
                              }
                              name="expectedDeliveryValue"
                              type="number"
                              value="2"
                            />
                            <label className="field">
                              <span className="field-label">
                                {isAr ? "وحدة مدة التوصيل" : "Delivery unit"}
                              </span>
                              <select className="select" name="expectedDeliveryUnit">
                                <option value="DAYS">{isAr ? "أيام" : "DAYS"}</option>
                                <option value="HOURS">{isAr ? "ساعات" : "HOURS"}</option>
                              </select>
                            </label>
                            <Field
                              label={
                                isAr
                                  ? "مرجع الطلب لدى المورد (اختياري)"
                                  : "Supplier reference (Optional)"
                              }
                              name="supplierReference"
                              required={false}
                            />
                            <SubmitButton>{t.markOrdered}</SubmitButton>
                          </form>
                        </OperationDialog>
                      ) : null}

                      {/* Receive action */}
                      {canReceive &&
                      (order.status === "ORDERED" || order.status === "PARTIALLY_RECEIVED") ? (
                        <OperationDialog closeLabel={isAr ? "إغلاق" : "Close"} label={t.receive}>
                          <form action={receiveInventoryOrderAction} className="form-grid">
                            <input name="locale" type="hidden" value={locale} />
                            <input name="id" type="hidden" value={order.id} />
                            <input name="requestKey" type="hidden" value={randomUUID()} />
                            <Field
                              label={isAr ? "الكمية المستلمة" : "Received quantity"}
                              name="quantity"
                              type="number"
                              value={String(remainingQty)}
                            />
                            {locations.length > 0 ? (
                              <label className="field">
                                <span className="field-label">{t.location}</span>
                                <select className="select" name="locationId">
                                  {locations.map((loc) => (
                                    <option key={loc.id} value={loc.id}>
                                      {loc.name}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            ) : null}
                            <Field
                              label={isAr ? "رقم التشغيلة (Batch Number)" : "Batch number"}
                              name="batchNumber"
                              required={false}
                            />
                            <Field
                              label={isAr ? "تاريخ انتهاء الصلاحية" : "Expiry date"}
                              name="expiryDate"
                              required={false}
                              type="date"
                            />
                            {canCost ? (
                              <Field
                                label={
                                  isAr ? "تكلفة الشراء الإجمالية / سعر الشراء" : "Purchase cost"
                                }
                                name="purchaseCost"
                                required={false}
                                type="number"
                              />
                            ) : null}
                            <Field
                              label={isAr ? "تاريخ ووقت الاستلام" : "Received at"}
                              name="receivedAt"
                              type="datetime-local"
                              value={new Date().toISOString().slice(0, 16)}
                            />
                            <Field
                              label={isAr ? "ملاحظة (اختياري)" : "Note (Optional)"}
                              name="note"
                              required={false}
                            />
                            <SubmitButton>{t.receive}</SubmitButton>
                          </form>
                        </OperationDialog>
                      ) : null}
                    </article>
                  );
                })}
            </div>
          )}
        </div>
      ) : null}

      {/* ─────────────────────────────────────────────────────────────────
          TAB 6: MOVEMENTS (STOCK MOVEMENT LEDGER)
      ───────────────────────────────────────────────────────────────── */}
      {tab === "movements" ? (
        <div className="page-stack">
          {movements.length === 0 ? (
            <p className="panel">{t.empty}</p>
          ) : (
            <div className="table-wrapper" style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ width: "100%", textAlign: "start" }}>
                <thead>
                  <tr>
                    <th>{isAr ? "التاريخ والوقت" : "Timestamp"}</th>
                    <th>{t.items}</th>
                    <th>{isAr ? "نوع الحركة" : "Type"}</th>
                    <th>{isAr ? "التغيير" : "Quantity"}</th>
                    <th>{isAr ? "الرصيد قبل" : "Before"}</th>
                    <th>{isAr ? "الرصيد بعد" : "After"}</th>
                    <th>{t.location}</th>
                    <th>{t.batches}</th>
                    <th>{isAr ? "السبب / المرجع" : "Reason / Reference"}</th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map((m) => {
                    const isPositive = Number(m.quantity) > 0;
                    return (
                      <tr key={m.id}>
                        <td style={{ whiteSpace: "nowrap", fontSize: "0.85rem" }}>
                          {new Date(m.createdAt).toLocaleString(isAr ? "ar-JO" : "en-JO")}
                        </td>
                        <td>
                          <strong>{m.item.name}</strong>
                          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>
                            {m.item.unitOfMeasure}
                          </div>
                        </td>
                        <td>
                          <span className="status" style={{ fontSize: "0.75rem" }}>
                            {movementTypeLabel(m.type, isAr)}
                          </span>
                        </td>
                        <td
                          style={{ fontWeight: "bold", color: isPositive ? "#15803d" : "#b91c1c" }}
                        >
                          {isPositive ? `+${String(m.quantity)}` : String(m.quantity)}{" "}
                          {m.item.unitOfMeasure}
                        </td>
                        <td>{String(m.balanceBefore)}</td>
                        <td>
                          <strong>{String(m.balanceAfter)}</strong>
                        </td>
                        <td>{m.location?.name ?? "—"}</td>
                        <td>
                          {m.batch ? (
                            <span>
                              {m.batch.batchNumber}{" "}
                              {m.batch.expiryDate ? (
                                <small>({new Date(m.batch.expiryDate).toLocaleDateString()})</small>
                              ) : null}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td style={{ fontSize: "0.85rem", opacity: 0.85 }}>
                          {m.reason ?? "—"}
                          {m.appointmentId ? (
                            <div>
                              <Link href={`/${locale}/dashboard/appointments/${m.appointmentId}`}>
                                #{m.appointmentId.slice(0, 8)}
                              </Link>
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

function Field({
  label,
  name,
  required = true,
  type = "text",
  value,
  min,
  step,
}: Readonly<{
  label: string;
  name: string;
  required?: boolean;
  type?: string;
  value?: string;
  min?: string;
  step?: string;
}>) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        className="input"
        defaultValue={value}
        min={min}
        name={name}
        required={required}
        step={step}
        type={type}
      />
    </label>
  );
}
