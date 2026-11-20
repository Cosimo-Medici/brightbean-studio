#!/usr/bin/env node
// Native BrightBean draft handoff for verified local clips. No provider calls.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const engine=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../cosimo-content-engine/content-engine');
const {verifyClip}=require(path.join(engine,'lib/media-clip.cjs'));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=f=>JSON.parse(fs.readFileSync(f,'utf8'));
const assert=(c,m)=>{if(!c)throw Error(m);};
const save=(file,v)=>{fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});const temp=`${file}.${process.pid}.tmp`;fs.writeFileSync(temp,JSON.stringify(v,null,2)+'\n',{mode:0o600});fs.renameSync(temp,file);};
export async function prepareVideo(clipFile,{captionFile,title,speaker}) {
  const checked=await verifyClip(clipFile),clip=read(clipFile),caption=fs.readFileSync(captionFile,'utf8');
  assert(title&&speaker&&caption.trim(),'Title, speaker and caption are required');
  assert(caption.includes(clip.disclosure),'Caption must retain the exact fictional/source disclosure');
  assert(clip.outputs.video.media.video.codec==='h264'&&clip.outputs.video.media.audio?.codec==='aac','This adapter currently accepts the verified H.264/AAC clip contract');
  return {schemaVersion:1,sourceId:clip.sourceId,parentSourceId:clip.parentSourceId,parentEpisodeId:clip.parentEpisodeId,
    clipFile:path.resolve(clipFile),clipSha256:hash(fs.readFileSync(clipFile)),video:clip.outputs.video,
    captions:clip.outputs.captions,caption,captionSha256:hash(caption),title,speaker,review:clip.review,
    disclosure:clip.disclosure,technicalVerification:checked,status:'draft_only_unreviewed',
    gaps:[...clip.gaps,'Native draft support does not verify account permission or successful platform publication.']};
}
async function validate(bundle) {
  assert(bundle.schemaVersion===1&&bundle.status==='draft_only_unreviewed','Expected explicit unreviewed draft bundle');
  assert(hash(fs.readFileSync(bundle.clipFile))===bundle.clipSha256,'Clip manifest changed after preparation');
  const clip=read(bundle.clipFile);await verifyClip(bundle.clipFile);
  assert(bundle.sourceId===clip.sourceId&&bundle.parentSourceId===clip.parentSourceId&&bundle.parentEpisodeId===clip.parentEpisodeId,'Clip source identity differs');
  assert(JSON.stringify(bundle.video)===JSON.stringify(clip.outputs.video)&&JSON.stringify(bundle.captions)===JSON.stringify(clip.outputs.captions),'Bundle media differs from clip');
  assert(JSON.stringify(bundle.review)===JSON.stringify(clip.review),'Review status differs from the actual clip');
  assert(hash(bundle.caption)===bundle.captionSha256&&bundle.caption.includes(clip.disclosure)&&bundle.disclosure===clip.disclosure,'Caption hash or required disclosure differs');
  return fs.readFileSync(bundle.video.path);
}
export async function importVideoDraft(bundle,{url,tokenFile,account,journal}) {
  const origin=new URL(url);
  assert(origin.protocol==='http:'&&['127.0.0.1','localhost'].includes(origin.hostname)&&origin.pathname==='/'&&!origin.username&&!origin.password&&!origin.search&&!origin.hash,'This component adapter only supports a local loopback hub origin');
  const bytes=await validate(bundle),token=fs.readFileSync(tokenFile,'utf8').trim();
  assert(token.startsWith('bb_studio_'),'Expected a private BrightBean token file');
  const request=async(route,options={})=>{const res=await fetch(new URL(`/api/v1/${route}`,origin),{...options,redirect:'error',signal:AbortSignal.timeout(60000),headers:{Authorization:`Bearer ${token}`,...options.headers}});assert(res.ok,`Native ${route}: HTTP ${res.status}. Retain the journal and reconcile before retry.`);return res.json();};
  fs.mkdirSync(path.dirname(journal),{recursive:true,mode:0o700});
  const lock=`${journal}.lock`,fd=fs.openSync(lock,'wx',0o600);fs.writeFileSync(fd,String(process.pid));
  try {
    const state=fs.existsSync(journal)?read(journal):{schemaVersion:1,kind:'video-drafts',origin:origin.origin,account,posts:{}};
    assert(state.kind==='video-drafts'&&state.origin===origin.origin&&state.account===account,'Journal belongs to another adapter/hub/account');
    const me=await request('me/');
    assert(me.permissions.includes('create_posts')&&me.permissions.includes('upload_media')&&!me.permissions.includes('publish_directly'),'Use a draft/upload-only key without publish_directly');
    const target=me.allowlisted_accounts.find(a=>a.id===account);
    assert(target&&['linkedin_personal','linkedin_company'].includes(target.platform),'Only explicitly allowlisted native LinkedIn draft accounts are supported');
    const weight=[...bundle.caption].length+[...bundle.caption].filter(c=>target.escaped_chars.includes(c)).length;
    assert(weight<=target.char_limit,'Caption exceeds the native account character budget');
    const fingerprint=hash(JSON.stringify(bundle));let entry=state.posts[bundle.sourceId];
    if(entry)assert(entry.fingerprint===fingerprint,'A different source version already owns this ID; edit the existing draft instead of duplicating it');
    if(entry?.postId){
      const actual=await request(`posts/${entry.postId}`),notes=JSON.parse(actual.internal_notes||'{}');
      assert(notes.sourceId===bundle.sourceId&&notes.videoSha256===bundle.video.sha256,'Saved post source identity no longer matches');
      assert(Array.isArray(actual.media_asset_ids)&&actual.media_asset_ids.length===1&&actual.media_asset_ids[0]===entry.mediaId,'Native video attachment changed; reconcile the existing draft');
      return {sourceId:bundle.sourceId,id:actual.id,mediaId:entry.mediaId,status:actual.status,reused:true,captionChanged:actual.caption!==bundle.caption,publication:'not_requested',attachmentVerification:'native_rest_media_ids'};
    }
    entry??=state.posts[bundle.sourceId]={fingerprint,startedAt:Date.now(),status:'pending'};
    const tokenHash=hash(token);assert(!entry.tokenHash||entry.tokenHash===tokenHash,'Unresolved operation used another key; reconcile before credential changes');entry.tokenHash=tokenHash;
    assert(Date.now()-entry.startedAt<23*3600000,'Unresolved operation exceeded the native replay window; reconcile instead of recreating');save(journal,state);
    const key=`cosimo-video-${hash(`${account}:${bundle.sourceId}`)}`;
    if(!entry.mediaId){const form=new FormData();form.set('file',new Blob([bytes],{type:'video/mp4'}),`${bundle.video.sha256}.mp4`);form.set('title',bundle.title);form.set('alt_text',bundle.disclosure);form.set('idempotency_key',`${key}-media`);const media=await request('media/',{method:'POST',body:form});entry.mediaId=media.id;save(journal,state);}
    let media;
    for(let attempt=0;attempt<30;attempt++){media=await request(`media/${entry.mediaId}`);if(['completed','failed'].includes(media.processing_status))break;await new Promise(r=>setTimeout(r,1000));}
    assert(media.processing_status==='completed','Native video processing did not complete. Media ID retained for reconciliation.');
    assert(media.media_type==='video'&&media.file_size===bytes.length&&media.width===bundle.video.media.video.width&&media.height===bundle.video.media.video.height&&Math.abs(media.duration-bundle.video.media.duration)<0.1,'Native video metadata differs from verified local media');
    const fileUrl=new URL(media.url,origin);assert(fileUrl.origin===origin.origin,'Remote media storage byte verification is unimplemented; stop before draft creation');
    const response=await fetch(fileUrl,{redirect:'error',signal:AbortSignal.timeout(60000)});assert(response.ok,'Cannot read uploaded local media bytes');
    assert(hash(Buffer.from(await response.arrayBuffer()))===bundle.video.sha256,'Uploaded native media bytes differ');
    entry.mediaVerified={at:new Date().toISOString(),sha256:bundle.video.sha256,processingStatus:media.processing_status,width:media.width,height:media.height,duration:media.duration};save(journal,state);
    const notes={sourceId:bundle.sourceId,parentSourceId:bundle.parentSourceId,parentEpisodeId:bundle.parentEpisodeId,speaker:bundle.speaker,clipSha256:bundle.clipSha256,videoSha256:bundle.video.sha256,captionSha256:bundle.captionSha256,review:bundle.review,disclosure:bundle.disclosure,captions:bundle.captions,publication:'not_requested'};
    const created=await request('posts/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({social_account_id:account,title:bundle.title,caption:bundle.caption,media_asset_ids:[entry.mediaId],internal_notes:JSON.stringify(notes),action:'draft',idempotency_key:key})});entry.postId=created.id;save(journal,state);
    const actual=await request(`posts/${created.id}`);
    assert(actual.status==='draft'&&actual.caption===bundle.caption&&!actual.scheduled_at&&!actual.published_at&&JSON.parse(actual.internal_notes).sourceId===bundle.sourceId,'Actual native draft does not match the requested handoff');
    assert(Array.isArray(actual.media_asset_ids)&&actual.media_asset_ids.length===1&&actual.media_asset_ids[0]===entry.mediaId,'Native draft attachment differs from verified video');
    entry.status='draft_verified';save(journal,state);
    return {sourceId:bundle.sourceId,id:actual.id,mediaId:entry.mediaId,status:actual.status,reused:false,media:entry.mediaVerified,publication:'not_requested',attachmentVerification:'native_rest_media_ids'};
  } finally {fs.closeSync(fd);fs.unlinkSync(lock);}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
 try{const [cmd,...args]=process.argv.slice(2),opts={};for(let i=0;i<args.length;i+=2){assert(args[i].startsWith('--')&&args[i+1],'Expected named options');opts[args[i].slice(2)]=args[i+1];}
  if(cmd==='prepare'){const b=await prepareVideo(opts.clip,{captionFile:opts.caption,title:opts.title,speaker:opts.speaker});save(opts.out,b);console.log(JSON.stringify({status:b.status,sourceId:b.sourceId,out:opts.out}));}
  else if(cmd==='import')console.log(JSON.stringify(await importVideoDraft(read(opts.bundle),{url:opts.url,tokenFile:opts['token-file'],account:opts.account,journal:opts.journal}),null,2));
  else throw Error('Use prepare --clip FILE --caption FILE --title TEXT --speaker NAME --out FILE or import --bundle FILE --url LOOPBACK --token-file FILE --account UUID --journal FILE');
 }catch(e){console.error(e.message);process.exitCode=1;}
}
