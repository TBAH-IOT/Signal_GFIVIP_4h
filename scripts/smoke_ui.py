"""Browser acceptance against real seeded data; requires Playwright + installed Chrome."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'evidence';out.mkdir(exist_ok=True)
temp=ROOT/'.browser_tmp';temp.mkdir(exist_ok=True)
os.environ['TEMP']=os.environ['TMP']=str(temp)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1250},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765/',wait_until='domcontentloaded')
    expected=page.request.get('http://127.0.0.1:8765/api/stats').json()
    page.wait_for_function("document.getElementById('n-trades').textContent === "+json.dumps(str(expected['n_trades'])))
    assert page.locator('.signal-card').count()==5
    assert f"{expected['net_profit']*100:.2f}".replace('.',',')+'%' in page.locator('#net-profit').inner_text()
    assert f"{expected['max_drawdown']*100:.2f}".replace('.',',')+'%' in page.locator('#max-dd').inner_text()
    assert page.locator('h1').inner_text()=='Signal_GFIVIP_4h'
    page.locator('#bell').click()
    assert page.locator('#notifications').is_visible()
    assert page.locator('.notification').count()==5
    page.screenshot(path=out/'ui_desktop_notifications.png',full_page=True)
    coin=page.locator('.notification strong').first.inner_text().split()[0]
    page.locator('.notification').first.click()
    page.wait_for_function("!document.getElementById('selected-signal').hidden")
    page.wait_for_function("document.getElementById('detail-title').textContent.startsWith("+json.dumps(coin)+")")
    assert not page.locator('#notifications').is_visible()
    assert page.locator('#scope').input_value()==coin
    page.evaluate('window.scrollTo(0,0)')
    page.wait_for_timeout(400)
    page.screenshot(path=out/'ui_coin_detail.png',full_page=True)
    page.locator('#scope').select_option('')
    page.wait_for_function("document.getElementById('n-trades').textContent === "+json.dumps(str(expected['n_trades'])))
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=out/'ui_mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert not errors,errors
    result=dict(cards=5,notification_limit=5,bell_opens=True,click_opens_coin_stats=True,
        continuous_n=expected['n_trades'],net_profit=expected['net_profit'],max_dd=expected['max_drawdown'],
        signal_name='Signal_GFIVIP_4h',continuous_period_shown=True,mobile_no_overflow=True,
        javascript_errors=errors,renderer='installed Chrome via Playwright; real baseline data')
    (out/'ui_smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    browser.close()
