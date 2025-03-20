import requests
import json
import sys
import time
import datetime
import re
import argparse
from collections import defaultdict
import os
import glob
import csv
from multiprocessing import Lock
from functools import partial
#from atlassian import Jira
from requests.auth import HTTPDigestAuth

import email, smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import mysetting
from pprint import PrettyPrinter
import string

if os.name == 'posix':
    import psutil  # https://pypi.org/project/psutil/

# https://superfastpython.com/multiprocessing-pool-mutex-lock/
# lock[row['id']] = Lock()

# - 특정 조건 : 그 사람 (최근 일주일)
#- 모든 ticket중에서 "그 사람"이 comments를 남긴 내용중에 tiger_weekly_report 이 comments의 첫줄에 적은 ticket들에 적은 comments를 출력한다.
#- status 상관없고, 
# multiprocessing with multiple arguments : https://python.omics.wiki/multiprocessing_map/multiprocessing_partial_function_multiple_arguments

print(os.name)

dateRe = re.compile(r'^\s*(?P<date>(?P<year>20[0-9]+)-(?P<month>[0-9]+)-(?P<day>[0-9]+))')
deliverablesRe = re.compile(r'^\s*deliverables\s*:')
vgitUrlLineRe2 = re.compile(r'^\s*The changes\(commits\) about this JIRA ticket have been merged in\s*(?P<url2>http\S+)\s*$')
vgitUrlLineRe = re.compile(r'^\s*#\s*(?P<url>\S+)\s*$')
vgitVlmLineRe = re.compile(r'^\s*For further information, please refer to release notification\s*(?P<vlm>\S+)\s*$')
vgitBranchLineRe = re.compile(r'^\s*\*\s*branch\s*:\s*(?P<branch>\S+)\s*$')
slddUrlLineRe = re.compile(r'^\s*The changes\(commits\) about this JIRA ticket have been merged in SLDD\s*(?P<url>http\S+)\s*$')
vlmRe = re.compile(r'^\s*VLM\s*:\s*(?P<vlm>[A-Z0-9]+-[0-9]+)\s+')
commit_idRe = re.compile(r'^\s*commit_id\s*:\s*(?P<commit_id>\S+)\s+')
projectRe = re.compile(r'^\s*project\s*:\s*(?P<project>\S+)\s+')
modelRe = re.compile(r'^\s*model\s*:\s*(?P<model>\S+)\s+')
branchRe = re.compile(r'^\s*branch\s*:\s*(?P<branch>\S+)\s+')
committerRe = re.compile(r'^\s*committer\s*:\s*(?P<committerEmail>(?P<committer>[a-z.A-Z0-9-_]+)@[a-z.A-Z0-9-_]+)')
summaryRe = re.compile(r'^\s*summary\s*:\s*(?P<summary>.*)$')
slddDateRe = re.compile(r'^date\s*:\s*(?P<date>(?P<year>20\d+)-(?P<month>\d+)-(?P<day>\d+)\s+(?P<time>\S+))\s+(?P<timezone>\S+)')
totalAutoFileRe = re.compile(r'^\s*total count of auto file\s*:\s*(?P<slddtotalautofile>\d+)')
totalSLDDRe = re.compile(r'^\s*total changed count of sldd file\s*:\s*(?P<slddtotalsldd>\d+)')
totalOthersRe = re.compile(r'^\s*total changed count of others file\s*:\s*(?P<slddtotalothers>\d+)')
modUrlLineRe = re.compile(r'^\s*The changes\(commits\) about this JIRA ticket have been merged in mod\.lge\.com\s*(?P<url>http\S+)\.\s*$')
modDateRe = re.compile(r'^\s*(?P<date>(?P<year>20\d+)-(?P<month>\d+)-(?P<day>\d+))T(?P<time>\d+:\d+:\d+\.\d+)+(?P<timezone>\S+)\s*$') # 06:33:43.000+09:00
wr1Re = re.compile(r'[^\n]*\s*{wr}\s*:[^\n]*'.format(wr=mysetting.weeklyReportLabel),re.DOTALL)
wr11Re = re.compile(r'^{wr}\s*:[^\n]*'.format(wr=mysetting.weeklyReportLabel),re.MULTILINE)
#wr1Re = re.compile(r'(^|[^\n]+)*\s*(?P<wr>{wr}\s*:[^\n]*)'.format(wr=mysetting.weeklyReportLabel),re.MULTILINE)  # it is better.
wr2Re = re.compile(r'&lt;*\s*{wr}\s*&gt;.*&lt;\s*/{wr}\s*&gt;'.format(wr=mysetting.weeklyReportLabel),re.DOTALL)  # MULTILINE
wr3Re = re.compile(r'<\s*{wr}\s*>.*<\s*/{wr}\s*>'.format(wr=mysetting.weeklyReportLabel),re.DOTALL)  # MULTILINE


# update
# - copy necessary info into self.vlm
# - make a vlm list for person / org
# - calculate this vlm info each self.each [person / org]
# 
# statistics (history)
# - person , org
# - kind , whichModel , project (add , sub , origin #)
# - added , processed (done or transfered or changed) ticket#s
#
# html 
# - make a html each person / org
# - fields : project , VLM , summary , status , assignee lists (date) , work priority (evidence , kinds) , reason
#   created , updated , PL , whichModel ,  pingpong , "recentUpdatedDateFromAssignee" ,  last 3 your comments
# - how to analyze per group
# - how to analyze organization statistics ,  how many project + kinds(PRTS , MH)
# 

class CWeekyReport :
    """ 
    This Class analyze VLM ticket from real data.
    Then get necessary fields to reduce the size.
    c = CWeekyReport(...)
    """
    def __init__(self
                 , inputdir
                 , inputfileprefix
                 , outputfileprefix
                 , reportDurationDays 
                 , debug
                ):
        """ 
        This funciton is issue creating & initializing function.
        """
        self.inputdir = inputdir
        self.inputfileprefix = inputfileprefix
        self.outputfileprefix = outputfileprefix
        self.reportDurationDays = reportDurationDays
        self.debug = debug

        self.vlmKeySet = set()
        self.vlmMyCommentsDict = {}
        self.vlmTodoDict = {}
        '''
        self.assignee = set()
        '''

        self.custom_printer = PrettyPrinter(
                indent=4,
                width=200,
                depth=10,
                compact=True,
                sort_dicts=False
                )

        self.today = datetime.date.today()
        now = datetime.datetime.now()
        self.formatted_date = now.strftime("%Y-%m-%d %H:%M:%S")
    
        self.lang = 'korean'


        vlmfilelist = []
        l = os.listdir(self.inputdir)
        print(l, self.inputfileprefix)
        for s in l:
            if s.startswith('{f}-'.format(f=self.inputfileprefix)):
                vlmfilelist.append(self.inputdir + '/' + s)
        print('vlmfilelist:',sorted(vlmfilelist))

        for fname in vlmfilelist:
            print('read:',fname)
            with open(fname,"r") as st_json: 
                origin = json.load(st_json) 
                for kVlm,v1 in origin.items():
                    if kVlm in self.vlmKeySet:
                        print('duplicated:',kVlm,fname)
                        continue
                    self.vlmKeySet.add(kVlm)
                    if len(v1.get('myCommentsList',[])) or v1['resolution']:
                        self.vlmMyCommentsDict[kVlm] = v1
                    if v1['status'] in ['Open','In Progress','Reopened'] and v1['assignee'] == mysetting.myid:
                        self.vlmTodoDict[kVlm] = v1

        with open('self-vlmMyCommentsDict.json',"w") as json_file: 
            print('write jsonoutput:','self-vlmMyCommentsDict.json' , '<- self.vlmMyCommentsDict',len(self.vlmMyCommentsDict))
            json.dump(self.vlmMyCommentsDict,json_file,indent = 4)
        with open('self-vlmTodoDict.json',"w") as json_file: 
            print('write jsonoutput:','self-vlmTodoDict.json' , '<- self.vlmTodoDict',len(self.vlmTodoDict))
            json.dump(self.vlmTodoDict,json_file,indent = 4)

        html = self.makeHtml()
        today = datetime.date.today()
        filename = mysetting.myid + '/' + mysetting.myid + '-' + str(today) + '.html'
        idhtmlfilename = mysetting.myid + '/' + mysetting.myid + '.html'
        print("created file :" + filename)
        with open(filename, 'w', encoding='utf-8', errors='ignore') as ff:
            ff.write(html)
        with open(idhtmlfilename, 'w', encoding='utf-8', errors='ignore') as ff:
            ff.write(html)
        
        if os.name == 'posix':
            self.sendMail(subject=str(today) + ' 슬기로운 개발 생활 : 일주일동안의 Comments 기반의 report'
                , sender = mysetting.myid
                , receiver = [mysetting.myid]
                , htmlBody = html
                , attachfiles = [filename]
                , test = mysetting.myIsTestToSendMail
                )

        
    def sendMail(self
                 , subject=''
                 , sender = 'cheoljoo.lee@lge.com'
                 , receiver = []
                 , htmlBody = ''
                 , attachfiles = []
                 , test = True
            ):
        if '@' not in sender:
            sender += '@lge.com'
        receiver = [ item if '@' in item else item+'@lge.com' for item in receiver]
        if test == True:
            print('not send mail:',sender,receiver,subject)
            return
        else :
            print('send mail:',sender,receiver,subject,attachfiles)
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ','.join(receiver)

        # Turn these into plain/html MIMEText objects
         #part = MIMEText(htmlBody, "plain")
        part = MIMEText(htmlBody, "html")

        # Add HTML/plain-text parts to MIMEMultipart message
        # The email client will try to render the last part first
        #message.attach(part1)
        message.attach(part)

        for file in attachfiles:
            if not os.path.exists(file):
                print(file , "is not exist")
                quit(4)

            # Open PDF file in binary mode
            with open(file, "rb") as attachment:
                # Add file as application/octet-stream
                # Email client can usually download this automatically as attachment
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())

            # Encode file in ASCII characters to send by email
            encoders.encode_base64(part)

            # Add header as key/value pair to attachment part
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {file}",
            )

            # Add attachment to message and convert message to string
            message.attach(part)

        # Create secure connection with server and send email
        #context = ssl.create_default_context()
        #with smtplib.SMTP_SSL("lgekrhqmh01.lge.com", 465, context=context) as server:
            
        for r in receiver:
            print("! sent mail to " , r , "from:",sender , "subject:",subject)
            with smtplib.SMTP("lgekrhqmh01.lge.com", 25) as server:
                #print(sender, r , message)
                server.sendmail(
                    sender, r , message.as_string()
                )
                server.quit()


    def makeHtml(self):
        # fixed first column and row
        # https://adrianroselli.com/2020/01/fixed-table-headers.html  
        #print(data,file=self.printf)
        s = ""
        s += """<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <link rel="icon" href="../img/tiger256.ico"/>
    <link rel="apple-touch-icon" href="../img/tiger256.ico"/>
    <title>Weekly Report based on comments</title>
    <style>
        body {
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto,
              Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
            line-height: 1.4;
            color: #333;
            background-color: #fff;
            padding: 0 5vw;
          }
          
          /* Standard Tables */
          
          table {
            margin: 1em 0;
            border-collapse: collapse;
            border: 0.1em solid #d6d6d6;
          }
          
          caption {
            text-align: left;
            font-style: italic;
            padding: 0.25em 0.5em 0.5em 0.5em;
          }
          
          th,
          td {
            padding: 0.25em 0.5em 0.25em 1em;
            vertical-align: text-top;
            text-align: left;
            text-indent: -0.5em;
          }
          
          th {
            vertical-align: bottom;
            background-color: #666;
            color: #fff;
          }
          
          tr:nth-child(even) th[scope=row] {
            background-color: #f2f2f2;
          }
          
          tr:nth-child(odd) th[scope=row] {
            background-color: #fff;
          }
          
          tr:nth-child(even) {
            background-color: rgba(0, 0, 0, 0.05);
          }
          
          tr:nth-child(odd) {
            background-color: rgba(255, 255, 255, 0.05);
          }

          tr td:last-child{
            width:35%;
          }
          
          /* Fixed Headers */
          
          th {
            position: -webkit-sticky;
            position: sticky;
            top: 0;
            z-index: 2;
          }
          
          th[scope=row] {
            position: -webkit-sticky;
            position: sticky;
            left: 0;
            z-index: 1;
          }
          
          th[scope=row] {
            vertical-align: top;
            color: inherit;
            background-color: inherit;
            background: linear-gradient(90deg, transparent 0%, transparent calc(100% - .05em), #d6d6d6 calc(100% - .05em), #d6d6d6 100%);
          }
          
          
          /* Strictly for making the scrolling happen. */
          
          body {
            padding-bottom: 90vh;
          }
    </style>
</head>

<body>
        """

        """
          th[scope=row] + td {
            min-width: 24em;
          }
          
          th[scope=row] {
            min-width: 20em;
          }
          
          td:nth-of-type(2) {
            font-style: italic;
          }
          
          th:nth-of-type(3),
          td:nth-of-type(3) {
            text-align: right;
          }
          table:nth-of-type(2) th:not([scope=row]):first-child {
            left: 0;
            z-index: 3;
            background: linear-gradient(90deg, #666 0%, #666 calc(100% - .05em), #ccc calc(100% - .05em), #ccc 100%);
          }
        """

        todaytime = datetime.datetime.today()
        s += """<H2>{t}</H2>""".format(t=str(todaytime))
        if mysetting.myhttp.strip():
            s += """<a href="{http}/{id}/{id}.html">Today</a> """.format(id=mysetting.myid,http=mysetting.myhttp)
            s += """ :  """
            s += """<a href="{http}/{id}/">History</a> """.format(id=mysetting.myid,http=mysetting.myhttp)
        if self.lang == 'korean':
            s += """
<br>
<br> weekly report for you.   <b>JIRA 기준의 보이게 일하는 좋은 습관</b>
<br> 제가 수동으로 실행시키고 있습니다. 본인 것을 빠르게 돌려보시려면, 아래 source를 받아서 Makefile의 id,passwd를 변경후 , LGE-list.csv에 자신 것만 넣고 동작시키시면 본인 것만 메일을 받아보실수 있습니다.
<br> 규칙
<br> <li>assignee나 coworker에 자신이 포함되고 , 1주일 이내 resolved 된 ticket들을 나타낸다.</li>
<br> <li>watcher에 자신이 포함(comments를 남기면 자동 watcher에 포함됨)되고 , comments를 남긴 ticket들을 나타낸다.</li>
<br> <li>어떤 ticket이든 comments에 &lt;wr&gt; ... multiple line....&lt;/wr&gt; 이라고 적으면 이들을 모아서 보여준다.</li>
<br> <li>중요한 일을 끝냈을때 (resolve) &lt;wr&gt; ... multiple line....&lt;/wr&gt; 로 정리를 해두면 추후 편하게 볼수 있다.</li>
<br>
""".format(http=mysetting.myhttp,id=mysetting.myid)
        else:
            s += """
<br>
<br> weekly report for you.   <b>Good working habit based on JIRA comments</b>
<br> Rule - What does it check?
<br> <li>resolved tickets within 8 days if you are included in assignee / coworker.</li>
<br> <li>tickets with you as watcher.   jira add you as watcher if you add your comments.</li>
<br> if you do not have any item in below table , i recommend that you work visible.
<br>
<br> <b>Simple Weekly Report within 7 days<b> : <a href="{http}/mouse/ddpi/wrjson/wr.html.7days.{id}.html">Only_For_Your</a> ::  <a href="{http}/mouse/ddpi/wrjson/wr.html.7days.html">All_Members</a>
<br> <li>It shows your weekly report if you write &lt;wr&gt; ... multiple line....&lt;/wr&gt; in comments of any ticket.</li>
<br> <li>If you write comment with &lt;wr&gt; ... multiple line....&lt;/wr&gt;  when you resolve ticket, it will be a good weekly report.</li>
<br>
""".format(http=mysetting.myhttp,id=mysetting.myid)

        ###
        ### resolved by me or updated by me
        ###
        html , tableFlag  = self.makeHtmlTable(
                title="1.1 resolved or updated weekly comments/description summary with {wr} tag by me for last week".format(wr=mysetting.weeklyReportLabel)
                , titleSummary = False
                , sortedList = sorted(self.vlmMyCommentsDict.items(),key = lambda item: (str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=True
                , wrOnly = True             # only comments with wr tag
                , existsReportDurationDays = True       # within recent 7 days
                , workPriority=False
                )
        if tableFlag:
            s+= html

        html , tableFlag  = self.makeHtmlTable(
                title="1.2 resolved or updated comments/description summary of all comments by me for last week".format(wr=mysetting.weeklyReportLabel)
                , titleSummary = True
                , sortedList = sorted(self.vlmMyCommentsDict.items(),key = lambda item: (str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=True
                , wrOnly = False                     # all comments
                , existsReportDurationDays = True       # within recent 7 days
                , workPriority=False
                )
        if tableFlag:
            s+= html

        html , tableFlag  = self.makeHtmlTable(
                title="1.3 resolved or updated comments/description summary in related to me for {d}".format(d=mysetting.crawlDurationDays)
                , titleSummary = True
                , sortedList = sorted(self.vlmMyCommentsDict.items(),key = lambda item: (str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=True
                , wrOnly = False                     # all comments
                , existsReportDurationDays = False    # all days (for 15 days)
                , workPriority=False
                )
        if tableFlag:
            s+= html

        # <H2>2. resolved or updated comments/description</H2>
        subHtml = ""
        html , tableFlag  = self.makeHtmlTable(
                title="2.1 resolved or updated weekly comments/description with {wr} tag by me for last week".format(wr=mysetting.weeklyReportLabel)
                , titleSummary = True
                , sortedList = sorted(self.vlmMyCommentsDict.items(),key = lambda item: (str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=False
                , wrOnly = True             # only comments with wr tag
                , existsReportDurationDays = True       # within recent 7 days
                , workPriority=False
                )
        if tableFlag:
            subHtml += html

        html , tableFlag  = self.makeHtmlTable(
                title="2.2 resolved or updated comments/description of all comments by me for last week".format(wr=mysetting.weeklyReportLabel)
                , titleSummary = True
                , sortedList = sorted(self.vlmMyCommentsDict.items(),key = lambda item: (str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=False
                , wrOnly = False                     # all comments
                , existsReportDurationDays = True       # within recent 7 days
                , workPriority=False
                )
        if tableFlag:
            subHtml += html

        html , tableFlag  = self.makeHtmlTable(
                title="2.3 resolved or updated comments/description summary in related to me for {d}".format(d=mysetting.crawlDurationDays)
                , titleSummary = True
                , sortedList = sorted(self.vlmMyCommentsDict.items(),key = lambda item: (str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=False
                , wrOnly = False                     # all comments
                , existsReportDurationDays = False    # all days (for 15 days)
                , workPriority=False
                )
        if tableFlag:
            subHtml += html
        s += "<details><summary><H2>2. resolved or updated comments/description</H2></summary>" + subHtml + "</details><br>\n"





        ###
        ### created by me and assigned to me : my todo list
        ###

        html , tableFlag  = self.makeHtmlTable(
                title="3. my TODO list with status (Open,In Progress,Reopened)"
                , titleSummary = True
                , sortedList = sorted(self.vlmTodoDict.items(),key = lambda item: (-item[1]['workPriority'] , str(item[1]['key'].split('-')[0]),int(item[1]['key'].split('-')[1])))
                , commentsSummary=True
                , wrOnly = False                     # all comments
                , existsReportDurationDays = False       # within recent 7 days
                , workPriority=True
                , todo = True
                )
        if tableFlag:
            s+= html

        if os.name == 'posix':
            import psutil  # https://pypi.org/project/psutil/
            sysinfo = '<p style=\"color:blue\">hostname: </p>' + os.popen('hostname').read()
            sysinfo += '\b<br><p style=\"color:blue\">process path: </p>' + str(get_parent_process())
            sysinfo += '\n<br><p style=\"color:blue\">memory: </p>' + str(psutil.virtual_memory())
            sysinfo += '\n<br><p style=\"color:blue\">disk /home: </p>' + str(psutil.disk_usage('/home'))
            sysinfo += '\n<br><p style=\"color:blue\">boot_time: </p>' + str(psutil.boot_time())
            sysinfo += '\n<br><p style=\"color:blue\">network: </p>' + str(psutil.net_if_addrs())
            p = psutil.Process(os.getpid())
            sysinfo += '\n<br><p style=\"color:blue\">cwd: </p>' + str(p.cwd())
        #sysinfo += '\n<br><p style=\"color:blue\">cmdline: </p>' + str(p.cmdline())
            sysinfo += '\n<br><p style=\"color:blue\">users: </p>' + str(psutil.users())
            sysinfo += '\n<br><p style=\"color:blue\">username: </p>' + str(p.username())
            s += """
<br>
<br> <a href="http://mod.lge.com/hub/cheoljoo.lee/weekly_work_report_from_jira">Source</a>
<br> 직접 고쳐서 merge request를 해주시면 무쟈게 감사하겠습니다. 
<br> 추가 요청 사항 있으시면 , <a href="http://vlm.lge.com/issue/browse/TIGER-10754">TIGER-10754</a> 에 subtask로 ticket생성 부탁드립니다. assignee는 cheoljoo.lee 로 해주십시요.
<br>
<br> Contribution:
<br> 1. jongseok.won - add arrow mark to show conveniently with details tag
<br>
<br><details><summary>Running System Information</summary>""" + sysinfo + """
</details><br>
<br>"""

        s += """
<br>
<br> Have a happy time!
<br>
"""
        s += "</body> </html>\n"
        return s

    def makeHtmlTable(self
            , title=''
            , titleSummary = False
            , sortedList=[]
            , commentsSummary=True   # show details summary type : "<details><summary>" + ss + "</summary>" + ll + "</details>"
            , wrOnly = False         # show all if False , show wr tag if True (wr : weeklyReport with wr tag)
            , existsReportDurationDays=False # show all tickets if False , or show within recent mysetting.reportDurationDays if True (ex. 7 : within recent 7 days)
            , workPriority=False
            , todo=False
            ):
        tableFlag = False
        sss = ""

        if titleSummary == True:
            sss += "<details><summary><H2>{t}</H2></summary>".format(t=title)
        else:
            sss += "<H2>{t}</H2>\n".format(t=title)
        sss += "<table border=1>\n"
        sss += """<thread><tr style="cursor: default;">"""
        sss += """<th>Idx</th>"""
        sss += """<th>Issue</th>"""
        if workPriority == True:
            sss += """<th>workPriority</th>"""
            sss += """<th>Evidence</th>"""
        sss += """<th>Components</th>"""
        sss += """<th>Assignee</th>"""
        sss += """<th>Reporter</th>"""
        sss += """<th>Parent / Summary</th>"""
        sss += """<th>Status</th>"""
        sss += """<th>Created</th>"""
        sss += """<th>Updated</th>"""
        sss += """<th>DueDate</th>"""
        sss += """<th>Labels</th>"""
        sss += """<th>Comments</th>"""
        sss += """<th>Description</th>"""
        sss += "</tr></thread>\n"
       
        #for vlm , v in sorted(self.vcIntegrator.items(),key = lambda item: (str(item[0].split('-')[0]),int(item[0].split('-')[1]))):
        lineNum = 1
        for k,v in sortedList:
            # filter routine
            if mysetting.myid != v['assignee'] and mysetting.myid != v['reporter'] :
                continue
            rowFlag = False
            rowTable = "<tr>"
            rowTable += """<th scope="row"> """ + str(lineNum) + "</th> "
            rowTable += """<th scope="row"> <a href="http://vlm.lge.com/issue/browse/""" + v['key'] + '" target="_blank">' + v['key'] + "</a>" + "</th> "
            # sss += """<th> <a href="http://vlm.lge.com/issue/browse/""" + v['key'] + '">' + v['key'] + "</a>" + "</th> "
            if workPriority == True:
                rowTable += "<td>{w}</td>".format(w=v.get('workPriority',0))
                rowTable += "<td>{w}</td>".format(w=' / '.join(v.get('workPriorityEvidence',[])))
            rowTable += "<td align=left>" + "<br> / ".join(v['components']) + "</td> "
             #print(v['key'],v.get('assigneeHistory',[]))
            assigneeHistory = [ item for item in v.get('assigneeHistory',[]) if item ]
            ah = ''
            if len(assigneeHistory) > 1:
                ah = ' ( {ah} )'.format(ah=' / '.join(assigneeHistory))
            rowTable += "<td align=center>{a}{ah}</td> ".format(a=v['assigneeName'],ah=ah)
            rowTable += "<td align=center>" + v['reporterName'] + "</td> "
            if v['parent']:
                rowTable += "<td align=left>" + """<a href="http://vlm.lge.com/issue/browse/""" + v['parent'] + '">' + v['parent'] + "</a> / " + v['summary'] + "</td> "
            else:
                rowTable += "<td align=left>" + v['summary'] + "</td> "
            if v['reopened'] == True:
                reopenedList = [f"{author} ({date})" for author, date in zip(data["reopenedAuthor"], data["reopenedCreatedDate"])]
                rowTable += "<td align=center>" + v['status'] + ' (Reopened by ' + ' <br>'.join(reopenedList) + ' )</td> '
            else:
                rowTable += "<td align=center>" + v['status'] + "</td> "
            rowTable += "<td align=left>" + v['createdDate'] + "</td> "
            rowTable += "<td align=left>" + v['updatedDate'] + "</td> "
            rowTable += "<td align=left>" + v.get('dueDate','') + "</td> "
            rowTable += "<td align=left>" + "<br>".join(v['labels']) + "</td> "
            if v.get('myCommentsList',[]):
                rowTable += """<td align=left>"""
                for ii,vv in enumerate(v.get('myCommentsList',[])):
                    if wrOnly:
                        if mysetting.myid != vv['author']:
                            continue
                        if not vv.get('wrBody',''):
                            continue
                    if existsReportDurationDays == True:
                        if self.isWithinCheckDay(vv['updated']) == False:
                            continue
                    rowTable += """<span style="color:green"><b>""" +vv['updated'] + " / " + vv['authorName'] + "</b></span> <br>"
                    if wrOnly:
                        if commentsSummary:
                            ss,ll = self.getShortSummary(vv.get('wrBody',''),3)
                            rowTable += "<details><summary>" + ss + "</summary>" + ll + "</details>"
                        else:
                            rowTable += vv.get('wrBody','')
                    else:
                        if commentsSummary:
                            ss,ll = self.getShortSummary(vv.get('body',''),3)
                            rowTable += "<details><summary>" + ss + "</summary>" + ll + "</details>"
                        else:
                            rowTable += vv.get('body','')
                    rowFlag = True
                rowTable += "</td>"
            else :
                rowTable += "<td> </td>"
            if v['description']:
                #sss += "<td align=left><details><summary>Detail</summary>" + self.description[v['key']] + "</details></td> "
                if commentsSummary:
                    ss , ll = self.getShortSummary(v['description'],6)
                    rowTable += "<td align=left><details><summary>" + ss + "</summary>" + ll + "</details></td> "
                else:
                    rowTable += "<td align=left>" + v['description'] + "</td> "
            else :
                rowTable += "<td> </td>"
            rowTable += "</tr>\n"
            if todo:
                rowFlag = True   # show row even though ticket does not have comments
            if rowFlag:
                sss += rowTable
                tableFlag = True
                lineNum += 1
        sss += "</table>\n"
        if titleSummary == True:
            sss += "</details><br>\n"
        return sss , tableFlag

    def getShortSummary(self,s,lines):
        splitKeyList = ['\n','<br>','<p>']
        if s:
            if self.debug: print('getShortSummary s:',s)
            laList = [s]
            laendList = ['']
            while splitKeyList:
                splitKey = splitKeyList.pop(0)
                lcList = []
                lcendList = []
                for lai,la in enumerate(laList):
                    lbList = la.split(splitKey)
                    for lbi, lb in enumerate(lbList):
                        lcList.append(lb)
                        if lbi == len(lbList) - 1:
                            lcendList.append(laendList[lai])
                        else:
                            lcendList.append(splitKey)
                laList = lcList
                laendList = lcendList
                 #print('laList:',laList)
                 #print('laendList:',laendList)
                
            for lai,la in enumerate(laList):
                laList[lai] = la + laendList[lai]
             #print('laList final:',laList)
            return '\n'.join(laList[0:lines]) , '\n' + '\n'.join(laList[lines:])
        return '\n','\n'

    def isWithinCheckDay(self,d):
        if d == "":
            return False
        today = datetime.date.today()
        #print("today:",str(today),file=self.printf)
        # print(d,file=self.printf)
        grp = dateRe.search(d)
        if grp:
            target = datetime.date(int(grp.group('year')),int(grp.group('month')),int(grp.group('day')))
            diff = today - target
            # print(diff,today,target,file=self.printf)
            if target + datetime.timedelta(days=self.reportDurationDays) >= today:
                return True
            else:
                return False
        else :
            return False
        return True

def get_parent_process(limit=10):
    '''Walk up the process tree until we find a process we like.
    Arguments:
        ok_names: Return the first one of these processes that we find
    '''

    depth = 0
    this_proc = psutil.Process(os.getpid())
    #print(this_proc.name())
    argv = sys.argv
    for i,v in enumerate(argv):
        if v == '--authpasswd':
            argv.pop(i)
            argv.pop(i)
    allPath = this_proc.name() + ' ' + ' '.join(argv)
    next_proc = parent = psutil.Process(this_proc.ppid())
    #print(parent.name())
    while depth < limit:
        #print(next_proc.pid)
        allPath = str(next_proc.name()) + ':' + allPath
        if int(next_proc.pid) < 2:
            return allPath

        next_proc = psutil.Process(next_proc.ppid())
        depth += 1

    return allPath

if (__name__ == "__main__"):
    if mysetting.optionalId:
        mysetting.myid = mysetting.optionalId

    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description= 'weekly report (html)',
        epilog='''  '''
    )

    parser.add_argument(
        '--inputdir',
        metavar="<str>",
        type=str,
        default='update',
        help='input directory name    default : update')

    parser.add_argument(
        '--inputfileprefix',
        metavar="<str>",
        type=str,
        default='update',
        help='input file prefix for ticket information    default : update-*')

    parser.add_argument(
        '--outputfileprefix',
        metavar="<str>",
        type=str,
        default='html',
        help='weekly report   default : html')

    parser.add_argument( '--debug', default=False , action="store_true" , help="debug mode on")

    args = parser.parse_args()

    inputdir = args.inputdir
    if mysetting.myid:
        inputdir = mysetting.myid + '/' + args.inputdir
    if not os.path.exists(inputdir):
        print('error : ', inputdir , 'does not exist')
        quit(4)
    
    start = int(time.time())

    cs = CWeekyReport(
             inputdir = inputdir
             , inputfileprefix = args.inputfileprefix
             , outputfileprefix = args.outputfileprefix
             , reportDurationDays = mysetting.reportDurationDays
             , debug = args.debug
             )

    print()
    print("***run time(sec) :", int(time.time()) - start)
    print()

