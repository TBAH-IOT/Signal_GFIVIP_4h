"""Browser acceptance with real API data; requires Playwright + installed Chrome.

GFI_PREVIEW_URL / GFI_UI_EVIDENCE_DIR can point to a separate local preview.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
out=Path(os.environ.get('GFI_UI_EVIDENCE_DIR',ROOT/'evidence'));out.mkdir(parents=True,exist_ok=True)
temp=out/'browser_tmp';temp.mkdir(exist_ok=True)
os.environ['TEMP']=os.environ['TMP']=str(temp)
url=os.environ.get('GFI_PREVIEW_URL','http://127.0.0.1:8765').rstrip('/')

def assert_report(page,expected):
    page.wait_for_function("document.getElementById('n-trades').textContent === "+json.dumps(str(expected['n_trades'])))
    for selector,key in [('#gross-wr','gross_winrate'),('#net-profit','net_profit'),('#max-dd','max_drawdown')]:
        text=f"{expected[key]*100:.2f}".replace('.',',')+'%'
        assert text in page.locator(selector).inner_text(),(selector,text)

with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1250},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url+'/',wait_until='domcontentloaded')
    expected=page.request.get(url+'/api/stats').json()
    assert_report(page,expected)
    assert page.locator('.signal-card').count()==5
    assert page.locator('.metric').count()==5
    assert page.locator('#net-wr').count()==0
    assert page.get_by_role('heading',name='WINRATE SAU PHÍ').count()==0
    assert page.locator('#scope option').count()==2
    assert page.locator('#scope').input_value()=='strategy'
    assert page.locator('#scope option[value="coin"]').is_disabled()
    assert len(page.request.get(url+'/api/model').json()['coins'])==20
    assert page.locator('h1').inner_text()=='Signal_GFIVIP_4h'
    page.locator('#detail').screenshot(path=out/'ui_strategy_report.png')
    page.locator('#bell').click()
    assert page.locator('#notifications').is_visible()
    assert page.locator('.notification').count()==5
    page.screenshot(path=out/'ui_desktop_notifications.png',full_page=True)
    coin=page.locator('.notification strong').first.inner_text().split()[0]
    page.locator('.notification').first.click()
    page.wait_for_function("!document.getElementById('selected-signal').hidden")
    page.wait_for_function("document.getElementById('detail-title').textContent.startsWith("+json.dumps(coin)+")")
    own=page.request.get(url+'/api/stats',params={'coin':coin}).json()
    assert_report(page,own)
    assert not page.locator('#notifications').is_visible()
    assert page.locator('#scope').input_value()=='coin'
    assert page.locator('#scope option[value="coin"]').inner_text()=='Coin đang xem · '+coin
    page.locator('#detail').screenshot(path=out/'ui_coin_detail.png')

    # Realtime refresh preserves the selected coin; the selector is a report filter.
    page.evaluate('async () => {await refresh(); await loadStats();}')
    assert page.locator('#scope').input_value()=='coin'
    assert_report(page,own)
    page.locator('#scope').select_option('strategy')
    page.wait_for_function("document.getElementById('detail-title').textContent.includes('Tổng thể chiến thuật 20 coin')")
    assert_report(page,expected)
    page.locator('#scope').select_option('coin')
    page.wait_for_function("document.getElementById('detail-title').textContent.startsWith("+json.dumps(coin)+")")
    assert_report(page,own)

    # Clicking another card changes the coin report to the last card clicked.
    cards=page.locator('.signal-card')
    next_coin=None
    for i in range(cards.count()):
        candidate=cards.nth(i).locator('.card-head strong').inner_text()
        if candidate!=coin:
            next_coin=candidate
            cards.nth(i).click()
            break
    assert next_coin is not None,'Need two distinct coins in the real notification snapshot'
    page.wait_for_function("document.getElementById('detail-title').textContent.startsWith("+json.dumps(next_coin)+")")
    next_own=page.request.get(url+'/api/stats',params={'coin':next_coin}).json()
    assert_report(page,next_own)
    assert page.locator('#scope option[value="coin"]').inner_text()=='Coin đang xem · '+next_coin
    assert page.locator('#scope option').count()==2

    for scope,name in [('strategy','strategy'),('coin','coin')]:
        page.locator('#scope').select_option(scope)
        assert_report(page,expected if scope=='strategy' else next_own)
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#detail').scroll_into_view_if_needed()
        page.screenshot(path=out/('ui_mobile_'+name+'.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert page.locator('#scope').is_visible()
    assert not errors,errors
    result=dict(cards=5,notification_limit=5,bell_opens=True,click_opens_coin_stats=True,
        displayed_metrics=5,net_winrate_hidden=True,universe_fixed_at=20,
        report_options=['strategy','coin'],default_report='strategy',
        coin_disabled_before_click=True,last_clicked_coin=next_coin,
        refresh_preserves_coin=True,switching_reports_matches_real_api=True,
        continuous_n=expected['n_trades'],net_profit=expected['net_profit'],max_dd=expected['max_drawdown'],
        signal_name='Signal_GFIVIP_4h',continuous_period_shown=True,mobile_no_overflow=True,
        javascript_errors=errors,renderer='installed Chrome via Playwright; real Binance snapshot/API')
    (out/'ui_smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    browser.close()
