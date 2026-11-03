export type KarmaliteServiceTemplate = Readonly<{
  category: string;
  configurationStatus: "DRAFT";
  defaultDurationMins: number;
  descriptionAr: string;
  descriptionEn: string;
  isOnlineBookable: false;
  minimumNoticeMins: null;
  nameAr: string;
  nameEn: string;
  postTreatmentInstructionsAr: string;
  postTreatmentInstructionsEn: string;
  preTreatmentInstructionsAr: string;
  preTreatmentInstructionsEn: string;
}>;

export const karmaliteTemplate = {
  aiBusinessGuidance:
    "You are Karmalite Assistant (مساعد كارمالايت). Reply in the customer's English or Arabic with a professional, welcoming, elegant, concise and calm tone. Offer only the five configured beauty-center services. Never introduce diagnosis, prescriptions, medication changes, insurance, medical records, gynecology, surgery, injectables, doctors, doctor schedules, clinical interpretation, mineral-result interpretation or unpublished information. Never estimate prices, availability, provider schedules, results, session counts or suitability. When a service has no approved numeric price, respond exactly in English: “Contact Karmalite for the current price.” Respond exactly in Arabic: “يرجى التواصل مع كارمالايت لمعرفة السعر الحالي.” Use info@karmalite.com, +962 6 586 8024 and +962 77 586 8024 for public contact. These services are in tenant review: collect a booking request and request a human handoff until a service is approved and real provider assignments, schedules and live availability exist. Never claim a booking is confirmed unless the protected booking gateway returns confirmation. Cancellation and rescheduling require verified identity and explicit confirmation.",
  branch: {
    addressAr:
      "مبنى سلطان، الطابق الثاني، شارع نقيب عمران المعايطة رقم 33، الصويفية / دير غبار، عمّان، الأردن",
    addressEn:
      "Sultan Building, 2nd Floor, 33 Naqib Omran Al-Maayetah Street, Sweifieh / Deir Ghbar, Amman, Jordan",
    email: "info@karmalite.com",
    mapUrl: "https://maps.google.com/?q=Karmalite+Medical+Esthetic+Amman",
    mobilePhone: "+962 77 586 8024",
    nameAr: "كارمالايت للتجميل الطبي - الصويفية",
    nameEn: "Karmalite Medical Esthetic - Sweifieh",
    phone: "+962 6 586 8024",
    timezone: "Asia/Amman",
  },
  branding: {
    accentColor: "#A7B4B4",
    logoUrl: "/api/workspace/logo",
    primaryColor: "#4D6160",
    status: "PENDING_APPROVAL" as const,
  },
  hours: [
    { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "SATURDAY" },
    { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "SUNDAY" },
    { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "MONDAY" },
    { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "TUESDAY" },
    { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "WEDNESDAY" },
    { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "THURSDAY" },
  ] as const,
  knowledge: {
    name: "Karmalite beauty-center production draft",
    originalFilename: "Karmalite_Beauty_Center_Knowledge_Base_Production_Draft.docx",
    title: "Karmalite beauty-center knowledge — production draft",
  },
  organization: {
    descriptionAr:
      "كارمالايت للتجميل الطبي مركز للعناية الجمالية في عمّان. تم إعداد مساحة العمل على نظام جورمول لخمس خدمات أولية، وإدارة المواعيد، والتواصل مع العملاء، وقائمة الانتظار، والمساعدة المعتمدة بالذكاء الاصطناعي.",
    descriptionEn:
      "Karmalite Medical Esthetic is a beauty and aesthetic-care center in Amman. This JorMall workspace is configured for five launch services, appointments, customer communication, waitlist handling, and approved AI assistance.",
    nameAr: "كارمالايت للتجميل الطبي",
    nameEn: "Karmalite Medical Esthetic",
    slug: "karmalite-medical-esthetic",
    subtitleAr: "مركز كارمالايت للعناية بالجسم والبشرة",
  },
  services: [
    {
      category: "Laser",
      configurationStatus: "DRAFT",
      defaultDurationMins: 60,
      descriptionAr:
        "خدمة تجميلية لإزالة الشعر بالليزر. يتم تأكيد منطقة العلاج وخطة الجلسات والتفاصيل من قبل فريق كارمالايت.",
      descriptionEn:
        "Aesthetic laser service for unwanted hair. The exact treatment area, session plan, and service details are confirmed by Karmalite staff.",
      isOnlineBookable: false,
      minimumNoticeMins: null,
      nameAr: "إزالة الشعر بالليزر",
      nameEn: "Laser Hair Removal",
      postTreatmentInstructionsAr:
        "يُرجى اتباع تعليمات مقدم الخدمة المسؤول والتواصل مباشرة مع كارمالايت عند وجود أي استفسار بعد الجلسة.",
      postTreatmentInstructionsEn:
        "Follow the instructions provided by the assigned service provider. Contact Karmalite directly with any post-session concern.",
      preTreatmentInstructionsAr:
        "يرجى التواصل مع كارمالايت للحصول على تعليمات التحضير الخاصة بالمنطقة المختارة. لا يجوز للمساعد تقديم نصائح بشأن بدء أو إيقاف الأدوية أو مستحضرات البشرة.",
      preTreatmentInstructionsEn:
        "Please contact Karmalite for the preparation instructions that apply to the selected area. The assistant must not advise starting or stopping medication or skin products.",
    },
    {
      category: "Face & Skin Care",
      configurationStatus: "DRAFT",
      defaultDurationMins: 60,
      descriptionAr:
        "خدمة للعناية بالبشرة تركز على التنظيف وتحسين مظهر البشرة وإحساسها، ويتم اختيار البروتوكول المناسب من قبل فريق كارمالايت.",
      descriptionEn:
        "A facial-care service focused on cleansing and improving the appearance and feel of the skin. The exact protocol is selected by Karmalite staff.",
      isOnlineBookable: false,
      minimumNoticeMins: null,
      nameAr: "تنظيف عميق وعناية بالبشرة",
      nameEn: "Deep Cleansing Facial & Skincare",
      postTreatmentInstructionsAr:
        "يُرجى اتباع تعليمات العناية المقدمة أثناء الموعد. لا يجوز للمساعد وصف منتجات أو برامج علاجية.",
      postTreatmentInstructionsEn:
        "Follow the aftercare instructions given during the appointment. The assistant must not prescribe products or treatment routines.",
      preTreatmentInstructionsAr:
        "يُفضّل الحضور ببشرة نظيفة واتباع أي تعليمات تحضير تصدر عن كارمالايت. يجب تأكيد أي قيود على المنتجات مع الفريق.",
      preTreatmentInstructionsEn:
        "Arrive with clean skin when possible and follow any preparation instructions issued by Karmalite. Product restrictions must be confirmed by staff.",
    },
    {
      category: "Body Care",
      configurationStatus: "DRAFT",
      defaultDurationMins: 45,
      descriptionAr:
        "خدمة جمالية للعناية بالجسم. يتم تأكيد الجهاز والمنطقة وخطة الجلسات من قبل فريق كارمالايت بعد مراجعة هدف العميل.",
      descriptionEn:
        "An aesthetic body-care service. The device, treatment area, and session plan are confirmed by Karmalite staff after reviewing the customer’s goal.",
      isOnlineBookable: false,
      minimumNoticeMins: null,
      nameAr: "نحت الجسم والعناية بمظهر السيلوليت",
      nameEn: "Body Contouring & Cellulite Appearance Care",
      postTreatmentInstructionsAr:
        "يُرجى اتباع تعليمات مقدم الخدمة، وعدم تقديم الخدمة على أنها علاج طبي أو وسيلة مضمونة لإنقاص الوزن.",
      postTreatmentInstructionsEn:
        "Follow the service-provider instructions. Do not position the service as a medical or guaranteed weight-loss treatment.",
      preTreatmentInstructionsAr:
        "لا توجد حالياً بطاقة تحضير معتمدة من كارمالايت ضمن النظام. يُطلب من العميل التواصل مع كارمالايت للحصول على التعليمات الحالية.",
      preTreatmentInstructionsEn:
        "No Karmalite-approved preparation card is currently loaded. Ask the customer to contact Karmalite for current instructions.",
    },
    {
      category: "Hair Care",
      configurationStatus: "DRAFT",
      defaultDurationMins: 30,
      descriptionAr:
        "خدمة جمالية للعناية بالشعر وفروة الرأس، ويتم تأكيد تفاصيلها من قبل فريق كارمالايت. لا يقوم المساعد بتقييم أو تشخيص أسباب تساقط الشعر.",
      descriptionEn:
        "An aesthetic hair and scalp-care service. The exact service protocol is confirmed by Karmalite staff. The AI does not assess or diagnose causes of hair loss.",
      isOnlineBookable: false,
      minimumNoticeMins: null,
      nameAr: "العناية بالشعر وفروة الرأس",
      nameEn: "Hair & Scalp Care",
      postTreatmentInstructionsAr:
        "يُرجى اتباع التعليمات المقدمة أثناء الموعد. لا يجوز للمساعد تشخيص تساقط الشعر أو اقتراح أدوية أو مكملات.",
      postTreatmentInstructionsEn:
        "Follow the instructions provided at the appointment. The assistant must not diagnose hair loss or recommend medication or supplements.",
      preTreatmentInstructionsAr:
        "يُفضّل الحضور بشعر نظيف وجاف ومن دون مستحضرات تصفيف ثقيلة، ما لم تصدر كارمالايت تعليمات مختلفة.",
      preTreatmentInstructionsEn:
        "Arrive with clean, dry hair and avoid heavy styling products when possible, unless Karmalite gives different instructions.",
    },
    {
      category: "Screening Appointment",
      configurationStatus: "DRAFT",
      defaultDurationMins: 20,
      descriptionAr:
        "موعد لفحص المعادن لدى كارمالايت. يمكن للمساعد توضيح إجراءات الحجز فقط، ولا يجوز له تفسير النتائج أو تشخيص النقص أو تقييم المناعة أو اقتراح علاج أو مكملات.",
      descriptionEn:
        "A Karmalite mineral-screening appointment. The AI may explain booking logistics only. It must not interpret results, diagnose deficiencies, assess immunity, or recommend treatment or supplements.",
      isOnlineBookable: false,
      minimumNoticeMins: null,
      nameAr: "جلسة فحص المعادن (Oligo Check)",
      nameEn: "Mineral Screening Session (Oligo Check)",
      postTreatmentInstructionsAr:
        "يجب أن يتم شرح النتائج والخطوات التالية من قبل فريق كارمالايت المخول. يقتصر دور المساعد على الحجز أو توجيه التواصل.",
      postTreatmentInstructionsEn:
        "Results and next steps must be explained by authorized Karmalite staff. The assistant may only help with scheduling or contact routing.",
      preTreatmentInstructionsAr:
        "لا توجد حالياً تعليمات تحضير معتمدة ضمن النظام. يُطلب من العميل تأكيد التعليمات الحالية مع كارمالايت قبل الحضور.",
      preTreatmentInstructionsEn:
        "No approved preparation instruction is currently loaded. Ask the customer to confirm current instructions with Karmalite before attending.",
    },
  ] satisfies readonly KarmaliteServiceTemplate[],
  settings: {
    bookingPolicyStatus: "DRAFT" as const,
    bookingWindowDays: null,
    cancellationWindowMins: 720,
    confirmationEnabled: false,
    currency: "JOD",
    defaultAppointmentStatus: "PENDING" as const,
    defaultLocale: "en" as const,
    noShowPolicyAr:
      "يرجى التواصل مع كارمالايت لتأكيد سياسة الإلغاء وتغيير الموعد والتأخر وعدم الحضور الحالية.",
    noShowPolicyEn:
      "Please contact Karmalite to confirm the current cancellation, rescheduling, late-arrival, and no-show policy.",
    reminderLeadMins: 1440,
    rescheduleWindowMins: 720,
    secondaryReminderLeadMins: 240,
    timezone: "Asia/Amman",
  },
  widget: {
    displayNameAr: "مساعد كارمالايت",
    displayNameEn: "Karmalite Assistant",
    name: "Karmalite Assistant",
  },
} as const;
