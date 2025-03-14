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
import shutil
print(os.sys.path)
#from atlassian import Jira

import email, smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import mysetting

jira_rest_url = "http://vlm.lge.com/issue/rest/api/latest/"
issue_url = jira_rest_url + "issue/"
search_url = jira_rest_url + "search/"
tracker_url = jira_rest_url + "project/"
fieldList_url = jira_rest_url + "field/"
jsonHeaders = {'Content-Type': 'application/json'}

# - 특정 조건 : 그 사람 (최근 일주일)
#- 모든 ticket중에서 "그 사람"이 comments를 남긴 내용중에 tiger_weekly_report 이 comments의 첫줄에 적은 ticket들에 적은 comments를 출력한다.
#- status 상관없고, 
# multiprocessing with multiple arguments : https://python.omics.wiki/multiprocessing_map/multiprocessing_partial_function_multiple_arguments

dateRe = re.compile('^\s*(?P<date>(?P<year>20[0-9]+)-(?P<month>[0-9]+)-(?P<day>[0-9]+))')
deliverablesRe = re.compile('^\s*deliverables\s*:')


class CSearchVlm :
    """ 
    This Class gets issue in jira system.
    c = CSearchVlm(...)
    """
    def __init__(self
                 , auth_name = mysetting.myid
                 , auth_passwd = mysetting.mypassword
                 , alltickets = False
                 , updateduration = ''
                 , lang = 'english'
                 , debug = False
                 , dirname = 'json'
                 , fileprefix = 'jira'
                ):
        """ 
        This funciton is issue creating & initializing function.
        """
        self.auth_name = auth_name
        self.auth_passwd = auth_passwd
        self.alltickets = alltickets
        self.updateduration = updateduration
        self.lang = lang
        if mysetting.myid:
            self.dirname = mysetting.myid + '/' + dirname
        self.fileprefix = fileprefix
        self.debug = debug
        # print("isTest:",self.isTest)

        self.reporter = []
        self.comments = {} # key -> reporter    # excluding if exists RobotComment
        self.commentsTable = {}     # includes if exists RobotComment. this is all list which need updates.
        
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
        if os.path.isdir(self.dirname) == True :
            shutil.rmtree(self.dirname)
        os.makedirs(self.dirname,exist_ok=True)

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
    
    def connect(self):
        # JQL
        # https://atlassian-python-api.readthedocs.io/index.html
        #    pip3 install atlassian-python-api
        # https://atlassian-python-api.readthedocs.io/jira.html
        # https://www.programcreek.com/python/example/93020/jira.JIRA
        
        today = datetime.date.today()
        print("today:",str(today))

        #jql_request = '(assignee in ({list}) ) {issuetypeFilter}'.format(list=mysetting.myid,issuetypeFilter=mysetting.CJQLAdvancedIssuetypeFilter)
        jql_request = '(assignee in ({list}) OR reporter in ({list}) OR  watcher in ({list})) {issuetypeFilter}'.format(list=mysetting.myid,issuetypeFilter=mysetting.CJQLAdvancedIssuetypeFilter)
        if not self.alltickets:
            jql_request += ' AND status not in (Monitoring, Resolved, Closed)'
        if self.updateduration:
            jql_request += ' AND updated >= "{sd}"'.format(sd=self.updateduration)
        else:
            jql_request += ' AND updated >= "{sd}"'.format(sd=mysetting.fromDateStr)
        jql_request = '( ' + jql_request + ' ) ' + ' OR ( assignee in ({list}) AND status in ("Open","In Progress") {issuetypeFilter} )'.format(list=mysetting.myid,issuetypeFilter=mysetting.CJQLAdvancedIssuetypeFilter)
        #jql_request = '( ' + jql_request + ' ) ' + ' OR ( assignee in ({list}) AND status in ("Open","In Progress") )'.format(list=mysetting.myid,issuetypeFilter=mysetting.CJQLAdvancedIssuetypeFilter)
        print("it will take a long time (JQL) : " + jql_request)
        # 19 fields arguments are maximal number. if it is over , it will be slow and happen error (bad json).
        JIRA_JQL_Search_All(jql_request,fields = [ "*all" ],auth=self.auth_name,passwd=self.auth_passwd,group=str(0),dirname=self.dirname,fileprefix='{s}-first'.format(s=self.fileprefix)) #해당 JIRA 쿼리문에 해당하는 모든 ticket들의 정보를 가져옴. fields 미입력시 summary 정보만 가져옴
        #issuesJQL = JIRA_JQL_Search_All(jql_request,fields = None ,auth=self.auth_name,passwd=self.auth_passwd) #해당 JIRA 쿼리문에 해당하는 모든 ticket들의 정보를 가져옴. fields 미입력시 summary 정보만 가져옴

def get_parent_process(limit=10):
    '''Walk up the process tree until we find a process we like.
    Arguments:
        ok_names: Return the first one of these processes that we find
    '''

    depth = 0
    this_proc = psutil.Process(os.getpid())
    print(this_proc.name())
    argv = sys.argv
    for i,v in enumerate(argv):
        if v == '--authpasswd':
            argv.pop(i)
            argv.pop(i)
    allPath = this_proc.name() + ' ' + ' '.join(argv)
    next_proc = parent = psutil.Process(this_proc.ppid())
    print(parent.name())
    while depth < limit:
        print(next_proc.pid)
        allPath = str(next_proc.name()) + ':' + allPath
        if int(next_proc.pid) < 2:
            return allPath

        next_proc = psutil.Process(next_proc.ppid())
        depth += 1

    return allPath

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

def JIRA_JQL_Search_Recent_one(jql, start = 0, maxresults = 1, fields = ['summary'],auth='',passwd=''): #본 py내 다른 함수들이 호출하는 함수 / 사용 금지
    query = jql
    max_retry = 10
    sleep_time = 4
    retry_count = 0

    while True :

        if retry_count > 0 :
            time.sleep(sleep_time)

        retry_count += 1

        try :
            if fields == None:
                #print('1;:',query , start , maxresults,auth,passwd)
                result = requests.get(url=search_url, params={"jql" : query, "startAt" : start, "maxResults" : maxresults , "expand":'changelog'} ,auth=(auth, passwd) ,headers=jsonHeaders)
                #print('result len 1:',len(result))
                #print('result keys 1:',list(result.keys()))
            else:
                #print('2;:',query , start , maxresults,auth,passwd)
                result = requests.get(url=search_url, params={"jql" : query, "startAt" : start, "maxResults" : maxresults, "fields" : fields , "expand":'changelog'} ,auth=(auth, passwd) ,headers=jsonHeaders)
                #print('result len 2:',len(result))
                #print('result keys 2:',result)
            try :
                jsondata = result.json()
            except :
                if retry_count > max_retry :
                    print('bad json',start)
                    quit(4)
                else :
                    print('1:retry count:', retry_count,'start:',start, maxresults,auth,passwd)
                    continue

        except requests.exceptions.RequestException as e:
            print(e)

            if retry_count > max_retry :
                print('bad json',start)
                quit(4)
            else :
                print('2:retry count:2', retry_count,'start:',start, maxresults,auth,passwd)
                continue

        break

    return jsondata

def work_func(x,jql,fields,auth,passwd,gap,group,dirname,fileprefix):
    print('!work startAt',x,'gap:',gap, 'len(jql):',len(jql),'len(fields):',len(fields),'group:',group) 
    jsondata = JIRA_JQL_Search_Recent_one( jql = jql, start = x, maxresults = gap, fields = fields,auth=auth,passwd=passwd)
    with open("{dirname}/{fileprefix}-g{g}-{x}.json".format(dirname=dirname,fileprefix=fileprefix,g=group,x=x),"w") as json_file: 
        json.dump(jsondata,json_file,indent = 4)
    '''
    for k,v in jsondata.items():
        if isinstance(v,dict):
            print(x,'jsondata key dict:',k,'len:',len(v))
        elif isinstance(v,list):
            print(x,'jsondata key list:',k,'len:',len(v))
        else:
            print(x,'jsondata key:',k,v)
    '''
    return len(jsondata.get('issues',[]))

def JIRA_JQL_Search_one(jql,fields = ['summary'],auth='',passwd=''):#JIRA쿼리문에 해당하는 ticket중 제일 먼저 검색되는 항목 한개만 가져옴.
    jsondata = JIRA_JQL_Search_Recent_one( jql = jql, start = 0, maxresults = 1, fields = fields,auth=auth,passwd=passwd)['issues']
    return jsondata[0]

def JIRA_JQL_Search_All(jql,fields = ['summary'],auth='',passwd='',group='',dirname='',fileprefix=''):#해당 JIRA 쿼리문에 해당하는 모든 ticket들의 정보를 가져옴. fields 미입력시 summary 정보만 가져옴
    jqlRet = JIRA_JQL_Search_Recent_one(jql,auth=auth,passwd=passwd)
    print('keys:', list(jqlRet.keys()))
    if 'total' not in jqlRet:
        print('warning : jqlRet does not have total key : ' , jqlRet)
        return
    print("total:",jqlRet['total'])
    pageMin = 0
    pageMax = jqlRet['total']
    start = int(time.time())
    num_cores = 20
    GAP = 200 if (pageMax // num_cores) > 200 else pageMax // num_cores
    div = 1
    g = GAP
    while True:
        if g // div == 0:
            break
        div *= 10
    print('div//10:',div//10,g)
    GAP -= GAP % (div//10)
    if GAP < 200:
        GAP = 200
    pool = Pool(num_cores)
    ansCnt = 0
    partial_func = partial(work_func, jql=jql,fields=fields,auth=auth,passwd=passwd,gap=GAP,group=group,dirname=dirname,fileprefix=fileprefix) 
    rt = pool.map(partial_func, range(pageMin,pageMax,GAP))
    print('rt process count:',len(rt))
    for ri in rt:
        ansCnt += ri
    print()
    print("***run time(sec) :", int(time.time()) - start)
    print("***len ans :", ansCnt)

    return 

if (__name__ == "__main__"):

    parser = argparse.ArgumentParser(
        prog=sys.argv[0],
        description= 'gather tickets',
    )


    #parser.add_argument("-t", "--test", action="store_true",help='just test and not send e-mail for only first id')

    parser.add_argument(
        '--authname',
        metavar="<id>",
        type=str,
        help='jira id  ex) cheoljoo.lee    without @')

    parser.add_argument(
        '--authpasswd',
        metavar="<passwd>",
        type=str,
        help='jira passwd')

    parser.add_argument(
        '--idfile',
        metavar="<str>",
        type=str,
        default='LGE-list.csv',
        help='id file name    default : id.csv')

    parser.add_argument(
        '--lang',
        metavar="<str>",
        type=str,
        default='english',
        help='language    default : english   ex) english or korea')

    parser.add_argument(
        '--dirname',
        metavar="<str>",
        type=str,
        default='json',
        help='directory name for saved file    default : json')

    parser.add_argument(
        '--fileprefix',
        metavar="<str>",
        type=str,
        default='jira',
        help='prefix of filenme   default : jira')

    parser.add_argument(
        '--updateduration',
        metavar="<str>",
        type=str,
        default='',
        help='jql query use it (updated >= [--updateduration]\n\t\t\tex) --updateduration=-7d to get tickets within 1 week\n\t\t\tdeault: use mysetting.fromDateStr {d}'.format(d=mysetting.fromDateStr))

    parser.add_argument( '--alltickets', default=False , action="store_true" , help='get all type tickets. but it gets unresolved tickets without --alltickets')
    parser.add_argument( '--debug', default=False , action="store_true" , help="debug mode on")

    args = parser.parse_args()

    cs = CSearchVlm(
                 lang = args.lang
                 , debug = args.debug
                 , dirname = args.dirname
                 , fileprefix = args.fileprefix
                 , alltickets = args.alltickets
                 , updateduration = args.updateduration
                 )
    cs.connect()


    print('raw data location is' , cs.dirname)
    l = os.listdir(cs.dirname)
    for s in l:
        if s.startswith('{fileprefix}-'.format(fileprefix=args.fileprefix)):
            print(s)



