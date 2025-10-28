#!/usr/bin/env python3

import curses
import threading
import time
import requests
import html
import uuid
import string
import random
import textwrap
import os
import re

API_BASE = "https://api.mail.tm"
POLL_INTERVAL = 4.0


def random_string(length=10):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def create_account():
    try:
        domains_resp = requests.get(f"{API_BASE}/domains", timeout=10)
        domains_resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Could not fetch domains from Mail.tm: {e}")

    try:
        domains = [d["domain"] for d in domains_resp.json().get("hydra:member", [])]
    except Exception as e:
        raise RuntimeError(f"Unexpected domains response: {e}")

    if not domains:
        raise RuntimeError("Mail.tm returned no available domains")

    chosen_domain = random.choice(domains)
    address = f"{random_string()}@{chosen_domain}"
    password = str(uuid.uuid4())

    session = requests.Session()

    try:
        r = session.post(f"{API_BASE}/accounts", json={"address": address, "password": password}, timeout=10)
    except Exception as e:
        raise RuntimeError(f"Network error when creating mailbox: {e}")

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create mailbox: HTTP {r.status_code} - {r.text[:200]}")

    try:
        r = session.post(f"{API_BASE}/token", json={"address": address, "password": password}, timeout=10)
    except Exception as e:
        raise RuntimeError(f"Network error when logging in: {e}")

    if r.status_code != 200:
        raise RuntimeError(f"Login failed: HTTP {r.status_code} - {r.text[:200]}")

    token = r.json().get("token")
    if not token:
        raise RuntimeError("Login response did not include a token")

    session.headers.update({"Authorization": f"Bearer {token}"})
    return session, address


def get_messages(session):
    try:
        r = session.get(f"{API_BASE}/messages", timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get('hydra:member', [])
    except Exception:
        return []


def read_message(session, msg_id):
    try:
        r = session.get(f"{API_BASE}/messages/{msg_id}", timeout=10)
    except Exception as e:
        raise RuntimeError(f"Network error while fetching message: {e}")
    if r.status_code != 200:
        raise RuntimeError(f"Failed to read message: HTTP {r.status_code} - {r.text[:200]}")
    try:
        return r.json()
    except Exception as e:
        raise RuntimeError(f"Failed to parse message JSON: {e}")


def delete_message_api(session, msg_id):
    try:
        r = session.delete(f"{API_BASE}/messages/{msg_id}", timeout=10)
    except Exception as e:
        raise RuntimeError(f"Network error while deleting message: {e}")
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Failed to delete message: HTTP {r.status_code} - {r.text[:200]}")
    return True


class InboxState:
    def __init__(self, session, address):
        self.session = session
        self.address = address
        self.messages = []
        self.lock = threading.Lock()

        self.selected = 0
        self.inbox_scroll = 0

        self.open_message = None
        self.msg_lines = []
        self.msg_scroll = 0

        self.status_message = None
        self.status_expire = 0

        self.running = True

    def update_messages(self):
        msgs = get_messages(self.session)
        with self.lock:
            self.messages = msgs
            if self.selected >= len(self.messages):
                self.selected = max(0, len(self.messages) - 1)
            if self.inbox_scroll > self.selected:
                self.inbox_scroll = self.selected


def poller(state: InboxState):
    while state.running:
        try:
            state.update_messages()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)



def init_colors():
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_WHITE)
    except Exception:
        pass


def safe_hline(stdscr, y, x, width):
    try:
        stdscr.hline(y, x, '-', width)
    except Exception:
        try:
            stdscr.addnstr(y, x, '-' * max(0, width), max(0, width))
        except Exception:
            pass


def wrap_text(text, width):
    lines = []
    for para in text.splitlines() or ['']:
        if not para:
            lines.append('')
            continue
        wrapped = textwrap.wrap(para, width=width) or ['']
        lines.extend(wrapped)
    return lines


def build_message_view(msg_json, width):
    lines = []
    subject = msg_json.get('subject') or '(no subject)'
    lines.append(f"Subject: {subject}")

    from_obj = msg_json.get('from') or {}
    from_name = from_obj.get('name') or ''
    from_addr = from_obj.get('address') or ''
    if from_name:
        lines.append(f"From: {from_name}")
        lines.append(f"Address: {from_addr}")
    else:
        lines.append(f"From: {from_addr}")

    to_list = msg_json.get('to') or []
    if to_list and isinstance(to_list, list):
        to_addrs = ', '.join([t.get('address', '') for t in to_list])
        lines.append(f"To: {to_addrs}")

    date = msg_json.get('createdAt') or msg_json.get('date') or ''
    if date:
        lines.append(f"Date: {date}")

    mid = msg_json.get('id')
    if mid is not None:
        lines.append(f"Message-ID: {mid}")

    attachments = msg_json.get('files') or []
    if attachments:
        fnames = ', '.join([a.get('filename', '<file>') for a in attachments])
        lines.append(f"Attachments: {fnames}")

    lines.append('')
    lines.append('---')
    lines.append('')

    body = msg_json.get('text')
    if not body:
        body = msg_json.get('intro')
    if not body:
        html_body = msg_json.get('html') or msg_json.get('htmlBody') or ''
        if html_body:
            body = re.sub('<[^<]+?>', '', html_body)
    if not body:
        body = '(no body)'

    body = html.unescape(body)
    body_lines = wrap_text(body, max(10, width))
    lines.extend(body_lines)
    return lines


def format_full_message_text(msg_json):
    parts = []
    subject = msg_json.get('subject') or '(no subject)'
    parts.append(f"Subject: {subject}")

    from_obj = msg_json.get('from') or {}
    from_name = from_obj.get('name') or ''
    from_addr = from_obj.get('address') or ''
    if from_name:
        parts.append(f"From: {from_name} <{from_addr}>")
    else:
        parts.append(f"From: {from_addr}")

    to_list = msg_json.get('to') or []
    if to_list and isinstance(to_list, list):
        to_addrs = ', '.join([t.get('address', '') for t in to_list])
        parts.append(f"To: {to_addrs}")

    date = msg_json.get('createdAt') or msg_json.get('date') or ''
    if date:
        parts.append(f"Date: {date}")

    mid = msg_json.get('id')
    if mid is not None:
        parts.append(f"Message-ID: {mid}")

    attachments = msg_json.get('files') or []
    if attachments:
        fnames = ', '.join([a.get('filename', '<file>') for a in attachments])
        parts.append(f"Attachments: {fnames}")

    parts.append('')
    parts.append('----------------------------------------')
    parts.append('')

    body = msg_json.get('text')
    if not body:
        body = msg_json.get('intro')
    if not body:
        html_body = msg_json.get('html') or msg_json.get('htmlBody') or ''
        if html_body:
            body = re.sub('<[^<]+?>', '', html_body)
    if not body:
        body = '(no body)'

    body = html.unescape(body)
    parts.append(body)
    parts.append('')
    return '\n'.join(parts)


def sanitize_filename(name, fallback):
    if not name:
        name = fallback
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    maxlen = 120
    if len(name) > maxlen:
        name = name[:maxlen]
    return name


def save_mail_to_disk(msg_json, home_dir):
    try:
        folder = os.path.join(home_dir, 'Documents', 'tempmail')
        os.makedirs(folder, exist_ok=True)
        subject = msg_json.get('subject') or ''
        mid = msg_json.get('id') or f"msg_{int(time.time())}"
        safe_name = sanitize_filename(subject, f"message_{mid}")
        filename = f"{safe_name}.txt"
        path = os.path.join(folder, filename)
        base, ext = os.path.splitext(path)
        counter = 1
        final_path = path
        while os.path.exists(final_path):
            final_path = f"{base}_{counter}{ext}"
            counter += 1
        content = format_full_message_text(msg_json)
        with open(final_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return final_path
    except Exception as e:
        raise RuntimeError(f"Failed to save message to disk: {e}")



def draw_inbox(stdscr, state: InboxState):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    header = f"Temp Mail (Mail.tm): {state.address}"
    try:
        stdscr.attron(curses.color_pair(1))
        stdscr.addnstr(0, 0, header.ljust(max(0, w - 1)), max(0, w - 1))
        stdscr.attroff(curses.color_pair(1))
    except Exception:
        stdscr.addnstr(0, 0, header[:max(0, w - 1)], max(0, w - 1))

    safe_hline(stdscr, 1, 0, w)

    help_line = " ↑/↓ move  Enter open  d delete  s save  q quit "
    try:
        stdscr.attron(curses.color_pair(3))
        stdscr.addnstr(2, 0, help_line[:max(0, w - 1)], max(0, w - 1))
        stdscr.attroff(curses.color_pair(3))
    except Exception:
        stdscr.addnstr(2, 0, help_line[:max(0, w - 1)], max(0, w - 1))

    content_y = 4
    content_h = max(0, h - content_y - 2)

    with state.lock:
        msgs = list(state.messages)
        sel = state.selected
        scroll = state.inbox_scroll

    if not msgs:
        stdscr.addnstr(content_y, 0, "Inbox is empty. Waiting for messages..."[:max(0, w - 1)], max(0, w - 1))
        draw_status(stdscr, state)
        stdscr.refresh()
        return

    if scroll < 0:
        scroll = 0
    if scroll > max(0, len(msgs) - 1):
        scroll = max(0, len(msgs) - 1)

    if sel < scroll:
        scroll = sel
    if sel >= scroll + content_h:
        scroll = sel - content_h + 1

    state.inbox_scroll = scroll

    for i in range(content_h):
        idx = scroll + i
        y = content_y + i
        if idx >= len(msgs):
            break
        m = msgs[idx]
        subj = m.get('subject') or '(no subject)'
        from_field = m.get('from', {}).get('address', '')
        date_field = m.get('createdAt', '')[:19]
        left = f"{from_field:<25.25}  {subj:<40.40}"
        line = f"{left}  {date_field}"
        try:
            if idx == sel:
                stdscr.attron(curses.color_pair(4))
                stdscr.addnstr(y, 0, line[:max(0, w - 1)], max(0, w - 1))
                stdscr.attroff(curses.color_pair(4))
            else:
                stdscr.addnstr(y, 0, line[:max(0, w - 1)], max(0, w - 1))
        except Exception:
            stdscr.addnstr(y, 0, line[:max(0, w - 1)], max(0, w - 1))

    status = f"{len(msgs)} messages — showing {scroll + 1}-{min(len(msgs), scroll + content_h)}"
    try:
        stdscr.attron(curses.color_pair(3))
        stdscr.addnstr(h - 1, 0, status[:max(0, w - 1)], max(0, w - 1))
        stdscr.attroff(curses.color_pair(3))
    except Exception:
        stdscr.addnstr(h - 1, 0, status[:max(0, w - 1)], max(0, w - 1))

    draw_status(stdscr, state)
    stdscr.refresh()


def draw_message(stdscr, state: InboxState):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    if state.open_message is None:
        return

    state.msg_lines = build_message_view(state.open_message, max(10, w - 2))

    header_title = state.msg_lines[0] if state.msg_lines else ''
    try:
        stdscr.attron(curses.color_pair(1))
        stdscr.addnstr(0, 0, header_title.ljust(max(0, w - 1)), max(0, w - 1))
        stdscr.attroff(curses.color_pair(1))
    except Exception:
        stdscr.addnstr(0, 0, header_title[:max(0, w - 1)], max(0, w - 1))

    safe_hline(stdscr, 1, 0, w)

    help_line = " ↑/↓ scroll  Backspace back  q quit "
    try:
        stdscr.attron(curses.color_pair(3))
        stdscr.addnstr(2, 0, help_line[:max(0, w - 1)], max(0, w - 1))
        stdscr.attroff(curses.color_pair(3))
    except Exception:
        stdscr.addnstr(2, 0, help_line[:max(0, w - 1)], max(0, w - 1))

    content_y = 4
    content_h = max(0, h - content_y - 2)

    if state.msg_scroll < 0:
        state.msg_scroll = 0
    if state.msg_scroll > max(0, len(state.msg_lines) - 1):
        state.msg_scroll = max(0, len(state.msg_lines) - 1)

    top = state.msg_scroll
    for i in range(content_h):
        idx = top + i
        y = content_y + i
        if idx >= len(state.msg_lines):
            break
        try:
            stdscr.addnstr(y, 0, state.msg_lines[idx][:max(0, w - 1)], max(0, w - 1))
        except Exception:
            stdscr.addnstr(y, 0, state.msg_lines[idx][:max(0, w - 1)], max(0, w - 1))

    status = f"Message lines {min(len(state.msg_lines), top + 1)}-{min(len(state.msg_lines), top + content_h)} of {len(state.msg_lines)}"
    try:
        stdscr.attron(curses.color_pair(3))
        stdscr.addnstr(h - 1, 0, status[:max(0, w - 1)], max(0, w - 1))
        stdscr.attroff(curses.color_pair(3))
    except Exception:
        stdscr.addnstr(h - 1, 0, status[:max(0, w - 1)], max(0, w - 1))

    draw_status(stdscr, state)
    stdscr.refresh()


def draw_status(stdscr, state: InboxState):
    if state.status_message and time.time() < state.status_expire:
        h, w = stdscr.getmaxyx()
        try:
            stdscr.attron(curses.color_pair(3))
            stdscr.addnstr(h - 1, 0, state.status_message[:max(0, w - 1)], max(0, w - 1))
            stdscr.attroff(curses.color_pair(3))
        except Exception:
            stdscr.addnstr(h - 1, 0, state.status_message[:max(0, w - 1)], max(0, w - 1))


def set_status(state: InboxState, text, duration=3.0):
    state.status_message = text
    state.status_expire = time.time() + duration



def confirm_dialog(stdscr, prompt, default_yes=True):
    h, w = stdscr.getmaxyx()
    win_w = min(60, w - 4)
    win_h = 7
    sx = max(2, (w - win_w) // 2)
    sy = max(2, (h - win_h) // 2)
    win = curses.newwin(win_h, win_w, sy, sx)
    win.keypad(True)

    choice = 0 if default_yes else 1

    while True:
        win.erase()
        try:
            win.border()
        except Exception:
            pass

        win.addnstr(1, 2, prompt[:win_w - 4], win_w - 4)

        yes_x = win_w // 2 - 10
        no_x = win_w // 2 + 4

        if choice == 0:
            win.attron(curses.color_pair(4))
            win.addnstr(3, yes_x, " Yes ", 5)
            win.attroff(curses.color_pair(4))
            win.addnstr(3, no_x, " No ", 4)
        else:
            win.addnstr(3, yes_x, " Yes ", 5)
            win.attron(curses.color_pair(4))
            win.addnstr(3, no_x, " No ", 4)
            win.attroff(curses.color_pair(4))

        win.addnstr(5, 2, "←/→ to choose   Enter confirm   Esc/q cancel", win_w - 4)
        win.refresh()

        ch = win.getch()
        if ch in (curses.KEY_LEFT, ord('<')):
            choice = 0
        elif ch in (curses.KEY_RIGHT, ord('>')):
            choice = 1
        elif ch in (10, 13):
            return choice == 0
        elif ch in (27, ord('q')):
            return False


def save_and_notify(state: InboxState, msg_json):
    try:
        home = os.path.expanduser('~')
        path = save_mail_to_disk(msg_json, home)
        set_status(state, f"Saved as {path}", duration=4.0)
    except Exception as e:
        set_status(state, f"Failed to save: {e}", duration=4.0)


def delete_and_notify(state: InboxState, msg_id):
    try:
        delete_message_api(state.session, msg_id)
        state.update_messages()
        set_status(state, "Message deleted", duration=3.0)
        with state.lock:
            if state.selected >= len(state.messages):
                state.selected = max(0, len(state.messages) - 1)
    except Exception as e:
        set_status(state, f"Delete failed: {e}", duration=4.0)


def main_curses(stdscr, state: InboxState):
    curses.curs_set(0)
    init_colors()
    stdscr.nodelay(True)
    stdscr.timeout(150)

    while True:
        if state.open_message is None:
            draw_inbox(stdscr, state)
        else:
            draw_message(stdscr, state)

        ch = stdscr.getch()
        if ch == -1:
            if state.status_message and time.time() > state.status_expire:
                state.status_message = None
            continue

        if ch in (ord('q'), 27):
            state.running = False
            break

        if state.open_message is None:
            if ch == curses.KEY_UP:
                with state.lock:
                    if state.selected > 0:
                        state.selected -= 1
                        if state.selected < state.inbox_scroll:
                            state.inbox_scroll = state.selected
            elif ch == curses.KEY_DOWN:
                with state.lock:
                    if state.selected < max(0, len(state.messages) - 1):
                        state.selected += 1
                        h, w = stdscr.getmaxyx()
                        content_h = max(0, h - 4 - 2)
                        if state.selected >= state.inbox_scroll + content_h:
                            state.inbox_scroll = state.selected - content_h + 1
            elif ch in (10, 13):
                with state.lock:
                    if 0 <= state.selected < len(state.messages):
                        mid = state.messages[state.selected].get('id')
                    else:
                        mid = None
                if mid is not None:
                    try:
                        msg = read_message(state.session, mid)
                        state.open_message = msg
                        state.msg_lines = build_message_view(msg, max(10, stdscr.getmaxyx()[1] - 2))
                        state.msg_scroll = 0
                    except Exception as e:
                        state.open_message = {'subject': 'Error', 'from': {'address': 'system'}, 'text': f'Failed to fetch message: {e}'}
                        state.msg_lines = build_message_view(state.open_message, max(10, stdscr.getmaxyx()[1] - 2))
                        state.msg_scroll = 0
            elif ch in (127, curses.KEY_BACKSPACE, 8):
                pass
            elif ch in (ord('d'), ord('D')):
                with state.lock:
                    if 0 <= state.selected < len(state.messages):
                        mid = state.messages[state.selected].get('id')
                    else:
                        mid = None
                if mid is None:
                    set_status(state, "No message selected to delete", duration=3.0)
                else:
                    confirm = confirm_dialog(stdscr, "Delete this message?", default_yes=True)
                    if confirm:
                        delete_and_notify(state, mid)
                    else:
                        set_status(state, "Delete canceled", duration=2.0)
            elif ch in (ord('s'), ord('S')):
                with state.lock:
                    if 0 <= state.selected < len(state.messages):
                        mid = state.messages[state.selected].get('id')
                    else:
                        mid = None
                if mid is None:
                    set_status(state, "No message selected to save", duration=3.0)
                else:
                    try:
                        msg = read_message(state.session, mid)
                        threading.Thread(target=save_and_notify, args=(state, msg), daemon=True).start()
                    except Exception as e:
                        set_status(state, f"Failed to fetch for save: {e}", duration=4.0)
        else:
            if ch == curses.KEY_UP:
                if state.msg_scroll > 0:
                    state.msg_scroll -= 1
            elif ch == curses.KEY_DOWN:
                if state.msg_scroll < max(0, len(state.msg_lines) - 1):
                    h, w = stdscr.getmaxyx()
                    content_h = max(0, h - 4 - 2)
                    if state.msg_scroll + content_h < len(state.msg_lines):
                        state.msg_scroll += 1
            elif ch in (127, curses.KEY_BACKSPACE, 8):
                state.open_message = None
                state.msg_lines = []
                state.msg_scroll = 0


def main():
    print("Creating temporary mailbox (Mail.tm)...")
    try:
        session, address = create_account()
    except Exception as e:
        print(f"Failed to create mailbox: {e}")
        return

    print(f"Your temporary mailbox: {address}")

    state = InboxState(session, address)
    state.update_messages()

    t = threading.Thread(target=poller, args=(state,), daemon=True)
    t.start()

    try:
        curses.wrapper(main_curses, state)
    finally:
        state.running = False
        t.join(timeout=1)


if __name__ == '__main__':
    main()
