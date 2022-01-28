from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import os
import re
import json
import telebot
import logging


logging.basicConfig()
logging.getLogger('TeleBot').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    logger.debug(f'\n\nGET_STATUSES {username}')
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


if __name__ == "__main__":
    BOT_TOKEN = os.environ['BOT_TOKEN']  # Make sure you have a chat with this bot
    USER_ID = int(os.environ['USER_ID'])  # Write to @RawDataBot and get your ID or put ID of your chat with this bot
    ACCOUNTS = json.load(open('accounts.json'))  # Format as in accounts.default.json
    last_statuses = dict()
    while True:
        wait = 600
        wait_page_loading = 5
        for acc in ACCOUNTS:
            try:
                statuses = get_statuses(acc['credentials'], acc['username'], wait_page_loading)
                for status in statuses:
                    process_status(status, last_statuses)
            except Exception as e:
                logger.exception("EXCEPTION")
                wait = 120
                wait_page_loading = 20
        time.sleep(wait)
