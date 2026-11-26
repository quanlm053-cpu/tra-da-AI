"""Populate the existing Lending backlog from the agreed role plan.

Run with the Lending service stopped so it cannot create the same tasks.
"""
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from office import Office, PROJECT, LABELS, ROLES, STATUS, TASK_NAMES, TASK_TOPICS

MEMBER_ROLES = {'sa':4, 'ba':6, 'backend':8, 'frontend':7, 'devops':4, 'reviewer':4, 'tester':9}
ORDER = {113:0, 114:3, 115:6, 116:9}


def run():
    office = Office()
    api = office.api
    today = datetime.now(timezone(timedelta(hours=7))).date()
    start = today + timedelta(days=1)
    known_users = api.request('GET','/users.json?name=lending-ai-&limit=100')['users']
    memberships = api.request('GET',f'/projects/{PROJECT}/memberships.json?limit=100')['memberships']
    members = {item['user']['id'] for item in memberships if 'user' in item}

    def ensure_assignee(role):
        login = 'lending-ai-' + role
        user = next((u for u in known_users if u['login']==login),None)
        if user is None:
            user = api.request('POST','/users.json',{'user':{
                'login':login,'firstname':'Lending AI','lastname':LABELS[role],
                'mail':login+'@example.invalid','password':'A9!'+secrets.token_urlsafe(28),
                'auth_source_id':None,'mail_notification':'none'},'send_information':False})['user']
        if user['id'] not in members:
            api.request('POST',f'/projects/{PROJECT}/memberships.json',{'membership':{
                'user_id':user['id'],'role_ids':[MEMBER_ROLES[role]]}})
        return user['id']

    def plan_story(story, assignees):
        story_id = story['id']
        issue = api.issue(story_id)
        assert issue['project']['id'] == PROJECT
        children = {i['subject']:i['id'] for i in issue.get('children',[])}
        offset = ORDER.get(story_id)
        branch_date = start + timedelta(days=offset) if offset is not None else None
        for role in ROLES:
            if story['state']=='done' and role not in story['tasks']:
                continue
            topic = TASK_TOPICS.get(story_id)
            title = f'{LABELS[role]}: {TASK_NAMES[role]}' + (f' · {topic}' if topic else '')
            issue_id = story['tasks'].get(role,{}).get('id') or children.get(title)
            values = {'assigned_to_id':assignees[role]}
            if branch_date is not None:
                # SA and BA can prepare later Stories before their implementation slots.
                window = {
                    'sa':(start+timedelta(days=min(offset//3,3)),)*2,
                    'ba':(start+timedelta(days=min(offset//3,3)),)*2,
                    'backend':(branch_date,branch_date+timedelta(days=1)),
                    'frontend':(branch_date+timedelta(days=1),)*2,
                    'devops':(branch_date+timedelta(days=1),)*2,
                    'reviewer':(branch_date+timedelta(days=2),)*2,
                    'tester':(branch_date+timedelta(days=2),)*2,
                }[role]
                values.update(start_date=window[0].isoformat(),due_date=window[1].isoformat())
            if not issue_id:
                issue_id = api.request('POST','/issues.json',{'issue':{
                    **values,'project_id':PROJECT,'tracker_id':5,'status_id':STATUS['todo'],
                    'subject':title,'parent_issue_id':story_id,
                    'description':f'{TASK_NAMES[role]}.\n\nTiêu chí Story: {story["acceptance"]}'}})['issue']['id']
                story['tasks'][role]={'id':issue_id,'state':'queued'}
                office.save()
                continue
            child = api.issue(issue_id)
            assert child['project']['id']==PROJECT and child['parent']['id']==story_id
            if not branch_date and not child.get('start_date'):
                values['start_date']=child['created_on'][:10]
            if not branch_date and not child.get('due_date'):
                values['due_date']=(child.get('closed_on') or child['updated_on'])[:10]
            api.update(issue_id,**values)
            if role not in story['tasks']:
                story['tasks'][role]={'id':issue_id,'state':'queued'}
                office.save()
        return story_id

    if office.data['active'] or office.data.get('preparing'):
        raise RuntimeError('Lending vẫn còn agent hoạt động.')
    with ThreadPoolExecutor(max_workers=5) as pool:
        assignees = dict(zip(ROLES,pool.map(ensure_assignee,ROLES)))
        for story_id in pool.map(lambda story:plan_story(story,assignees),office.data['stories']):
            print(f'Story #{story_id}: Redmine assignments and dates saved',flush=True)


if __name__=='__main__':
    run()
