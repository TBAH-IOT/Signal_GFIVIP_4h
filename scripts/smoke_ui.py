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

def assert_axis(page,expected):
    curve=expected['equity_curve']
    page.wait_for_function("document.querySelector('.equity-svg')?.dataset.startMs === "+json.dumps(str(curve[0]['time_ms'])))
    chart=page.locator('.equity-svg')
    assert int(chart.get_attribute('data-end-ms'))==curve[-1]['time_ms']
    assert page.locator('.time-tick').count()>=3
    assert page.locator('.equity-time-label').count()>=3
    assert '01/01/2026' in page.locator('.equity-time-label').first.text_content()
    # Monthly ticks must be spaced by timestamp, and labels must not collide.
    layout=page.evaluate('''() => {
        const svg=document.querySelector('.equity-svg');
        const start=Number(svg.dataset.axisStartMs),dataStart=Number(svg.dataset.startMs),end=Number(svg.dataset.endMs);
        const ticks=[...svg.querySelectorAll('.time-tick')].map(g=>({time:Number(g.dataset.timeMs),x:Number(g.querySelector('circle').getAttribute('cx'))}));
        const labels=[...svg.querySelectorAll('.equity-time-label')].map(t=>{const b=t.getBoundingClientRect();return {text:t.textContent,left:b.left,right:b.right};});
        const pathStartX=Number(svg.querySelector('.equity-path').getAttribute('d').match(/^M([0-9.]+),/)[1]);
        return {start,dataStart,end,ticks,labels,pathStartX};
    }''')
    first,last=layout['ticks'][0],layout['ticks'][-1]
    assert layout['dataStart']==curve[0]['time_ms']
    data_fraction=(layout['dataStart']-layout['start'])/(layout['end']-layout['start'])
    assert abs(layout['pathStartX']-(first['x']+data_fraction*(last['x']-first['x'])))<.01
    assert layout['pathStartX']>first['x']  # no invented curve/flat equity before actual data
    for tick in layout['ticks']:
        fraction=(tick['time']-layout['start'])/(layout['end']-layout['start'])
        assert abs(tick['x']-(first['x']+fraction*(last['x']-first['x'])))<.01
    for a,b in zip(layout['labels'],layout['labels'][1:]):
        assert a['right']+5<=b['left'],(a,b)
    return [r['text'] for r in layout['labels']]

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
    assert page.locator('#sharpe-note').inner_text()=='Theo ngày UTC'
    assert page.locator('#scope option').count()==2
    assert page.locator('#scope').input_value()=='strategy'
    page.wait_for_function("!document.querySelector('#scope option[value=coin]').disabled")
    default_coin=page.locator('.signal-card.selected .card-head strong').inner_text()
    assert page.locator('#scope option[value="coin"]').inner_text()=='Coin đang xem · '+default_coin
    assert page.locator('#scope option[value="strategy"]').inner_text()=='Tổng thể'
    assert page.locator('#detail-title').inner_text()=='Signal_GFIVIP_4h · Tổng thể'
    desktop_ticks=assert_axis(page,expected)
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
    page.wait_for_function("document.getElementById('detail-title').textContent === 'Signal_GFIVIP_4h · Tổng thể'")
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
        page.wait_for_function("Math.abs(document.querySelector('.equity-svg').viewBox.baseVal.width-document.getElementById('equity-chart').clientWidth)<2")
        mobile_ticks=assert_axis(page,expected if scope=='strategy' else next_own)
        page.locator('#detail').scroll_into_view_if_needed()
        page.screenshot(path=out/('ui_mobile_'+name+'.png'),full_page=True)
        page.locator('.equity-panel').screenshot(path=out/('ui_axis_mobile_'+name+'.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert page.locator('#scope').is_visible()
    assert not errors,errors
    result=dict(cards=5,notification_limit=5,bell_opens=True,click_opens_coin_stats=True,
        displayed_metrics=5,net_winrate_hidden=True,universe_fixed_at=20,
        report_options=['strategy','coin'],default_report='strategy',
        initial_coin=default_coin,last_clicked_coin=next_coin,
        default_coin_option_named=True,overall_label='Tổng thể',
        desktop_time_ticks=desktop_ticks,mobile_time_ticks=mobile_ticks,
        time_labels_no_overlap=True,time_axis_matches_real_timestamps=True,
        refresh_preserves_coin=True,switching_reports_matches_real_api=True,
        continuous_n=expected['n_trades'],net_profit=expected['net_profit'],max_dd=expected['max_drawdown'],
        signal_name='Signal_GFIVIP_4h',continuous_period_shown=True,mobile_no_overflow=True,
        javascript_errors=errors,renderer='installed Chrome via Playwright; real Binance snapshot/API')
    (out/'ui_smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    browser.close()
