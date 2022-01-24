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


def get_status(credentials):
    logger.debug('\n\nGET_STATUS')
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
    logger.debug('waiting 5 sec')
    time.sleep(5)

    logger.debug('processing source code')
    lastBatch = driver.find_element(By.XPATH, "(//span[@id='spanBatches']/div)[last()]")
    source = lastBatch.get_attribute('innerHTML')

    status = re.findall(r'Status:\s*(<b>)?\s*(.*?)\s*(</b>)?\s*<br>', source, re.DOTALL)
    logger.debug(f'status: {status}')
    status = status[0][1]

    topic = re.findall(r'following theme:\s*(<b>)?\s*(.*?)\s*(</b>)?\s*<br>', source, re.DOTALL)
    logger.debug(f'topic: {topic}')
    topic = topic[0][1]

    puzzles = re.findall(r'Number of puzzles:\s*<b>(.*?)</b>', source, re.DOTALL)
    logger.debug(f'puzzles: {puzzles}')
    puzzles = puzzles[0]

    res = {'status': status, 'topic': topic, 'puzzles': puzzles}
    logger.debug('closing driver')
    driver.close()
    return res


def send_to_tg(st):
    bot = telebot.TeleBot(BOT_TOKEN)
    msg = f'Username: {st["username"]}\n' \
          f'Status: <b>{st["status"]}</b>\n' \
          f'Topic: {st["topic"]}\n' \
          f'Puzzles: {st["puzzles"]}'
    bot.send_message(USER_ID, msg, parse_mode='html')
    bot.stop_bot()


def process_status(st, last_statuses):
    if last_statuses.get(st['username'], None) == st:
        return
    last_statuses[st['username']] = st
    send_to_tg(st)


if __name__ == "__main__":
    BOT_TOKEN = os.environ['BOT_TOKEN']
    USER_ID = int(os.environ['USER_ID'])
    ACCOUNTS = json.load(open('accounts.json'))
    last_statuses = dict()
    while True:
        wait = 600
        for acc in ACCOUNTS:
            try:
                status = get_status(acc['credentials'])
                status['username'] = acc['username']
                logger.debug(status)
                process_status(status, last_statuses)
            except Exception as e:
                logger.debug(f'EXCEPTION: {e}')
                wait = 120
        time.sleep(wait)
