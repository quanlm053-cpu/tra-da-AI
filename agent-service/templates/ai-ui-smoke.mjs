// UI render smoke only. SQL Server acceptance tests remain QA's responsibility.
import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const url=process.env.AI_PREVIEW_URL||'http://127.0.0.1:3101';
const out='test-results/ai-ui';
await mkdir(out,{recursive:true});
const browser=await chromium.launch();
const errors=[];
try{
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});
  page.on('pageerror',e=>errors.push({viewport:name,message:e.message}));
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  assert.ok(response&&response.status()<400,'Frontend must return a successful response');
  await page.locator('body').waitFor();
  await page.locator('h1').first().waitFor({timeout:20000});
  await page.screenshot({path:`${out}/${name}.png`,fullPage:true});
  const body=await page.locator('body').innerText();
  assert.ok(body.length>100,'Page must contain rendered application content');
  await page.close();
 }
 await writeFile(`${out}/page-errors.json`,JSON.stringify(errors,null,2));
 assert.equal(errors.length,0,'Uncaught browser error; inspect screenshots and page-errors.json');
 console.log('Desktop/mobile UI rendered. This does not certify database acceptance tests.');
}finally{await browser.close()}
