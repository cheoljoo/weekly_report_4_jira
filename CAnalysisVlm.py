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
import psutil  # https://pypi.org/project/psutil/
from multiprocessing import Pool
from functools import partial
print(os.sys.path)
#from atlassian import Jira
from requests.auth import HTTPDigestAuth
from pygerrit2 import GerritRestAPI, HTTPBasicAuth

import email, smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import mysetting

# - 특정 조건 : 그 사람 (최근 일주일)
#- 모든 ticket중에서 "그 사람"이 comments를 남긴 내용중에 tiger_weekly_report 이 comments의 첫줄에 적은 ticket들에 적은 comments를 출력한다.
#- status 상관없고, 
# multiprocessing with multiple arguments : https://python.omics.wiki/multiprocessing_map/multiprocessing_partial_function_multiple_arguments

dateRe = re.compile('^\s*(?P<date>(?P<year>20[0-9]+)-(?P<month>[0-9]+)-(?P<day>[0-9]+))')
deliverablesRe = re.compile('^\s*deliverables\s*:')
vgitUrlLineRe2 = re.compile('^\s*The changes\(commits\) about this JIRA ticket have been merged in\s*(?P<url2>http\S+)\s*$')
vgitUrlLineRe = re.compile('^\s*#\s*(?P<url>\S+)\s*$')
vgitVlmLineRe = re.compile('^\s*For further information, please refer to release notification\s*(?P<vlm>\S+)\s*$')
vgitBranchLineRe = re.compile('^\s*\*\s*branch\s*:\s*(?P<branch>\S+)\s*$')
slddUrlLineRe = re.compile('^\s*The changes\(commits\) about this JIRA ticket have been merged in SLDD\s*(?P<url>http\S+)\s*$')
vlmRe = re.compile('^\s*VLM\s*:\s*(?P<vlm>[A-Z0-9]+-[0-9]+)\s+')
commit_idRe = re.compile('^\s*commit_id\s*:\s*(?P<commit_id>\S+)\s+')
projectRe = re.compile('^\s*project\s*:\s*(?P<project>\S+)\s+')
modelRe = re.compile('^\s*model\s*:\s*(?P<model>\S+)\s+')
branchRe = re.compile('^\s*branch\s*:\s*(?P<branch>\S+)\s+')
committerRe = re.compile('^\s*committer\s*:\s*(?P<committerEmail>(?P<committer>[a-z.A-Z0-9-_]+)@[a-z.A-Z0-9-_]+)')
summaryRe = re.compile('^\s*summary\s*:\s*(?P<summary>.*)$')
slddDateRe = re.compile('^date\s*:\s*(?P<date>(?P<year>20\d+)-(?P<month>\d+)-(?P<day>\d+))\s+(?P<time>\S+)\s+(?P<timezone>\S+)')
totalAutoFileRe = re.compile('^\s*total count of auto file\s*:\s*(?P<slddtotalautofile>\d+)')
totalSLDDRe = re.compile('^\s*total changed count of sldd file\s*:\s*(?P<slddtotalsldd>\d+)')
totalOthersRe = re.compile('^\s*total changed count of others file\s*:\s*(?P<slddtotalothers>\d+)')
modUrlLineRe = re.compile('^\s*The changes\(commits\) about this JIRA ticket have been merged in mod\.lge\.com\s*(?P<url>http\S+)\.\s*$')
modDateRe = re.compile('^\s*(?P<date>(?P<year>20\d+)-(?P<month>\d+)-(?P<day>\d+))T(?P<time>\d+:\d+:\d+\.\d+)+(?P<timezone>\S+)\s*$') # 06:33:43.000+09:00
robotStartRe = re.compile('^\s*written by CMU robot for updating comments overdue and pending etc ->\s+(?P<id>\S+)\s+needs update')
robotReasonRe = re.compile('^\s*reason message\s*:(?P<msg>.*)')
robotTestcaseRe = re.compile('^\s*written by CMU robot for cmu-testcase')

# wr:  or <wr> .. </wr>
mentionedRe = re.compile(r'\[~{wr}\]'.format(wr=mysetting.myid),re.DOTALL)
wr1Re = re.compile(r'[^\n]*\s*{wr}\s*:[^\n]*'.format(wr=mysetting.weeklyreportLabel),re.DOTALL)
wr11Re = re.compile(r'^{wr}\s*:[^\n]*'.format(wr=mysetting.weeklyreportLabel),re.MULTILINE)
#wr1Re = re.compile(r'(^|[^\n]+)*\s*(?P<wr>{wr}\s*:[^\n]*)'.format(wr=mysetting.weeklyreportLabel),re.MULTILINE)  # it is better.
wr2Re = re.compile(r'&lt;*\s*{wr}\s*&gt;.*&lt;\s*/{wr}\s*&gt;'.format(wr=mysetting.weeklyreportLabel),re.DOTALL)  # MULTILINE
wr3Re = re.compile(r'<\s*{wr}\s*>.*<\s*/{wr}\s*>'.format(wr=mysetting.weeklyreportLabel),re.DOTALL)  # MULTILINE


class CAnalysisVlm :
    """ 
    This Class analyze VLM ticket from real data.
    Then get necessary fields to reduce the size.
    c = CAnalysisVlm(...)
    """
    def __init__(self
                 , inputdir = ''
                 , filename = ''
                 , debug = False
                 , outputfileprefix = ''
                ):
        """ 
        This funciton is issue creating & initializing function.
        """
        if inputdir:
            self.jsonfilename =  inputdir.strip() + '/' + filename.strip()
            self.jsonoutput =  inputdir.strip() + '/{px}-'.format(px=outputfileprefix) + filename.strip()
        else :
            self.jsonfilename = filename.strip()
            self.jsonoutput =  '{px}-'.format(px=outputfileprefix) + filename.strip()
        self.debug = debug
        print("CAnalysisVim.init:jsonfilename:",self.jsonfilename)

        with open(self.jsonfilename,"r") as st_json: 
            print('read: ' , self.jsonfilename , '-> self.origin')
            self.origin = json.load(st_json) 

        self.vlm = {}

        sevenDayAgo = datetime.date.today() - datetime.timedelta(days=7)
        sevenDaysAgoStr = sevenDayAgo.strftime('%Y-%m-%d')
        for issue in self.origin['issues']:
            self.vlm[issue['key']] = {}
            v = self.vlm[issue['key']]
            v['key'] = issue['key']
            v['id'] = issue['id']
            f = issue['fields']
            v['labels'] = f['labels']
            self.setPerson(v,f,'reporter','reporter')
            v['priority'] = f['priority']['name'] if 'priority' in f else None
            self.setDate(v,f,'created','created')
            self.setPerson(v,f,'assignee','assignee')
            v['status'] = f['status']['name']
            v['components'] = []
            for component in f['components']:
                v['components'].append(component['name'])
            v['project'] = f['project']['key']
            v['projectName'] = f['project']['name']
            v['issuetype'] = f['issuetype']['name'] if 'issuetype' in f else None
            if f['duedate'] :
                v['dueDate'] = f['duedate']
            self.setDate(v,f,'updated','updated')
            v['summary'] = f['summary']
            v['resolutiondate'] = f['resolutiondate']
            if 'customfield_10002' in f:
                tmp = f['customfield_10002'] if 'customfield_10002' in f else None
                if tmp:
                    v['storyPoints'] = [ { 
                        'author': v['reporter'] ,
                        'date': v['createdDate'] , 
                        'value':tmp,
                    } ]
    
            v['isOverdue'] = self.isOverdue(f['duedate'])


             #v['createdDate'] = self.getDate(f['created'])

            v['createdDateToAssignee'] = v['createdDate']
             #v['updated'] = f['updated']
             #v['updatedDate'] = self.getDate(f['updated'])
            v['description'] = f.get('description','')
             #v['reporter'] = f['reporter']['name'] if 'name' in f['reporter'] else ''
             #v['reporterName'] = f['reporter']['displayName'] if 'displayName' in f['reporter'] else ''
             #v['reporterEmail'] = f['reporter']['emailAddress'] if 'emailAddress' in f['reporter'] else ''
            '''
            if v['key'] == 'XWAVE-2235':
                print('!-> XWAVE-2235 assignee:',v['assignee'] , f['assignee'])
            '''
            v['taskCategory'] = f['customfield_10311']['value'] if 'customfield_10311' in f and f['customfield_10311'] else None
            v['parent'] = f['parent']['key'] if 'parent' in f else None
            v['labels'] = f['labels']
            v['setAgainDueDate'] = self.isOverSetDueDate(f['duedate'])
            v['resolution'] = f['resolution']['name'] if 'resolution' in f and f['resolution'] and 'name' in f['resolution'] else None

            # comments
            if 'comment' in f and 'comments' in f['comment'] :
                comments = f['comment']['comments']
                for comment in comments:
                    if comment['updated']  < sevenDaysAgoStr:
                         #continue
                        pass
                    ccc = {}
                    ansBodyParse = {}
                    mentionedFlag = False
                    self.setPerson(ccc,comment,'author','updateAuthor')
                    self.setDate(ccc,comment,'updated','updated')
                     #ccc['author'] = comment['updateAuthor']['name']
                     #ccc['authorName'] = comment['updateAuthor']['displayName']
                     #ccc['authorEmail'] = comment['updateAuthor']['emailAddress']
                    ccc['body'] = comment['body']
                     #ccc['updated'] = comment['updated']
                     #ccc['updatedDate'] = self.getDate(comment['updated'])
                    date = ccc['updated']
                    y = wr1Re.findall(comment['body'])
                    if y:
                        #print('wr1',kVlm , y)
                        if date not in ansBodyParse:
                            ansBodyParse[date] = []
                        for y1 in y:
                            y2 = wr11Re.findall(y1)
                            #print('y2:',y2)
                            ansBodyParse[date] += y2
                    y = wr2Re.findall(comment['body'])
                    if y:
                        #print('wr2',kVlm , y)
                        if date not in ansBodyParse:
                            ansBodyParse[date] = []
                        ansBodyParse[date] += y
                    y = wr3Re.findall(comment['body'])
                    if y:
                        #print('wr3',kVlm , y)
                        if date not in ansBodyParse:
                            ansBodyParse[date] = []
                        ansBodyParse[date] += y
                    if ansBodyParse:
                        ccc['wrBody'] = ansBodyParse
                        v['existsWrBody'] = True
                    y = mentionedRe.findall(comment['body'])
                    if y:
                        mentionedFlag = True
                        v['existsMentionedBody'] = True
                        ccc['mentionedBody'] = ccc['body']
                    if ccc['author'] != mysetting.myid and mentionedFlag == False:
                        continue
                    if 'myCommentsList' not in v:
                        v['myCommentsList'] = []
                    v['myCommentsList'].append(ccc)

            # changelog histories
            v['reopened'] = False
            if 'changelog' in issue and 'histories' in issue['changelog'] :
                #v['histories'] = []
                histories = issue['changelog']['histories']
                for history in histories:
                    hhh = {}
                    self.setPerson(hhh,history,'author','author')
                    self.setDate(hhh,history,'created','created')
                    hhh['items'] = []
                    for item in history['items'] if 'items' in history else []:
                        hhh['items'].append({'field':item['field'] , 'fromString':item['fromString'] , 'from':item['from'], 'toString':item['toString'] , 'to':item['to']} )
                        if item['field'] == 'duedate':
                             #print("!duedate:",v['key'],item['field'] , 'fromString:',item['fromString'] , 'from:',item['from'], 'toString:',item['toString'] , 'to:',item['to'] )
                            if item['from']:
                                if 'duedateStat' not in v:
                                    v['duedateStat'] = {}
                                if hhh['author'] not in v['duedateStat']:
                                    v['duedateStat'][hhh['author']] = []
                                v['duedateStat'][hhh['author']].append(item['to'])
                        elif item['field'] == 'status' and item['toString'] == 'Reopened' :
                            v['reopened'] = True
                            if 'reopenedAuthor' not in v:
                                v['reopenedAuthor'] = []
                            v['reopenedAuthor'].append(hhh['author'])
                            v['reopenedAssignee'] = []
                             #self.setDate(v,hhh,'reopenedCreated','created')
                            grp = dateRe.search(hhh['created'])
                            if 'reopenedCreatedDate' not in v:
                                v['reopenedCreatedDate'] = []
                            if grp:
                                v['reopenedCreatedDate'].append(grp.group('date'))
                            else :
                                v['reopenedCreatedDate'].append('')
                        elif item['field'] == 'assignee':
                            if 'assigneeHistory' not in v:
                                v['assigneeHistory'] = [item['from'],item['to']]
                                v['assigneeDateHistory'] = [v['createdDate'],hhh['createdDate']]
                                if v['assignee'] == item['to']:
                                    v['createdDateToAssignee'] = hhh['createdDate']
                            else:
                                v['assigneeHistory'].append(item['to'])
                                v['assigneeDateHistory'].append(hhh['createdDate'])
                                if v['assignee'] == item['to']:
                                    v['createdDateToAssignee'] = hhh['createdDate']
                        '''
                        elif item['field'] in ['RemoteIssueLink','Link']:
                            if item['field'] not in v:
                                v[item['field']] = [item['toString']]
                            else:
                                v[item['field']].append(item['toString'])
                        '''
                    #v['histories'].append(hhh)

            # check recent comments from assginee 
            assigneeCommentDate = ''
            if 'comments' in v:
                for idx,sh in reversed(list(enumerate(v['comments']))):
                    if sh['author'] == v['assignee']:
                        assigneeCommentDate = sh['updatedDate']
                        break
                     # we need to decide whether commit is one of comments or not.
                    if 'commit' in sh and 'committer' in sh['commit'] and sh['commit']['committer'] == v['assignee']:
                        assigneeCommentDate = sh['updatedDate']
                        break
            if assigneeCommentDate:
                v['recentUpdatedDateFromAssignee'] = assigneeCommentDate

            # mysetting.workPriority calculation
            # Priority (1000) > Mentioned (200) > expired (150 + 7일마다 11점)  > reopen (횟수 * 100) > pingpong 5번 이상 (횟수 * 12)
            if 'workPriority' not in v:
                v['workPriority'] = 0
                v['workPriorityEvidence'] = []
            if v['priority'] == 'P0':
                v['workPriority'] += 1000
                v['workPriorityEvidence'].append('P0')
            elif v['priority'] == 'P1':
                v['workPriority'] += 500
                v['workPriorityEvidence'].append('P1')
            if v.get('existsMentionedBody',False) == True:
                v['workPriority'] += 200
                v['workPriorityEvidence'].append('mentioned')
            if v.get('dueDate',None):
                date = v.get('dueDate',None)
                format = "%Y-%m-%d"
                vDate = datetime.datetime.strptime(date, format)
                today = datetime.datetime.today()
                diffDays = (today - vDate).days
                if diffDays >= 7:
                    v['workPriority'] += 120
                    v['workPriority'] += ((diffDays-7) // 7) * 11
                    v['workPriorityEvidence'].append('overdue({d}d)'.format(d=diffDays))
            if v.get('reopened',False) == True:
                v['workPriority'] += 130
                v['workPriorityEvidence'].append('reopened')
            if len(v.get('assigneeHistory',[])) >= 5:
                v['workPriority'] += (len(v.get('assigneeHistory',[])) - 4)*12
                v['workPriorityEvidence'].append('pingpong({d})'.format(d=len(v.get('assigneeHistory',[]))))

                
        #print('vlm:',self.vlm)
        with open(self.jsonoutput,"w") as json_file: 
            print('write jsonoutput:',self.jsonoutput , '<- self.vlm')
            json.dump(self.vlm,json_file,indent = 4)
        
        '''
        self.tableFieldName = {  # { Display : multiple keys with comma }
            'VLM':'vlmlink'
            , 'Reporter':'reporter'
            , 'Assignee':'assigneeName'
            , 'LastCreate' : 'lastCreatedDate'
            , 'LastUpdate' : 'lastUpdatedDate'
            , 'Due Date' : 'duedate'
            , 'Reason' : 'reason,reasonMsg'
            , 'Status' : 'status,reopenedlink,reopenedAuthor'
            , 'Summary' : 'summary'
            , 'Description' : 'descriptionlink'
            , 'Comment' : 'commentlink'
            }
        '''

    def updateComments(self,a):
        #for i,a in enumerate(issuesJQL['issues']):
        #   a = issuesJQL['issues'][i]
        checkHelpMsg = ''
        checkOverdue = False
        keyI = a['key']
        summaryI = a['fields']['summary']
        descriptionI = a['fields'].get('description','')
        duedateI = a['fields']['duedate']
        projectI = ''
        today = datetime.date.today()
        if duedateI and duedateI >= str(today):
            return
        if duedateI and duedateI < str(today):
            checkOverdue = True
             #print(duedateI,str(today))
            if not checkHelpMsg:
                checkHelpMsg = '''it is overdue date.
(korean) 진행 내용 update 해주시기 요청 드립니다.
- resolve or close is the best.
- change your due date. but it should be within 15 days if possible.
- change the status ('BACK LOG' or 'WAIT RESPONSE') in TIGER Project
  - BACK LOG : this is not important or it takes a long time. so we should estimate it again.
  - WAIT RESPONSE : wait for other engineer's done
'''
            
        if 'project' in a['fields'] and None !=  a['fields']['project']:
            projectI = a['fields']['project'].get('key','')
            projectNameI = a['fields']['project'].get('name','')
        if projectI not in mysetting.cmuProject:
            return 
        taskCategory = ""
        if 'customfield_10311' in a['fields'] and None !=  a['fields']['customfield_10311']:
            # TypeError: 'NoneType' object is not subscriptable  --> https://daewonyoon.tistory.com/368
            taskCategory = a['fields']['customfield_10311']['value']
            #print("category:",keyI,len(issuesJQL['issues']),i,"taskCategory:",taskCategory)
        cmuLabels = ['cmu-wait-response','cmu-backlog','cmu-wait-for-response']
        labelsListI = []
        labelsListCmuFlag = False
        if 'labels' in a['fields']:
            for lk in a['fields']['labels']:
                labelsListI.append(lk)
                if lk.lower() in cmuLabels:
                    labelsListCmuFlag = True
            
        # for idx in a['fields']['labels']:
        #     print(idx)
        #     labelsListI.append(a['fields']['labels'][idx])
        reporterI = ""
        reporterNameI = ""
        reporterEmailI = ""
        if 'reporter' in a['fields'] and None != a['fields']['reporter']:
            if 'name' in a['fields']['reporter']:
                reporterI = a['fields']['reporter']['name']
            if 'displayName' in a['fields']['reporter']:
                reporterNameI = a['fields']['reporter']['displayName']
            if 'emailAddress' in a['fields']['reporter']:
                reporterEmailI = a['fields']['reporter']['emailAddress']
        assigneeI = ""
        assigneeNameI = ""
        assigneeEmailI = ""
        if 'assignee' in a['fields'] and a['fields']['assignee'] != None:
            # print(a['fields']['assignee'])
            if  'name' in a['fields']['assignee']:
                # print(a['fields']['assignee']['name'])
                assigneeI = a['fields']['assignee']['name']
                assigneeNameI = a['fields']['assignee']['displayName']    
            if 'emailAddress' in a['fields']['assignee']:
                assigneeEmailI = a['fields']['assignee']['emailAddress']
        if reporterI == assigneeI:
            return 
        if reporterI in ['auto-tiger','tigerauto']:
            return
        hdrMsg = 'written by CMU robot for updating comments overdue and pending etc -> {assignee} needs update'.format(assignee=assigneeI)
        iid = assigneeI
        if iid in member:
            hdrCommitterMsg = 'assignee (committer) display:{d} mobile:{m} unit:{u} ({uu}) part:{p} scrum:{s}\n'.format(d=member[iid]['displayName'],m=member[iid]['mobile'],u=member[iid]['department'],uu=member[iid]['unit'],p=member[iid]['part'],s=member[iid]['scrum'])
        else:
            hdrCommitterMsg = 'assignee : {a} is not related to CMU\n'.format(a=iid)
        
        id = assigneeI
        updatedI = a['fields']['updated']
        grp = dateRe.search(updatedI)
        updatedDateI = ""
        if grp:
            updatedDateI = grp.group('date')
        createdI = a['fields']['created']
        grp = dateRe.search(createdI)
        createdDateI = ""
        if grp:
            createdDateI = grp.group('date')
        statusI = a['fields']['status']['name']
        # componentsListI = a['fields']['components']
        componentsListI = []
        for idx in a['fields']['components']:
            # print(idx)
            componentsListI.append(idx['name'])
        parentI = ""
        if 'parent' in a['fields']:
            parentI = a['fields']['parent']['key']
        priorityI = ''
        if 'priority' in a ['fields']:
            priorityI = a['fields']['priority']['name']

        # check last reopen in changelog
        reopenedI = False
        reopenedAuthor = ''
        reopenedCreated = ''
        historyI = a['changelog']['histories']
        lastCreatedDate = createdDateI
        assigneeList = []
        for hi,hv in enumerate(historyI):
            if 'items' in hv:
                for itemi,itemv in enumerate(hv['items']):
                    if itemv['field'] == 'status' and itemv['toString'] == 'Reopened':
                        reopenedI = True
                        reopenedAuthor = hv['author']['displayName']
                        reopenedCreated = hv['created']
                        assigneeList = []
                        grp = dateRe.search(hv['created'])
                        if grp:
                            lastCreatedDate  = grp.group('date')
                    if itemv['field'] == 'assignee':
                        if not assigneeList:
                            assigneeList.append(itemv['from'])
                        assigneeList.append(itemv['to'])
                        if itemv['to'] == assigneeI:
                            grp = dateRe.search(hv['created'])
                            if grp:
                                lastCreatedDate  = grp.group('date')
                        
        
        # comments
        lastDateRobotComment = ''
        lastDateAssignee = ''
        lastDateUpdated = ''
        for ii,vv in enumerate(a['fields']['comment']['comments']):
            # c = {}
            # c['author'] = vv['updateAuthor']['name']
            # c['authorName'] = vv['updateAuthor']['displayName']
            # c['authorEmail'] = vv['updateAuthor']['emailAddress']
            # c['updated'] = vv['updated']
            grp = dateRe.search(vv['updated'])
            updatedDate = ""
            if grp:
                updatedDate = grp.group('date')
            # c['updatedDate'] = updatedDate
            # c['body'] = vv['body']
            # print("body::",vv['body'])
            if vv['body'].lstrip().find(hdrMsg) >= 0:
                if vv['body'].lstrip().startswith(hdrMsg):
                    if updatedDate > lastDateRobotComment:
                        lastDateRobotComment = updatedDate
                        continue
                else :
                    print('vv-[body]:"{v}"'.format(v=vv['body']))
            if updatedDate > lastDateUpdated:
                lastDateUpdated = updatedDate
            if vv['updateAuthor']['name'] == assigneeI:
                if updatedDate > lastDateAssignee:
                    lastDateAssignee = updatedDate
            
                    
        # open,reopen  == statusI
        #   statusI 
        checkOpenDateProject = ''
        checkProgressDateProject = ''
        chekcOpenNoCommentDateProject = ''
        chekcProgressNoCommentDateProject = ''
        if projectI in mysetting.cmuProject:
            checkOpenDateProject = mysetting.check_tiger_open_days   # create 시간 기준
            checkProgressDateProject = mysetting.check_tiger_progress_days   # create 시간 기준
            checkNoCommentDateProject = checkProgressDateProject    # // 2   # ticket  update 해야 하는 것은 status 상관없이 동일
            if not checkHelpMsg:
                checkHelpMsg = '''you should do one of the following actions.
(korean) 진행 내용 update 해주시기 요청 드립니다.
- resolve or close is the best.
- add your comments for this issue
- change your due date. but it should be within 15 days if possible.
- change the status ('BACK LOG' or 'WAIT RESPONSE') in TIGER Project
  - BACK LOG : this is not important or it takes a long time. so we should estimate it again.
  - WAIT RESPONSE : wait for other engineer's done
'''
        else:
            checkOpenDateProject = mysetting.check_open_days
            checkProgressDateProject = mysetting.check_progress_days
            checkNoCommentDateProject = checkProgressDateProject  # // 2
            if not checkHelpMsg:
                checkHelpMsg = '''you should do one of the following actions.
(korean) 진행 내용 update 해주시기 요청 드립니다.
- resolve or close
- add your comments for this issue
- change your due date. but it should be within 15 days if possbile.
- change the status ('BACK LOG' or 'WAIT RESPONSE') in TIGER Project
  - BACK LOG : this is not important or it takes a long time. so we should estimate it again.
  - WAIT RESPONSE : wait for other engineer's done
'''
        if priorityI == 'P0' or priorityI == 'P1':
            checkOpenDateProject //= 2
            checkProgressDateProject //= 2
            checkNoCommentDateProject //= 2
        commentMsg = ''
        commentFlag = False
        reason = ''
        reasonMsg = ''
        if statusI in ['Open','Reopened'] and labelsListCmuFlag == False:
            if checkOverdue or (not self.isWithinCheckDay(lastCreatedDate,checkOpenDateProject)) :
                if self.isWithinCheckDay(date=lastDateAssignee,checkDays=checkNoCommentDateProject) == False:
                    print('Found Open ',lastDateAssignee,checkOpenDateProject , lastCreatedDate,checkNoCommentDateProject)
                    print('Open False',statusI,createdI,projectI,keyI,duedateI)
                    print('Open label:',labelsListI, labelsListCmuFlag)
                    print('Open reopened:',reopenedI,reopenedAuthor)
                    print('Open comments Robot:',lastDateRobotComment,'A:',lastDateAssignee,'U:',lastDateUpdated)
                    commentMsg = hdrMsg + '\n\n' + hdrCommitterMsg + checkHelpMsg
                    commentFlag = True
                    reason = 'lastUpdatedDate'
                    reasonMsg = 'TooLongInOpen project:{pro} priority:{pri} <br>pending duration:{d} <br>update:{u} <br>last Open:{r} <br>{e}'.format(pro=projectI,pri=priorityI,d=checkOpenDateProject,u=updatedDateI,r=lastCreatedDate,e='last assigned to you :{t}'.format(t=lastDateAssignee) if lastDateAssignee else '')
                    print('lastCreatedDate:',lastCreatedDate, 'assigneeList', assigneeList)
                    print('Open commentMsg:',commentMsg)
        elif statusI in ['In Progress'] and labelsListCmuFlag == False:
            if checkOverdue or (not self.isWithinCheckDay(lastCreatedDate,checkProgressDateProject)) :
                if self.isWithinCheckDay(date=lastDateAssignee,checkDays=checkNoCommentDateProject) == False:
                    print('Found Progress ',lastDateAssignee,checkProgressDateProject , lastCreatedDate,checkNoCommentDateProject)
                    print('Progress False',statusI,createdI,projectI,keyI,duedateI)
                    print('Progress label:',labelsListI, labelsListCmuFlag)
                    print('Progress reopened:',reopenedI,reopenedAuthor)
                    print('Progress comments Robot:',lastDateRobotComment,'A:',lastDateAssignee,'U:',lastDateUpdated)
                    commentMsg = hdrMsg + '\n\n' + hdrCommitterMsg + checkHelpMsg
                    commentFlag = True
                    reason = 'lastUpdatedDate'
                    reasonMsg = 'TooLongInProgress project:{pro} priority:{pri} <br>pending duration:{d} <br>update:{u} <br>last Open:{r} <br>{e}'.format(pro=projectI,pri=priorityI,d=checkProgressDateProject,u=updatedDateI, r=lastCreatedDate,e='last assigned to you :{t}'.format(t=lastDateAssignee) if lastDateAssignee else '')
                    print('lastCreatedDate:',lastCreatedDate, 'assigneeList', assigneeList)
                    print('Progress commentMsg:',commentMsg)
        if checkOverdue:
            commentFlag = True
            reason = 'duedate'
            reasonMsg = 'OverDue duedate: {ov}'.format(ov=duedateI)
            checkHelpMsg = '''you should do one of the following actions.
(korean) 진행 내용 update 해주시기 요청 드립니다.
- resolve or close
- change your due date. but it should be within 15 days if possbile.
- change the status ('BACK LOG' or 'WAIT RESPONSE') in TIGER Project
  - BACK LOG : this is not important or it takes a long time. so we should estimate it again.
  - WAIT RESPONSE : wait for other engineer's done
'''
            commentMsg = hdrMsg + '\n\n' + hdrCommitterMsg + checkHelpMsg
        if commentFlag :
            p = {}
            p['addCommentNow'] = 'O'  # if you remove 'O' , it is not added in comments. generally this feature is for forced editor before running vlm-add-comment.py
            p['VLM'] = keyI
            p['vlmlink'] = '''<a href="http://vlm.lge.com/issue/browse/{vlm}">{vlm}</a>'''.format(vlm=keyI)
            p['reporter'] = reporterI
            p['reporterName'] = reporterNameI
            p['assignee'] = assigneeI
            p['assigneeName'] = assigneeNameI
            p['lastCreatedDate'] = lastCreatedDate
            p['duedate'] = duedateI
            p['lastUpdatedDate'] = lastDateAssignee
            p['reason'] = reason
            p['reasonMsg'] = reasonMsg
            p['status'] = statusI
            p['reopened'] = reopenedI
            p['reopenedlink'] = ''
            if reopenedI:
                p['reopenedlink'] = '(Reopened)'
            p['reopenedAuthor'] = reopenedAuthor
            p['assigneeList'] = assigneeList
            p['comment'] = commentMsg
            p['commentlink'] = '<br>'.join(commentMsg.split('\n')) + '<br> reason message :{t}\n'.format(t=reasonMsg) if reasonMsg else ''
            p['summary'] = summaryI
            ss,ll = self.getShortSummary(descriptionI,mysetting.description_show_lines_count)
            p['descriptionlink'] = "<details><summary>" + ss + "</summary>" + ll + "</details>"
            p['lastDateRobotComment'] = lastDateRobotComment
            
            if id not in self.commentsAll:
                self.commentsAll[id] = {}
            if keyI not in self.commentsAll[id]:
                self.commentsAll[id][keyI] = {}
            self.commentsAll[id][keyI] = p
            
            if lastDateRobotComment and self.isWithinCheckDay(date=lastDateRobotComment,checkDays=checkNoCommentDateProject) == True:
                return
            print('lastDateRobotComment:',lastDateRobotComment, checkNoCommentDateProject , 'vlm:',keyI)
            if id not in self.comments:
                self.comments[id] = {}
            if keyI not in self.comments[id]:
                self.comments[id][keyI] = {}
            self.comments[id][keyI] = p

    def getShortSummary(self,s,lines):
        if s:
            a = s.split('\n')
            return '\n'.join(a[0:lines]) , '\n' + '\n'.join(a[lines:])
        return '\n','\n'

    def runWorkPriorityRule(self,v,rule,evidence,depth=0):
        # workPriorityRule['_field_(rk)']['project(rk2)'] = {
        #   'WAVE(rk3)':500(rv3),
         #if depth > 0: print(rule,evidence,depth)
        for rk,rv in rule.items():
            if rk == '_field_':
                if isinstance(rv,dict):
                    for rk2,rv2 in rv.items():
                        if rk2 not in v:
                            continue
                        if not isinstance(rv2,dict):
                            print('runWorkPriorityRule: _field_ : error : key : ' ,rk2, 'type:',type(rv2)) 
                        for rk3 , rv3 in rv2.items():
                             #if depth > 0: print('0:',rk2,v[rk2],rk3,rv3,evidence,depth)
                            if isinstance(v[rk2] ,(list,tuple)):
                                 #if depth > 0: print('1:',rk3,rv3,evidence,depth)
                                for i4 in v[rk2]:
                                    if (isinstance(rk3,str) and i4.lower() == rk3.lower()) or (not isinstance(rk3,str) and i4 == rk3) :
                                        if isinstance(rv3,dict):
                                            self.runWorkPriorityRule(v,rv3,'{a}-{b}-{i} : '.format(a=rk2,b=rk3,i=str(v[rk2])) + evidence,depth=depth+1)
                                        else:
                                            if len(rv3) < 4 : print('ERROR', rv2 , ':',rv3 , ':should more than 4.')
                                            v['workPriority'] += rv3[0]
                                            if rv3[1] and rv3[1] not in v['workPriorityKinds']:
                                                v['workPriorityKinds'].append(rv3[1])
                                            v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type f1: {e}'.format(e=evidence + ':{a}-{b}'.format(a=rk2,b=rk3),v=int(rv3[0]),r=rv3[2]))
                                            v['workPriorityEvidence'].append({'reason-eng' : rv3[2] , 'reason-kor' : rv3[3] , 'point' : rv3[0] ,  'kind' : rv3[1] , 'variable':rk2 , 'value':rk3})
                            else :
                                 #if depth > 0: print('2:',rk3,rv3,evidence,depth)
                                if (isinstance(rk3,str) and isinstance(v[rk2],str) and v[rk2].lower() == rk3.lower()) or (not isinstance(rk3,str) and v[rk2] == rk3) :
                                    if isinstance(rv3,dict):
                                        self.runWorkPriorityRule(v,rv3,'{a}-{b} : '.format(a=rk2,b=rk3) + evidence ,depth=depth+1)
                                    else:
                                        v['workPriority'] += rv3[0]
                                        if rv3[1] and rv3[1] not in v['workPriorityKinds']:
                                            v['workPriorityKinds'].append(rv3[1])
                                        v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type f2: {e}'.format(e=evidence + ':{a}-{b}'.format(a=rk2,b=rk3),v=int(rv3[0]),r=rv3[2]))
                                        v['workPriorityEvidence'].append({'reason-eng' : rv3[2] , 'reason-kor' : rv3[3] , 'point' : rv3[0] ,  'kind' : rv3[1] , 'variable':rk2 , 'value':rk3})
                else:
                    print('runWorkPriorityRule: _field_ : error : type : ' , type(rv))
            elif rk == '_default_':
                v['workPriority'] += rv[0]
                if rv[1] and rv[1] not in v['workPriorityKinds']:
                    v['workPriorityKinds'].append(rv[1])
                v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type d1: {e}'.format(e=evidence,v=int(rv[0]),r=rv[2]))
                v['workPriorityEvidence'].append({'reason-eng' : rv[2] , 'reason-kor' : rv[3] , 'point' : rv[0] ,  'kind' : rv[1] , 'variable':rk , 'value':rk})
            elif rk == '_include_':
                if isinstance(rv,dict):
                    for rk2,rv2 in rv.items():
                        if rk2 not in v:
                            continue
                        if not isinstance(rv2,dict):
                            print('runWorkPriorityRule: _include_ : error : key : ' ,rk2, 'type:',type(rv2)) 
                        for rk3 , rv3 in rv2.items():
                             #print('0:',rk2,v[rk2],rk3,rv3,evidence,depth)
                            if isinstance(v[rk2] ,(list,tuple)):
                                 #print('1:',rk3,rv3,evidence,depth)
                                for i4 in v[rk2]:
                                    if not i4:
                                        continue
                                    if isinstance(rk3,(list,tuple)):
                                         #print('1-1:',rk3,rv3,evidence,depth)
                                        myFindFlag = True
                                        for myitem in rk3:
                                            if not myitem:
                                                continue
                                            if i4.lower().find(myitem.lower()) < 0:
                                                myFindFlag = False
                                                break
                                        if myFindFlag:
                                            v['workPriority'] += rv3[0]
                                            if rv3[1] and rv3[1] not in v['workPriorityKinds']:
                                                v['workPriorityKinds'].append(rv3[1])
                                            v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type i1: {e}'.format(e=evidence + ':{a}-{b}'.format(a=rk2,b=str(rk3)),v=int(rv3[0]),r=rv3[2]))
                                            v['workPriorityEvidence'].append({'reason-eng' : rv3[2] , 'reason-kor' : rv3[3] , 'point' : rv3[0] ,  'kind' : rv3[1] , 'variable':rk2 , 'value':rk3})
                                    elif (isinstance(rk3,str) and i4.lower() == rk3.lower()) or (not isinstance(rk3,str) and i4 == rk3) :
                                        if isinstance(rv3,dict):
                                            self.runWorkPriorityRule(v,rv3,'{a}-{b}-{i} : '.format(a=rk2,b=rk3,i=str(v[rk2])) + evidence,depth=depth+1)
                                        else:
                                            v['workPriority'] += rv3[0]
                                            if rv3[1] and rv3[1] not in v['workPriorityKinds']:
                                                v['workPriorityKinds'].append(rv3[1])
                                            v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type i3: {e}'.format(e=evidence + ':{a}-{b}'.format(a=rk2,b=rk3),v=int(rv3[0]),r=rv3[2]))
                                            v['workPriorityEvidence'].append({'reason-eng' : rv3[2] , 'reason-kor' : rv3[3] , 'point' : rv3[0] ,  'kind' : rv3[1] , 'variable':rk2 , 'value':rk3})
                            else :
                                 #print('2:',rk3,rv3,evidence,depth)
                                if isinstance(rk3,(list,tuple)):
                                    myFindFlag = True
                                    for myitem in rk3:
                                        if not myitem:
                                            continue
                                        print('2-1:',myitem,i4,evidence,depth)
                                        if i4.lower().find(myitem.lower()) < 0:
                                            myFindFlag = False
                                            break
                                    if myFindFlag:
                                        v['workPriority'] += rv3[0]
                                        if rv3[1] and rv3[1] not in v['workPriorityKinds']:
                                            v['workPriorityKinds'].append(rv3[1])
                                        v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type i2: {e}'.format(e=evidence + ':{a}-{b}'.format(a=rk2,b=str(rk3)),v=int(rv3[0]),r=rv3[2]))
                                elif v[rk2].lower().find(rk3.lower()) >= 0:
                                     #print('2-2:',v[rk2],rk3,depth)
                                    if isinstance(rv3,dict):
                                        self.runWorkPriorityRule(v,rv3,'{a}-{b} : '.format(a=rk2,b=rk3) + evidence,depth=depth+1)
                                    else:
                                        v['workPriority'] += rv3[0]
                                        if rv3[1] and rv3[1] not in v['workPriorityKinds']:
                                            v['workPriorityKinds'].append(rv3[1])
                                        v['workPriorityEvidenceStr'].append('point {v:-15d} : reason> {r} : type i4: {e}'.format(e=evidence + ':{a}-{b}'.format(a=rk2,b=rk3),v=int(rv3[0]),r=rv3[2]))
                else:
                    print('runWorkPriorityRule: _include_ : error : type : ' , type(rv))
            else:
                print('runWorkPriorityRule: error : ' , rk)


    def getOwner(self, commiturl) :
        ownereamil : str = ''
        if (commiturl.find("http://vgit.lge.com/na") >=0) : # mysetting.mygerriturl
            commiturlparsing=commiturl.split("/")
            changestr = "/changes/"+commiturlparsing[-1]+"/detail"
            try:
                changes = self.restna.get(changestr, headers={'Content-Type': 'application/json'})
            except:
                return ''
            ownereamil = str(changes['owner']['email']).split('@')[0]
        elif (commiturl.find("http://vgit.lge.com/eu") >=0) : # mysetting.mygerriturl
            commiturlparsing=commiturl.split("/")
            changestr = "/changes/"+commiturlparsing[-1]+"/detail"
            try:
                changes = self.resteu.get(changestr, headers={'Content-Type': 'application/json'})
            except:
                return ''
            ownereamil = str(changes['owner']['email']).split('@')[0]
        elif (commiturl.find("http://vgit.lge.com/as") >=0) : # mysetting.mygerriturl
            commiturlparsing=commiturl.split("/")
            changestr = "/changes/"+commiturlparsing[-1]+"/detail"
            try:
                changes = self.restas.get(changestr, headers={'Content-Type': 'application/json'})
            except:
                return ''
            ownereamil = str(changes['owner']['email']).split('@')[0]
        '''
        '''
        return ownereamil

    def commentBodyParse(self,c,body):
        if not body:
            return None
        c['whom'] = []
        result_list = re.findall(r"\[~([a-zA-Z0-9\._\+]+)\]",body)
        for i in result_list:
            c['whom'].append(i)
        if body.startswith('written by CMU robot for cmu-testcase'):
            if c['author'] in ['tigerauto','cheoljoo.lee']:
                print('! autoTestcaseComment')
                c['autoTestcaseComment'] = c['author']
        if body.startswith('written by CMU robot for updating comments overdue and pending etc ->'):
            if c['author'] in ['tigerauto','cheoljoo.lee']:
                c['autoUpdateComments'] = {}
                parseKey = {}
                parseKey['id'] = robotStartRe
                parseKey['msg'] = robotReasonRe
                for a in body.split('\n'):
                    for line in a.split('<br>'):
                        for k,vRe in parseKey.items():
                            grp = vRe.search(line)
                            if grp:
                                c['autoUpdateComments'][k] = grp.group(k)
        if body.startswith('The changes(commits) about this JIRA ticket have been merged in'):  # vgit
            if c['author'] == 'vc.integrator':
                c['commit'] = {}
                c['commit']['type'] = 'vgit'
                c['commit']['date'] = c['updatedDate']
                parseKey = {}
                parseKey['url'] = vgitUrlLineRe
                parseKey['url2'] = vgitUrlLineRe2
                parseKey['vlm'] = vgitVlmLineRe
                parseKey['branch'] = vgitBranchLineRe
                for a in body.split('\n'):
                    for line in a.split('<br>'):
                        for k,vRe in parseKey.items():
                            grp = vRe.search(line)
                            if grp:
                                if 'url' in  c['commit'] or 'url2' in  c['commit']:
                                    continue
                                c['commit'][k] = grp.group(k)
                                if self.debug: print('matched:',k,grp.group(k))
                if 'url' in c['commit']:
                    return c['commit']['url']
                elif 'url2' in c['commit']:
                    return c['commit']['url2']
            elif body.startswith('The changes(commits) about this JIRA ticket have been merged in SLDD'):
                c['commit'] = {}
                c['commit']['type'] = 'sldd'
                parseKey = {}
                parseKey['url'] = slddUrlLineRe
                parseKey['vlm'] = vlmRe
                parseKey['model'] = modelRe
                parseKey['branch'] = branchRe
                parseKey['committer'] = committerRe
                parseKey['summary'] = summaryRe
                parseKey['date'] = slddDateRe
                for a in body.split('\n'):
                    for line in a.split('<br>'):
                        for k,vRe in parseKey.items():
                            grp = vRe.search(line)
                            if grp:
                                c['commit'][k] = grp.group(k)
                                if self.debug: print('matched:',k,grp.group(k))
            elif body.startswith('The changes(commits) about this JIRA ticket have been merged in mod.lge.com'):
                c['commit'] = {}
                c['commit']['type'] = 'mod'
                parseKey = {}
                parseKey['url'] = modUrlLineRe
                parseKey['committer'] = committerRe
                parseKey['summary'] = summaryRe
                parseKey['date'] = modDateRe
                for a in body.split('\n'):
                    for line in a.split('<br>'):
                         #print('!line:',line)
                        for k,vRe in parseKey.items():
                             #print(k,vRe)
                            grp = vRe.search(line)
                            if grp:
                                c['commit'][k] = grp.group(k)
                                if self.debug: print('matched:',k,grp.group(k))
        return None


    def whichProgress(self,wp):
        pg = ['DV','PV','MP']
        if wp in mysetting.milestoneStart:
            today = str(datetime.date.today())
             #print('today:',today)
            for pgi in pg:
                if pgi in mysetting.milestoneStart[wp] and mysetting.milestoneStart[wp][pgi] and today <= mysetting.milestoneStart[wp][pgi]:
                    return pgi
            pgi = pg[-1]
            if pgi in mysetting.milestoneStart[wp] and mysetting.milestoneStart[wp][pgi] and today > mysetting.milestoneStart[wp][pgi]:
                return 'AS'
        return None
    def whichModel(self,p):
         #if p['key'] == 'GENXII-6732': print(p['key'])
        if p['project'] in self.whichModelLower:
            ans = self.whichModelLower[p['project']].get('default',p['project'])
             #if p['key'] == 'GENXII-6732': print('ans:',ans)
            k = p['project']
            v = self.whichModelLower[k]
             #if p['key'] == 'GENXII-6732': print('ans:',k)
            for k2,v2 in v.get('fields',{}).items():
                 #if p['key'] == 'GENXII-6732': print('ans:',k2)
                if k2 in p and p[k2]:
                     #if p['key'] == 'GENXII-6732': print('whichModel !1 p k2:',k2 , 'value:',p[k2], 'k3 = keys v2:',list(v2.keys()), 'ans:',ans, 'which model:',self.whichModelLower)
                    if self.debug : print('whichModel !1 p k2:',k2 , 'value:',p[k2], 'k3 = keys v2:',list(v2.keys()), 'ans:',ans, 'which model:',self.whichModelLower , p,file=self.printf)
                    for k3,v3 in v2.items():
                        if isinstance(p[k2], (list, tuple)):
                            p[k2] = [x.lower().replace('_','-') for x in p[k2]]
                            if k3 in p[k2]:
                                 #if p['key'] == 'GENXII-6732': print('whichModel !2 matched p k3:',k3 , 'value:',p[k2], 'return:',v3)
                                if self.debug : print('whichModel !2 matched p k3:',k3 , 'value:',p[k2], 'return:',v3,file=self.printf)
                                return v3
                        else:
                            p[k2] = p[k2].replace('_','-')
                            if k3 == p[k2].lower():
                                 #if p['key'] == 'GENXII-6732': print('whichModel !2 matched p k3:',k3 , 'value:',p[k2].lower(), 'return:',v3)
                                if self.debug : print('whichModel !2 matched p k3:',k3 , 'value:',p[k2].lower(), 'return:',v3,file=self.printf)
                                return v3
        else :
            ans = p['project']
         #if p['key'] == 'GENXII-6732': print('ret ans:',ans)
        return ans

    def setPerson(self,v,f,vname,fname):
        '''
        if 'key' in v and v['key'] == 'XWAVE-2235':
            print('!! XWAVE-2235 setPerson assignee:',fname, f[fname])
        '''
        if fname in f:
            if f[fname]:
                v[vname] = f[fname]['name'] if 'name' in f[fname] else ''
                v[vname+'Name'] = f[fname]['displayName'] if 'displayName' in f[fname] else ''
                v[vname+'Email'] = f[fname]['emailAddress'] if 'emailAddress' in f[fname] else ''
                return
        v[vname] = ''
        v[vname+'Name'] = ''
        v[vname+'Email'] = ''

    def setDate(self,v,f,vname,fname):
        if fname in f:
            if f[fname]:
                v[vname] = f[fname]
                grp = dateRe.search(f[fname])
                if grp:
                    v[vname+'Date'] = grp.group('date')

    def isWithinCheckDay(self,date,checkDays):
        """
        True  : date + checkDays >= today
        False : date + checkDays <  today
        """
        if date == "":
            print("warning : isWithinCheckDay")
            return False
        today = datetime.date.today()
        grp = dateRe.search(date)
        if grp:
            target = datetime.date(int(grp.group('year')),int(grp.group('month')),int(grp.group('day')))
            # diff = today - target
            # print("today:",str(today))
            # print("date+checkDayes:",str(target + datetime.timedelta(days=checkDays)))
            if target + datetime.timedelta(days=checkDays) >= today:
                return True
            else:
                return False
        else :
            return False
        return True
    def isOverdue(self,date):
        """
        True  : date > today
        False : otherwise
        """
        if not date or date == "":
            return False
        today = datetime.date.today()
         #print('overdue:',date)
        grp = dateRe.search(date)
        if grp:
            target = datetime.date(int(grp.group('year')),int(grp.group('month')),int(grp.group('day')))
            # diff = today - target
            # print("today:",str(today))
            # print("date+checkDayes:",str(target + datetime.timedelta(days=checkDays)))
            if target > today:
                return False
            else:
                return True
        else :
            return False
        return False
    def isOverSetDueDate(self,date):
        """
        True  : date > today
        False : otherwise
        """
        if not date or date == "":
            return False
        target = datetime.date.today() + datetime.timedelta(days=10)   # mysetting.cmuDueDateMaxDuration)
         #print('overdue:',date)
        grp = dateRe.search(date)
        if grp:
            due = datetime.date(int(grp.group('year')),int(grp.group('month')),int(grp.group('day')))
            # diff = today - target
            # print("today:",str(today))
            # print("date+checkDayes:",str(target + datetime.timedelta(days=checkDays)))
            if due > target:
                return True
            else:
                return False
        else :
            return False
        return False
    

def traverseFD(f,vv,start:str):
    print(start,":",file=f)
    if isinstance(vv, dict):
        for k, v in vv.items():
            traverseFD(f,v,start + ":key=" + k )
    elif isinstance(vv, (list, tuple)):
        for i, x in enumerate(vv):
            traverseFD(f,x,start + ":idx=" + str(i) )
    else :
        print(start ,  ":value=", vv , file=f)

def traverseFile(filename:str,v,start:str,att):
    with open(filename, att, encoding='utf-8', errors='ignore') as f:
        traverseFD(f,v,start)

def transform(obj):
    _type = type(obj)
    if _type == tuple: _type = list
    rslt = _type()
    if isinstance(obj, dict):
        for k, v in obj.items():
            rslt[k] = transform(v)
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            rslt.append(transform(x))
    elif isinstance(obj, set):
        for x in obj:
            rslt.add(transform(x))
    elif isinstance(obj, (int)):
        rslt = hex(obj)
    else:
        rslt = obj

    return rslt

#element = transform(element)

def objwalk(obj, path=(), memo=None):
    if memo is None:
        memo = set()
    iterator = None
    if isinstance(obj, dict):
        iterator = iteritems
    elif isinstance(obj, (list, set)) and not isinstance(obj, string_types):
        iterator = enumerate
    if iterator:
        if id(obj) not in memo:
            memo.add(id(obj))
            for path_component, value in iterator(obj):
                if isinstance(value, tuple):
                    obj[path_component] = value = list(value)
                for result in objwalk(value, path + (path_component,), memo):
                    yield result
            memo.remove(id(obj))
    else:
        yield path, obj

class checkWorkPriorityRule:
    def __init__(self,rule,prefix='',inputdir='.'):
        self.wpr = []
        self.printWorkPriorityRule(rule,prefix)
        # for item in self.wpr:
        #     print("normal:",item)
        self.wpr = sorted(self.wpr)
        with open('{ii}/rule.txt'.format(ii=inputdir),"w") as external_file:
            print('rule definition output file :','{ii}/rule.txt'.format(ii=inputdir))
            for v,s in self.wpr:
                # sort(key = lambda item : ( -1 * item['workPriority'] , len(item['print'])
                print('rule:{v:-10d} {s}'.format(v=v,s=s),file=external_file)
                print('rule:{v:-10d} {s}'.format(v=v,s=s))
            
    def printWorkPriorityRule(self,rule,prefix):
        for rk,rv in rule.items():
            if rk == '_field_' or rk == '_include_':
                if isinstance(rv,dict):
                    for rk2,rv2 in rv.items():   # rk2 == 'project'
                        if not isinstance(rv2,dict):
                            print('printWorkPriorityRule: _field_ : error : key : ' ,rk2, 'type:',type(rv2)) 
                        for rk3 , rv3 in rv2.items():   # rk3 == HONDATELE   rv3 == [1000,'','','']
                            if isinstance(rv3,dict):
                                self.printWorkPriorityRule(rv3,prefix + ' : {t}-{a}-{b} '.format(t=rk,a=rk2,b=rk3))
                            else:
                                if len(rv3) < 4 : print('ERROR', rv2 , ':',rv3 , ':should more than 4.')
                                self.wpr.append([rv3[0],prefix + ' : {t}-{a}-{b}-{k}\n\t\teng:{r1}\n\t\tkor:{r2} '.format(t=rk,a=rk2,b=rk3,k=rv3[1],r1=rv3[2],r2=rv3[3])])
                                # print({'workPriority':rv3[0],'print': prefix + ' : {a}-{b}-{k}-{r1}-{r2} '.format(a=rk2,b=rk3,k=rv3[1],r1=rv3[2],r2=rv3[3])})
                else:
                    print('printWorkPriorityRule: _field_ : error : type : ' , type(rv))
            elif rk == '_default_':
                self.wpr.append([rv[0],prefix + ' : {a}-{b}-{k}-{r1}-{r2} '.format(a=rk,b='',k=rv[1],r1=rv[2],r2=rv[3])])
                # print({'workPriority':rv[0],'print': prefix + ' : {a}-{b}-{k}-{r1}-{r2} '.format(a=rk,b='',k=rv[1],r1=rv[2],r2=rv[3])})
            else:
                print('printWorkPriorityRule: error : ' , rk)
    

def work_func(x,inputdir,debug,outputfileprefix):
    #partial_func = partial(work_func, inputdir=args.inputdir,debug=args.debug,jqlLogFlag=args.jqlLog) 
    #print('!work filename',x,'inputdir:',inputdir)
    cs = CAnalysisVlm(
                 inputdir = inputdir
                 , filename = x
                 , debug = args.debug
                 , outputfileprefix = outputfileprefix
                 )
    return (len(cs.vlm) )

if (__name__ == "__main__"):

    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description= 'update comments on  untouched issues for a long time & this is library test',
        epilog='''id.csv (repoter) -> vlm.json (with comments)'''
    )

    parser.add_argument(
        '--inputdir',
        metavar="<str>",
        type=str,
        default='json',
        help='input directory name    default : json')

    parser.add_argument(
        '--finaldir',
        metavar="<str>",
        type=str,
        default='json',
        help='final directory name    default : json')

    parser.add_argument(
        '--inputfileprefix',
        metavar="<str>",
        type=str,
        default='jira',
        help='input file prefix    default : jira-*')

    parser.add_argument(
        '--outputfileprefix',
        metavar="<str>",
        type=str,
        default='now',
        help='output file prefix    default : now-*')

    parser.add_argument( '--debug', default=False , action="store_true" , help="debug mode on")

    args = parser.parse_args()


    filelist = []
    
    inputdir = args.inputdir
    if mysetting.myid:
        inputdir = mysetting.myid + '/' + args.inputdir
        finaldir = mysetting.myid + '/' + args.finaldir
    os.makedirs("{ii}".format(ii=finaldir),exist_ok=True)
    if not os.path.exists(inputdir):
        print('error : ', inputdir , 'does not exist')
        quit(4)
    l = os.listdir(inputdir)
    for s in l:
        if s.startswith('{file}-'.format(file=args.inputfileprefix)):
            filelist.append(s)
     #filelist.sort()
    print('filelist:',filelist)
    start = int(time.time())
    num_cores = 20   # 20
    pool = Pool(num_cores)
    partial_func = partial(work_func, inputdir=inputdir,debug=args.debug,outputfileprefix=args.outputfileprefix) 
    rt = pool.map(partial_func, filelist)
    print()
    print('rt process count:',len(rt))
    with open('{oo}/final-rt.json'.format(oo=finaldir),"w") as json_file: 
        print('write {oo}/final-rt.json'.format(oo=finaldir))
        json.dump(rt,json_file,indent = 4)
    
    ansCnt = 0
    for cnt in rt:
        ansCnt += cnt
    print('vlm count',ansCnt)
    '''
    ansCnt = 0
    nonplModelSet = set()
    reopenTestcase = []
    gComments = {}
    gCommentsAll = {}
    for cnt, gwDict,nonplModel , testcase , comments , commentsAll in rt:
         #gComments.append(comments)
        for gcId in comments:
            for gcVlm in comments[gcId]:
                if gcId not in gComments:
                    gComments[gcId] = {}
                if gcVlm not in gComments[gcId]:
                    gComments[gcId][gcVlm] = comments[gcId][gcVlm]
         #gCommentsAll.append(commentsAll)
        for gcId in commentsAll:
            for gcVlm in commentsAll[gcId]:
                if gcId not in gCommentsAll:
                    gCommentsAll[gcId] = {}
                if gcVlm not in gCommentsAll[gcId]:
                    gCommentsAll[gcId][gcVlm] = commentsAll[gcId][gcVlm]
        ansCnt += cnt
        for npm in nonplModel:
            nonplModelSet.add(npm)
        for url,owner in gwDict.items():
            if url in gerritOwnerDict and gerritOwnerDict[url] != owner:
                print('!!! warning:  {url}  :  {f} -> {t}'.format(url=url,f=gerritOwnerDict[url],t=owner))
            gerritOwnerDict[url] = owner
        reopenTestcase += testcase

    with open('{oo}/final-reopenTestcase.json'.format(oo=args.finaldir),"w") as json_file: 
        print('write {oo}/final-reopenTestcase.json'.format(oo=args.finaldir))
        json.dump(reopenTestcase,json_file,indent = 4)
     #print('gComments:',gComments)
    with open('{oo}/final-updateCommentsAll.json'.format(oo=args.finaldir),"w") as json_file: 
        print('write {oo}/final-updateCommentsAll.json'.format(oo=args.finaldir))
        json.dump(gCommentsAll,json_file,indent = 4)
    with open('{oo}/final-updateCommentsNew.json'.format(oo=args.finaldir),"w") as json_file: 
        print('write {oo}/final-updateCommentsNew.json'.format(oo=args.finaldir))
        json.dump(gComments,json_file,indent = 4)
    print('write end')
    fieldnames = ['url','owner']
    with open(gerritOwnerCsv , 'w', encoding='utf-8', errors='ignore',newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for k3,v3 in gerritOwnerDict.items():
            tmp = {'url':k3 , 'owner': v3}
            writer.writerow(tmp)
    print('ansCnt:',ansCnt)
    '''
    print("***run time(sec) :", int(time.time()) - start)

    
    '''
    l = os.listdir(args.inputdir)
    for s in l:
        if s.startswith('{file}-'.format(file=args.outputfileprefix)):
            print(s)
    '''



