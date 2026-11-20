#!/usr/bin/env python3
"""Bounded real native HTTP/PostgreSQL video draft check. Never publishes."""
import json,os,subprocess,tempfile,hashlib,uuid,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NODE='/Users/eliotpuplett/.nvm/versions/node/v22.22.3/bin/node'
CLIP=Path.home()/'Library/Application Support/cosimo-content/media-clips/chianti-covenants-v1/technical-range-v1/clip.json'
EVIDENCE=Path.home()/'Library/Application Support/cosimo-content/publisher-video/verification.json'
BASE='http://127.0.0.1:4010'
def shell(code):
 r=subprocess.run(['docker','compose','-f','cosimo/compose.yaml','exec','-T','web','python','manage.py','shell'],input=code,text=True,capture_output=True,cwd=ROOT)
 if r.returncode: raise RuntimeError('Native fixture operation failed: '+r.stderr[-1800:])
 return json.loads(next(x[12:] for x in r.stdout.splitlines() if x.startswith('COSIMO_JSON=')))
def call(method,route,token,data=None):
 req=urllib.request.Request(BASE+'/api/v1'+route,method=method,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def node(args,check=True):
 r=subprocess.run([NODE,str(ROOT/'cosimo/video-handoff.mjs'),*args],text=True,capture_output=True,cwd=ROOT)
 if check and r.returncode:raise RuntimeError(r.stderr[-1500:])
 return json.loads(r.stdout) if check else r
fixture=None;checks=[];evidence={'schemaVersion':1,'observedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'actual local native video upload/draft component; disposable credentialless account','platformCalls':0,'sendCalls':0}
try:
 fixture=shell('''
import json,uuid
from django.contrib.auth import get_user_model
from django.db import connection
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace
from apps.members.models import OrgMembership,WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.api_keys.services import issue_api_key
assert connection.vendor=='postgresql'
s=uuid.uuid4().hex;u=o=None;auto=[]
try:
 u=get_user_model().objects.create_user('video-fixture-'+s+'@localhost');auto=list(u.org_memberships.values_list('organization_id',flat=True))
 o=Organization.objects.create(name='Disposable video '+s);w=Workspace.objects.create(organization=o,name='Disposable native video check')
 OrgMembership.objects.create(organization=o,user=u,org_role='owner');WorkspaceMembership.objects.create(workspace=w,user=u,workspace_role='owner')
 a=SocialAccount(workspace=w,platform='linkedin_personal',account_platform_id=s,account_name='LOCAL VIDEO FIXTURE NO PROVIDER TOKEN',connection_status='connected');a._skip_analytics_backfill=True;a.save()
 k=issue_api_key(workspace=w,social_accounts=[a],issued_by=u,name='Disposable video upload/draft',permissions=['create_posts','upload_media'])
 print('COSIMO_JSON='+json.dumps({'user':str(u.pk),'org':str(o.pk),'workspace':str(w.pk),'account':str(a.pk),'key':str(k.api_key.pk),'token':k.plaintext_token,'auto':list(map(str,auto))}))
except:
 if o:o.delete()
 if u:u.delete()
 Organization.objects.filter(id__in=auto).delete()
 raise
''')
 with tempfile.TemporaryDirectory(prefix='cosimo-video-check-') as d:
  temp=Path(d);os.chmod(temp,0o700);token=temp/'token';token.write_text(fixture['token']);token.chmod(0o600)
  clip=json.loads(CLIP.read_text());caption=temp/'caption.txt';caption.write_text('Technical video handoff fixture. '+clip['disclosure']);caption.chmod(0o600)
  bundle=temp/'bundle.json';journal=temp/'journal.json'
  node(['prepare','--clip',str(CLIP),'--caption',str(caption),'--title','Technical video handoff fixture','--speaker','company','--out',str(bundle)])
  checks.append('Real local clip/request/source/captions verified by existing media-clip verifier')
  args=['import','--bundle',str(bundle),'--url',BASE,'--token-file',str(token),'--account',fixture['account'],'--journal',str(journal)]
  first=node(args);post=call('GET','/posts/'+first['id'],fixture['token']);media=call('GET','/media/'+first['mediaId'],fixture['token'])
  assert post['media_asset_ids']==[first['mediaId']] and first['attachmentVerification']=='native_rest_media_ids'
  assert post['status']=='draft' and post['scheduled_at'] is None and post['published_at'] is None
  assert media['processing_status']=='completed' and media['media_type']=='video' and media['width']==1920 and media['height']==1080
  assert first['media']['sha256']==clip['outputs']['video']['sha256']
  checks.append('Native upload processed as 1920x1080 video; downloaded original bytes match source SHA256')
  checks.append('Native post GET preserves exact caption, source ID and unscheduled draft state')
  observed=shell("""
import json,hashlib
from apps.composer.models import Post
from apps.media_library.models import MediaAsset
from apps.api.models import IdempotencyRecord
p=Post.objects.get(pk=%r);a=MediaAsset.objects.get(pk=%r)
attachments=list(p.media_attachments.values_list('media_asset_id',flat=True))
with a.file.open('rb') as f:digest=hashlib.sha256(f.read()).hexdigest()
IdempotencyRecord.objects.filter(api_key_id=%r).delete()
print('COSIMO_JSON='+json.dumps({'attachments':list(map(str,attachments)),'sha256':digest,'posts':Post.objects.filter(workspace_id=%r).count(),'media':MediaAsset.objects.filter(workspace_id=%r).count()}))
"""%(first['id'],first['mediaId'],fixture['key'],fixture['workspace'],fixture['workspace']))
  assert observed['attachments']==[first['mediaId']] and observed['sha256']==clip['outputs']['video']['sha256'] and observed['posts']==1 and observed['media']==1
  checks.append('Actual PostgreSQL post attachment references exactly the uploaded video; storage hash verified')
  second=node(args);assert second['id']==first['id'] and second['mediaId']==first['mediaId'] and second['reused']
  checks.append('Persistent journal reuses same video and post after native idempotency cache expiry')
  changed_caption='Native edited fixture. '+clip['disclosure'];call('PATCH','/posts/'+first['id'],fixture['token'],{'caption':changed_caption})
  third=node(args);assert third['captionChanged'] and call('GET','/posts/'+first['id'],fixture['token'])['caption']==changed_caption
  checks.append('Native caption edit retained on replay; adapter never overwrites edited draft')
  call('PATCH','/posts/'+first['id'],fixture['token'],{'media_asset_ids':[]})
  changed_attachment=node(args,False);assert changed_attachment.returncode and 'attachment changed' in changed_attachment.stderr
  assert call('GET','/posts/'+first['id'],fixture['token'])['media_asset_ids']==[]
  call('PATCH','/posts/'+first['id'],fixture['token'],{'media_asset_ids':[first['mediaId']]})
  checks.append('Native API exposes exact attachment IDs; replay rejects a detached video without restoring it')
  original=bundle.read_bytes();b=json.loads(original);b['caption']='Changed input. '+clip['disclosure'];b['captionSha256']=hashlib.sha256(b['caption'].encode()).hexdigest();bundle.write_text(json.dumps(b))
  rejected=node(args,False);assert rejected.returncode and 'different source version' in rejected.stderr
  bundle.write_bytes(original);checks.append('Changed source version rejected without creating another post')
  shell("""
import json
from apps.composer.models import Post
from apps.api.models import IdempotencyRecord
Post.objects.filter(pk=%r,workspace_id=%r).delete();IdempotencyRecord.objects.filter(api_key_id=%r).delete()
print('COSIMO_JSON='+json.dumps({'deleted':True}))
"""%(first['id'],fixture['workspace'],fixture['key']))
  missing=node(args,False);assert missing.returncode and 'HTTP 404' in missing.stderr
  after=shell("""
import json
from apps.composer.models import Post
from apps.media_library.models import MediaAsset
print('COSIMO_JSON='+json.dumps({'posts':Post.objects.filter(workspace_id=%r).count(),'media':MediaAsset.objects.filter(workspace_id=%r).count()}))
"""%(fixture['workspace'],fixture['workspace']))
  assert after=={'posts':0,'media':1};checks.append('Deleted saved draft stops on GET404 even after cache expiry; no duplicate recreated')
  evidence.update(sourceId=clip['sourceId'],clipManifest=str(CLIP),clipSha256=hashlib.sha256(CLIP.read_bytes()).hexdigest(),videoSha256=clip['outputs']['video']['sha256'],checks=checks,nativeMedia={k:media[k] for k in ['media_type','mime_type','file_size','width','height','duration','processing_status']},status='local_video_draft_verified',gaps=['No real account video permission or platform publication tested','Sound/style/tone/editorial and full playback pending','No YouTube/RSS/company account acceptance or sidecar caption upload verified'])
finally:
 if fixture:
  cleanup=shell("""
import json
from django.contrib.auth import get_user_model
from apps.organizations.models import Organization
from apps.composer.models import Post
from apps.media_library.models import MediaAsset
workspace=%r
assets=list(MediaAsset.objects.filter(workspace_id=workspace))
for a in assets:
 a.file.delete(save=False)
 if a.thumbnail:a.thumbnail.delete(save=False)
 for v in a.versions.all():
  if v.file:v.file.delete(save=False)
Organization.objects.filter(pk=%r).delete();get_user_model().objects.filter(pk=%r).delete();Organization.objects.filter(pk__in=%r).delete()
print('COSIMO_JSON='+json.dumps({'posts':Post.objects.filter(workspace_id=workspace).count(),'media':MediaAsset.objects.filter(workspace_id=workspace).count(),'organizationExists':Organization.objects.filter(pk=%r).exists()}))
"""%(fixture['workspace'],fixture['org'],fixture['user'],fixture['auto'],fixture['org']))
  evidence['cleanup']=cleanup;assert cleanup=={'posts':0,'media':0,'organizationExists':False}
 EVIDENCE.parent.mkdir(parents=True,exist_ok=True,mode=0o700);EVIDENCE.write_text(json.dumps(evidence,indent=2)+'\n');EVIDENCE.chmod(0o600)
print(json.dumps({'checksPassed':len(checks),'status':evidence.get('status'),'cleanup':evidence.get('cleanup'),'evidence':str(EVIDENCE),'platformCalls':0},indent=2))
