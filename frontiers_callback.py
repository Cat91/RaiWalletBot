#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# RaiBlocks Telegram bot
# @RaiWalletBot https://t.me/RaiWalletBot
# 
# Source code:
# https://github.com/SergiySW/RaiWalletBot
# 
# Released under the BSD 3-Clause License
# 
"""
Usage:
Press Ctrl-C on the command line or send a signal to the process to stop the server.
"""

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Bot, ParseMode
import logging
import socket, json
import time, math
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
import threading


# Parse config
import ConfigParser
config = ConfigParser.ConfigParser()
config.read('bot.cfg')
api_key = config.get('main', 'api_key')
log_file_frontiers = config.get('main', 'log_file_frontiers')
wallet = config.get('main', 'wallet')
fee_account = config.get('main', 'fee_account')
fee_amount = int(config.get('main', 'fee_amount'))
raw_fee_amount = fee_amount * (10 ** 24)
welcome_account = config.get('main', 'welcome_account')
callback_port = int(config.get('main', 'callback_port'))

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
					level=logging.INFO, filename=log_file_frontiers)

logger = logging.getLogger(__name__)

account_url = 'https://raiblockscommunity.net/account/index.php?acc='
hash_url = 'https://raiblockscommunity.net/block/index.php?h='
faucet_account = 'xrb_13ezf4od79h1tgj9aiu4djzcmmguendtjfuhwfukhuucboua8cpoihmh8byo'

# MySQL requests
from common_mysql import mysql_update_balance, mysql_update_frontier, mysql_select_accounts_list, mysql_set_price, mysql_select_language, mysql_set_sendlist, mysql_delete_sendlist, mysql_select_by_account


# Request to node
from common_rpc import *


# Common functions
from common import push, mrai_text


# Translation
with open('language.json') as lang_file:    
	language = json.load(lang_file)
def lang_text(text_id, lang_id):
	try:
		return language[lang_id][text_id]
	except KeyError:
		return language['en'][text_id]


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
	allow_reuse_address = True
	"""Handle requests in a separate thread."""


class POST_server(BaseHTTPRequestHandler):
	def do_POST(self):
		post_string = self.rfile.read(int(self.headers['Content-Length']))
		post = json.loads(post_string)
		#print(post)
		self.send_response(200)
		self.send_header('Content-Type','application/json')
		self.end_headers()
		# Return empty JSON
		self.wfile.write('{}\n')
		
		xrb_account = post['account']
		account = mysql_select_by_account(xrb_account)
		if (account is not False):
			block = json.loads(post['block'])
			if ((block['type'] == 'receive') or (block['type'] == 'open')):
				bot = Bot(api_key)
				raw_received = int(post['amount'])
				received_amount = int(math.floor(raw_received / (10 ** 24)))
				balance = account_balance(xrb_account)
				frontier = post['hash']
				max_send = balance - fee_amount
				if (max_send < 0):
					max_send = 0
				mysql_update_frontier(account[1], frontier)
				logging.info('{0} --> {1}	{2}'.format(mrai_text(account[3]), mrai_text(balance), frontier))
				# retrieve sender
				send_source = block['source']
				block_account = rpc({"action":"block_account","hash":send_source}, 'account')
				sender = ''
				lang_id = mysql_select_language(account[0])
				# Sender info
				if (block_account == faucet_account):
					sender = lang_text('frontiers_sender_faucet', lang_id)
				elif ((block_account == fee_account) or (block_account == welcome_account)):
					sender = lang_text('frontiers_sender_bot', lang_id)
				elif (block_account == account[1]):
					sender = lang_text('frontiers_sender_self', lang_id)
				else:
					accounts_list = mysql_select_accounts_list()
					for sender_account in accounts_list:
						if (sender_account[1] == block_account):
							if ((sender_account[4] is not None) and (sender_account[4])):
								sender = lang_text('frontiers_sender_username', lang_id).format(sender_account[4])
							else:
								sender = lang_text('frontiers_sender_users', lang_id)
				logging.info(sender)
				
				logging.info(block_account)
				mysql_update_balance(account[1], balance)
				logging.info('{0} Mrai (XRB) received by {1}, hash: {2}'.format(mrai_text(received_amount), account[0], frontier))
				text = lang_text('frontiers_receive', lang_id).format(mrai_text(received_amount), mrai_text(balance), mrai_text(max_send), frontier, hash_url, sender)
				mysql_set_sendlist(account[0], text.encode("utf8"))
				#print(text)
				push(bot, account[0], text)
				mysql_delete_sendlist(account[0])
		return
	
	def log_message(self, format, *args):
		return


try:
	#Create a web server and define the handler to manage the incoming request
	server = ThreadedHTTPServer(('localhost', callback_port), POST_server)
	print 'Starting callback server at localhost:{0}'.format(callback_port)
	
	#Wait forever for incoming POST requests
	server.serve_forever()

except KeyboardInterrupt:
	print 'Stop callback server'
	server.socket.close()
