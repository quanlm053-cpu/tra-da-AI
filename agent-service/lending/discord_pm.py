"""Discord frontend for the existing local Lending PM queue."""
import asyncio
import argparse
import getpass
import json
import re
import time
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import discord
from discord_credentials import read_token, save_token

DEPLOYMENT = Path(__file__).resolve().parents[2] / 'deployment.local.json'
DISCORD_CONFIG = json.loads(DEPLOYMENT.read_text(encoding='utf-8-sig')).get('discord',{}) if DEPLOYMENT.exists() else {}
GUILD = int(DISCORD_CONFIG.get('guild_id',0))
WORK = int(DISCORD_CONFIG.get('work_channel_id',0))
TEA = int(DISCORD_CONFIG.get('tea_channel_id',0))
OFFICE = 'http://127.0.0.1:8767/lending-api'
VIETNAM = timezone(timedelta(hours=7))
REPORT_STATE = Path(__file__).resolve().parent.parent / 'runtime/lending/discord-last-report'
EVENT_CURSOR = REPORT_STATE.with_name('discord-event-cursor')
ROLE_NAMES = {
    'pm': 'PM', 'sa': 'SA', 'ba': 'BA', 'frontend': 'FE', 'backend': 'BE',
    'tester': 'TESTER', 'reviewer': 'REVIEW', 'devops': 'DEVOPS',
}


def get_token(label, replace=False):
    saved = None if replace else read_token(label)
    if saved:
        print(f'{label}: dùng token đã lưu trong Windows.', flush=True)
        return saved
    entered = getpass.getpass(f'Dán Discord Bot Token của {label} (không hiển thị): ').strip()
    if not entered:
        raise SystemExit(f'Chưa nhập Bot Token của {label}.')
    save_token(label, entered)
    print(f'{label}: đã lưu token trong Windows.', flush=True)
    return entered


def load_custom_agents():
    """Fetch identities only. Tokens stay in Windows Credential Manager."""
    state = office_request('/state')
    for agent in state.get('agents', []):
        if not agent.get('builtin') and agent['status']=='ready':
            ROLE_NAMES[agent['id']] = agent['name']


def credential_label(role):
    return role if role.startswith('agent-') else ROLE_NAMES[role]


def office_request(path, message=None, role='pm'):
    body = None if message is None else json.dumps({'message': message, 'role': role}).encode()
    request = Request(OFFICE + path, data=body, headers={
        'Origin': 'http://localhost:8766', 'Content-Type': 'application/json',
    })
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def daily_report(state, now):
    day = now.date()
    handoffs = [m for m in state['messages'] if m.get('task') and m.get('sender') != 'pm'
                and m.get('recipient') != 'human' and datetime.fromtimestamp(m['at'], VIETNAM).date() == day]
    tasks = sorted({m['task'] for m in handoffs})
    story_titles = {story['id']: story['title'] for story in state['stories']}
    assignments = []
    for slot in ('active', 'preparing'):
        run = state.get(slot)
        if run:
            role = ROLE_NAMES.get(run['role'], run['role'].upper())
            story_id = run['story']
            title = discord.utils.escape_markdown(story_titles.get(story_id, '')[:180])
            story = f'Story #{story_id}' + (f' · {title}' if title else '')
            assignments.append(f'• **{role}** · Task #{run["task"]} · {story}')
    blocked = [s for s in state['stories'] if s['state'] == 'attention']
    queued = [s for s in state['stories'] if s['state'] == 'queued']
    def issues(items):
        return ', '.join(f'#{item}' for item in items[:12]) + (f' (+{len(items)-12})' if len(items)>12 else '')
    return '\n'.join([
        f'📊 **Báo cáo cuối ngày · {day:%d/%m/%Y}**',
        '✅ **Đã bàn giao hôm nay** · ' + (issues(tasks) or 'Chưa có lượt bàn giao.'),
        '🛠️ **Công việc hiện tại**',
        *(assignments or ['Không có agent đang chạy task.']),
        '⚠️ **Story cần xử lý** · ' + (issues([s['id'] for s in blocked]) or 'Không có.'),
        '⏳ **Story đang chờ** · ' + (issues([s['id'] for s in queued]) or 'Không có.'),
    ])


def format_event(event):
    sender = event.get('sender')
    recipient = event.get('recipient')
    story = event.get('story')
    if not story:
        return None
    issue = f'Story #{story}'
    if event.get('task'):
        issue += f' · Task #{event["task"]}'
    if sender == 'pm' and recipient == 'human':
        return f'⚠️ **{issue} cần xử lý**\nMở Workflow trong Văn phòng AI để xem lý do dừng.'
    if sender not in ROLE_NAMES or recipient not in ROLE_NAMES:
        return None
    body = discord.utils.escape_markdown(event['text'].strip()[:850])[:1700]
    return f'💬 **Gửi {ROLE_NAMES[recipient]}** · {issue}\n{body}'


async def publish_events(channels, events):
    if not EVENT_CURSOR.exists():
        EVENT_CURSOR.write_text(str(len(events)), encoding='utf-8')
        return
    cursor = int(EVENT_CURSOR.read_text(encoding='utf-8'))
    if not 0 <= cursor <= len(events):
        EVENT_CURSOR.write_text(str(len(events)), encoding='utf-8')
        return
    for index, event in enumerate(events[cursor:cursor + 20], start=cursor + 1):
        message = format_event(event)
        channel = channels.get(event.get('sender'))
        if message and channel is not None:
            nonce = f'{int(event["at"] * 1000)}-{index}'
            await channel.send(message, nonce=nonce)
        temp = EVENT_CURSOR.with_suffix('.tmp')
        temp.write_text(str(index), encoding='utf-8')
        temp.replace(EVENT_CURSOR)


class PMBot(discord.Client):
    def __init__(self, role='pm'):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.agent_channels = {}
        self.role = role
        self.report_task = None

    async def setup_hook(self):
        if self.role == 'pm':
            self.report_task = asyncio.create_task(self.reports())

    async def on_ready(self):
        guild = self.get_guild(GUILD)
        if guild:
            self.owner_id = guild.owner_id
        print(f'{ROLE_NAMES[self.role]} Discord đã kết nối: {self.user}', flush=True)

    async def on_message(self, message):
        if (message.author.bot or message.guild is None or message.guild.id != GUILD
                or message.channel.id not in (WORK, TEA) or self.user not in message.mentions):
            return
        if message.author.id != getattr(self, 'owner_id', None):
            return
        command = re.sub(rf'<@!?{self.user.id}>', '', message.content).strip()
        if not command:
            return
        try:
            queued = await asyncio.to_thread(office_request, '/chat', command, self.role)
            request_id = queued['id']
            state_path = '/state'
            if queued.get('project'):
                from urllib.parse import urlencode
                state_path += '?' + urlencode({'project':queued['project']})
        except (OSError, KeyError, ValueError):
            await message.reply('Không xác nhận được yêu cầu từ Văn phòng AI. Kiểm tra lịch sử PM trước khi gửi lại.', mention_author=False)
            return
        receipt = await message.reply(f'{ROLE_NAMES[self.role]} đã nhận yêu cầu #{request_id}.', mention_author=False)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            await asyncio.sleep(3)
            try:
                state = await asyncio.to_thread(office_request, state_path)
            except (OSError, ValueError):
                continue
            row = next((item for item in state['chat'] if item['id'] == request_id), None)
            if row and row['state'] in ('done', 'failed'):
                reply = row.get('reply') or 'Yêu cầu đã kết thúc.'
                await receipt.edit(content=reply[:1900])
                return
        await receipt.edit(content=f'Yêu cầu #{request_id} vẫn đang chờ. Xem lịch sử PM trong Văn phòng AI.')

    async def reports(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(VIETNAM)
            day = now.date().isoformat()
            try:
                channel = self.get_channel(WORK)
                if isinstance(channel, discord.TextChannel) and channel.guild.id == GUILD:
                    state = await asyncio.to_thread(office_request, '/state')
                    REPORT_STATE.parent.mkdir(parents=True, exist_ok=True)
                    last = REPORT_STATE.read_text(encoding='utf-8').strip() if REPORT_STATE.exists() else ''
                    if now.hour >= 18 and last != day:
                        await channel.send(daily_report(state, now))
                        REPORT_STATE.write_text(day, encoding='utf-8')
                    await publish_events({**self.agent_channels, 'pm': channel}, state['messages'])
            except (discord.DiscordException, OSError, ValueError):
                print('Chưa đồng bộ được cập nhật Discord. Sẽ thử lại.', flush=True)
            await asyncio.sleep(15)


async def run_team(pm_token, agent_tokens):
    async with AsyncExitStack() as clients:
        pm = await clients.enter_async_context(PMBot())
        while True:
            try:
                await pm.login(pm_token)
                break
            except discord.LoginFailure as exc:
                print(connection_error('PM', exc), flush=True)
                pm_token = get_token('PM', replace=True)
        used_accounts = {pm.user.id}
        agent_clients = []
        for role, token in agent_tokens.items():
            label = ROLE_NAMES[role]
            while True:
                client = PMBot(role)
                try:
                    await client.login(token)
                    print(f'{label} đăng nhập thành công: {client.user} (ID {client.user.id}).', flush=True)
                    if client.user.id in used_accounts:
                        raise ValueError('Token thuộc bot đã dùng cho vai trò khác.')
                    channel = await client.fetch_channel(WORK)
                    guild = await client.fetch_guild(GUILD)
                    client.owner_id = guild.owner_id
                    if not isinstance(channel, discord.TextChannel) or channel.guild.id != GUILD:
                        raise ValueError('Kênh công việc không thuộc server Trà đá AI đã cấu hình.')
                except (discord.DiscordException, OSError, ValueError) as exc:
                    await client.close()
                    print(connection_error(label, exc), flush=True)
                    token = getpass.getpass(
                        f'Nhập lại token {label}, hoặc Enter để dừng (không hiển thị): '
                    ).strip()
                    if not token:
                        raise SystemExit(f'Đã dừng kết nối tại {label}.') from None
                    save_token(credential_label(role), token)
                    continue
                clients.push_async_callback(client.close)
                break
            used_accounts.add(client.user.id)
            pm.agent_channels[role] = channel
            agent_clients.append(client)
            print(f'{label} có thể truy cập kênh: {client.user}', flush=True)
        guild = await pm.fetch_guild(GUILD)
        pm.owner_id = guild.owner_id
        connections = [asyncio.create_task(client.connect(reconnect=True))
                       for client in [pm, *agent_clients]]
        try:
            await asyncio.gather(*connections)
        finally:
            for connection in connections:
                connection.cancel()
            await asyncio.gather(*connections, return_exceptions=True)


def connection_error(label, exc):
    if isinstance(exc, discord.LoginFailure):
        reason = 'Discord từ chối token. Lấy Bot Token trong ứng dụng đúng vai trò, mục Bot.'
    elif isinstance(exc, discord.Forbidden):
        reason = (
            f'Đăng nhập được nhưng Discord từ chối truy cập kênh #{WORK}. '
            'Kiểm tra bot đã vào đúng server và quyền ghi đè của kênh.'
        )
    elif isinstance(exc, discord.NotFound):
        reason = f'Discord không tìm thấy kênh #{WORK} cho bot này.'
    elif isinstance(exc, discord.HTTPException):
        reason = f'Discord trả HTTP {exc.status}, mã lỗi {exc.code}.'
    elif isinstance(exc, ValueError):
        reason = str(exc)
    else:
        reason = f'Lỗi kết nối hoặc dữ liệu Discord ({type(exc).__name__}).'
    return f'{label}: {reason}'


async def test_report(token, target):
    client = PMBot()
    async with client:
        await client.login(token)
        channel = await client.fetch_channel(WORK)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != GUILD:
            raise RuntimeError('Không tìm thấy kênh công việc đúng server.')
        now = datetime.now(VIETNAM)
        if now >= target + timedelta(minutes=1):
            raise RuntimeError('Giờ thử đã qua. Chọn một mốc mới.')
        print(f'Chờ gửi một báo cáo thử lúc {target:%H:%M}.', flush=True)
        await asyncio.sleep(max(0, (target-now).total_seconds()))
        state = await asyncio.to_thread(office_request, '/state')
        await channel.send('🧪 **BÁO CÁO THỬ**\n' + daily_report(state, datetime.now(VIETNAM)))
        print('Đã gửi báo cáo thử vào kênh công việc.', flush=True)


async def check_agent(label, token):
    async with discord.Client(intents=discord.Intents.none()) as client:
        try:
            await client.login(token)
            print(f'{label} đăng nhập thành công: {client.user} (ID {client.user.id}).', flush=True)
            channel = await client.fetch_channel(WORK)
            if not isinstance(channel, discord.TextChannel) or channel.guild.id != GUILD:
                raise ValueError('Kênh công việc không thuộc server Trà đá AI đã cấu hình.')
            print(f'{label} truy cập được kênh công việc.', flush=True)
        except (discord.DiscordException, OSError, ValueError) as exc:
            raise SystemExit(connection_error(label, exc)) from None


if __name__ == '__main__':
    try:
        load_custom_agents()
    except (OSError, ValueError):
        print('Chưa đọc được agent mới từ Office; các bot gốc vẫn dùng được.', flush=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-at', metavar='HH:MM', help='Gửi một báo cáo thử trong ngày theo giờ Việt Nam.')
    parser.add_argument('--agents', nargs='+', type=str.upper,
                        choices=[label for role, label in ROLE_NAMES.items() if role != 'pm'],
                        help='Kết nối các bot vai trò riêng, ví dụ --agents BA TESTER.')
    parser.add_argument('--custom-agents', nargs='+', metavar='AGENT_ID',
                        help='Kết nối bot riêng cho agent mới bằng id trong panel Agents.')
    parser.add_argument('--check-agent', type=str.upper, choices=list(ROLE_NAMES.values()),
                        help='Chỉ kiểm tra đăng nhập và truy cập kênh của một bot.')
    parser.add_argument('--replace-token', type=str.upper, choices=list(ROLE_NAMES.values()),
                        help='Nhập lại và lưu token của riêng một bot.')
    parser.add_argument('--replace-custom-token', metavar='AGENT_ID',
                        help='Nhập lại token riêng của agent mới theo ID ổn định.')
    args = parser.parse_args()
    if args.replace_custom_token:
        role=args.replace_custom_token
        if args.agents or args.custom_agents or args.test_at or args.check_agent or args.replace_token:
            parser.error('Dùng riêng --replace-custom-token.')
        if not role.startswith('agent-') or role not in ROLE_NAMES:
            parser.error('Agent chưa sẵn sàng trong dự án đang chọn: '+role)
        replacement=get_token(credential_label(role),replace=True)
        asyncio.run(check_agent(ROLE_NAMES[role],replacement))
        raise SystemExit(0)
    if args.replace_token:
        if args.agents or args.custom_agents or args.test_at or args.check_agent:
            parser.error('Dùng riêng --replace-token.')
        replacement = get_token(args.replace_token, replace=True)
        asyncio.run(check_agent(args.replace_token, replacement))
        raise SystemExit(0)
    if args.check_agent:
        if args.agents or args.custom_agents or args.test_at:
            parser.error('Dùng riêng --check-agent.')
        check_token = get_token(args.check_agent)
        asyncio.run(check_agent(args.check_agent, check_token))
        raise SystemExit(0)
    target = None
    if args.test_at:
        if args.agents or args.custom_agents:
            parser.error('Chọn --test-at hoặc --agents.')
        try:
            hour, minute = map(int,args.test_at.split(':'))
            target = datetime.now(VIETNAM).replace(hour=hour,minute=minute,second=0,microsecond=0)
        except ValueError:
            parser.error('Nhập giờ theo định dạng HH:MM.')
        if datetime.now(VIETNAM) >= target + timedelta(minutes=1):
            parser.error('Giờ thử đã qua. Chọn một mốc mới.')
    for role in args.custom_agents or []:
        if not role.startswith('agent-') or role not in ROLE_NAMES:
            parser.error('Agent chưa sẵn sàng trong dự án đang chọn: '+role)
    token = get_token('PM')
    if target:
        asyncio.run(test_report(token,target))
    else:
        agent_tokens = {}
        for role in args.custom_agents or []:
            if not role.startswith('agent-') or role not in ROLE_NAMES:
                parser.error('Agent chưa sẵn sàng trong dự án đang chọn: '+role)
            agent_tokens[role] = get_token(credential_label(role))
        for role, label in ROLE_NAMES.items():
            if not role.startswith('agent-') and label in (args.agents or []):
                agent_token = get_token(label)
                agent_tokens[role] = agent_token
        if agent_tokens:
            asyncio.run(run_team(token, agent_tokens))
        else:
            PMBot().run(token)
