"""用本机 Chrome 在真实沙箱 iframe 中验证页面；宿主消息桥使用合成回复库。"""
# ruff: noqa: E501

import argparse
import json
import tempfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

DRIVER = r"""
<script>
(async () => {
  const checks = [];
  const assert = (condition, label) => { if (!condition) throw new Error(label); checks.push(label); };
  async function until(condition) { for (let i = 0; i < 600; i++) { if (condition()) return; await new Promise(r => setTimeout(r, 10)); } throw new Error('等待界面状态超时'); }
  async function settled() { await until(() => !busy); }
  function change(id, value) { $(id).value = value; $(id).dispatchEvent(new Event('change')); }
  try {
    await until(() => state !== null && !busy);
    assert(scope === 'unity', '首次打开 unity 模板库');
    change('scope', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'); await settled();
    assert(snapshot.entries.length > 100, '载入超过一页的回复');
    assert($('entries').children.length === 100, '每页 100 个回复键');
    $('next').click(); assert(page === 2, '回复键分页');
    change('filter', 'modified'); assert(filtered().length > 0 && filtered().length < snapshot.entries.length, '已修改筛选');
    change('filter', 'all'); change('pack', '2'); await settled();
    assert(snapshot.readonly && $('text').disabled && $('save').disabled, 'smp 只读');
    change('pack', '3'); await settled();
    $('query').value = 'strRoll'; $('query').dispatchEvent(new Event('input'));
    $('entries').firstElementChild.click(); $('text').value = '网页实际保存🦊'; $('text').dispatchEvent(new Event('input'));
    assert(!$('save').disabled, '未保存状态可以提交');
    $('save').click(); await settled();
    assert((await request('export', {selection: 3})).data.strRoll === '网页实际保存🦊', '页面保存通过消息桥生效');
    $('reindex').click();
    for (const input of $('numbers').querySelectorAll('input')) input.value = input.dataset.old === '3' ? '5' : '3';
    $('number-submit').click(); await settled();
    assert(selection === 5 && snapshot.entries.find(item=>item.key==='strRoll').value === '网页实际保存🦊', '改序号保留正在使用的回复');
    $('create').click(); await settled(); $('source-pack').value = '2'; $('copy-name').value = '网页新建';
    $('copy-submit').click(); await settled();
    assert(state.replies.some(item => item.name === '网页新建'), '从 smp 新建复制');
    const duplicate = importData('温柔回复', {strRoll:'副本回复'});
    await until(() => $('collision').open); $('collision').querySelector('[data-choice="copy"]').click(); await duplicate;
    assert(state.replies.some(item => item.name === '温柔回复 - 副本1'), '同名导入创建副本');
    $('transfer').click(); await settled(); change('source-scope', 'unity'); await settled();
    $('copy-name').value = '加载共享模板'; $('copy-submit').click(); await settled();
    assert((await request('export', {selection})).data.strRoll === '共享模板回复', 'unity 模板加载到 bot');
    $('settings').click(); $('enabled').checked = false; $('settings-submit').click(); await settled();
    assert(!state.config.enabled && $('config-info').textContent.includes('关'), '全局开关和界面同步');
    $('help').click(); await settled(); assert($('help-content').textContent.includes('1/default'), '独立 Markdown 编写帮助');
    assert($('help-content').scrollTop === 0 && $('help-dialog').scrollTop === 0, '帮助首次打开从顶部显示');
    $('help-content').scrollTop = $('help-content').scrollHeight;
    assert($('help-content').scrollTop > 0 && $('help-close').getBoundingClientRect().top < $('help-content').getBoundingClientRect().top, '滚动帮助后右上角关闭按钮仍可见');
    $('help-close').click(); assert(!$('help-dialog').open, '右上角叉号关闭帮助');
    $('help').click(); await settled();
    assert($('help-content').scrollTop === 0 && $('help-dialog').scrollTop === 0, '帮助再次打开重置到顶部');
    $('help-close').click();
    const large = {}; for (let i=0; i<40; i++) large['strBig'+i] = '中文🦊'.repeat(1500);
    const imported = await request('import', {name:'Unicode 大回复', data:large});
    const exported = await request('export', {selection:imported.selection});
    assert(exported.data.strBig39 === large.strBig39, 'Unicode 大 JSON 双向分片完整');
    selection = 5; await loadState();
    $('query').value = ''; $('query').dispatchEvent(new Event('input')); setActive(snapshot.entries.find(item => item.key==='strRoll')); render();
    window.parent.postMessage({type:'mcs_test_result', ok:true, checks}, '*');
  } catch(error) { window.parent.postMessage({type:'mcs_test_result', ok:false, checks, error:String(error.stack || error)}, '*'); }
})();
</script>
"""

HOST = r"""
const bot='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', limit=192*1024;
let revision=1, uploads={}, downloads={};
const original={strBotName:'Core 自定义骰名',strRoll:'默认掷骰 {tRollResult}'};
for(let i=0;i<110;i++) original['strExample'+String(i).padStart(3,'0')]='示例回复 '+i;
const models={1:{name:'default',data:{...original}},2:{name:'smp',data:{...original,strBotName:'真实骰子'}},
3:{name:'温柔回复',data:{...original,strRoll:'温柔掷骰 {tRollResult}'}},5:{name:'简洁回复',data:{...original,strRoll:'{tRollResult}'}}};
const unity={共享模板:{...original,strRoll:'共享模板回复'}};
const config={reply_model:1,enabled:true};
const trace=[];
function list(scope){return scope==='unity'?Object.keys(unity).map(name=>({selection:name,name,available:true,readonly:false})):
Object.entries(models).map(([id,item])=>({selection:Number(id),name:item.name,available:true,readonly:Number(id)===2}));}
function values(scope,selection){return scope==='unity'?unity[selection]:models[selection].data;}
function snapshot(scope,selection){const data=values(scope,selection);return {revision:String(revision),readonly:scope!=='unity'&&Number(selection)===2,
entries:Object.entries(data).sort().map(([key,value],i)=>({key,value,default:original[key]||null,modified:i%11===0,note:'保留 Core 模板变量；可用 | 分隔随机回复。'}))};}
function api(p){switch(p.op){
case 'accounts':return {version:'1.0.0',accounts:[{hash:'unity',label:'unity 模板库'},{hash:bot,label:'qq · 1001'}]};
case 'state':case 'reload':return {replies:list(p.scope),config:p.scope==='unity'?null:config,groups:{},modules:['OlivaDiceCore','MultiCustomSwitch']};
case 'snapshot':return snapshot(p.scope,p.selection);
case 'edit':values(p.scope,p.selection)[p.key]=p.value;revision++;return snapshot(p.scope,p.selection);
case 'export':return {data:values(p.scope,p.selection)};
case 'reindex':{const next={1:models[1],2:models[2]};for(const [old,id] of Object.entries(p.mapping))next[id]=models[old];for(const id of Object.keys(models))delete models[id];Object.assign(models,next);return {replies:list(bot)};}
case 'create':{const id=Math.max(...Object.keys(models).map(Number))+1;models[id]={name:p.name,data:{...values(p.source_scope,p.source_selection)}};return {selection:id,name:p.name};}
case 'import':{let name=p.name;const found=Object.entries(models).find(([id,v])=>v.name===name);if(found&&!p.conflict)return {conflict:true,name};if(p.conflict==='cancel')return {cancelled:true};
if(found&&p.conflict==='copy')name+=' - 副本1';const id=found&&p.conflict==='overwrite'?Number(found[0]):Math.max(...Object.keys(models).map(Number))+1;
models[id]={name,data:{...p.data}};return {selection:id,name};}
case 'settings':config.enabled=p.enabled;config.reply_model=p.model;return {};
case 'help':return {markdown:HELP};
default:throw new Error('mock API 未实现 '+p.op);}}
function ascii(value){return JSON.stringify(value).replace(/[\u007f-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));}
function transport(p){
if(p.transport==='upload_start'){const token='u'+Math.random();uploads[token]='';return {token};}
if(p.transport==='upload_chunk'){if(uploads[p.token].length!==p.offset)throw new Error('分片顺序错误');uploads[p.token]+=p.text;return {received:uploads[p.token].length};}
if(p.transport==='upload_finish'){const request=JSON.parse(uploads[p.token]);delete uploads[p.token];return transport(request);}
if(p.transport==='download_chunk'){const source=downloads[p.token],text=source.slice(p.offset,p.offset+limit),done=p.offset+text.length>=source.length;if(done)delete downloads[p.token];return {text,done};}
const result=api(p), encoded=ascii(result);if(encoded.length<=limit)return result;const token='d'+Math.random();downloads[token]=encoded;return {download_token:token};}
window.addEventListener('message',event=>{
if(event.source!==document.querySelector('iframe').contentWindow)return;
const m=event.data;if(m.type==='mcs_test_result'){document.getElementById('result').textContent=JSON.stringify(m);return;}
if(m.type!=='olivos:plugin_event')return;
trace.push(m.payload.op||m.payload.transport);document.getElementById('result').dataset.trace=JSON.stringify(trace);
let payload;try{payload={ok:true,result:transport(m.payload)};}catch(error){payload={ok:false,error:String(error)};}
event.source.postMessage({type:'olivos:plugin_reply',request_id:m.request_id,payload},'*');});
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', required=True)
    parser.add_argument('--driver', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plugin = Path(__file__).resolve().parents[1]
    page = (plugin / 'webui' / 'index.html').read_text(encoding='utf-8') + DRIVER
    page_json = json.dumps(page, ensure_ascii=True).replace('<', '\\u003c')
    help_json = json.dumps((plugin / 'writer_help.md').read_text(encoding='utf-8'), ensure_ascii=True).replace(
        '<', '\\u003c'
    )
    wrapper = output / 'webui-smoke.html'
    wrapper.write_text(
        '<!doctype html><meta charset="utf-8"><style>body{margin:0}#result{display:none}iframe{width:100%;height:100vh;border:0}</style>'
        '<output id="result"></output><iframe sandbox="allow-scripts allow-modals allow-downloads"></iframe><script>'
        f'const HELP={help_json};' + HOST + f'document.querySelector("iframe").srcdoc={page_json};</script>',
        encoding='utf-8',
    )
    with tempfile.TemporaryDirectory(prefix='mcs-browser-') as profile:
        options = webdriver.ChromeOptions()
        options.binary_location = args.browser
        options.ignore_local_proxy_environment_variables()
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        for argument in [
            '--headless=new',
            '--disable-gpu',
            '--disable-extensions',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-background-networking',
            '--disable-component-update',
            f'--user-data-dir={profile}',
            '--window-size=1240,1050',
        ]:
            options.add_argument(argument)
        driver = webdriver.Chrome(service=Service(args.driver), options=options)
        try:
            driver.get(wrapper.as_uri())
            WebDriverWait(driver, 25).until(lambda browser: browser.find_element('id', 'result').get_attribute('textContent'))
            report = json.loads(driver.find_element('id', 'result').get_attribute('textContent'))
        except Exception as exc:
            report = {'ok': False, 'error': str(exc), 'logs': driver.get_log('browser')}
        finally:
            driver.save_screenshot(str(output / 'webui.png'))
            driver.execute_cdp_cmd('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-color-scheme', 'value': 'dark'}]})
            driver.save_screenshot(str(output / 'webui-dark.png'))
            driver.execute_cdp_cmd('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-color-scheme', 'value': 'light'}]})
            driver.set_window_size(440, 1000)
            driver.save_screenshot(str(output / 'webui-mobile.png'))
            source = driver.page_source
            driver.quit()
        (output / 'browser-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
        if not report['ok']:
            (output / 'browser-failure.html').write_text(source, encoding='utf-8')
            raise SystemExit(1)


if __name__ == '__main__':
    main()
