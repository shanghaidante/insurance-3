# coding=utf8
import json
import time
from urllib.parse import urljoin
from urllib.request import urlopen

import requests
from pymongo import MongoClient
from bs4 import BeautifulSoup
import company_craw
connection = MongoClient('localhost', 27017)  # 数据库连接
db = connection.insurance
collection = db.XYZ
def download(url):  # url下载
    if url is None:
        return None
    response = urlopen(url)
    if response.getcode() != 200:
        return None
    return response.read()


class UrlManager(object):  # url管理器类
    def __init__(self):
        self.new_urls = set()  # 未被爬取的url串
        self.old_urls = set()  # 已被爬取的url串

    def add_new_url(self, url):  # 将一条新的url加入url串里
        if url is None:
            return
        if url not in self.new_urls and url not in self.old_urls:
            self.new_urls.add(url)

    def add_new_urls(self, urls):  # 添加新的url串
        if urls is None or len(urls) == 0:
            return
        for url in urls:
            self.add_new_url(url)

    def has_new_url(self):  # 是否含有url
        return len(self.new_urls) != 0

    def get_new_url(self):  # 从url串中获取一条新的url
        new_url = self.new_urls.pop()
        self.old_urls.add(new_url)
        return new_url


class HtmlParser(object):  # 爬虫的解析器类
    def parse(self, page_url, html_cont,d_url_company):
        if page_url is None or html_cont is None:
            return
        soup = BeautifulSoup(html_cont, 'html.parser', from_encoding='utf-8')  # 配置网页解析器
        new_urls = self._get_new_urls(page_url, soup)
        new_data = self._get_new_data(page_url, soup,d_url_company)
        return new_urls, new_data

    def _get_new_urls(self, page_url, soup):

        # 判断是否为主页面,若是则去获取跳转页面
        # 若为保险页面则无需去获取跳转页面
        if page_url.split('/p')[0] == 'http://www.xyz.cn/mall/jiankangxian':
            new_urls = set()
            links = soup.find_all('a', class_="hazardC_pro_toSee dev_trialSuccess")  # 获取所有"去看看"按钮的跳转页面的标签
            for link in links:
                new_url = link['href']
                new_full_url = urljoin(page_url, new_url)  # 用page_url和href来拼接保险页面的完整的url
                new_urls.add(new_full_url)
            return new_urls

    def _get_new_data(self, page_url, soup,d_url_company):
        res_data = {'url': page_url}
        l = page_url.split('/')

        if l[4] != "jiankangxian":  # 判断是否为保险页面,若是则获取下面的数据
            title_node = soup.find('h1', class_="product-intro__title-text")
            res_data['title'] = title_node.get_text(strip=True)
            title_info = soup.find_all('div',class_="hc-form-item hc-clearFix")     # 产品特色 承保年龄...
            title_info.pop(0)
            res_data['info'] = title_info
            product_spe = ''
            for info in res_data['info']:
                product_spe += info.get_text(strip=True)

            # 获取'投保须知'
            insurance_notice_temp = soup.find_all('div', class_='product-detail__content hc-ckeditor')
            insurance_notice_temp.pop(0)
            insurance_notice = ''
            for notice in insurance_notice_temp:
                insurance_notice += notice.get_text(strip=True)

            # 获取'保障内容'json数据
            safeguard_content_temp = soup.find('input', id='dev_benefitesCategoryJson').get('value')
            json_datas = json.loads(safeguard_content_temp)
            safeguard_content = []
            for json_data in json_datas:
                for a_data in json_data['protectPropDTOs']:
                    safeguard_content += [{'name':a_data['name'],'explanation':a_data['explanation']}]

            collection.insert({'title': res_data['title'], 'url': res_data['url'], 'product_special': product_spe})
            #collection.update({'title': res_data['title']}, {'$set': {'title': res_data['title'], 'url': res_data['url'], 'product_special': product_spe}})        # 添加数据到数据库

            # 将'保障内容'与'投保须知'加如数据库
            collection.update({'title':res_data['title']}, {'$set': {'company':d_url_company[page_url], 'safeguard_content': safeguard_content, 'insurance': insurance_notice}})
        return res_data


class SpiderMain(object):  # 爬虫类
    def __init__(self):
        self.parser = HtmlParser()
        self.urls = UrlManager()

    def craw(self, root_url,d_url_company):
        count = 1
        self.urls.add_new_url(root_url)  # 将根url添加到url串里
        while self.urls.has_new_url():
            try:
                new_url = self.urls.get_new_url()     # url串里弹出url
                print('craw %d : %s'%(count, new_url))       # 输出对应的保险序号以及网址
                html_cont = download(new_url)     # 下载网页内容

                # 把content传入parser中爬取各保险的网址
                # 或者爬取保险页面的内容 分别赋值给new_urls和new_data
                new_urls, new_data = self.parser.parse(new_url,html_cont,d_url_company)

                # 若成功爬取new_urls,将获取的url串加入url管理器的url串中
                self.urls.add_new_urls(new_urls)

                # 计数器加1
                count = count+1
                # 当前网页不能接受过于频繁的访问,延迟+1+1s 0--0
                time.sleep(2)
            except:
                print('craw failed')


if __name__ == "__main__":

    base_url = 'http://www.xyz.cn'
    first_page_url = "/mall/jiankangxian/p1.html"

    # 创建爬虫类以及公司字典
    obj_spider = SpiderMain()
    d_url_company = company_craw.company_main()

    # 开始前先清空数据库 便于添加新数据
    collection.remove()

    #创建soup对象
    response = requests.get(base_url+first_page_url)
    soup = BeautifulSoup(response.text, 'lxml')

    # pager为网页分页信息的div，从这里找到所有的a标签
    # 把找到的href查重,排序
    all_a = soup.find('div', class_='pager').find_all('a')
    all_href = list()
    for one_a in all_a:
        all_href.append(one_a.get('href'))
    all_href = list(set(all_href))
    all_href.sort()

    # 调用爬虫
    obj_spider.craw(base_url+first_page_url, d_url_company)
    for one_href in all_href:
        root_url = base_url+one_href
        obj_spider.craw(root_url, d_url_company)