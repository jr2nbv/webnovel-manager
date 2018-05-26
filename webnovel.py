# coding: utf-8

import sys
import re
import json
import requests
import os
import io
import pprint	# for debug
import hashlib
from enum import Enum
from bs4 import BeautifulSoup, NavigableString, Tag
import xml.sax.saxutils
import shlex
import subprocess
import shutil
from jinja2 import Environment, FileSystemLoader
import pprint
from collections import deque


class Publishers(Enum):

	narou = dict(
		name = u'小説家になろう',
		url = u'http://ncode.syosetu.com/',
		api = u'http://api.syosetu.com/novelapi/api/',
		ncode_pattern = r'n\d{4}\w{1,2}',
		meta_list_valid_length = 2
	)
	hameln = dict(
		name = u'ハーメルン',
		url = u'https://novel.syosetu.org/',
		ncode_pattern = r'',
		meta_list_valid_length = 2
	)
	kakuyomu = dict(
		name = u'カクヨム',
		url = u'https://kakuyomu.jp/',
		ncode_pattern = r'\d{11,}',
		meta_list_valid_length = 2
	)

	def url(self):
		return self.value['url']

	def api(self):
		return self.value['api']

	def pattern(self):
		return self.value['ncode_pattern']

	def valid_length(self):
		return self.value['meta_list_valid_length']


# TODO: マルチユーザー対応?
class WebNovel:

	def __init__(self, url):
		# TODO: __download_image()が使い終わったらまた初期化する
		self.image_count = 1	# __download_image() only use
		self.__judge_publisher(url)
		self.__get_meta()

	def is_serial_story(self):
		return self.meta['serial_story_flag']

	def get_ncode(self):
		return self.ncode

	def get_publisher(self):
		return self.publisher

	# TODO: validateのためにラッパーメソッドを作る。引数のパスを後ろくっつけて、normpath()->validate
	def get_novel_path(self):
		return self.novel_path + '/'

	def get_output_name(self):
		return self.meta['output_name']

	# TODO: validate
	def get_base_path(self):
		return self.base_path + '/'

	def get_title(self):
		return self.meta['title']

	def get_episode(self):
		return self.meta['episode']

	def get_writer(self):
		return self.meta['writer']

	def get_last_posted(self):
		return self.meta['last_posted']

	def get_updated(self):
		return self.meta['updated']

	def get_mobi(self, is_force):
		self.download(is_force)
		self.format()
		return self.convert()

	def download(self, is_force):
		self.__make_html_dir(is_force)
		if self.get_publisher() == 'narou':
			dirs = self.__gen_output_dirs()
			for d in dirs:
				path = self.get_novel_path() + 'html/' + d + 'index.html'
				url = Publishers.narou.url() + self.get_ncode() + '/' + d
				self.__download_file(url, path)

	def format(self):
		self.__print_message('Format', self.get_novel_path() + 'html/')
		self.__make_tmp_dir()
		dirs = self.__gen_output_dirs()
		for d in dirs:
			if d:
				self.__format_episode(d)
			else:
				self.__format_index()

	# TODO: validate
	# TODO: タイトルをファイル名に
	def convert(self):
		self.__print_message('Convert', self.get_novel_path() + 'tmp/')
		kindlegen = self.get_base_path() + 'bin/kindlegen'
		opf = self.get_novel_path() + 'tmp/content.opf'
		# opf = shlex.quote(self.get_novel_path() + 'tmp/content.opf')
		output = shlex.quote(self.get_output_name())
		cmd = [kindlegen, opf, '-verbose', '-locale', 'en', '-o', output]
		# subprocess.run(cmd)
		subprocess.run(cmd, stdout=subprocess.DEVNULL)
		mobi = self.get_novel_path() + 'tmp/' + output
		try:
			return shutil.move(mobi, self.get_novel_path())
		except shutil.Error:
			os.remove(self.get_novel_path() + output)
			return shutil.move(mobi, self.get_novel_path())

	def is_nested_list(self, obj):
		is_nested = False
		if isinstance(obj, list):
			for val in obj:
				is_nested |= isinstance(val, list)
		return is_nested

	def worship_jinja(self, tpl_name, context, create_path):
		loader = FileSystemLoader(self.get_base_path() + 'template/', encoding='utf8')
		env = Environment(loader=loader, trim_blocks=True, autoescape=True)
		tpl = env.get_template(tpl_name)
		output = tpl.render(context)
		self.__print_message('Create', create_path)
		with open(create_path, 'wb') as f:
			f.write(output.encode())

	def print_meta_json(self):
		string = json.dumps({
			'path': os.path.normpath(self.get_novel_path() + self.get_output_name()),
			'publisher': Publishers[self.get_publisher()].value['name'],
			'title': self.get_title(),
			'writer': self.get_writer(),
			'ncode': self.get_ncode(),
			'episode': self.get_episode(),
			'last_posted': self.get_last_posted(),
			'updated': self.get_updated(),
			'status': 'Success'
		})
		print(string)

	def __judge_publisher(self, url):
		for publisher in Publishers:
			pattern = r'^' + publisher.url()
			if re.match(pattern, url):	# if URL is valid
				pattern = publisher.pattern()
				match = re.search(pattern, url)
				if match and isinstance(match.group(), str):	# if ncode is valid
					self.publisher = publisher.name
					self.ncode = match.group()
					domain = re.sub(r'^https?://', '', publisher.url())
					path = 'cache/' + domain + self.get_ncode() + '/'
					base = os.path.dirname(os.path.relpath(__file__))
					self.base_path = os.path.normpath(base)
					self.novel_path = os.path.normpath(os.path.join(base, path))
					break
				else:
					raise RuntimeError('Ncode is invaild')
		else:
			raise RuntimeError('Publisher NOT Exist')

	def __get_meta(self):
		if not hasattr(self, 'meta'):
			if self.get_publisher() == 'narou':
				narou = Publishers.narou
				params={'ncode': self.get_ncode(), 'out': 'json'}
				response = requests.get(narou.api(), params)
				meta = json.loads(response.text)
				if len(meta) == narou.valid_length():
					meta = meta[1]
					self.meta = {}
					self.meta['title'] = meta['title']
					self.meta['writer'] = meta['writer']
					self.meta['episode'] = meta['general_all_no']
					self.meta['last_posted'] = meta['general_lastup']
					self.meta['updated'] = meta['novelupdated_at']
					self.meta['serial_story_flag'] = (meta['novel_type'] == 1)
					self.meta['output_name'] = self.get_ncode() + '.mobi'
					# self.meta['output_name'] = self.get_title() + '.mobi'
				else:
					raise RuntimeError('Novel NOT Exist')

	#  TODO: validation
	def __make_html_dir(self, is_force):
		dirs = self.__gen_output_dirs()
		try:
			os.makedirs(self.get_novel_path())
		except FileExistsError:
			if is_force:
				shutil.rmtree(self.get_novel_path())
				os.makedirs(self.get_novel_path())
			else:
				raise FileExistsError
		for d in dirs:
			os.makedirs(self.get_novel_path() + 'html/' + d)


	def __make_tmp_dir(self):
		# TODO: コピーするファイルは細かく指定したほうがいい。ファイル差し替えの危険はあるけどめんどいので優先度低
		try:
			common = self.get_base_path() + 'common/'
			tmp = self.get_novel_path() + 'tmp/'
			shutil.copytree(common, tmp)
		except FileExistsError:
			# TODO: 削除してもう一度コピーする？
			pass

	def __parse_narou_index(self, soup):
		toc = list()
		index = soup.find(class_='index_box')
		for child in index.children:
			if not child.string == '\n':
				if 'chapter_title' in child['class']:
					toc.append(child.string)
					toc.append(list())	# subtitle list
				elif 'novel_sublist2' in child['class']:
					if toc and isinstance(toc[-1], list):
						toc[-1].append(child.a.string)
					else:
						toc.append(child.a.string)
		return toc

	def __parse_other_index(self, soup):
		toc = list()
		return toc

	def __format_episode(self, ep):
		read_path = self.get_novel_path() + 'html/' + ep + 'index.html'
		soup = self.__read_html(read_path)
		if self.get_publisher() == 'narou':
			subtitle, paragraphs = self.__parse_narou_episode(soup)
		else:	# TODO: ほかの小説投稿サイト
			subtitle, paragraphs = self.__parse_other_episode(soup)
		context = dict(
			title = subtitle,
			pars = paragraphs
		)
		create_path = self.get_novel_path() + 'tmp/xhtml/' + str(ep).replace('/', '') + '.xhtml'
		self.worship_jinja('episode.tpl.xhtml', context, create_path)

	def __parse_narou_episode(self, soup):
		text = soup.find(id='novel_honbun')
		subtitle = soup.find(class_='novel_subtitle').string
		imgs = text.find_all('img')
		urls = [img['src'] for img in imgs]
		paths = self.__download_images(urls)
		queue = deque(paths)

		# TODO: parsはタグを含むのでテンプレート内でエスケープできない
		# 		parse html (this block is unco)
		# TODO: 前書きと後書きに対応
		pars = []
		pre_is_br = False
		buf = ''
		for child in text.children:
			if isinstance(child, Tag):	# strip wrapper tag from novel context
				if child.name == 'p':	# if tag contains text like serif, land-sentence
					child = child.contents[0]
			if isinstance(child, NavigableString) and not str(child) == '\n':
				pars.append(re.sub(r'^\n?\u3000?', '', str(child)))
				pre_is_br = False
			elif isinstance(child, Tag):
				if child.name == 'br':
					if pre_is_br:
						pars.append('<br />')
					else:
						pre_is_br = True
		pars.append(buf)	# last sentence
		return subtitle, pars

	def __parse_other_episode(self, soup):
		raise RuntimeError('This publisher is NOT supported')

	def __format_index(self):
		path = self.get_novel_path() + 'html/index.html'
		soup = self.__read_html(path)
		if self.is_serial_story():
			if self.get_publisher() == 'narou':
				toc = self.__parse_narou_index(soup)
			else:
				toc = self.__parse_other_index(soup)	# TODO: ほかの小説投稿サイト
			self.__create_navigation(toc)	# create navigation-documents.xhtml
			self.__create_toc(toc)	# create toc.xhtml
		else:	# if short story
			raise RuntimeError('Short story is NOT supported')
		self.__create_titlepage()	# create titlepage.xhtml
		self.__create_opf()	# create content.opf

	def __create_navigation(self, toc):
		context = dict(
			toc = toc
		)
		path = self.get_novel_path() + 'tmp/navigation-documents.xhtml'
		if self.is_nested_list(toc):
			tpl_path = 'navigation-documents/some-chapters.tpl.xhtml'
		else:
			tpl_path = 'navigation-documents/no-chapters.tpl.xhtml'
		self.worship_jinja(tpl_path, context, path)

	def __create_toc(self, toc):
		context = dict(
			toc = toc,
			title = self.get_title()
		)
		path = self.get_novel_path() + 'tmp/xhtml/toc.xhtml'
		if self.is_nested_list(toc):
			tpl_path = 'toc/some-chapters.tpl.xhtml'
		else:
			tpl_path = 'toc/no-chapters.tpl.xhtml'
		self.worship_jinja(tpl_path, context, path)

	def __create_titlepage(self):
		context = dict(
			title = self.get_title(),
			writer = self.get_writer()
		)
		path = self.get_novel_path() + 'tmp/xhtml/titlepage.xhtml'
		self.worship_jinja('titlepage.tpl.xhtml', context, path)

	def __create_opf(self):
		context = dict(
			title = self.get_title(),
			writer = self.get_writer(),
			publisher = self.get_publisher(),
			episode = self.get_episode()
		)
		path = self.get_novel_path() + 'tmp/content.opf'
		self.worship_jinja('content.tpl.opf', context, path)

	def __download_images(self, urls):
		paths = []
		for url in urls:
			url = re.sub(r'^//', "http://", url)	# URLの補正
			path = self.get_novel_path() + 'tmp/image/' + str(self.image_count) + '.jpg'
			paths.append('../image/' + str(self.image_count) + '.jpg')
			self.__download_file(url, path)
			self.image_count += 1
		return paths

	def __download_file(self, url, path):
		self.__print_message('Download', url)
		response = requests.get(url)
		with open(path, 'wb') as f:
			f.write(response.content)

	def __read_html(self, path):
		with open(path, 'rb') as f:
			html = f.read()
		return BeautifulSoup(html, 'html.parser')

	def __gen_output_dirs(self):
		dirs = ['']	# '' mean './'
		if self.is_serial_story():
			last = self.get_episode() + 1
			dirs += [str(ep) + '/' for ep in range(1, last)]
		return dirs

	def __print_message(self, verb, obj):
		pass
		# print('%-8s:' % verb, obj)


def get(url, is_force):
	novel = WebNovel(url)
	novel.get_mobi(is_force)


def get_json(url, is_force):
	novel = WebNovel(url)
	try:
		novel.get_mobi(is_force)
		novel.print_meta_json()
	except FileExistsError:
		print(json.dumps({'status': 'FileExistsError'}))


def download(url):
	narou = WebNovel(url)
	narou.download()


def convert(url):
	narou = WebNovel(url)
	narou.convert()


def print_usage():
		print("Usage: $ python narou.py [command]")
		print("  - get [url] [--force]")
		print("  - get_json [url] [--force]")
		print("  - download [url]")
		print("  - format [url]")
		print("  - convert [url]")
		# print("  - update [url]")
		sys.exit(1)


def main():
	argvs = sys.argv
	argc = len(argvs)
	if argc != 3 and argc != 4:
		print_usage()
	else:
		cmd = argvs[1]
		url = argvs[2]
# TODO: argparse
		try:
			opt = argvs[3]
		except:
			opt = ''
		if cmd == 'get':
			get(url, is_force=True)
		elif cmd == 'download':
			download(url)
		elif cmd == 'format':
			format(url)
		elif cmd == 'convert':
			convert(url)
		elif cmd == 'get_json':
			if opt == '--force':
				get_json(url, is_force=True)
			else:
				get_json(url, is_force=False)
		else:
			print_usage()


if __name__ == '__main__':
	main()