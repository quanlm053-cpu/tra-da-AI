// Gemini CLI 0.71.1 credential bridge. API keys never leave the Node process.
try {
 if(process.argv[2]==='models'||process.argv[2]==='probe'){
  const {run}=await import('./gemini-models.mjs');
  let input='';for await(const part of process.stdin)input+=part;
  const payload=input?JSON.parse(input):{};
  process.stdout.write(JSON.stringify(await run(process.argv[2],payload.model)));
 }else{
  const {loadApiKey}=await import('../tools/providers/node_modules/@google/gemini-cli/bundle/chunk-4UW3VJTT.js');
  process.stdout.write(JSON.stringify({configured:Boolean(await loadApiKey())}));
 }
}catch{
 process.stdout.write(JSON.stringify({configured:false,ok:false,error:'Không đọc được cấu hình Gemini CLI.',code:'credential_store_unavailable'}));
 process.exitCode=1;
}
