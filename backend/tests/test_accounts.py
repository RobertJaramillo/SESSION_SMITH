"""Exercise real cookie sessions, two-user consent, and cross-campaign isolation."""
import asyncio
import json
import time
import unittest
from uuid import uuid4

from backend.accounts import accounts
from backend.tests._asgi_client import request_raw


class AccountTests(unittest.TestCase):
    def run_scenario(self, fn):
        asyncio.run(fn())

    def test_accounts_friends_and_campaign_invitation_lifecycle(self):
        async def scenario():
            async def call(method, path, body=None, cookie='', expected=200, extra=None):
                code, headers, raw = await request_raw(method,path,body=body,headers={'cookie':cookie,**(extra or {})})
                response = json.loads(raw)
                self.assertEqual(code,expected,response)
                return response.get('data'), headers.get('set-cookie','').split(';')[0]

            suffix = uuid4().hex
            email_a, email_b = f'a{suffix}@example.com', f'b{suffix}@example.com'
            a, ca = await call('POST','/v1/auth/register',{'name':'Alice','email':email_a.upper(),'password':'strong-password-a'})
            b, cb = await call('POST','/v1/auth/register',{'name':'Bob','email':email_b,'password':'strong-password-b'})
            self.assertNotIn('password_hash',a)
            code,headers,_ = await request_raw('POST','/v1/auth/login',body={'email':email_a,'password':'strong-password-a'})
            self.assertEqual(code,200)
            self.assertIn('HttpOnly',headers['set-cookie'])
            self.assertIn('SameSite=lax',headers['set-cookie'])
            await call('GET','/v1/campaigns',expected=401)
            await call('POST','/v1/auth/login',{'email':email_a,'password':'wrong-password'},expected=401)
            _, logged_in = await call('POST','/v1/auth/login',{'email':email_a,'password':'strong-password-a'})
            await call('GET','/v1/auth/me',cookie=logged_in)
            await call('POST','/v1/auth/register',{'name':'Other','email':email_a,'password':'strong-password-a'},expected=409)
            await call('POST','/v1/friends',{'email':email_a},ca,400)
            f,_ = await call('POST','/v1/friends',{'email':email_b},ca)
            await call('POST','/v1/friends',{'email':email_a},cb,409)
            await call('POST',f"/v1/friends/{f['id']}/accept",{},ca,404)
            await call('POST',f"/v1/friends/{f['id']}/accept",{},cb)
            friends,_ = await call('GET','/v1/friends',cookie=ca)
            self.assertEqual(friends[0]['status'],'accepted')
            await call('POST','/v1/campaigns',{'name':'   '},ca,422)
            campaign,_ = await call('POST','/v1/campaigns',{'name':'Owned world'},ca,201)
            cid = campaign['campaignId']
            self.assertEqual(campaign['owner']['id'],a['id'])
            await call('GET',f'/v1/campaigns/{cid}',cookie=cb,expected=404)
            await call('GET','/v1/campaigns/campaign_ashes_of_kestrel_vale',cookie=ca,expected=404)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':'not-an-email'},ca,422)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':email_b,'role':'owner'},ca,422)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':email_b,'role':'player'},ca)
            pending,_ = await call('GET','/v1/invitations',cookie=cb)
            inv = pending[0]['id']
            await call('POST',f'/v1/invitations/{inv}/accept',{},ca,404)
            await call('POST',f'/v1/invitations/{inv}/accept',{},cb)
            await call('POST',f'/v1/invitations/{inv}/accept',{},cb,404)
            sections,_ = await call('GET','/v1/campaigns',cookie=cb)
            self.assertEqual(sections[1]['campaigns'][0]['role'],'player')
            await call('GET',f'/v1/campaigns/{cid}/canon-events',cookie=cb)
            for path in ('workspace','entries','world-export','memory-proposals','session-prep','jobs'):
                await call('GET',f'/v1/campaigns/{cid}/{path}',cookie=cb,expected=403)
            await call('PATCH',f'/v1/campaigns/{cid}',{'name':'Hijacked'},cb,403)
            await call('POST',f'/v1/campaigns/{cid}/notes',{'content':'A secret','sessionNumber':'1'},cb,403)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':'other@example.com'},cb,403)
            submitted,_ = await call('POST',f'/v1/campaigns/{cid}/notes',{'content':'The council raised taxes.','sessionNumber':'1'},ca,202)
            await call('GET',f"/v1/jobs/{submitted['jobId']}",cookie=cb,expected=403)
            proposals,_ = await call('GET',f'/v1/campaigns/{cid}/memory-proposals',cookie=ca)
            self.assertTrue(proposals)
            await call('PATCH',f"/v1/memory-proposals/{proposals[0]['id']}",{'action':'approve'},cb,403)
            await call('DELETE',f'/v1/campaigns/{cid}/members/{a["id"]}',cookie=ca,expected=404)
            await call('DELETE',f'/v1/campaigns/{cid}/members/{b["id"]}',cookie=ca)
            await call('GET',f'/v1/campaigns/{cid}',cookie=cb,expected=404)
            await call('DELETE',f"/v1/friends/{f['id']}",cookie=ca)
            await call('POST','/v1/auth/logout',{},cb)
            await call('GET','/v1/auth/me',cookie=cb,expected=401)
            await call('POST','/v1/auth/logout',{},ca,403,{'origin':'https://evil.example'})
            with accounts.transaction() as sql:
                sql('UPDATE account_sessions SET expires_at=%s WHERE user_id=%s',(time.time()-1,a['id']))
            await call('GET','/v1/auth/me',cookie=ca,expected=401)
        self.run_scenario(scenario)

    def test_invitation_before_signup_expiry_decline_and_revoke(self):
        async def scenario():
            suffix = uuid4().hex
            async def call(method,path,body=None,cookie='',expected=200):
                code,headers,raw = await request_raw(method,path,body=body,headers={'cookie':cookie})
                self.assertEqual(code,expected,raw)
                return json.loads(raw).get('data'),headers.get('set-cookie','').split(';')[0]
            _,owner = await call('POST','/v1/auth/register',{'name':'Owner','email':f'owner{suffix}@example.com','password':'long-enough-password'})
            campaign,_ = await call('POST','/v1/campaigns',{'name':'Invites'},owner,201)
            cid=campaign['campaignId']; email=f'new{suffix}@example.com'
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':email,'role':'viewer'},owner)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':email},owner,409)
            _,peer = await call('POST','/v1/auth/register',{'name':'New','email':email,'password':'long-enough-password'})
            invites,_=await call('GET','/v1/invitations',cookie=peer)
            await call('DELETE',f"/v1/invitations/{invites[0]['id']}",cookie=peer)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':email},owner)
            invites,_=await call('GET','/v1/invitations',cookie=peer)
            with accounts.transaction() as sql:
                sql('UPDATE campaign_invitations SET expires_at=0 WHERE id=%s',(invites[0]['id'],))
            await call('POST',f"/v1/invitations/{invites[0]['id']}/accept",{},peer,404)
            await call('POST',f'/v1/campaigns/{cid}/invitations',{'email':email},owner)
            invites,_=await call('GET','/v1/invitations',cookie=peer)
            await call('DELETE',f"/v1/invitations/{invites[0]['id']}",cookie=owner)
        self.run_scenario(scenario)

    def test_profile_updates_require_password_and_revoke_old_sessions(self):
        async def scenario():
            async def call(method,path,body=None,cookie='',expected=200):
                code,headers,raw = await request_raw(method,path,body=body,headers={'cookie':cookie})
                self.assertEqual(code,expected,raw)
                return json.loads(raw).get('data'),headers.get('set-cookie','').split(';')[0]
            email=f'profile{uuid4().hex}@example.com'
            _,cookie=await call('POST','/v1/auth/register',{'email':email,'name':'Original','password':'original-password'})
            _,second=await call('POST','/v1/auth/login',{'email':email,'password':'original-password'})
            await call('PATCH','/v1/auth/me',{'email':'not-an-email','currentPassword':'original-password'},cookie,422)
            updated,cookie=await call('PATCH','/v1/auth/me',{'name':'Updated'},cookie)
            self.assertEqual(updated['name'],'Updated')
            await call('PATCH','/v1/auth/me',{'password':'replacement-password','currentPassword':'incorrect'},cookie,403)
            _,new=await call('PATCH','/v1/auth/me',{'password':'replacement-password','currentPassword':'original-password'},cookie)
            await call('GET','/v1/auth/me',cookie=second,expected=401)
            await call('GET','/v1/auth/me',cookie=cookie,expected=401)
            await call('GET','/v1/auth/me',cookie=new)
            await call('POST','/v1/auth/login',{'email':email,'password':'original-password'},expected=401)
            await call('POST','/v1/auth/login',{'email':email,'password':'replacement-password'})
        self.run_scenario(scenario)
