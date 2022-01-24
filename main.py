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


def get_status(credentials, username):
    logger.debug(f'\n\nGET_STATUS {username}')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    logger.debug('starting driver')
    driver = webdriver.Chrome(executable_path=f'{os.getcwd()}/chromedriver97', chrome_options=chrome_options)
    time.sleep(1)

    logger.debug('getting page')
    driver.get("https://nearcrowd.com/starfish")
    logger.debug('passing credentials')

    for key in credentials:
        driver.execute_script("window.localStorage.setItem(arguments[0], arguments[1]);", key, credentials[key])
    time.sleep(1)
    logger.debug('refreshing')
    driver.refresh()
    logger.debug('waiting 15 sec')
    time.sleep(15)

    logger.debug('processing source code')
    lastBatch = driver.find_element(By.XPATH, "(//span[@id='spanBatches']/div)[last()]")
    source = lastBatch.get_attribute('innerHTML')

    status = re.findall(r'Status:\s*(<b>)?\s*(.*?)\s*(</b>)?\s*<br>', source, re.DOTALL)[0][1]
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

    res = {'status': status, 'topic': topic, 'puzzles': puzzles, 'reward': reward, 'batch': batch}
    logger.debug('closing driver')
    driver.close()
    return res


def send_to_tg(msg):
    bot = telebot.TeleBot(BOT_TOKEN)
    bot.send_message(USER_ID, msg, parse_mode='html')
    bot.stop_bot()


def process_status(st, last_statuses):
    if last_statuses.get(st['username'], None) == st:
        return
    last_statuses[st['username']] = st

    msg = f'Username: {st["username"]}\n' \
          f'Status: <b>{st["status"]}</b>\n' \
          f'Topic: {st["topic"]}\n' \
          f'Batch: {st["batch"]}\n' \
          f'Reward: {st["reward"]}\n' \
          f'Puzzles: {st["puzzles"]}'

    send_to_tg(msg)


if __name__ == "__main__":
    BOT_TOKEN = os.environ['BOT_TOKEN']  # Make sure you have a chat with this bot
    USER_ID = int(os.environ['USER_ID'])  # Write to @RawDataBot and get your ID or put ID of your chat with this bot
    ACCOUNTS = json.load(open('accounts.json'))  # Format as in accounts.default.json
    last_statuses = dict()
    while True:
        wait = 600
        for acc in ACCOUNTS:
            try:
                status = get_status(acc['credentials'], acc['username'])
                status['username'] = acc['username']
                logger.debug(status)
                process_status(status, last_statuses)
            except Exception as e:
                logger.exception("EXCEPTION")
                wait = 120
        time.sleep(wait)
