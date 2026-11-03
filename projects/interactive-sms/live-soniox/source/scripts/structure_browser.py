"""Local browser UI verification using captured live Soniox audio; no paid voice calls."""
import json,struct,sys,time,wave
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.structure_journal import ROOT,record


def main(name):
    row={'browser':name,'physical_device':False,'microphone':'NOT RUN','voice_transport':'Captured live Soniox PCM, browser route fixture; live API verified separately'}
    browser=None
    try:
        with sync_playwright() as p:
            browser=getattr(p,name).launch(headless=True,timeout=15000)
            page=browser.new_page();errors=[];requests=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            mode={'value':'normal'}
            def speech(route):
                data=route.request.post_data_json;requests.append(data)
                assert data['message_id'] and 'text' not in data
                with wave.open(str(ROOT/('soniox-'+data['language']+'.wav')),'rb') as f:pcm=f.readframes(f.getnframes())
                body=b''.join(struct.pack('<I',len(pcm[i:i+8192]))+pcm[i:i+8192] for i in range(0,len(pcm),8192))
                if mode['value']=='normal':body+=b'\0'*4
                route.fulfill(status=200,body=body,headers={'Content-Type':'application/x-jormall-pcm','X-Voice-Provider':'soniox','X-Voice-Model':'tts-rt-v2','X-Voice-Voice':'Kayla','X-Assistant-Message-ID':data['message_id']})
            page.route('**/speak',speech)
            page.goto('http://127.0.0.1:5005/interactive-sms/',wait_until='networkidle',timeout=20000)
            page.locator('#prechat-lead-name').fill('Local Structure Browser')
            page.locator('#prechat-lead-phone').fill('0790000000')
            page.locator('#review-contact-notice').click();page.locator('#notice-dialog-close').click()
            page.locator('#prechat-lead-submit').click()
            page.wait_for_selector('#prechat-lead-overlay',state='hidden',timeout=10000)
            page.locator('.language-button[data-language="en"]').first.click()
            page.locator('#chat-input').fill('Hello');page.locator('#send-button').click()
            play=page.locator('.assistant-speech-play').last;play.wait_for(timeout=15000)
            start=time.monotonic();play.click();page.wait_for_function('activeVoiceSources.size > 0',timeout=10000)
            row['fixture_first_playback_seconds']=time.monotonic()-start
            page.locator('#voice-orb-button').click();page.wait_for_function('activeVoiceSources.size === 0')
            play.click();page.wait_for_function('activeVoiceSources.size > 0')
            assert requests[-1]['message_id']==requests[-2]['message_id']
            page.locator('.language-button[data-language="ar"]').first.click();page.wait_for_function('activeVoiceSources.size === 0')
            assert page.locator('html').get_attribute('lang')=='ar'
            page.locator('#chat-input').fill('مرحبا');page.locator('#send-button').click()
            page.wait_for_function("document.querySelectorAll('.assistant-speech-play').length >= 2")
            page.locator('.assistant-speech-play').last.click();page.wait_for_function('activeVoiceSources.size > 0')
            assert requests[-1]['language']=='ar' and requests[-1]['message_id']!=requests[0]['message_id']
            page.locator('#chat-input').fill('Hello');page.locator('#send-button').click();page.wait_for_function('activeVoiceSources.size === 0')
            page.wait_for_function("document.querySelectorAll('.assistant-speech-play').length >= 3")
            mode['value']='truncated';page.locator('.assistant-speech-play').last.click()
            page.wait_for_timeout(800);page.wait_for_function('activeVoiceSources.size === 0')
            assert page.evaluate('chatbotConfig.voiceBrowserFallbackEnabled') is False
            assert page.locator('#chat-input').is_enabled()
            assert not errors,errors
            row.update(status='PASS',play_stop_replay='PASS',language_change='PASS',new_question_cancellation='PASS',truncated_stream='PASS',console_errors=errors)
            page.screenshot(path=str(ROOT/(name+'.png')))
            browser.close()
    except Exception as error:
        row.update(status='FAIL',error=type(error).__name__+': '+str(error)[:600]);record('browser-'+name,'Play/stop/replay/language/cancellation',row['error'],provider='browser')
    (ROOT/('browser-'+name+'.json')).write_text(json.dumps(row,indent=2));print(json.dumps(row));return 0 if row['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
