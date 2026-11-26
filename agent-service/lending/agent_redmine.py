"""Idempotent provisioning of dedicated, project-owned Redmine accounts."""
import hashlib
import secrets
from urllib.parse import urlencode


class AgentRedmine:
    def __init__(self, api, project, registry):
        self.api, self.project, self.registry = api, project, registry

    def identity(self, profile):
        login = 'trada-' + hashlib.sha256(f'{self.project}:{profile["id"]}'.encode()).hexdigest()[:24]
        # Redmine name fields have bounded lengths. Keep the display name across two fields.
        full = 'Trà đá AI ' + profile['name']
        split = full.rfind(' ', max(1,len(full)-30),31)
        split = split if split>0 else 30
        return dict(login=login,mail=login+'@agents.trada.invalid',
                    firstname=full[:split].strip(),lastname=full[split:].strip())

    def fingerprint(self, profile):
        values = (self.project,profile['id'],profile['name'],profile['specialty'],
                  profile['access'],profile['status'])
        return hashlib.sha256(repr(values).encode()).hexdigest()

    @staticmethod
    def desired_status(profile):
        return 1 if profile['status']=='ready' else 3

    def _list(self, path, key, params=None):
        offset = 0
        while True:
            page = self.api.request('GET',path+'?'+urlencode({**(params or {}),'limit':100,'offset':offset}))
            rows = page[key]
            yield from rows
            offset += len(rows)
            if not rows or offset>=page.get('total_count',offset):
                return

    def _find_user(self, identity):
        # Some Redmine installations reject status="" with HTTP 422.
        for status in (1,3,2):
            user = next((u for u in self._list('/users.json','users',
                {'status':status,'name':identity['login']}) if u['login']==identity['login']),None)
            if user is not None:
                return user
        return None

    def _owned_user(self, user_id, identity):
        user = self.api.request('GET',f'/users/{user_id}.json')['user']
        if user.get('login')!=identity['login'] or user.get('mail')!=identity['mail'] or user.get('admin'):
            raise ValueError('Tài khoản Redmine trùng định danh nhưng không thuộc agent này. Không tự sửa tài khoản khác.')
        return user

    def role(self, profile):
        preferred = {'frontend':'FE','backend':'BE','ba':'BA','tester':'TESTER',
                     'reviewer':'Reporter','sa':'Developer','devops':'Developer'}.get(profile['specialty'])
        fallback = 'Developer' if profile['access']=='write' else 'Reporter'
        roles = self.api.request('GET','/roles.json')['roles']
        role = next((r for name in dict.fromkeys([preferred,fallback]) if name
                     for r in roles if r['name'].casefold()==name.casefold()),None)
        if not role:
            raise ValueError('Redmine chưa có vai trò '+fallback+' phù hợp để nhận task.')
        details = self.api.request('GET',f'/roles/{role["id"]}.json')['role']
        if not details.get('assignable') or 'view_issues' not in details.get('permissions',[]):
            raise ValueError('Vai trò Redmine không được nhận task hoặc không được xem công việc.')
        if {'manage_members','delete_project','edit_project'} & set(details.get('permissions',[])):
            raise ValueError('Vai trò Redmine đang có quyền quản trị dự án; cần dùng vai trò chuyên môn.')
        return role

    def _membership(self, user_id):
        return next((m for m in self._list(f'/projects/{self.project}/memberships.json','memberships')
                     if m.get('user',{}).get('id')==user_id),None)

    def ensure(self, key):
        profile = self.registry.get(key)
        if profile['builtin']:
            return profile
        identity = self.identity(profile)
        role = self.role(profile)
        self.registry.sync_update(key,state='provisioning',error='',retry_at=0)
        if profile.get('redmine_managed') and profile.get('redmine_user_id'):
            user = self._owned_user(profile['redmine_user_id'],identity)
        else:
            user = self._find_user(identity)
            if user is None:
                try:
                    created = self.api.request('POST','/users.json',{'user':{
                        **identity,'password':'Aa9!'+secrets.token_urlsafe(48),'admin':False,
                        'status':3,'mail_notification':'none','must_change_passwd':False,
                        'auth_source_id':None},'send_information':False})['user']
                    user = {'id':created['id']}
                except Exception:
                    # A timed-out response may already have committed the new user.
                    user = self._find_user(identity)
                    if user is None:
                        raise
            user = self._owned_user(user['id'],identity)
            # Save ownership immediately; membership/name/status steps can be retried.
            self.registry.sync_update(key,state='provisioning',redmine_user_id=user['id'],
                                      redmine_managed=True,login=identity['login'],
                                      previous_user_id=profile.get('redmine_user_id'))
        # Account is locked while membership and role are reconciled.
        desired = self.desired_status(profile)
        fields = {k:v for k,v in {**identity,'status':3}.items() if k!='login' and user.get(k)!=v}
        if fields:
            self.api.request('PUT',f'/users/{user["id"]}.json',{'user':fields})
        membership = self._membership(user['id'])
        if membership is None:
            try:
                self.api.request('POST',f'/projects/{self.project}/memberships.json',
                    {'membership':{'user_id':user['id'],'role_ids':[role['id']]}})
            except Exception:
                membership = self._membership(user['id'])
                if membership is None:
                    raise
        membership = self._membership(user['id'])
        if not membership:
            raise ValueError('Chưa xác nhận được agent là thành viên dự án Redmine.')
        if any(r.get('inherited') for r in membership['roles']):
            raise ValueError('Agent có quyền kế thừa từ nhóm trên Redmine; cần kiểm tra nhóm trước khi đồng bộ.')
        if {r['id'] for r in membership['roles']}!={role['id']}:
            self.api.request('PUT',f'/memberships/{membership["id"]}.json',
                             {'membership':{'role_ids':[role['id']]}})
        if desired!=3:
            self.api.request('PUT',f'/users/{user["id"]}.json',{'user':{'status':desired}})
        verified = self._owned_user(user['id'],identity)
        membership = self._membership(user['id'])
        if (any(verified.get(k)!=v for k,v in identity.items()) or verified.get('status')!=desired
                or not membership or {r['id'] for r in membership['roles']}!={role['id']}):
            raise ValueError('Redmine chưa khớp tên, trạng thái hoặc vai trò sau đồng bộ.')
        return self.registry.sync_update(key,state='synced',error='',retry_at=0,
            redmine_user_id=user['id'],redmine_managed=True,login=identity['login'],
            role_id=role['id'],role_name=role['name'],membership_id=membership['id'],
            user_status=desired,fingerprint=self.fingerprint(profile))

    def lock_for_delete(self, key):
        """Confirm an owned account stays locked; retain its history in Redmine."""
        profile = self.registry.get(key)
        if profile.get('redmine_managed') and profile.get('redmine_user_id'):
            identity = self.identity(profile)
            user = self._owned_user(profile['redmine_user_id'],identity)
            if user.get('status')!=3:
                self.api.request('PUT',f'/users/{user["id"]}.json',{'user':{'status':3}})
            if self._owned_user(user['id'],identity).get('status')!=3:
                raise ValueError('Chưa khóa được tài khoản Redmine; chưa xóa hồ sơ agent.')
