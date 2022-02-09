from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import os
import re
import json
import telebot
import logging
import requests
import heapq


logging.basicConfig()
logging.getLogger('TeleBot').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_wallet_balance(wallet_name):
    url = 'https://rpc.mainnet.near.org'
    data = {
        "method": "query",
        "params": {
            "request_type": "view_account",
            "account_id": wallet_name,
            "finality": "optimistic"
        },
        "id": 1,
        "jsonrpc": "2.0"
    }
    resp = requests.post(url, json=data).json()
    logger.debug(f'{wallet_name} balance: {resp}')
    if 'error' in resp or 'result' not in resp:
        raise Exception(resp)
    res = resp['result']
    balance = max(0.0, int(res['amount']) / 1e24 - res['storage_usage'] / 1e5 - 0.05)
    balance = round(balance, 3)
    return balance


def open_page(credentials, wait_page_loading):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    logger.debug('starting driver')
    driver = webdriver.Chrome(executable_path=f'{os.getcwd()}/chromedriver97', options=chrome_options)
    time.sleep(1)

    logger.debug('getting page')
    driver.get("https://nearcrowd.com/starfish")
    logger.debug('passing credentials')

    for key in credentials:
        driver.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", key, credentials[key])
    time.sleep(1)
    logger.debug('refreshing')
    driver.refresh()
    logger.debug(f'waiting {wait_page_loading} sec')
    time.sleep(wait_page_loading)

    return driver


def parse_batch(source, username):
    logger.debug(f'parsing new batch')

    status = re.findall(r'Status:\s*(<b>)?\s*(<font .*?>)?\s*(.*?)\s*(</font>)?\s*(</b>)?\s*<br>', source, re.DOTALL)[0][2]
    topic = re.findall(r'following theme:\s*(<b>)?\s*(.*?)\s*(</b>)?\s*<br>', source, re.DOTALL)[0][1]
    puzzles = re.findall(r'Number of puzzles:\s*<b>(.*?)</b>', source, re.DOTALL)[0]
    batch = re.findall(r'Batch (\d+)', source, re.DOTALL)[0]
    reward = re.findall(r'Reward per puzzle:\s*<b>(.*?)</b>', source, re.DOTALL)[0]

    reward = reward.strip().split()
    currency = reward[0]
    reward_per_one = float(reward[-1])
    number_of_puzzles = int(puzzles)
    reward_for_all = round(reward_per_one * number_of_puzzles, 2)
    reward = f'{currency} {reward_per_one} — {currency} {reward_for_all} in total'

    res = {'status': status, 'topic': topic, 'puzzles': puzzles, 'reward': reward, 'batch': batch, 'username': username}
    logger.debug(f'batch {batch} parsed')
    logger.debug(res)
    return res


def get_statuses(credentials, username, wait_page_loading):
    logger.debug(f'GET_STATUSES {username}')
    driver = open_page(credentials, wait_page_loading)

    logger.debug('processing source code')
    batches = driver.find_elements(By.XPATH, "(//span[@id='spanBatches']/div)")
    if len(batches) == 0:
        raise Exception("No batches found!")
    statuses = []
    for batch in batches:
        source = batch.get_attribute('innerHTML')
        statuses.append(parse_batch(source, username))

    logger.debug('closing driver')
    driver.close()
    return statuses


def send_to_tg(msg):
    bot = telebot.TeleBot(BOT_TOKEN)
    bot.send_message(USER_ID, msg, parse_mode='html')
    bot.stop_bot()


def process_status(st, last_statuses):
    key = (st['username'], st['batch'])
    if last_statuses.get(key, None) == st:
        return
    title = 'New batch' if key not in last_statuses else 'Batch update'
    last_statuses[key] = st

    msg = f'{title} at {st["username"]}!\n\n' \
          f'Batch: {st["batch"]}\n' \
          f'Status: <b>{st["status"]}</b>\n' \
          f'Topic: {st["topic"]}\n' \
          f'Puzzles: {st["puzzles"]}\n' \
          f'Reward: {st["reward"]}'

    if title.lower() == 'new batch' and st['status'].lower() == 'accepted':
        return
    send_to_tg(msg)


def process_wallet_balance(wallet_name, balance, last_balances):
    old_balance = last_balances.get(wallet_name, None)
    if old_balance == balance:
        return
    last_balances[wallet_name] = balance
    if old_balance is None:
        msg = f'Balance at {wallet_name}\n' \
              f'Ⓝ {balance}'
    else:
        delta = round(balance - old_balance, 3)
        sign = '-' if delta < 0 else '+'
        delta = abs(delta)
        msg = f'Balance at {wallet_name}\n' \
              f'Ⓝ {old_balance} {sign} Ⓝ {delta} = Ⓝ {balance}'

    send_to_tg(msg)


def event_id():
    global EVENT_ID
    EVENT_ID += 1
    return EVENT_ID


if __name__ == "__main__":
    BOT_TOKEN = os.environ['BOT_TOKEN']  # Make sure you have a chat with this bot
    USER_ID = int(os.environ['USER_ID'])  # Write to @RawDataBot and get your ID or put ID of your chat with this bot
    ACCOUNTS = json.load(open('accounts.json'))  # Format as in accounts.default.json

    WAIT_PAGE_LOADING = {'DEFAULT': 5, 'EXCEPTION': 20}
    WAIT_EVENT_STARFISH = {'DEFAULT': 600, 'EXCEPTION': 120}
    WAIT_EVENT_WALLETS = {'DEFAULT': 300, 'EXCEPTION': 120}
    EVENT_ID = 0

    last_statuses = dict()
    last_balances = dict()

    events = [(0.0, event_id(), {'type': 'starfish', 'account': acc}) for acc in ACCOUNTS['starfish']]
    events += [(0.0, event_id(), {'type': 'wallets', 'account': acc}) for acc in ACCOUNTS['wallets']]
    heapq.heapify(events)

    while True:
        event = heapq.heappop(events)
        wait = max(0.0, event[0] - time.time())
        logger.debug(f'\n\nWAITING: {wait} sec')
        time.sleep(wait)
        logger.debug(f'NEW EVENT: {event}\n')

        ev = event[2]
        acc_type = ev['type']
        acc = ev['account']

        if acc_type == 'starfish':
            wait_page_loading = ev.get('wait_page_loading', WAIT_PAGE_LOADING['DEFAULT'])
            try:
                statuses = get_statuses(acc['credentials'], acc['username'], wait_page_loading)
                for status in statuses:
                    process_status(status, last_statuses)
            except Exception as e:
                logger.exception("EXCEPTION STATUSES")
                wait_until = time.time() + WAIT_EVENT_STARFISH['EXCEPTION']
                ev['wait_page_loading'] = WAIT_PAGE_LOADING['EXCEPTION']
            else:
                wait_until = time.time() + WAIT_EVENT_STARFISH['DEFAULT']
                ev['wait_page_loading'] = WAIT_PAGE_LOADING['DEFAULT']
            heapq.heappush(events, (wait_until, event_id(), ev))

        elif acc_type == 'wallets':
            try:
                wallet_name = acc
                if wallet_name is not None:
                    balance = get_wallet_balance(wallet_name)
                    process_wallet_balance(wallet_name, balance, last_balances)
            except Exception as e:
                logger.exception("EXCEPTION BALANCES")
                wait_until = time.time() + WAIT_EVENT_WALLETS['EXCEPTION']
            else:
                wait_until = time.time() + WAIT_EVENT_WALLETS['DEFAULT']
            heapq.heappush(events, (wait_until, event_id(), ev))

        else:
            logger.debug(f'Unknown account type: {acc_type}')
