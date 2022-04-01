from selenium import webdriver
import time
import os
import json
import requests
import heapq
import telebot
import logging


logging.basicConfig()
logging.getLogger('TeleBot').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def start_driver():
    logger.debug('Starting driver')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(executable_path=f'{os.getcwd()}/chromedriver97', options=chrome_options)
    logger.debug('Driver getting nearcrowd starfish')
    driver.get("https://nearcrowd.com/starfish")
    return driver


def get_raw_batches(creds):
    driver = start_driver()
    logger.debug('Passing creds')
    for key in creds:
        driver.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", key, creds[key])
    logger.debug('Refreshing')
    driver.refresh()
    time.sleep(1)

    logger.debug('Executing super script')
    hashcode = driver.execute_script('''return await window.contract.account.signTransaction("app.nearcrowd.near", [nearApi.transactions.functionCall("starfish", {}, 0, 0)]).then(arr => {
      let encodedTx = btoa(String.fromCharCode.apply(null, arr[1].encode()));
      return encodeURIComponent(encodedTx)
    })''')
    logger.debug('Getting batches info')
    raw_batches = requests.get('https://nearcrowd.com/starfish/batches/' + hashcode, verify=False).json()
    logger.debug('Closing driver')
    driver.close()
    return raw_batches


def prettify_batch(index, topic, puzzles, comment, reward, reward_total, status):
    text = f'''
Batch: {index}
Status: <b>{status}</b>
Topic: {topic}
Puzzles: {puzzles}
Reward: Ⓝ {reward} — Ⓝ {reward_total} in total
'''.strip()
    if comment is not None:
        text += f'\nComment: {comment}'
    return text


def send_to_tg(msg):
    logger.debug(f'Sending to TG: {msg}')
    bot = telebot.TeleBot(BOT_TOKEN)
    bot.send_message(USER_ID, msg, parse_mode='html')
    bot.stop_bot()


def process_batch(batch, last_batches, username):
    logger.debug(f'Parsing batch: {batch}')
    topic = batch['assigned_theme']
    puzzles = int(batch['batch_limit'])
    index = int(batch['batch_ord'])
    comment = batch['comment']
    reward = int(batch['micro_near']) / 1000
    reward_total = round(puzzles * reward, 3)

    can_submit = batch['can_submit']
    cant_submit_until = 'Cannot be submitted until ' + batch['locked_until']
    statuses = ['Not submitted' if can_submit else cant_submit_until, 'Pending Review', 'ACCEPTED', 'REJECTED']
    status = statuses[int(batch['status'])]

    info = [index, topic, puzzles, comment, reward, reward_total, status]
    old_batches = last_batches.get((username, index))
    if old_batches == info:
        return
    last_batches[(username, index)] = info

    if old_batches is None:
        if status.upper() == 'ACCEPTED':
            return
        title = f'New batch at {username}'
    else:
        title = f'Batch update at {username}'

    text = prettify_batch(*info)
    text = title + '\n\n' + text
    send_to_tg(text)


def get_balance(username):
    logger.debug('Getting balance')
    url = 'https://rpc.mainnet.near.org'
    data = {
        "method": "query",
        "params": {
            "request_type": "view_account",
            "account_id": username,
            "finality": "optimistic"
        },
        "id": 1,
        "jsonrpc": "2.0"
    }
    resp = requests.post(url, json=data).json()

    if 'error' in resp or 'result' not in resp:
        raise Exception(f'No result in balance request: {resp}')
    res = resp['result']
    logger.debug(f'Wallet status: {res}')
    balance = max(0.0, int(res['amount']) / 1e24 - res['storage_usage'] / 1e5 - 0.05)
    balance = round(balance, 3)
    return balance


def process_balance(balance, last_balances, username):
    logger.debug(f'Processing balance: {balance}')
    old_balance = last_balances.get(username)
    if old_balance == balance:
        return
    last_balances[username] = balance

    if old_balance is None:
        text = f'Ⓝ {balance}'
    else:
        delta = round(balance - old_balance, 3)
        sign = '-' if delta < 0 else '+'
        delta = abs(delta)
        if delta <= 0.002:  # 0.001 - approximate price of one transaction
            return
        text = f'Ⓝ {old_balance} {sign} Ⓝ {delta} = Ⓝ {balance}'

    title = f'Balance at {username}'
    text = title + '\n' + text
    send_to_tg(text)


def event_id():
    global EVENT_ID
    EVENT_ID += 1
    logger.debug(f'New event: {EVENT_ID}')
    return EVENT_ID


def make_events(accounts):
    events = []
    for acc_type in accounts:
        events += [(0.0, event_id(), {'type': acc_type, 'account': acc}) for acc in accounts[acc_type]]
    heapq.heapify(events)
    return events


if __name__ == "__main__":
    BOT_TOKEN = os.environ['BOT_TOKEN']  # Make sure you have a chat with this bot
    USER_ID = int(os.environ['USER_ID'])  # Write to @RawDataBot and get your ID or put ID of your chat with this bot
    ACCOUNTS = json.load(open('accounts.json'))  # Format as in accounts.default.json

    WAIT_EVENT_STARFISH = {'DEFAULT': 600, 'EXCEPTION': 120}
    WAIT_EVENT_WALLETS = {'DEFAULT': 300, 'EXCEPTION': 120}

    EVENT_ID = 0
    last_batches = dict()
    last_balances = dict()

    events = make_events(ACCOUNTS)

    while True:
        event = heapq.heappop(events)
        wait = max(0.0, event[0] - time.time())
        logger.debug(f'Waiting {wait}')
        time.sleep(wait)
        ev = event[2]
        acc = ev['account']

        if ev['type'] == 'starfish':
            try:
                batches = get_raw_batches(acc['credentials'])
                for batch in batches:
                    process_batch(batch, last_batches, acc['username'])
            except Exception as e:
                logger.exception(e)
                wait_until = time.time() + WAIT_EVENT_STARFISH['EXCEPTION']
            else:
                wait_until = time.time() + WAIT_EVENT_STARFISH['DEFAULT']
            heapq.heappush(events, (wait_until, event_id(), ev))

        elif ev['type'] == 'wallets':
            try:
                balance = get_balance(acc)
                process_balance(balance, last_balances, acc)
            except Exception as e:
                logger.exception(e)
                wait_until = time.time() + WAIT_EVENT_WALLETS['EXCEPTION']
            else:
                wait_until = time.time() + WAIT_EVENT_WALLETS['DEFAULT']
            heapq.heappush(events, (wait_until, event_id(), ev))

        else:
            logger.debug(f'Unknown account type: {ev["type"]}')
