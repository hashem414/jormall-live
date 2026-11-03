chrome.tabs?.query?.({active:true,currentWindow:true}, tabs => {
  const status=document.getElementById('status');
  const url=tabs?.[0]?.url || '';
  if (/^https?:\/\/sma\//i.test(url)) { status.textContent='Bridge active on this SMA tab.'; status.className='ok'; }
  else { status.textContent='Open an SMA page to activate the assistant.'; status.className='warn'; }
});