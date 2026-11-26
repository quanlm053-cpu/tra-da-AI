// Launch Gemini in a private session directory using documented user/workspace settings.
// Reuse the original CLI's key store before isolating CLI_HOME. Never serialize credentials.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {loadApiKey} from '../tools/providers/node_modules/@google/gemini-cli/bundle/chunk-4UW3VJTT.js';
try{
 const key=process.env.GEMINI_API_KEY||await loadApiKey();
 const home=process.env.TRADA_GEMINI_HOME,work=process.env.TRADA_GEMINI_WORK,target=process.env.TRADA_GEMINI_TARGET;
 if(!key)throw Error('missing_key');
 if(!home||!work||!target)throw Error('missing_session');
 const env={...process.env,GEMINI_CLI_HOME:home,GEMINI_API_KEY:key};
 delete env.TRADA_GEMINI_HOME;delete env.TRADA_GEMINI_WORK;delete env.TRADA_GEMINI_TARGET;
 delete env.PSModulePath;
 const entry=fileURLToPath(new URL('../tools/providers/node_modules/@google/gemini-cli/bundle/gemini.js',import.meta.url));
 const child=spawn(process.execPath,[entry,...process.argv.slice(2)],{cwd:work,env,stdio:['pipe','inherit','inherit'],windowsHide:true});
 child.on('error',()=>{process.stderr.write('Gemini CLI could not start.\n');process.exitCode=1});
 for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>child.kill(signal));
 let prompt='';for await(const part of process.stdin)prompt+=part;
 child.stdin.on('error',()=>{});
 child.stdin.end('TASK WORKSPACE: '+target+'\nThe process working directory is an isolated control directory. Read and write task files in TASK WORKSPACE only, using absolute file paths. Artifact names in the final response must be relative to TASK WORKSPACE. Never edit the control directory or its .gemini settings.\n'+prompt);
 const code=await new Promise(resolve=>child.on('close',resolve));
 process.exitCode=code??1;
}catch{
 process.stderr.write('Gemini runtime needs a saved API key and a valid isolated session.\n');
 process.exitCode=1;
}
