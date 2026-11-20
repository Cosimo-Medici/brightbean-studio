"""Real local HTTP/PostgreSQL component verification; no platform calls or sends.

Run from the publishing checkout: python3 cosimo/verify-comment-handoff.py
Only disposable native account/thread/post/key rows and private temporary files.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT.parent / "cosimo-content-engine/content-engine"
NODE = Path.home() / ".nvm/versions/node/v22.22.3/bin/node"
suffix = uuid.uuid4().hex
checks = []


def django(source):
    result = subprocess.run(["docker", "compose", "-f", "cosimo/compose.yaml", "exec", "-T", "web", "python", "manage.py", "shell"],
                            input=source, text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        raise RuntimeError("Disposable native fixture operation failed; inspect local service logs")
    return json.loads(result.stdout.strip().splitlines()[-1])


try:
    fixture = django('''
import json
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from apps.api_keys.services import issue_api_key
from apps.composer.models import Post, PlatformPost
from apps.inbox.models import InboxMessage
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace
assert connection.vendor == 'postgresql'
suffix = ''' + repr(suffix) + '''
u=get_user_model().objects.create_user('comment-component-'+suffix+'@localhost')
o=Organization.objects.create(name='comment-component-'+suffix)
w=Workspace.objects.create(organization=o,name='Disposable comment component')
OrgMembership.objects.create(organization=o,user=u,org_role='owner')
WorkspaceMembership.objects.create(workspace=w,user=u,workspace_role='owner')
a=SocialAccount(workspace=w,platform='linkedin_personal',account_platform_id=suffix,account_name='SYNTHETIC LOCAL FIXTURE',connection_status='disconnected')
a._skip_analytics_backfill=True
a.save()
k=issue_api_key(workspace=w,social_accounts=[a],issued_by=u,name='Disposable inbox key',permissions=['use_inbox','create_posts'])
source='component-comments:'+suffix
p=Post.objects.create(workspace=w,caption='Synthetic component parent. Not a real publication.',internal_notes=json.dumps({'sourceId':source}))
pp=PlatformPost.objects.create(post=p,social_account=a)
parent=InboxMessage.objects.create(workspace=w,social_account=a,platform_message_id='parent:'+suffix,sender_name='Synthetic parent',body='Parent fixture',received_at=timezone.now(),message_type='mention')
m=InboxMessage.objects.create(parent_message=parent,workspace=w,social_account=a,platform_message_id='synthetic:'+suffix,sender_name='Synthetic Input',sender_handle='https://www.linkedin.com/in/component-fixture/',body='Synthetic incoming fixture: explain the reconciliation example.',related_post=pp,received_at=timezone.now())
print(json.dumps({'account':str(a.id),'parent':str(parent.id),'platformId':m.platform_message_id,'message':str(m.id),'post':str(p.id),'source':source,'token':k.plaintext_token}))
''')
    with tempfile.TemporaryDirectory(prefix="cosimo-comment-component-") as temp:
        directory = Path(temp)
        token = directory / "api-token"
        token.write_text(fixture.pop("token"))
        token.chmod(0o600)
        journal = directory / "journal.json"
        journal.write_text(json.dumps({"origin": "http://127.0.0.1:4010", "account": fixture["account"], "posts": {fixture["source"]: {"postId": fixture["post"]}}}))
        journal.chmod(0o600)
        crm = directory / "crm.json"
        crm.write_text(json.dumps({"schemaVersion": 1, "observedAt": "2026-11-19T00:00:00Z", "tabs": {"Contacts": [{"Contact ID": "fixture-contact", "Firm ID": "fixture-firm", "Source links": "https://www.linkedin.com/in/component-fixture/", "Outreach control": "Do not contact"}], "Conversations": [{"Contact ID": "fixture-contact", "Conversation ID": "fixture-existing-conversation"}]}}))
        crm.chmod(0o600)
        program = r'''
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const mod=require(process.env.COMPONENT_ENGINE+'/lib/comment-handoff.cjs');
const dir=process.env.COMPONENT_DIR,fixture=JSON.parse(process.env.COMPONENT_FIXTURE);
const options={outDir:path.join(dir,'ledger'),tokenFile:path.join(dir,'api-token'),journalFile:path.join(dir,'journal.json'),crmFile:path.join(dir,'crm.json')};
(async()=>{
 const first=await mod.refresh(options);assert.equal(first.counts.actualIncomingObserved,1,JSON.stringify(first));assert.equal(first.counts.linkedToContent,1,JSON.stringify(first));assert.equal(first.counts.matchedExistingCrm,1,JSON.stringify(first));
 await mod.refresh(options);const ledgerFile=first.ledgerFile;let ledger=JSON.parse(fs.readFileSync(ledgerFile));assert.equal(Object.keys(ledger.messages).length,1);
 let row=Object.values(ledger.messages)[0];assert.equal(row.crm.outreachControl,'Do not contact');assert.equal(row.crm.conversationIds[0],'fixture-existing-conversation');
 assert.equal(row.platformCommentId,fixture.platformId);assert.equal(row.parentMessageId,fixture.parent);assert.equal(row.identityScope,'account_platform_comment');assert.equal(JSON.parse(row.platformKey)[3],fixture.platformId);
 const draftFile=path.join(dir,'draft.json');const draft={messageId:fixture.message,expectedContextSha256:row.contextSha256,body:'SYNTHETIC COMPONENT DRAFT. Never send.'};fs.writeFileSync(draftFile,JSON.stringify(draft),{mode:0o600});
 const created=await mod.saveNativeDraft({...options,draftFile});const replay=await mod.saveNativeDraft({...options,draftFile});assert.equal(created.replyId,replay.replyId);assert.equal(created.sent,false);
 draft.body='SYNTHETIC EDITED COMPONENT DRAFT. Never send.';fs.writeFileSync(draftFile,JSON.stringify(draft));const edited=await mod.saveNativeDraft({...options,draftFile});assert.equal(edited.replyId,created.replyId);
 draft.expectedContextSha256='0'.repeat(64);fs.writeFileSync(draftFile,JSON.stringify(draft));await assert.rejects(()=>mod.saveNativeDraft({...options,draftFile}),/matching observed comment/);
 await mod.refresh(options);ledger=JSON.parse(fs.readFileSync(ledgerFile));row=Object.values(ledger.messages)[0];assert.equal(row.draft.body,draft.body);assert.equal(row.draftContextCurrent,true);
 assert.equal(mod.crmLink({sender_handle:'not-a-profile'},JSON.parse(fs.readFileSync(options.crmFile)).tabs).status,'unresolved');
 const tabs=JSON.parse(fs.readFileSync(options.crmFile)).tabs;tabs.Contacts.push({...tabs.Contacts[0],'Contact ID':'second-fixture'});assert.equal(mod.crmLink({sender_handle:'https://www.linkedin.com/in/component-fixture/'},tabs).status,'ambiguous');
 const auth={Authorization:'Bearer '+fs.readFileSync(options.tokenFile,'utf8').trim(),'Content-Type':'application/json'};
 let live=await (await fetch('http://127.0.0.1:4010/api/v1/inbox/'+fixture.message,{headers:auth})).json();assert.equal(live.replies.length,1);assert.equal(live.replies[0].status,'draft');assert.equal(live.replies[0].sent_at,null);
 let changed=await fetch('http://127.0.0.1:4010/api/v1/inbox/replies/'+created.replyId,{method:'PATCH',headers:auth,body:JSON.stringify({body:'SYNTHETIC NATIVE EDIT. Never send.'})});assert.equal(changed.status,200);
 draft.expectedContextSha256=row.contextSha256;fs.writeFileSync(draftFile,JSON.stringify(draft));await assert.rejects(()=>mod.saveNativeDraft({...options,draftFile}),/Native draft was edited/);
 let deleted=await fetch('http://127.0.0.1:4010/api/v1/inbox/replies/'+created.replyId,{method:'DELETE',headers:auth});assert.equal(deleted.status,204);
 await assert.rejects(()=>mod.saveNativeDraft({...options,draftFile}),/Saved draft disappeared/);
 console.log(JSON.stringify({status:'passed',replyId:created.replyId,checks:['actual native read and source-ID mapping','read replay deduplicates native IDs and retains platform comment plus parent-thread identity','exact CRM profile reuses contact/conversation IDs and retains hold','native draft create/readback/replay/patch retains one ID and never sends','stale context rejected','refresh retains edited draft','unresolved and ambiguous CRM identities remain unlinked','native edit is not overwritten and discarded draft is not recreated'],fixtureOnly:true}));
})().catch(e=>{console.error(e.message);process.exitCode=1});
'''
        env = {**os.environ, "COMPONENT_DIR": temp, "COMPONENT_ENGINE": str(ENGINE), "COMPONENT_FIXTURE": json.dumps(fixture)}
        result = subprocess.run([str(NODE), "-"], input=program, text=True, capture_output=True, env=env)
        if result.returncode:
            raise RuntimeError("Comment adapter verification failed: " + result.stderr[-1200:])
        proof = json.loads(result.stdout)
        checks.extend(proof["checks"])
        state = django('''
import json
from apps.inbox.models import InboxMessage, InboxReply
m=InboxMessage.objects.get(id=''' + repr(fixture["message"]) + ''')
assert not InboxReply.objects.filter(inbox_message=m).exists()
print(json.dumps({'discardedDraftNotRecreated':True,'sent':False}))
''')
        checks.append("PostgreSQL confirms discarded draft was not recreated")
finally:
    cleanup = django('''
import json
from django.contrib.auth import get_user_model
from apps.organizations.models import Organization
suffix = ''' + repr(suffix) + '''
users=get_user_model().objects.filter(email='comment-component-'+suffix+'@localhost')
auto=[]
for u in users:
 auto.extend(u.org_memberships.values_list('organization_id',flat=True))
users.delete()
Organization.objects.filter(id__in=auto).delete()
Organization.objects.filter(name='comment-component-'+suffix).delete()
assert not get_user_model().objects.filter(email='comment-component-'+suffix+'@localhost').exists()
assert not Organization.objects.filter(name='comment-component-'+suffix).exists()
print(json.dumps({'cleanup':True}))
''')

evidence = {"schemaVersion": 1, "status": "component_checks_passed", "fixtureOnly": True, "actualIncomingThreadsVerified": 0,
            "checks": checks, "cleanup": cleanup["cleanup"], "externalSends": 0, "crmWrites": 0}
out = ROOT / "cosimo/private/comment-handoff-verification.json"
out.write_text(json.dumps(evidence, indent=2) + "\n")
out.chmod(0o600)
print(json.dumps(evidence, indent=2))
