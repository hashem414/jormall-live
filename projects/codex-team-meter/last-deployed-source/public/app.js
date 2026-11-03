'use strict';
const $=id=>document.getElementById(id);
let role='member',snapshot=null,profile=null,refreshing=false;
const n=v=>new Intl.NumberFormat('en-US').format(v??0);
const percent=v=>v===null?'—':new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(v)+'%';
function text(tag,value,cls){const el=document.createElement(tag);el.textContent=value;if(cls)el.className=cls;return el;}
function relative(value){if(!value)return 'لم تصل بيانات';const m=Math.max(0,Math.floor((Date.now()-Date.parse(value))/60000));if(m<1)return 'الآن';if(m<60)return `قبل ${m} دقيقة`;if(m<1440)return `قبل ${Math.floor(m/60)} ساعة`;return `قبل ${Math.floor(m/1440)} يوم`;}
const date=v=>v?new Date(v).toLocaleString('ar-JO',{timeZone:'Asia/Amman',dateStyle:'short',timeStyle:'short'}):'غير متاح';
async function api(path,options={}){const r=await fetch(path,{credentials:'same-origin',cache:'no-store',...options,headers:{'Content-Type':'application/json','X-CTM-Request':'1',...options.headers}});const b=await r.json();if(!r.ok){if(r.status===401&&path!='/api/login')showLogin();throw new Error(r.status===401?'مفتاح الدخول غير صحيح أو انتهت الجلسة.':r.status===429?'محاولات كثيرة؛ جرّب بعد دقيقة.':`تعذر الطلب (${r.status}).`);}return b;}
function showLogin(){$('app').hidden=true;$('login').hidden=false;$('logout').hidden=true;}
function download(name,data,type){const url=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function progress(value){const p=document.createElement('progress');p.max=100;p.value=value??0;p.setAttribute('aria-label',percent(value));return p;}
function renderMembers(data){
  $('members').replaceChildren();
  for(const m of data.members){
    const row=document.createElement('tr');const cell=document.createElement('td');const name=text('div','','name-cell');name.append(text('span',m.name.slice(0,1),'avatar'));const info=text('div','','name-info');info.append(text('b',m.name),text('small',m.active?(m.connected?'المرسل متصل':'المرسل غير متصل'):'مفتاح موقوف',m.connected&&m.active?'connected':''));name.append(info);cell.append(name);row.append(cell);
    const share=document.createElement('td'),top=text('div','','share-top');top.append(text('b',percent(m.share_percent)),text('small','من المرصود'));share.append(top,progress(m.share_percent));row.append(share);
    for(const value of [m.total_tokens,m.input_tokens,m.cached_input_tokens,m.output_tokens])row.append(text('td',n(value)));
    const seen=text('td',relative(m.last_seen));seen.title=date(m.last_seen);row.append(seen);
    if(role==='admin'){const manage=document.createElement('td');if(m.active){const button=text('button','إيقاف المفتاح','revoke');button.addEventListener('click',async()=>{if(!confirm(`إيقاف مفتاح ${m.name}؟ تبقى أرقامه السابقة.`))return;try{await api('/api/members/revoke',{method:'POST',body:JSON.stringify({id:m.id})});await refresh();}catch(e){alert(e.message);}});manage.append(button);}else manage.textContent='موقوف';row.append(manage);}
    $('members').append(row);
  }
  $('empty').hidden=data.total_tokens!==0;
}
function renderLimits(data){
  const root=$('limits');root.replaceChildren();
  if(!data.limits.length){root.append(text('p','لم يرسل Codex لقطة حدود بعد. غير متاح لا يعني صفرًا.','empty'));return;}
  for(const l of data.limits){const box=text('div','','limit-box'),head=text('div','','limit-title');head.append(text('span',`رصد جهاز ${l.name}`),text('code',l.limit_id));box.append(head,text('small',`تاريخ اللقطة: ${date(l.observed_at)} · ${relative(l.observed_at)}`));
    for(const [name,w] of [['النافذة الأساسية',l.primary],['النافذة الثانوية',l.secondary]]){
      if(!w)continue;
      const expired=w.resets_at!==null&&w.resets_at*1000<=Date.now();const old=Date.now()-Date.parse(l.observed_at)>15*60000;
      const line=text('div','','limit-window'),label=text('p','');label.append(text('span',`${name}${w.window_minutes?' · '+n(w.window_minutes)+' دقيقة':''}`),text('strong',percent(w.used_percent)+' مستخدم'));
      line.append(label,progress(w.used_percent),text('small',`${expired?'انتهى موعد النافذة؛ هذه لقطة قديمة وليست النسبة الحالية.':old?'اللقطة قديمة؛ حد الحساب الحالي غير مؤكد.':'آخر قيمة مرصودة، وليست نسبة هذا العضو.'} موعد التجدد المبلّغ: ${date(w.resets_at?w.resets_at*1000:null)}`));box.append(line);
    }
    root.append(box);
  }
}
async function refresh(){if(refreshing)return;refreshing=true;try{
  const data=await api('/api/summary?hours='+$('period').value);snapshot=data;
  $('total').textContent=n(data.total_tokens);$('member-count').textContent=n(data.members.filter(m=>m.active).length);$('online').textContent=n(data.members.filter(m=>m.active&&m.connected).length);
  const leader=data.members.find(m=>m.total_tokens>0);$('leader').textContent=leader?.name??'لا بيانات بعد';$('leader-share').textContent=leader?`${percent(leader.share_percent)} من التوكنز المرصودة`:'بانتظار أول استخدام';
  $('connection').textContent=`● متصل باللوحة · تحديث ${date(data.generated_at)} بتوقيت عمّان · نافذة متحركة، وليست نافذة إعادة ضبط الاشتراك`;
  const issues=data.members.reduce((s,m)=>s+m.issues,0),pending=data.members.reduce((s,m)=>s+m.pending,0);
  $('issues').textContent=issues?`${n(issues)} حالة تجاوزها المرسل أو احتاجت إعادة تأسيس عدّاد؛ قد يكون القياس ناقصًا. آخر طابور مُبلّغ: ${n(pending)} حدث.`:`لا توجد مشاكل مُبلّغ عنها من المرسلين. آخر طابور مُبلّغ: ${n(pending)} حدث. هذا لا يثبت تغطية الاستخدام كله.`;
  renderMembers(data);renderLimits(data);
}catch(e){$('connection').textContent='انقطع الاتصال باللوحة. الأرقام المعروضة قديمة. '+e.message;}finally{refreshing=false;}}
async function enter(){const me=await api('/api/me');role=me.role;$('login').hidden=true;$('app').hidden=false;$('logout').hidden=false;$('admin-panel').hidden=role!=='admin';$('manage-head').hidden=role!=='admin';await refresh();}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();$('login-error').textContent='';try{await api('/api/login',{method:'POST',body:JSON.stringify({credential:$('credential').value.trim()})});$('credential').value='';await enter();}catch(err){$('login-error').textContent=err.message;}});
$('logout').addEventListener('click',async()=>{await api('/api/logout',{method:'POST',body:'{}'}).catch(()=>{});snapshot=null;showLogin();});
$('refresh').addEventListener('click',refresh);$('period').addEventListener('change',refresh);
$('member-form').addEventListener('submit',async e=>{e.preventDefault();$('member-error').textContent='';try{const m=await api('/api/members',{method:'POST',body:JSON.stringify({name:$('member-name').value})});profile={server:m.server,token:m.token,name:m.name};$('profile-title').textContent='ربط '+m.name;$('profile-token').value=m.token;$('profile-dialog').showModal();$('member-name').value='';await refresh();}catch(err){$('member-error').textContent=err.message;}});
$('download-profile').addEventListener('click',()=>{if(profile)download('member-profile.json',JSON.stringify(profile,null,2),'application/json');});
$('close-dialog').addEventListener('click',()=>{$('profile-dialog').close();profile=null;$('profile-token').value='';});
$('profile-dialog').addEventListener('close',()=>{profile=null;$('profile-token').value='';});
$('export').addEventListener('click',()=>{if(!snapshot)return;const cell=v=>{let s=String(v??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};const rows=[['العضو','حصة التوكنز المرصودة % وليست حصة Pro','إجمالي التوكنز','مدخلات','منها كاش','مخرجات','منها تفكير','آخر مزامنة'],...snapshot.members.map(m=>[m.name,m.share_percent===null?'':m.share_percent.toFixed(4),m.total_tokens,m.input_tokens,m.cached_input_tokens,m.output_tokens,m.reasoning_output_tokens,m.last_seen])];download('codex-team-usage.csv','\ufeff'+rows.map(r=>r.map(cell).join(',')).join('\r\n'),'text/csv;charset=utf-8');});
setInterval(()=>{if(!$('app').hidden&&!document.hidden)refresh();},15000);
enter().catch(showLogin);
