import requests
import json
import sys
import time
from jira import JIRA
import jira.client
import datetime
import re
import argparse
from collections import defaultdict
import os
import glob
import csv
print(os.sys.path)
#from atlassian import Jira

import email, smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

jira_rest_url = "http://vlm.lge.com/issue/rest/api/latest/"
issue_url = jira_rest_url + "issue/"
search_url = jira_rest_url + "search/"
tracker_url = jira_rest_url + "project/"
fieldList_url = jira_rest_url + "field/"
jsonHeaders = {'Content-Type': 'application/json'}

# - 특정 조건 : 그 사람 (최근 일주일)
#- 모든 ticket중에서 "그 사람"이 comments를 남긴 내용중에 tiger_weekly_report 이 comments의 첫줄에 적은 ticket들에 적은 comments를 출력한다.
#- status 상관없고, 

dateRe = re.compile('^\s*(?P<date>(?P<year>20[0-9]+)-(?P<month>[0-9]+)-(?P<day>[0-9]+))')


class SendMail :
    def __init__(self
                 , sender = 'cheoljoo.lee@lge.com'
                 , logfile = 'cron.log'
                 , test = False
                ):
        self.sender = sender
        self.logfile = logfile
        self.test = test

    def sendMail(self,subject):
        # receiver = [a,b,c,d]
        # sendfiles = list

        #password = input("Type your password and press enter:")

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = self.sender

        # Create the plain-text and HTML version of your message
        #txt = """\
        #Hi,
        #How are you?
        #Real Python has many great tutorials:
        #www.realpython.com"""
        
        if not os.path.exists(self.logfile):
            print(self.logfile , "is not exist")
            quit(4)

        with open(self.logfile, "r") as logfd:
            rl = logfd.readlines()

        txt = '\n'.join(rl)
        txt += '\n'
        txt += '\n\nhostname:\n' + os.popen('hostname').read()
        txt += '\n\nnetwork:\n' + os.popen('/usr/sbin/ifconfig').read()
        txt += '\n\ndisk:\n' + os.popen('df -h').read()
        txt += '\n\ncwd:\n' + os.popen('pwd').read()
        txt += '\n\nuser:\n' + os.popen('id').read()
        print("txt:",txt)

        # Turn these into plain/html MIMEText objects
        part1 = MIMEText(txt, "plain")
        #part2 = MIMEText(html, "html")

        # Add HTML/plain-text parts to MIMEMultipart message
        # The email client will try to render the last part first
        message.attach(part1)
        #message.attach(part2)

        # Create secure connection with server and send email
        #context = ssl.create_default_context()
        #with smtplib.SMTP_SSL("lgekrhqmh01.lge.com", 465, context=context) as server:
        if self.test:
            print("No send mail to " , self.sender , "from:",self.sender , "subject:",subject)
            return
        print("send mail to " , self.sender , "from:",self.sender , "subject:",subject)
        with smtplib.SMTP("lgekrhqmh01.lge.com", 25) as server:
            #server.login(self.sender, password)
            server.sendmail(
                self.sender, self.sender , message.as_string()
            )
            server.quit()
                
if (__name__ == "__main__"):

    parser = argparse.ArgumentParser(
        prog='sendmail.py',
        description= 'send mail',
        epilog='''logfile cron.log  -> send mail to sender'''
    )

    parser.add_argument("-t", "--test", default=False,action="store_true",help='just test and not send e-mail for only first id')

    parser.add_argument(
        '--sender',
        default='cheoljoo.lee@lge.com',
        metavar="<str>",
        type=str,
        help='your email address  ex) cheoljoo.lee@lge.com     with @')

    parser.add_argument(
        '--logfile',
        default='cron.log',
        metavar="<str>",
        type=str,
        help='log file name    default : cron.log')

    args = parser.parse_args()

    print("the simple example to send mail")

    sendmail = SendMail(
                 sender = args.sender
                 , test = args.test
                 , logfile = args.logfile
                 )
    sendmail.sendMail("[Running ERROR] cron error for cron weekly report : " + args.sender)


