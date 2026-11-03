import type { SupportedLocale } from "@jormall/contracts/locales";

const en = {
  acceptOffer: "Accept offer",
  addResource: "Add resource",
  addResourceGroup: "Add resource group",
  addToWaitlist: "Add to waitlist",
  availability: "Available slots",
  branchHours: "Branch hours",
  capacity: "Capacity",
  conflictProtected: "Conflict protected",
  declineOffer: "Decline offer",
  expires: "Expires",
  expireOffer: "Expire offer",
  findSlots: "Find available slots",
  mockedDelivery: "Mocked delivery only — no message is sent.",
  preferredDates: "Preferred dates",
  preferredTime: "Preferred time window",
  priority: "Priority",
  resource: "Resource",
  resourceGroup: "Resource group",
  resources: "Resources",
  requirement: "Service requirement",
  sendMockOffer: "Create mocked offer",
  slotOffers: "Slot offers",
  waitlist: "Waitlist",
};

const ar: typeof en = {
  acceptOffer: "قبول العرض",
  addResource: "إضافة مورد",
  addResourceGroup: "إضافة مجموعة موارد",
  addToWaitlist: "إضافة إلى قائمة الانتظار",
  availability: "المواعيد المتاحة",
  branchHours: "ساعات عمل الفرع",
  capacity: "السعة",
  conflictProtected: "محمي من التعارض",
  declineOffer: "رفض العرض",
  expires: "ينتهي",
  expireOffer: "إنهاء العرض",
  findSlots: "البحث عن مواعيد متاحة",
  mockedDelivery: "إرسال تجريبي فقط — لن تُرسل أي رسالة.",
  preferredDates: "التواريخ المفضلة",
  preferredTime: "الفترة الزمنية المفضلة",
  priority: "الأولوية",
  resource: "المورد",
  resourceGroup: "مجموعة الموارد",
  resources: "الموارد",
  requirement: "متطلبات الخدمة",
  sendMockOffer: "إنشاء عرض تجريبي",
  slotOffers: "عروض المواعيد",
  waitlist: "قائمة الانتظار",
};

export const phaseThreeMessages: Readonly<Record<SupportedLocale, typeof en>> = { ar, en };

const labels: Readonly<Record<SupportedLocale, Readonly<Record<string, string>>>> = {
  ar: {
    ACCEPTED: "مقبول",
    ACTIVE: "نشط",
    CHAIR: "الكراسي",
    DECLINED: "مرفوض",
    DEVICE: "الأجهزة والآلات",
    EXPIRED: "منتهي",
    FULFILLED: "تم الحجز",
    INACTIVE: "غير نشط",
    MAINTENANCE: "صيانة",
    OFFERED: "تم تقديم عرض",
    PENDING: "قيد الانتظار",
    ROOM: "غرف العلاج",
    SHARED_EQUIPMENT: "المعدات",
  },
  en: {
    ACCEPTED: "Accepted",
    ACTIVE: "Active",
    CHAIR: "Chairs",
    DECLINED: "Declined",
    DEVICE: "Machines",
    EXPIRED: "Expired",
    FULFILLED: "Booked",
    INACTIVE: "Inactive",
    MAINTENANCE: "Maintenance",
    OFFERED: "Offered",
    PENDING: "Pending",
    ROOM: "Treatment Rooms",
    SHARED_EQUIPMENT: "Equipment",
  },
};

export function phaseThreeLabel(locale: SupportedLocale, value: string): string {
  return labels[locale][value] ?? value;
}
