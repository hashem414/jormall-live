(function () {
  const STORAGE_KEY = 'jormall_ui_language';
  const originalText = new WeakMap();

  const translations = {
    // Core/login/session
    'JorMall Assistant': 'مساعد جورمول',
    'Username': 'اسم المستخدم',
    'Password': 'كلمة المرور',
    'Login': 'تسجيل الدخول',
    'Your session will expire in': 'ستنتهي جلستك خلال',
    'seconds.': 'ثانية.',
    'Extend Session': 'تمديد الجلسة',
    'LOGOUT': 'تسجيل الخروج',
    'Please enter your client\'s information:': 'يرجى إدخال معلومات العميل:',
    'Client Name': 'اسم العميل',
    'Industry': 'القطاع',
    'Mobile Number': 'رقم الهاتف',
    'Continue': 'متابعة',

    // Header/tools
    'Sales Dept. Call Script Panel': 'لوحة نص مكالمات قسم المبيعات',
    'SMA Documents Panel': 'لوحة مستندات SMA',
    'Landing Pages Builder': 'منشئ صفحات الهبوط',
    'Close Landing Pages Builder': 'إغلاق منشئ صفحات الهبوط',
    'AI Embedding Analysis': 'تحليل بيانات',
    'AI Analysis': 'تحليل بيانات',
    'Refresh': 'تحديث',
    'Click Refresh or open this window to analyze the loaded chatbot embeddings.': 'اضغط تحديث أو افتح هذه النافذة لتحليل تضمينات قاعدة معرفة المساعد.',
    '2D PCA scatter plot': 'مخطط PCA ثنائي الأبعاد',
    'Each point is one embedded knowledge-base chunk. Click a point to inspect it.': 'كل نقطة تمثل مقطعاً من قاعدة المعرفة. اضغط على نقطة لمعاينتها.',
    'Selected chunk': 'المقطع المحدد',
    'No point selected yet.': 'لم يتم اختيار أي نقطة بعد.',
    'Chat History': 'سجل المحادثات',
    'New Chat': 'محادثة جديدة',
    'No previous chats yet': 'لا توجد محادثات سابقة بعد',
    'Previous Chat': 'محادثة سابقة',
    'Previous Chat (with credentials)': 'محادثة سابقة مع بيانات العميل',
    'Client:': 'العميل:',
    'Company:': 'الشركة:',
    'Industry:': 'القطاع:',
    'Phone:': 'الهاتف:',
    'Show client details': 'عرض بيانات العميل',
    'Toggle Sidebar Menu': 'إظهار/إخفاء القائمة الجانبية',
    'Start New Chat': 'بدء محادثة جديدة',
    'Sales Call Script': 'نص مكالمة المبيعات',
    'SMA Documents': 'مستندات SMA',
    'SMA Documents Layout': 'عرض مستندات SMA',
    'More Tools': 'أدوات إضافية',
    'Send Full Chat': 'إرسال كامل المحادثة',
    'Send Chat': 'إرسال المحادثة',
    'Create SMS Campaign': 'إنشاء حملة رسائل قصيرة',
    'Create SMS': 'إنشاء رسائل SMS',
    'Client Insights': 'لمحة عن العميل',
    'Fetch Profile or Marketing Plan Report': 'إنشاء ملف تعريفي أو خطة تسويقية',
    'Landing Pages': 'صفحات الهبوط',
    'File Library': 'مكتبة الملفات',
    'Chatbot documents': 'مستندات المساعد',
    'log-out': 'تسجيل الخروج',

    // Profile modal
    'Generate Report': 'إنشاء تقرير',
    'Information Source': 'مصدر المعلومات',
    'Company Name': 'اسم الشركة',
    'Company URL': 'رابط موقع الشركة',
    'About Text': 'نبذة نصية',
    'Profile Report': 'تقرير الملف التعريفي',
    'Marketing Plan': 'خطة تسويقية',
    'Processing complete': 'اكتملت المعالجة',
    '📄 DOCX report is ready.': '📄 ملف Word جاهز.',
    '⬇ Download Word Document': '⬇ تحميل ملف Word',

    // Location/cities
    'Cities (Optional)': 'المدن (اختياري)',
    'Select Cities': 'اختر المدن',
    'Amman': 'عمّان',
    'Irbid': 'إربد',
    'Zarqa': 'الزرقاء',
    'Balqa': 'البلقاء',
    'Madaba': 'مادبا',
    'Mafraq': 'المفرق',
    'Jerash': 'جرش',
    'Ajloun': 'عجلون',
    'Karak': 'الكرك',
    'Tafilah': 'الطفيلة',
    "Ma'an": 'معان',
    'Aqaba': 'العقبة',
    'Amman Directions': 'اتجاهات عمّان',
    'West': 'غرب',
    'East': 'شرق',

    // SMS modal
    'Generate SMS Campaign': 'إنشاء حملة رسائل قصيرة',
    'Document Language': 'لغة المستند',
    'English Document': 'مستند إنجليزي',
    'Arabic Document': 'مستند عربي',
    'SMS Type': 'نوع الرسائل',
    'Smart Reach SMS': 'رسائل الوصول الذكي',
    'Chain SMS': 'رسائل متسلسلة',
    'Premium SMS': 'رسائل مميزة',
    'Personalized SMS': 'رسائل مخصصة',
    'Lead SMS': 'رسائل لجمع العملاء المحتملين',
    'Opt-In SMS': 'رسائل الموافقة',
    'Send a single SMS with dynamic targeting and intelligent delivery optimization.': 'إرسال رسالة واحدة مع استهداف ديناميكي وتحسين ذكي للتوقيت والتوصيل.',
    'Send multiple scheduled messages in a campaign, each with its own date and content.': 'إرسال عدة رسائل مجدولة ضمن حملة واحدة، لكل رسالة تاريخ ومحتوى خاص.',
    'Includes SMS text, social media post caption, landing page design, banner design, and video description.': 'تشمل نص الرسائل، كابشن منصات التواصل، تصميم صفحة هبوط، تصميم بانر، ووصف فيديو.',
    'Ideal for one-to-one messages using customer names and unique offers to boost conversion.': 'مناسبة للرسائل الفردية التي تستخدم أسماء العملاء وعروضاً مخصصة لرفع التحويل.',
    'Targeted SMS campaigns designed to generate and capture potential customer leads.': 'حملات رسائل مستهدفة لجذب وتسجيل العملاء المحتملين.',
    'Collect customer consent for future SMS communications, ensuring compliance with regulations.': 'جمع موافقة العملاء للتواصل المستقبلي عبر الرسائل مع الالتزام بالتعليمات.',
    'Campaign Brief': 'ملخص الحملة',
    'Bitly Link': 'رابط Bitly',
    'Phone Number': 'رقم الهاتف',
    'Delivery:': 'التسليم:',
    'Today': 'اليوم',
    'Delivery: Today': 'التسليم: اليوم',
    "Delivery Date (Client's Request)": 'تاريخ التسليم (حسب طلب العميل)',
    'Campaign Title': 'عنوان الحملة',
    'Messages in Campaign': 'عدد رسائل الحملة',
    'Consent Link (Bitly)': 'رابط الموافقة (Bitly)',
    'Purpose or Notes (Optional)': 'الغرض أو الملاحظات (اختياري)',
    '⏳ Generating report. Please wait...': '⏳ جارٍ إنشاء التقرير. يرجى الانتظار...',
    'Processing is complete.': 'اكتملت المعالجة.',
    'Generate Campaign': 'إنشاء الحملة',
    'Cancel': 'إلغاء',
    'Generate Bitly': 'إنشاء رابط Bitly',
    'Long URL': 'الرابط الطويل',
    'Shorten': 'اختصار',
    'Insert': 'إدراج',

    // Reporting/email/chat
    'Report Chat': 'الإبلاغ عن المحادثة',
    'Report This Chat': 'الإبلاغ عن هذه المحادثة',
    'Please tell us why you\'re reporting this conversation:': 'يرجى توضيح سبب الإبلاغ عن هذه المحادثة:',
    'The response includes incorrect or misleading information.': 'الرد يحتوي على معلومات غير صحيحة أو مضللة.',
    'The answer is unclear, confusing, or poorly structured.': 'الإجابة غير واضحة أو مربكة أو غير منظمة.',
    'The assistant used an inappropriate or unprofessional tone.': 'استخدم المساعد نبرة غير مناسبة أو غير مهنية.',
    'This topic is not relevant for JorMall internal use.': 'هذا الموضوع غير مناسب للاستخدام الداخلي في جورمول.',
    'Other reason (please specify below):': 'سبب آخر (يرجى التوضيح أدناه):',
    'Submit Report': 'إرسال البلاغ',
    'Email ·': 'البريد الإلكتروني ·',
    'To:': 'إلى:',
    'CC:': 'نسخة:',
    'Chat content': 'محتوى المحادثة',
    'Send': 'إرسال',
    'Sales Tool': 'أداة المبيعات',
    'Ask Assistant': 'اسأل المساعد',
    'File': 'ملف',
    'Folder': 'مجلد',
    'Report Explainer': 'شرح التقرير',
    'Explain attached report': 'شرح التقرير المرفق',
    'Campaign Report Explainer': 'شرح تقرير الحملة',

    'About JorMall': 'عن جورمول',
    'SMS Products': 'منتجات الرسائل',
    'Campaign Ideas': 'أفكار حملات',
    'Proposal': 'عرض مقترح',
    'Call Script': 'نص مكالمة',
    'CTR & ROI Benchmarks': 'معايير CTR و ROI',
    'API Integration': 'تكامل API',
    'JorMall Platform': 'منصة جورمول',
    'ACR System': 'نظام ACR',
    'Campaign Generator by Industry': 'منشئ الحملات حسب القطاع',
    'Generate campaign ideas, SMS options, WhatsApp copy, targeting, timing, and CTA by industry.': 'إنشاء أفكار حملات وخيارات SMS ونص واتساب واستهداف وتوقيت ودعوة لاتخاذ إجراء حسب القطاع.',
    'Campaign by Industry': 'حملة حسب القطاع',
    'SMS Checker': 'فحص SMS',
    'SMS type': 'نوع الرسالة',
    'ADV / Advertising': 'ADV / إعلانية',
    'SRV / Service': 'SRV / خدمية',
    'Not sure': 'غير متأكد',
    'Client Sales Mode': 'وضع مبيعات العميل',
    'Preferred channel': 'القناة المفضلة',
    'All channels': 'كل القنوات',
    'WhatsApp': 'واتساب',
    'Email': 'البريد الإلكتروني',
    'Landing page': 'صفحة هبوط',
    'SMS + Landing page': 'SMS + صفحة هبوط',
    'WhatsApp + Landing page': 'واتساب + صفحة هبوط',
    'Channel': 'القناة',
    'Follow-up Message Generator': 'منشئ رسائل المتابعة',
    'Follow-up situation': 'حالة المتابعة',
    'After meeting': 'بعد الاجتماع',
    'After sending proposal': 'بعد إرسال العرض',
    'No reply': 'لا يوجد رد',
    'After campaign report': 'بعد تقرير الحملة',
    'Renewal follow-up': 'متابعة التجديد',
    'Payment / approval follow-up': 'متابعة الدفع / الموافقة',
    'Tone': 'النبرة',
    'Professional': 'رسمية',
    'Friendly': 'ودية',
    'Direct': 'مباشرة',
    'Premium / executive': 'تنفيذية / راقية',
    'Arabic formal': 'عربية رسمية',
    'Output channel': 'قناة الإخراج',
    'Arabic WhatsApp': 'واتساب عربي',
    'English Email': 'بريد إنجليزي',
    'Sales Call Script Generator': 'منشئ نص مكالمة المبيعات',
    'Call script language': 'لغة نص المكالمة',
    'Arabic style': 'أسلوب العربية',
    'Jordanian Dialect': 'اللهجة الأردنية',
    'Formal Arabic': 'العربية الفصحى',
    'Salesperson level': 'مستوى موظف المبيعات',
    'Beginner': 'مبتدئ',
    'Intermediate': 'متوسط',
    'Expert': 'خبير',
    'Follow-up channel': 'قناة المتابعة',
    'Campaign / client name': 'اسم الحملة / العميل',
    'Report type': 'نوع التقرير',
    'SMS delivery report': 'تقرير توصيل SMS',
    'WhatsApp broadcast report': 'تقرير بث واتساب',
    'Bitly / clicks report': 'تقرير Bitly / النقرات',
    'Mixed campaign report': 'تقرير حملة مختلطة',
    'Website / Client Analyzer': 'محلل الموقع / العميل',
    'Read a client website and prepare a JorMall sales analysis with recommended campaign ideas.': 'قراءة موقع العميل وتجهيز تحليل مبيعات لجورمول مع أفكار حملات مقترحة.',
    'Website Analyzer': 'محلل الموقع',
    'Recommended channel focus': 'تركيز القناة المقترحة',
    'Submit': 'إرسال',
    // Sales tools dynamic labels
    'Call objective': 'هدف المكالمة',
    'Book a Meeting': 'حجز اجتماع',
    'Sell SMS': 'بيع رسائل SMS',
    'Sell WhatsApp': 'بيع واتساب',
    'Sell Landing Pages': 'بيع صفحات الهبوط',
    'Upsell Existing Client': 'زيادة مبيعات لعميل حالي',
    'Renew Package': 'تجديد الباقة',
    'Follow-up': 'متابعة',
    'Campaign objective': 'هدف الحملة',
    'Offer / product focus': 'العرض / المنتج المستهدف',
    'Target area / segment': 'المنطقة / الشريحة المستهدفة',
    'SMS message': 'نص الرسالة',
    'Sender ID': 'اسم المرسل',
    'Website / Instagram URL': 'الموقع / رابط إنستغرام',
    'Business objective': 'هدف العمل',
    'Budget / quantity': 'الميزانية / الكمية',
    'Client notes': 'ملاحظات العميل',
    'Recommended package / budget': 'الباقة / الميزانية المقترحة',
    'Extra notes': 'ملاحظات إضافية',
    'Requested next action': 'الإجراء التالي المطلوب',
    'Context notes': 'ملاحظات السياق',
    'Client company': 'شركة العميل',
    'Contact role': 'صفة جهة الاتصال',
    'Client notes / objections': 'ملاحظات / اعتراضات العميل',
    'What should be checked?': 'ما المطلوب فحصه؟',
    'Sales objective': 'هدف المبيعات',
    'SMS Length': 'طول الرسالة',
    'ADV vs SRV Rules': 'قواعد ADV و SRV',
    'Pricing T&C': 'شروط وأحكام الأسعار',
    'SMS vs Channels': 'SMS مقارنة بالقنوات الأخرى',
    'Order Processing': 'معالجة الطلبات',
    'Sales Tools': 'أدوات المبيعات'
  };

  const placeholderTranslations = {
    'Username': 'اسم المستخدم',
    'Password': 'كلمة المرور',
    'Client Name': 'اسم العميل',
    'Company Name': 'اسم الشركة',
    'Industry': 'القطاع',
    'Mobile Number': 'رقم الهاتف',
    'Write or paste a short company description...': 'اكتب أو الصق نبذة قصيرة عن الشركة...',
    'A campaign on ...': 'حملة عن ...',
    'bit.ly/link (optional)': 'bit.ly/link (اختياري)',
    '07XXXXXXXX (optional)': '07XXXXXXXX (اختياري)',
    'Campaign Title': 'عنوان الحملة',
    'bit.ly/consent': 'bit.ly/consent',
    'e.g. Monthly offers, account updates...': 'مثال: عروض شهرية، تحديثات الحساب...',
    'Additional comments (optional)': 'تعليقات إضافية (اختياري)',
    'Recipient Email': 'البريد الإلكتروني للمستلم',
    'CC Email (optional)': 'نسخة CC (اختياري)',
    'Type your message here...': 'اكتب رسالتك هنا...',
    'Restaurant, clinic, real estate, retail...': 'مطعم، عيادة، عقار، تجزئة...',
    'Awareness, visits, leads, sales, renewal...': 'وعي، زيارات، عملاء محتملون، مبيعات، تجديد...',
    'Weekend discount, new branch, limited package...': 'خصم نهاية الأسبوع، فرع جديد، باقة محدودة...',
    'West Amman, families, students, high-income...': 'غرب عمّان، عائلات، طلاب، دخل مرتفع...',
    'Paste the SMS text here...': 'الصق نص الرسالة هنا...',
    'Sender ID / brand name': 'اسم المرسل / العلامة التجارية',
    'Increase visits, generate leads, sell package...': 'زيادة الزيارات، توليد عملاء محتملين، بيع باقة...',
    'e.g. 500 JD or 100,000 SMS': 'مثال: 500 دينار أو 100,000 رسالة',
    'What did the client say? Any objections or requirements?': 'ماذا قال العميل؟ هل توجد اعتراضات أو متطلبات؟',
    'Awareness, traffic, leads, sales...': 'وعي، زيارات، عملاء محتملون، مبيعات...',
    'SMS quantity, budget, package name...': 'كمية الرسائل، الميزانية، اسم الباقة...',
    'Offer, targeting, campaign date, special terms...': 'العرض، الاستهداف، تاريخ الحملة، شروط خاصة...',
    'Approve proposal, confirm quantity, schedule campaign...': 'اعتماد العرض، تأكيد الكمية، جدولة الحملة...',
    'Meeting summary, offer details, dates, objections...': 'ملخص الاجتماع، تفاصيل العرض، التواريخ، الاعتراضات...',
    'Client / company name': 'اسم العميل / الشركة',
    'Restaurant, clinic, bank, school...': 'مطعم، عيادة، بنك، مدرسة...',
    'Marketing manager, owner, CEO...': 'مدير تسويق، مالك، مدير عام...',
    'What do we know about them?': 'ماذا نعرف عنهم؟',
    'Upload the report, then mention delivery rate, failed numbers, clicks, or client concern.': 'ارفع التقرير، ثم اذكر معدل التسليم أو الأرقام الفاشلة أو النقرات أو ملاحظة العميل.',
    'Suggest SMS campaign, prepare pitch, analyze target customers...': 'اقتراح حملة SMS، تحضير عرض، تحليل العملاء المستهدفين...',
    'Any known products, target audience, branch locations, or budget?': 'أي منتجات معروفة، جمهور مستهدف، مواقع فروع، أو ميزانية؟'
  };

  function normalize(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }

  function translateString(text) {
    const key = normalize(text);
    if (!key) return text;
    if (translations[key]) return translations[key];
    let m = key.match(/^Campaign Pitch (\d+)$/);
    if (m) return `عرض الحملة ${m[1]}`;
    m = key.match(/^Date & Time for Message (\d+)$/);
    if (m) return `التاريخ والوقت للرسالة ${m[1]}`;
    m = key.match(/^Date for Message (\d+)$/);
    if (m) return `تاريخ الرسالة ${m[1]}`;
    m = key.match(/^Time for Message (\d+)$/);
    if (m) return `وقت الرسالة ${m[1]}`;
    m = key.match(/^Message (\d+)$/);
    if (m) return `الرسالة ${m[1]}`;
    return null;
  }

  function translatePlaceholder(text) {
    const key = normalize(text);
    if (placeholderTranslations[key]) return placeholderTranslations[key];
    let m = key.match(/^Enter message (\d+) pitch\.\.\.$/);
    if (m) return `أدخل فكرة الرسالة ${m[1]}...`;
    return null;
  }

  function shouldSkipNode(node) {
    const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    if (!el) return true;
    if (el.closest('script, style, noscript, svg, canvas')) return true;
    if (el.closest('#chat-messages, #email-body, #attachment-hover-preview')) return true;
    if (el.closest('[data-no-ui-translate]')) return true;
    return false;
  }

  function translateTextNode(node, lang) {
    if (!node || node.nodeType !== Node.TEXT_NODE || shouldSkipNode(node)) return;
    const original = originalText.get(node) || node.nodeValue;
    if (!originalText.has(node)) originalText.set(node, original);
    const translated = translateString(original);
    if (lang === 'ar' && translated) {
      const leading = (original.match(/^\s*/) || [''])[0];
      const trailing = (original.match(/\s*$/) || [''])[0];
      node.nodeValue = leading + translated + trailing;
    } else if (lang === 'en') {
      node.nodeValue = original;
    }
  }

  function translateAttributes(el, lang) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE || shouldSkipNode(el)) return;
    ['placeholder', 'title', 'aria-label'].forEach(attr => {
      if (!el.hasAttribute(attr)) return;
      const dataAttr = `data-i18n-${attr}-original`;
      if (!el.hasAttribute(dataAttr)) el.setAttribute(dataAttr, el.getAttribute(attr) || '');
      const original = el.getAttribute(dataAttr) || '';
      const translated = attr === 'placeholder' ? translatePlaceholder(original) : translateString(original);
      if (lang === 'ar' && translated && el.getAttribute(attr) !== translated) el.setAttribute(attr, translated);
      if (lang === 'en' && el.getAttribute(attr) !== original) el.setAttribute(attr, original);
    });
  }

  function walkAndTranslate(root, lang) {
    if (!root || shouldSkipNode(root)) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root, lang);
      return;
    }
    if (root.nodeType === Node.ELEMENT_NODE) translateAttributes(root, lang);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return shouldSkipNode(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach(node => translateTextNode(node, lang));
    if (root.querySelectorAll) root.querySelectorAll('[placeholder], [title], [aria-label]').forEach(el => translateAttributes(el, lang));
  }

  function setLanguage(lang) {
    lang = lang === 'ar' ? 'ar' : 'en';
    localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.body.classList.toggle('ui-ar', lang === 'ar');
    document.body.classList.toggle('ui-en', lang !== 'ar');
    walkAndTranslate(document.body, lang);
    updateToggleButton(lang);
    syncIframes(lang);
    document.dispatchEvent(new CustomEvent('jormall-ui-language-change', { detail: { lang } }));
  }

  function syncIframes(lang) {
    document.querySelectorAll('iframe').forEach(frame => {
      try {
        if (frame.contentWindow) frame.contentWindow.postMessage({ type: 'JORMALL_UI_LANGUAGE', lang }, window.location.origin);
      } catch (err) {}
    });
  }

  function updateToggleButton(lang) {
    const btn = document.getElementById('ui-language-toggle');
    if (!btn) return;
    btn.setAttribute('aria-pressed', lang === 'ar' ? 'true' : 'false');
    btn.setAttribute('title', lang === 'ar' ? 'Switch website to English' : 'تحويل الموقع إلى العربية');
    btn.innerHTML = lang === 'ar'
      ? '<span>EN</span><strong>عربي</strong>'
      : '<strong>EN</strong><span>عربي</span>';
  }

  function createToggleButton() {
    if (document.getElementById('ui-language-toggle')) return;
    const btn = document.createElement('button');
    btn.id = 'ui-language-toggle';
    btn.type = 'button';
    btn.className = 'ui-language-toggle';
    btn.addEventListener('click', () => {
      const current = localStorage.getItem(STORAGE_KEY) === 'ar' ? 'ar' : 'en';
      setLanguage(current === 'ar' ? 'en' : 'ar');
    });
    document.body.appendChild(btn);
  }

  function injectStyles() {
    if (document.getElementById('ui-language-toggle-styles')) return;
    const style = document.createElement('style');
    style.id = 'ui-language-toggle-styles';
    style.textContent = `
      .ui-language-toggle {
        position: fixed;
        top: 12px;
        right: 150px;
        z-index: 5000;
        height: 38px;
        min-width: 112px;
        border: 1px solid rgba(255,255,255,0.78);
        border-radius: 999px;
        background: linear-gradient(135deg, #ffffff 0%, #ebfaff 100%);
        color: #2575b6;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 4px 8px;
        font: 800 12px Arial, sans-serif;
        box-shadow: 0 8px 22px rgba(0,0,0,0.22);
        direction: ltr;
        cursor: pointer;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
      }
      .ui-language-toggle:hover {
        transform: translateY(-1px);
        border-color: #47c6f3;
        box-shadow: 0 11px 28px rgba(37,117,182,0.28);
      }
      .ui-language-toggle strong {
        background: linear-gradient(135deg, #2575b6, #47c6f3);
        color: white;
        border-radius: 999px;
        padding: 6px 10px;
        min-width: 34px;
        text-align: center;
      }
      .ui-language-toggle span {
        opacity: 0.78;
        padding: 6px 8px;
        min-width: 32px;
        text-align: center;
      }
      #logout-button {
        position: fixed !important;
        top: 12px !important;
        right: 20px !important;
        height: 38px;
        border-radius: 999px !important;
        padding: 0 16px !important;
        display: inline-flex !important;
        align-items: center;
        justify-content: center;
        gap: 8px;
        box-shadow: 0 8px 22px rgba(238,64,55,0.25);
      }
      body.ui-ar { direction: rtl; }
      body.ui-ar #login-modal-box,
      body.ui-ar #credentials-modal,
      body.ui-ar #profile-modal-content,
      body.ui-ar #sms-modal-content,
      body.ui-ar #bitly-modal-content,
      body.ui-ar #report-modal,
      body.ui-ar #email-modal,
      body.ui-ar #sales-tool-modal,
      body.ui-ar #embedding-analysis-content,
      body.ui-ar #landing-pages-modal-content {
        direction: rtl;
        text-align: right;
      }
      body.ui-ar input:not([type="url"]):not([type="email"]):not([type="tel"]):not([type="time"]):not([type="date"]):not([type="number"]),
      body.ui-ar textarea,
      body.ui-ar [contenteditable="true"] {
        direction: rtl;
        text-align: right;
      }
      body.ui-ar input[type="url"], body.ui-ar input[type="email"], body.ui-ar input[type="tel"],
      body.ui-ar #shortURL, body.ui-ar #smsCompanyURL, body.ui-ar #companyURL, body.ui-ar #longURL {
        direction: ltr;
        text-align: left;
      }
      body.ui-ar .input-group i { margin-right: 0; margin-left: 10px; }
      body.ui-ar #chat-sidebar {
        left: 0 !important;
        right: auto !important;
        direction: rtl;
        text-align: right;
        box-shadow: 4px 0 12px rgba(0,0,0,0.20);
      }
      body.ui-ar #chat-box.sidebar-visible { margin-left: 0 !important; margin-right: 0 !important; }
      body.ui-ar #chat-messages { direction: ltr; }
      body.ui-ar #chat-history-list { direction: rtl; text-align: right; }
      body.ui-ar .chat-entry { direction: rtl; text-align: right; }
      body.ui-ar .chat-entry-title { direction: rtl; text-align: right; }
      body.ui-ar .chat-entry-main { flex-direction: row; }
      body.ui-ar .sidebar-timestamp { text-align: right; direction: ltr; unicode-bidi: plaintext; }
      body.ui-ar .credentials-text { direction: rtl; text-align: right; }
      body.ui-ar .credentials-container { padding-left: 10px !important; padding-right: 10px !important; }
      body.ui-ar #user-input { direction: rtl; text-align: right; }
      body.ui-ar #sms-modal-content label,
      body.ui-ar #profile-modal-content label,
      body.ui-ar #bitly-modal-content label { text-align: right !important; }
      body.ui-ar .document-language-toggle { direction: rtl; }
      body.ui-ar .chain-message-block { direction: rtl; }
      body.ui-ar .date-time-row { direction: ltr; }
      body.ui-ar .city-dropdown-toggle { direction: rtl; text-align: right; }
      body.ui-ar #right-toolbar { direction: rtl; }
      body.ui-ar #toolbar-buttons button { text-align: right; }
      @media (max-width: 720px) {
        .ui-language-toggle { top: 8px; right: 114px; min-width: 88px; height: 32px; font-size: 11px; }
        #logout-button { top: 8px !important; right: 12px !important; height: 32px !important; padding: 0 12px !important; }
      }
    `;
    document.head.appendChild(style);
  }

  function observeMutations() {
    const observer = new MutationObserver(mutations => {
      const lang = localStorage.getItem(STORAGE_KEY) === 'ar' ? 'ar' : 'en';
      mutations.forEach(m => {
        m.addedNodes.forEach(node => walkAndTranslate(node, lang));
        if (m.type === 'attributes' && m.target) translateAttributes(m.target, lang);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label'] });
  }

  document.addEventListener('DOMContentLoaded', () => {
    injectStyles();
    createToggleButton();
    setLanguage(localStorage.getItem(STORAGE_KEY) === 'ar' ? 'ar' : 'en');
    observeMutations();
  });

  window.JorMallUILanguage = { set: setLanguage, translate: translateString };
})();
