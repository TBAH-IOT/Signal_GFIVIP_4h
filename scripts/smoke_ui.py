"""UI regression for compact cards, exact-trade selection, archive navigation and tabs.

Requires Playwright and installed Chrome. Uses real backend data; no fake fills.
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

def expect_trade(page,sid):
    page.wait_for_function("document.querySelector('.trade-chart')?.dataset.tradeId === "+json.dumps(sid))
    assert page.locator('#tab-trade').get_attribute('aria-selected')=='true'
    assert page.locator('#trade-panel').is_visible()
    assert not page.locator('#performance-panel').is_visible()

def expect_stats(page,expected):
    page.wait_for_function("document.getElementById('n-trades').textContent === "+json.dumps(str(expected['n_trades'])))
    for element,key in [('#gross-wr','gross_winrate'),('#net-profit','net_profit'),('#max-dd','max_drawdown')]:
        assert f"{expected[key]*100:.2f}".replace('.',',')+'%' in page.locator(element).inner_text()
    assert page.locator('#equity-chart .equity-time-label').first.text_content()=='01/05/2026'

with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url+'/',wait_until='domcontentloaded')
    page.wait_for_function("document.querySelectorAll('.signal-card').length===5")
    assert not page.locator('#detail').is_visible()
    assert page.locator('.signal-card.selected').count()==0
    assert page.evaluate("(()=>{const r=[...document.querySelectorAll('.signal-card')].map(x=>x.getBoundingClientRect());return r.every(x=>Math.abs(x.top-r[0].top)<3)})()")
    assert page.locator('.pnl-field').count()==5
    page.screenshot(path=out/'ui_cards_v1_3.png',full_page=True)
    notifications=page.request.get(url+'/api/notifications').json()['items']
    first=notifications[0];second=next(t for t in notifications if t['coin']!=first['coin'])
    page.locator('[data-signal="'+first['id']+'"]').first.click()
    expect_trade(page,first['id'])
    assert page.locator('.ohlc-candle').count()>0
    assert page.locator('.entry-marker').count()==1 and page.locator('.exit-marker').count()==1
    page.locator('#tab-performance').click()
    page.locator('#scope').select_option('strategy')
    expected=page.request.get(url+'/api/stats').json();expect_stats(page,expected)
    assert page.locator('#net-wr').count()==0
    assert page.locator('#sharpe-note').inner_text()=='Theo ngày UTC'
    page.locator('[data-signal="'+second['id']+'"]').first.click()
    expect_trade(page,second['id'])
    detail=page.request.get(url+'/api/trades/'+second['id']).json()
    assert second['coin'] in page.locator('#viewing-coin').inner_text()
    old=detail['navigation']['previous_id'];assert old
    page.locator('#history-prev').click();expect_trade(page,old)
    assert second['coin'] in page.locator('#trade-title').inner_text()
    page.locator('#history-next').click();expect_trade(page,second['id'])
    page.locator('#tab-performance').click()
    page.locator('#scope').select_option('coin')
    own=page.request.get(url+'/api/stats',params={'coin':second['coin']}).json();expect_stats(page,own)
    page.locator('#scope').select_option('strategy');expect_stats(page,expected)
    page.locator('#bell').click();assert page.locator('.notification').count()==5
    page.locator('.notification[data-signal="'+first['id']+'"]').click();expect_trade(page,first['id'])
    page.locator('#detail').screenshot(path=out/'ui_trade_detail_v1_3.png')
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function("Math.abs(document.querySelector('.trade-chart').viewBox.baseVal.width-document.getElementById('candle-chart').clientWidth)<2")
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('#detail').screenshot(path=out/'ui_trade_mobile_v1_3.png')
    page.locator('#tab-performance').click();expect_stats(page,expected)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert not errors,errors
    result=dict(initial_view='cards_only',cards=5,one_horizontal_strip=True,completed_pnl_on_cards=True,
        exact_trade_id_on_card_click=True,notification_click_opens_trade=True,archive_navigation=True,
        real_ohlc=True,entry_exit_markers=True,performance_tabs=True,mobile_no_overflow=True,
        net_winrate_hidden=True,javascript_errors=errors,signal_name='Signal_GFIVIP_4h',version='1.3.0')
    (out/'ui_smoke_v1_3.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));browser.close()
