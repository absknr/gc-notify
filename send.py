import platform
import json
import os
import datetime

import telegram

from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.utils import ChromeType

with open("settings.json") as f:
    settings = json.load(f)


class FindElement:
    def __init__(self, driver, wait_timeout=10):
        self.driver = driver
        self.wait_timeout = wait_timeout

    def _wait_until(self, predicate):
        return WebDriverWait(self.driver, self.wait_timeout).until(predicate)

    def by_xpath(self, xpath, get_all=False):
        find_element_type = (
            self.driver.find_elements if get_all else self.driver.find_element
        )
        return find_element_type(by=By.XPATH, value=xpath)

    def by_wait_until_presence(self, xpath, of_all=False):
        presence_type = (
            EC.presence_of_all_elements_located
            if of_all
            else EC.presence_of_element_located
        )
        return self._wait_until(presence_type((By.XPATH, xpath)))


class Dustbin:
    RESTMUELLTONNE = "black"
    PAPIERTONNE = "blue"
    BIOTONNE = "brown"


class TelegramBot:
    def __init__(self, bot_token, chat_id=None, msg_template=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.msg_template = msg_template

        self.bot = telegram.Bot(token=self.bot_token)

    def send_msg(self, **kwargs):
        assert self.chat_id != None
        assert self.msg_template != None

        msg = self.msg_template.format(**kwargs)

        self.bot.send_message(
            text=msg, chat_id=self.chat_id, parse_mode=telegram.ParseMode.MARKDOWN
        )


def extract_date(date_obj, strip=" *"):
    return date_obj.text.strip(strip)


def strp_date(date, format="%d.%m.%Y"):
    return datetime.datetime.strptime(date, format).date()


def date_format(date, format="%d/%m/%Y"):
    return date.strftime(format)


def is_tomorrow(date):
    return datetime.date.today() == date - datetime.timedelta(days=1)


def get_template(name="slw4a"):
    with open(f"msg_templates/{name}.txt") as f:
        return f.read()


def crawl():
    # Input locations
    form_xpath = "//form[@name='TargetForm']"
    ort_xpath = f"{form_xpath}//select[@name='Ort']"
    strasse_xpath = f"{form_xpath}//select[@name='Strasse']"
    hausnummer_xpath = f"{form_xpath}//input[@name='Hausnummer']"
    hausnummerzusatz_xpath = f"{form_xpath}//input[@name='Hausnummerzusatz']"
    weiter_btn_xpath = f"{form_xpath}//a[@name='forward']"

    haus_details = settings["haus_details"]
    ort = haus_details["ort"]
    strasse = haus_details["strasse"]
    nummer = haus_details["nummer"]
    nummerzusatz = haus_details["nummerzusatz"]

    strasse_option_xpath = (
        f"{form_xpath}//select[@name='Strasse']/option[@value='{strasse}']"
    )
    restmuell_parent_xpath = "//div[@id='terminerestmuell']"

    # Init
    chrome_driver_manager = (
        ChromeDriverManager().install()
        if platform.system() == "Darwin"
        else ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    )

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(
        service=Service(chrome_driver_manager), chrome_options=chrome_options
    )
    find_element = FindElement(driver)

    # Extract collection dates
    driver.get(settings["awg_url"])

    # Select ort
    ort_select = Select(find_element.by_xpath(ort_xpath))
    ort_select.select_by_value(ort)

    # Select strasse
    find_element.by_wait_until_presence(strasse_option_xpath)
    strasse_select = Select(find_element.by_xpath(strasse_xpath))
    strasse_select.select_by_value(strasse)

    # Enter hausnummer
    hausnummer_input = find_element.by_wait_until_presence(hausnummer_xpath)
    hausnummer_input.send_keys(nummer)

    # Enter hausnummerzusatz
    hausnummerzusatz_input = find_element.by_wait_until_presence(hausnummerzusatz_xpath)
    hausnummerzusatz_input.send_keys(nummerzusatz)

    # Submit the form
    weiter_btn = find_element.by_xpath(weiter_btn_xpath)
    weiter_btn.click()

    # Wait until output page loads
    find_element.by_wait_until_presence(restmuell_parent_xpath)

    # Output locations
    restmuell_xpath = f"{restmuell_parent_xpath}//td[@name='WasteDisposalServicesDialogComponent.DateRM']"
    papier_xpath = "//div[@id='terminepapier']//td[@name='WasteDisposalServicesDialogComponent.DatePapier']"
    bio_xpath = "//div[@id='terminebio']//td[@name='WasteDisposalServicesDialogComponent.DateBio']"

    restmuell_dates = [
        strp_date(extract_date(date_obj))
        for date_obj in find_element.by_xpath(restmuell_xpath, get_all=True)
    ]
    papier_dates = [
        strp_date(extract_date(date_obj))
        for date_obj in find_element.by_xpath(papier_xpath, get_all=True)
    ]
    bio_dates = [
        strp_date(extract_date(date_obj))
        for date_obj in find_element.by_xpath(bio_xpath, get_all=True)
    ]

    latest_restmuell_date, latest_papier_date, latest_bio_date = (
        restmuell_dates[:1],
        papier_dates[:1],
        bio_dates[:1],
    )

    telegram = TelegramBot(
        bot_token=os.environ["BOT_TOKEN"],
        chat_id=int(os.environ["SLW4A_CHAT_ID"]),
        msg_template=get_template(),
    )

    if latest_restmuell_date and is_tomorrow(latest_restmuell_date[0]):
        telegram.send_msg(
            tomorrow_date=date_format(latest_restmuell_date[0]),
            dustbin_type=Dustbin.RESTMUELLTONNE,
        )

    if latest_papier_date and is_tomorrow(latest_papier_date[0]):
        telegram.send_msg(
            tomorrow_date=date_format(latest_papier_date[0]),
            dustbin_type=Dustbin.PAPIERTONNE,
        )

    if latest_bio_date and is_tomorrow(latest_bio_date[0]):
        telegram.send_msg(
            tomorrow_date=date_format(latest_bio_date[0]),
            dustbin_type=Dustbin.BIOTONNE,
        )


if __name__ == "__main__":
    crawl()
