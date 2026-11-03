(function () {
  const STORAGE_KEY = 'jormall_ui_language';
  const originalText = new WeakMap();
  const T = {
    'Editable Mobile Website Template': 'قالب موقع موبايل قابل للتعديل',
    'Company Name': 'اسم الشركة',
    'PREMIUM EXPERIENCE': 'تجربة مميزة',
    'Drive the Future': 'قد المستقبل',
    'Luxury performance with modern technology.': 'أداء فاخر بتقنية حديثة.',
    'Starting Price: $21,000': 'السعر يبدأ من: 21,000 دولار',
    'Image preview appears here': 'تظهر معاينة الصورة هنا',
    'Clothing': 'ملابس',
    'Accessories': 'إكسسوارات',
    'Footwear': 'أحذية',
    'Bags': 'حقائب',
    'Get Started': 'ابدأ الآن',
    'Book a Test Drive': 'احجز تجربة قيادة',
    'Contact Us': 'تواصل معنا',
    'Find Location': 'اعرف الموقع',
    'All rights reserved.': 'جميع الحقوق محفوظة.',
    'Edit Template': 'تعديل القالب',
    'Change content and export as PNG': 'عدّل المحتوى وصدّره بصيغة PNG',
    'Output Language': 'لغة الصفحة الناتجة',
    'Template Defaults': 'إعدادات القالب الافتراضية',
    'Industry': 'القطاع',
    'Cars': 'سيارات',
    'Fashion': 'أزياء',
    'Grocery': 'بقالة',
    'Medical Labs': 'مختبرات طبية',
    'Cosmetics': 'مستحضرات تجميل',
    'Banking': 'مصارف',
    'Brand Section': 'قسم العلامة التجارية',
    'Brand Name': 'اسم العلامة التجارية',
    'Brand Logo': 'شعار العلامة التجارية',
    'Upload Logo': 'رفع الشعار',
    'Hero Section': 'القسم الرئيسي',
    'Tagline': 'العبارة الترويجية',
    'Title': 'العنوان',
    'Description': 'الوصف',
    'Price / Offer': 'السعر / العرض',
    'Main Image': 'الصورة الرئيسية',
    'Upload Image': 'رفع صورة',
    'Fashion Categories': 'فئات الأزياء',
    'Show Categories Section': 'إظهار قسم الفئات',
    'Category 1': 'الفئة 1',
    'Category 2': 'الفئة 2',
    'Category 3': 'الفئة 3',
    'Category 4': 'الفئة 4',
    'Button Text': 'نص الزر',
    'Features Section': 'قسم المزايا',
    'Show Features Section': 'إظهار قسم المزايا',
    'Feature 1 Title': 'عنوان الميزة 1',
    'Feature 1 Icon': 'أيقونة الميزة 1',
    'Feature 2 Title': 'عنوان الميزة 2',
    'Feature 2 Icon': 'أيقونة الميزة 2',
    'Feature 3 Title': 'عنوان الميزة 3',
    'Feature 3 Icon': 'أيقونة الميزة 3',
    'Footer Section': 'قسم التذييل',
    'Show Footer': 'إظهار التذييل',
    'Copyright Year': 'سنة حقوق النشر',
    'Footer Text': 'نص التذييل',
    'Design Controls': 'إعدادات التصميم',
    'Primary Theme Color': 'لون الثيم الأساسي',
    'Secondary Theme Color': 'لون الثيم الثانوي',
    'Button Color': 'لون الزر',
    'Background Color': 'لون الخلفية',
    'Apply Changes': 'تطبيق التغييرات',
    'Export PNG': 'تصدير PNG'
  };
  const P = {
    'Example: Toyota': 'مثال: Toyota',
    'Tagline': 'العبارة الترويجية',
    'Title': 'العنوان',
    'Write description': 'اكتب الوصف',
    'Starting Price': 'السعر يبدأ من',
    'Category 1': 'الفئة 1',
    'Category 2': 'الفئة 2',
    'Category 3': 'الفئة 3',
    'Category 4': 'الفئة 4',
    'Button Text': 'نص الزر',
    'Feature 1': 'الميزة 1',
    'Feature 2': 'الميزة 2',
    'Feature 3': 'الميزة 3',
    '2026': '2026',
    'All rights reserved.': 'جميع الحقوق محفوظة.'
  };
  function norm(x){ return String(x || '').replace(/\s+/g,' ').trim(); }
  function skip(node){ const el=node.nodeType===1?node:node.parentElement; return !el || el.closest('script,style,svg,canvas,[data-no-ui-translate]'); }
  function translateNode(node, lang){
    if(!node || node.nodeType!==3 || skip(node)) return;
    const original=originalText.get(node) || node.nodeValue;
    if(!originalText.has(node)) originalText.set(node, original);
    const tr=T[norm(original)];
    if(lang==='ar' && tr){
      const lead=(original.match(/^\s*/)||[''])[0], tail=(original.match(/\s*$/)||[''])[0];
      node.nodeValue=lead+tr+tail;
    } else if(lang==='en') node.nodeValue=original;
  }
  function translateAttrs(el, lang){
    if(!el || el.nodeType!==1 || skip(el)) return;
    ['placeholder','title','aria-label'].forEach(a=>{
      if(!el.hasAttribute(a)) return;
      const d='data-i18n-'+a+'-original';
      if(!el.hasAttribute(d)) el.setAttribute(d, el.getAttribute(a)||'');
      const original=el.getAttribute(d)||'';
      const tr=(a==='placeholder'?P[norm(original)]:T[norm(original)]);
      if(lang==='ar' && tr && el.getAttribute(a)!==tr) el.setAttribute(a,tr);
      if(lang==='en' && el.getAttribute(a)!==original) el.setAttribute(a,original);
    });
  }
  function walk(root, lang){
    if(!root || skip(root)) return;
    if(root.nodeType===3){ translateNode(root,lang); return; }
    if(root.nodeType===1) translateAttrs(root,lang);
    const w=document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode:n=>skip(n)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
    const arr=[]; while(w.nextNode()) arr.push(w.currentNode); arr.forEach(n=>translateNode(n,lang));
    if(root.querySelectorAll) root.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el=>translateAttrs(el,lang));
  }
  function updateBtn(lang){
    const b=document.getElementById('landing-ui-language-toggle'); if(!b) return;
    b.innerHTML=lang==='ar'?'<span>EN</span><strong>عربي</strong>':'<strong>EN</strong><span>عربي</span>';
  }
  function apply(lang){
    lang=lang==='ar'?'ar':'en';
    localStorage.setItem(STORAGE_KEY,lang);
    document.documentElement.lang=lang;
    document.documentElement.dir=lang==='ar'?'rtl':'ltr';
    document.body.classList.toggle('ui-ar',lang==='ar');
    walk(document.body,lang);
    updateBtn(lang);
  }
  function addBtn(){
    if(document.getElementById('landing-ui-language-toggle')) return;
    const b=document.createElement('button');
    b.id='landing-ui-language-toggle';
    b.type='button';
    b.className='landing-ui-language-toggle';
    b.onclick=()=>apply((localStorage.getItem(STORAGE_KEY)==='ar')?'en':'ar');
    document.body.appendChild(b);
  }
  function style(){
    const s=document.createElement('style');
    s.textContent=`
      .landing-ui-language-toggle{position:fixed;top:12px;right:14px;z-index:9999;height:32px;min-width:86px;border:1px solid #d8e9fb;border-radius:999px;background:white;color:#2575b6;display:flex;align-items:center;justify-content:center;gap:6px;padding:4px 10px;font:700 12px Arial,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,.15);direction:ltr}
      .landing-ui-language-toggle strong{background:#2575b6;color:white;border-radius:999px;padding:3px 8px}.landing-ui-language-toggle span{opacity:.75}
      body.ui-ar .editor-side{direction:rtl;text-align:right} body.ui-ar .editor-side input, body.ui-ar .editor-side textarea, body.ui-ar .editor-side select{text-align:right;direction:rtl}
      body.ui-ar .color-row input, body.ui-ar input[type=color]{direction:ltr;text-align:left} body.ui-ar .preview-side{direction:ltr}
    `;
    document.head.appendChild(s);
  }
  document.addEventListener('DOMContentLoaded',()=>{
    style(); addBtn(); apply(localStorage.getItem(STORAGE_KEY)==='ar'?'ar':'en');
    new MutationObserver(ms=>{const lang=localStorage.getItem(STORAGE_KEY)==='ar'?'ar':'en'; ms.forEach(m=>m.addedNodes.forEach(n=>walk(n,lang)));}).observe(document.body,{childList:true,subtree:true});
  });
  window.addEventListener('message', e=>{
    if(e.origin!==window.location.origin) return;
    if(e.data && e.data.type==='JORMALL_UI_LANGUAGE') apply(e.data.lang);
  });
})();
