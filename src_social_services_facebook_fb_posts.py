﻿"""@package docstring"""

import copy
import multiprocessing as mp
import multiprocessing.dummy as dummy_mp
import os
import re
from datetime import datetime, timedelta
from string import Template
from time import sleep

import pymorphy2
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

FB_LOGIN = '89026051080'
FB_PASSWORD = 'z6A-8Wd-XiV-VNY'

# Для истории. Попытки выделить ленты в разных сообществах, для групп и пользователей
# timeline_xpath = '//div[@data-pagelet="ProfileTimeline"]'
# Для публичных страниц может быть актуально такое
# document.querySelector('div[role="feed"]')
# document.querySelectorAll('div[role="main"]')[1].children[0]

posts_xpath = "div[role='article'][aria-posinset]"
post_more_button = './/div[contains(text(), "Ещё")]'
post_comment_more_button = './/span[starts-with(text(), "Посмотреть ещё")]'
post_comment_more_button2 = './/span[starts-with(text(), "Показать ещё")]'

textToDate_months = {
    'января': 1,
    'февраля': 2,
    'марта': 3,
    'фпреля': 4,
    'мая': 5,
    'июня': 6,
    'июля': 7,
    'августа': 8,
    'сентября': 9,
    'октября': 10,
    'ноября': 11,
    'декабря': 12
}


def textToDate(text):
    date = datetime.today()
    if text:
        s = text.split()
        t = int(s[0])
        if 'ч.' in s[1]:
            date -= timedelta(hours=t)
        elif 'д.' in s[1]:
            date -= timedelta(days=t)
        elif 'мин.' in s[1]:
            date -= timedelta(minutes=t)
        else:
            date = datetime(date.year, int(textToDate_months.get(s[1], date.month)), t)
    return date


post_xpath = "//div[@class='_5pcr userContentWrapper']"
comment_prl_xpath = "//a[@class='see_more_link']"
comment_area_ol_xpath = "//a[contains(text(), 'Комментарии')]"
comment_area_prl_xpath = "//a[contains(@class, 'CommentsPager') or contains(@data-testid, 'CommentsPager')]"

answer_area_prl_xpath = "//a[@class='UFICommentLink']"
post_likes_class = '_3chu'
login_url = 'https://www.facebook.com/login'
base_url = 'https://www.facebook.com'

js_click_script = Template("""let link = document.evaluate("$XPATH", document, null, 
XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
if (link != null && link.style.display != 'none') {
link.click(); return 0;
} else return -1;""")

post_prl_xpath = "//div[role='button' and contains(., 'Ещё')]"
js_post_prl_sqript = Template("""let link = document.evaluate("$XPATH", document, null, 
XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
if (link != null) {
    parent = link.closest(".text_exposed_root");
    if (parent != null && parent.classList.contains("text_exposed") != true) {
        link.click();
        return 0;
    }
}
return -1;""")


class Comment:

    def get_id(self, comment_soup):
        """Get comment's ID

        :param comment_soup: (object) comment soup

        :return: (str) comment's ID (None if error)
        """
        try:
            comment_url = comment_soup.find('a', attrs={'href': re.compile('.*\?comment_id=.*')})['href']
            return re.search('[0-9]+', re.search('comment_id=[0-9]+', comment_url).group(0)).group(0)
        except Exception as e:
            print(e)
            print('crashed while reading comment id')
            return None

    def get_icon_url(self, comment_soup):
        """Get comment author's avatar

        :param comment_soup: (object) comment soup

        :return: (str) author's avatar url (None if error)
        """
        try:
            return comment_soup.find('img')['src']
        except Exception as e:
            print(e)
            print('crashed while reading comment icon')
            return None

    def get_date(self, comment_soup):
        """Get comment's date

        :param comment_soup: (object) comment soup

        :return: (int) Unix Timestamp (None if error)
        """
        try:
            date = comment_soup.find('abbr')['data-utime']
            return datetime.fromtimestamp(int(date))
        except Exception as e:
            print(e)
            print('crashed while searching date')
            return None
        print('fe')

    def get_message(self, comment_soup):
        """Get comment's text

        :param comment_soup: (object) comment soup

        :return: (str) comment's text (None if error)
        """
        try:
            content = comment_soup.find('span', attrs={'class': re.compile('(_3l3x)|(UFICommentBody)')}).find('span')
            return content.text
        except Exception as e:
            print(e)
            print('crashed while reading comment')
            return None

    def get_owner_id(self, comment_soup):
        """Get comment author's ID

        :param comment_soup: (object) comment soup

        :return: (str) author's ID (None if error)
        """
        try:
            owner1 = comment_soup.findAll('a', attrs={
                'data-hovercard': re.compile('.*\/user\.php\?id=.*')})
            owner2 = comment_soup.findAll('a', attrs={
                'href': re.compile('(.*\/user\.php\?id=.*|.*\/profile\.php\?id=.*)')})
            if len(owner1) > 0:
                return re.search('[0-9]+',
                                 re.search('user\.php\?id=[0-9]+', owner1[0]['data-hovercard']).group(0)).group(0)
            if len(owner2) > 0:
                return re.search('[0-9]+', re.search('user\.php\?id=[0-9]+', owner2[0]['href']).group(0)).group(0)
            else:
                return None
        except Exception as e:
            print(e)
            print('crashed while searching comment owner id')
            return None

    def __init__(self, comment_soup):
        """Initialize

        :attr comment_soup: (object) comment soup
        """
        self.soup = comment_soup
        self.id = self.get_id(comment_soup)
        self.icon = self.get_icon_url(comment_soup)
        self.date = self.get_date(self.soup)
        self.owner = self.get_owner_id(comment_soup)
        self.message = self.get_message(comment_soup)

    def to_dict(self):
        """Format to dict

        :return: (dict) comment
        """
        return {'id': self.id,
                'avatar': self.icon,
                'owner': self.owner,
                'date': (None if self.date is None else self.date.timestamp()),
                'text': self.message}


class Post:

    def get_message(self, post_soup):
        """Get post's text

        :param post_soup: (object) post soup

        :return: (str) post's text ('' if error)
        """
        try:
            content = post_soup.find('div', attrs={'class': re.compile(r'.*userContent.*')}).findAll('p')
            return '\n'.join(list(map(lambda x: x.text, content)))
        except Exception as e:
            print(e)
            print('crashed while reading message')
            return ''

    def get_id(self, post_soup):
        """Get post's ID

        :param post_soup: (object) post soup

        :return: (str) '' if error
        """
        try:
            post_url = post_soup.find('a', attrs={'href': re.compile(r'.*/posts/.*')})['href']
            return re.search(r'/posts/([0-9]+)', post_url).group(1)
        except Exception as e:
            print(e)
            print('crashed while reading id')
            # return ''
            pass

        try:
            img_url = post_soup.find('a', attrs={'href': re.compile(r'.*/photos/[a-z]*\.[0-9]+/[0-9]+/')})['href']
            return re.search(r'/photos/[a-z]+\.[0-9]+/([0-9]+)/', img_url).group(1)
        except Exception as e:
            print(e)
            pass

        try:
            permalink = post_soup.find('a', attrs={'href': re.compile(r'.*/permalink/[0-9]+/.*')})['href']
            return re.search(r'.*/permalink/([0-9]+)/.*', permalink).group(1)
        except Exception as e:
            print(e)
            return ''

    def get_icon_url(self, post_soup):
        """Get user's/group's avatar

        :param post_soup: (object) post soup

        :return: (str) avatar url (None if error)
        """
        try:
            return post_soup.find('img')['src']
        except Exception as e:
            print(e)
            print('crashed while reading comment icon')
            return None

    def get_date(self, post_soup):
        """Get post's date

        :param post_soup: (object) post soup

        :return: (int) Unix Timestamp (None if error)
        """
        try:
            date = post_soup.find('abbr')['data-utime']
            return datetime.fromtimestamp(int(date))
        except Exception as e:
            print(e)
            print('crashed while searching date')
            return None

    def get_comments_count(self, post_soup):
        """Get count of post's comments

        :param post_soup: (object) post soup

        :return: (int) count of comments (0 if error)
        """
        try:
            coments_count = post_soup.find('a', text=re.compile(r'^\s*Комментарии:\s*\d+\s*$'))
            return int(re.search(r'\d+', coments_count.text).group(0))
        except Exception as e:
            print(e)
            print('crashed while searching number of comments')
            return 0

    def get_likes(self, post_soup):
        """Get count of post's likes

        :param post_soup: (object) post soup

        :return: (int) count of likes (0 if error)
        """
        try:
            likes = post_soup.find('span', attrs={'class': '_3dlh'})
            return int(likes.text)
        except Exception as e:
            print(e)
            print('crashed while counting likes')
            return 0

    def get_reposts_count(self, post_soup):
        """Get count of post's reposts

        :param post_soup: (object) post soup

        :return: (int) count of reposts (0 if error)
        """
        try:
            coments_count = post_soup.find('a', text=re.compile(r'^\s*Поделились:\s*\d+\s*$'))
            return int(re.search(r'\d+', coments_count.text).group(0))
        except Exception as e:
            print(e)
            print('crashed while searching number of reposts')
            return 0

    def get_comments(self, post_soup):
        """Get comments for post

        :param post_soup: (object) post soup

        :return: (list) comments
        """
        try:
            comment_el_list = []
            for div in post_soup.findAll(lambda x: x.name == 'div' and not x.attrs):
                l = div.findAll('div', attrs={'aria-label': re.compile(".*[Кк]омментарий.*")})
                if len(l) > 0: comment_el_list += l
            return [Comment(com_el) for com_el in comment_el_list if Comment(com_el).message is not None]
        except Exception as e:
            print(e)
            print('crashed while searching comments')
            return []

    def __init__(self, page_id, post_soup):
        """Initialize

        :attr page_id: (str) user/group ID
        :attr post_soup: (object) post soup
        """
        self.soup = post_soup
        self.page_id = page_id
        self.id = self.get_id(post_soup)
        self.icon = self.get_icon_url(post_soup)
        self.message = self.get_message(post_soup)
        self.date = self.get_date(post_soup)
        self.comments_count = self.get_comments_count(post_soup)
        self.likes = self.get_likes(post_soup)
        self.reposts = self.get_reposts_count(post_soup)
        self.comments = self.get_comments(post_soup)

    def to_dict(self):
        """Format to dict

        :return: (dict) post
        """
        return {'id': self.id,
                'owner': self.page_id,
                'avatar': self.icon,
                'date': (None if self.date is None else self.date.timestamp()),
                'text': self.message,
                'text_length': len(self.message),
                'likes_count': self.likes,
                'reposts_count': self.reposts,
                'comments_count': self.comments_count,
                'comments': [comment.to_dict() for comment in self.comments]}


class fbb(webdriver.Chrome):
    __base_url = 'https://www.facebook.com'
    __base_group_url = 'https://www.facebook.com/groups'
    __login_url = 'https://www.facebook.com/login'

    def element_exists(self, xpath):
        """Get element status

        :return: status
        """
        try:
            self.find_element_by_xpath(xpath)
        except NoSuchElementException:
            return False

        except Exception as e:
            print(e)
            return True

        return True

    def try_click_by_xpath(self, xpath):
        """Click button by xpath"""
        return self.execute_script(js_click_script.substitute(XPATH=xpath))

    def page_avaliable(self):
        """Get page status

        :return: status
        """
        page_soup = BeautifulSoup(self.page_source, 'lxml')
        try:
            nonavbl = page_soup.find('title', text=re.compile('.*Страница не найдена.*'))
            if nonavbl:
                print('Страница не найдена')
                return False
            nonavbl = page_soup.find('h2', text=re.compile('.*Эта страница недоступна.*'))
            if nonavbl:
                print('Эта страница недоступна')
                return False
            nonavbl = page_soup.find('h2', text=re.compile('.*К сожалению, этот контент сейчас недоступен.*'))
            if nonavbl:
                print('К сожалению, этот контент сейчас недоступен')
                return False
        except Exception as e:
            print(e)
            return True
        return True

    def scroll_to_end(self):
        for i in range(3):
            self.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def scroll_posts(self, limit, from_date=None, need_comments=True):
        """Scroll page

        :param limit: (int) scrolling limit
        :param from_date: (int) Unix Timestamp (default None)
        :param need_comments: (bool) default True

        :return posts_list: (list) posts
        """

        posts_list = []
        error_count = 0

        # раньше искало ленту новостей, но теперь не надо
        # try:
        #     WebDriverWait(self, 5).until(EC.presence_of_element_located((By.TAG_NAME, posts_xpath)))
        # except TimeoutException:
        #     print(posts_list)

        # набирает посты по лимиту

        postcount = -1

        while error_count < 5:
            try:
                mindate = datetime.today()
                while len(posts_list) < limit and len(posts_list) != postcount:
                    postcount = len(posts_list)
                    self.scroll_to_end()
                    posts_list = self.find_elements_by_tag_name(posts_xpath)

                # дорабатывает посты
                for post in posts_list:
                    # раскрыть ещё, если есть
                    more = post.find_elements_by_xpath(post_more_button)
                    if more:
                        more[0].click()

                    # раскрыть все комменты, если надо
                    if need_comments:
                        more_comments_finder = lambda: post.find_elements_by_xpath(
                            post_comment_more_button) + post.find_elements_by_xpath(
                            post_comment_more_button2)
                        more_comments = more_comments_finder()
                        while more_comments:
                            more_comments[0].click()
                            sleep(1)
                            more_comments = more_comments_finder()

                    # непонятная фильтрация по дате
                    # if from_date is not None and posts_list:
                    #     last_post = Post('some', BeautifulSoup(posts_list[-1].get_attribute('innerHTML')))
                    #     if last_post.date is not None:
                    #         if last_post.date.timestamp() < from_date:
                    #             return posts_list

            except Exception as e:
                print(e)
                error_count += 1
        posts_list = posts_list if posts_list else []
        return posts_list

    def get_posts(self, page_id, limit=20, from_date=None, need_coments=True):
        """Get posts from user/group

        :param page_id: (str) user/group ID
        :param limit: (int) scrolling limit (default 20)
        :param from_date: (int) Unix Timestamp
        :param need_comments: (bool) default True

        :return: (list) posts
        """
        self.get(self.__base_url + '/' + page_id)
        if not self.page_avaliable():
            print('page ' + self.__base_url + '/' + page_id + ' is not avaliable')
            self.get(self.__base_group_url + '/' + page_id)
            if not self.page_avaliable():
                print('page ' + self.__base_group_url + '/' + page_id + ' is not avaliable')
                return []
        return [Post(page_id, BeautifulSoup(post_el.get_attribute('innerHTML'))) for post_el in
                self.scroll_posts(limit + 2, from_date=from_date, need_comments=need_coments)]

    def enter_facebook(self, login, password):
        """Login to fb

        :param login: (str) fb login
        :param password: (str) fb password

        :return: -1 if error
        """
        self.get(self.__login_url)

        try:
            login_form = self.find_element_by_xpath("//input[@id='email' or @name='email']")
            login_form.clear()
            login_form.send_keys(login)
        except Exception as e:
            print(e)
            print('error: email')
            return -1

        try:
            pass_form = self.find_element_by_xpath("//input[@id='pass' or @name='pass']")
            pass_form.clear()
            pass_form.send_keys(password)
        except Exception as e:
            print(e)
            print('error: password')
            return -1

        try:
            self.find_element_by_xpath("//button[@id='loginbutton']").click()
        except Exception as e:
            print(e)
            print('error: login button')
            return -1

        if 'login_attempt' in self.current_url:
            return -1

    def __init__(self, login, password, proxy=None):
        """Initialize fbb

        :attr login: (str) fb login
        :attr password: (str) fb password
        :attr proxy: (str) default None
        """
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")

        options.add_argument("--disable-software-rasterizer")  # maybe not needed
        options.add_argument("--disable-dev-shm-usage")  # maybe not needed

        if proxy is not None:
            options.add_argument('--proxy-server=%s' % proxy)

        # path_to_browser = os.environ.get('CHROME_BIN', '/usr/bin/chromium-browser')
        # path_to_driver = os.environ.get('PATH_TO_CHROME_DRIVER', '/code/chromedriver')
        #
        # if os.path.isfile(path_to_browser):
        #     options.binary_location = path_to_browser
        # else:
        #     raise FileExistsError(f'{path_to_browser} does not exist')
        #
        # if not os.path.isfile(path_to_driver):
        #     raise FileExistsError(f'{path_to_driver} does not exist')
        #
        # super().__init__(path_to_driver, options=options)

        super().__init__(options=options)

        if self.enter_facebook(login, password) == -1:
            raise Exception("login error")


morph = pymorphy2.MorphAnalyzer()


def lemmatize(text):
    """Lemmatize text

    :param text: (str) post's text

    :return: (list) lemmatized post's text
    """
    return [morph.parse(word)[0].normal_form for word in re.split(r'\W+', text)]


def get_post_relevance(post_text, search_request):
    """Get post's relevance according to search query

    :param post_text: (str) post's text
    :param search_request: (dict) search request

    :return: (float) post's relevance
    """
    tokens = lemmatize(post_text.lower())
    relevance = 0
    if 'stop_words' in search_request:
        for stop_word in search_request['stop_words']:
            if morph.parse(stop_word)[0].normal_form in tokens:
                return relevance

    if 'key_words' not in search_request:
        return 1

    if len(search_request['key_words']) == 0:
        return 1

    for key_word in search_request['key_words']:
        if morph.parse(key_word)[0].normal_form in tokens:
            relevance += 1

    return relevance / len(search_request['key_words'])


def get_posts_(search_request):
    """Return list of posts from the given groups/users
    according to the given search query

    Arguments:

    search_request = {
    "key_words": |list of strings|,
    "stop_words": |list of strings|,
    "strong_key_words": |list of strings|,
    "from_date": |Unix Timestamp|,
    "to_date": |Unix Timestamp|,
    "ids": |list of strings|,
    "is_need_comments" : [0/1] - replies inclusion flag,
    "access_token": (str) user's VK access token
    }

    Return:
    
    list of posts = [post1, post2, ...]
    
    where    
    post = {
        'id': (str) unique ID for DB,
        'owner': (str) author's name,
        'id_owner': (int) author's ID,
        'avatar': (str) author's profile pic url,
        'url': (str) post's url,
        'post_id': (int) post unique ID,
        'date': (int) Unix Timestamp post creation time,
        'text': (str) post text,
        'text_length': (int) length of post's text,
        'likes_count': (int) count of likes,
        'views_count': (int) count of views,
        'reposts_count': (int) count of reposts,
        'comments_count': (int) count of comments,
        'photos': [photo1, photo2, ...] list of photo attachments' urls,
        'comments': [comment1, comment2, ...] list of comments  
    }
    
    where
    comment = {
        'id': (str) unique ID for DB,
        'owner_id': (int) author's ID,
        'comment_id': (int) comment unique ID,
        'owner': (str) author's name,
        'avatar': (str) author's profile pic url,
        'date': (int) Unix Timestamp comment creation time,
        'likes_count': (int) count of likes,
        'text': (str) comment text,
        'child': []
    }
    """
    if search_request['key_words'] == [""]:
        search_request['key_words'] = []

    if ('login' not in search_request) | ('password' not in search_request):
        search_request['login'] = FB_LOGIN
        search_request['password'] = FB_PASSWORD

    browser = fbb(search_request['login'], search_request['password'])

    posts = []
    for page_id in search_request['ids']:
        posts += browser.get_posts(page_id, 100, search_request['from_date'],
                                   search_request['is_need_comments'])

    browser.close()
    browser.quit()
    posts = [post.to_dict() for post in posts if
             get_post_relevance(post.message, search_request) > 0]

    if search_request['from_date'] is not None:
        posts = [post for post in posts if post['date'] >= search_request['from_date']]
    if search_request['to_date'] is not None:
        posts = [post for post in posts if post['date'] <= search_request['to_date']]

    if search_request['is_need_comments'] == 0:
        for post in posts:
            post['comments'] = []

    return posts


def get_posts(search_request):
    """Return list of posts from the given groups/users
    according to the given search query

    Arguments:

    search_request = {
    "key_words": |list of strings|,
    "stop_words": |list of strings|,
    "strong_key_words": |list of strings|,
    "from_date": |Unix Timestamp|,
    "to_date": |Unix Timestamp|,
    "ids": |list of strings|,
    "is_need_comments" : [0/1] - replies inclusion flag,
    "access_token": (str) user's VK access token
    }

    Return:
    
    list of posts = [post1, post2, ...]
    
    where    
    post = {
        'id': (str) unique ID for DB,
        'owner': (str) author's name,
        'id_owner': (int) author's ID,
        'avatar': (str) author's profile pic url,
        'url': (str) post's url,
        'post_id': (int) post unique ID,
        'date': (int) Unix Timestamp post creation time,
        'text': (str) post text,
        'text_length': (int) length of post's text,
        'likes_count': (int) count of likes,
        'views_count': (int) count of views,
        'reposts_count': (int) count of reposts,
        'comments_count': (int) count of comments,
        'photos': [photo1, photo2, ...] list of photo attachments' urls,
        'comments': [comment1, comment2, ...] list of comments  
    }
    
    where
    comment = {
        'id': (str) unique ID for DB,
        'owner_id': (int) author's ID,
        'comment_id': (int) comment unique ID,
        'owner': (str) author's name,
        'avatar': (str) author's profile pic url,
        'date': (int) Unix Timestamp comment creation time,
        'likes_count': (int) count of likes,
        'text': (str) comment text,
        'child': []
    }
    """
    rqst = []
    for i in range(len(search_request['ids'])):
        short_request = copy.copy(search_request)
        short_request['ids'] = [short_request['ids'][i]]
        rqst.append(short_request)
    with dummy_mp.Pool(mp.cpu_count()) as pool:
        results = pool.map(get_posts_, rqst)
    return [post for pl in results for post in pl]
