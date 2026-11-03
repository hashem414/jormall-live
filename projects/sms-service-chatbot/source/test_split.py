import re

def looks_like_pricing_request(question: str) -> bool:
    PRICING_INTENT_EN_PATTERN = re.compile(
        r'\b(?:price|prices|pricing|cost|costs|rate|rates|quote|quotation|'
        r'package|packages|fee|fees|tariff|setup\s+fee|platform\s+fees?|'
        r'how\s+much|price\s+per\s+sms|per\s+sms)\b',
        flags=re.IGNORECASE,
    )
    PRICING_INTENT_AR_TERMS = (
        'سعر', 'الأسعار', 'أسعار', 'تكلفة', 'تكاليف', 'عرض سعر',
        'تسعيرة', 'باقات', 'الباقات', 'رسوم', 'رسوم تأسيس',
    )
    normalized = question.lower()
    return bool(PRICING_INTENT_EN_PATTERN.search(normalized)) or any(
        term in question for term in PRICING_INTENT_AR_TERMS
    )

def split_pricing_and_non_pricing(question: str):
    if not looks_like_pricing_request(question):
        return '', question
        
    pattern = re.compile(
        r'\b(?:and\s+i\s+want|and\s+what\s+about|as\s+well\s+as|and|also|plus|additionally|then)\b'
        r'|بالإضافة\s+إلى|أيضا[ً]?|كمان|وأريد|وهل|ثم|\s+و\s+|(?<=\s)و(?=\S)|(?<=^)و(?=\S)',
        flags=re.IGNORECASE
    )
    
    parts = pattern.split(question)
    pricing = []
    non_pricing = []
    
    for part in parts:
        cleaned = part.strip()
        if not cleaned: continue
        if looks_like_pricing_request(cleaned):
            pricing.append(cleaned)
        else:
            non_pricing.append(cleaned)
            
    return pricing, non_pricing

cases = [
    'اعطيني الاسعار و انواع الخدمات',
    'كم الأسعار وكيف يعمل الـ API؟',
    'أريد عرض سعر وما هي رسائل OTP؟',
    'ما سعر الخدمة وكيف أستخدم المنصة؟',
    'كم تكلفة ACR وما فائدته؟',
    'أريد الأسعار ومعلومات التواصل',
    'كم السعر وما الفرق بين المنصة والـ API؟',
    'What are your prices and what services do you offer?',
    'How much does the API cost and how does it work?',
    'I need a quotation and information about OTP SMS.',
    'What does ACR cost and what does it do?',
    'Give me your prices and contact details.',
    'What is the price and what is the difference between the platform and API?'
]

for c in cases:
    p, np = split_pricing_and_non_pricing(c)
    print(f"Q: {c}\n  P: {p}\n  NP: {np}\n")
