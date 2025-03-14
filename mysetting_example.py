myid = "login id without @"
mypassword = "login password"
myhttp =        'http://your_site/path'  # you can see html results files.
myIsTestToSendMail = False       # if you want to send mail , change it.  False (send) , True (no send)
CJQLAdvancedIssuetypeFilter = '''AND issuetype in ("Bug","Issue","Change Request","OEM Bug","Request","Requirement","Task","Story","Sub-task")'''
# get information from this date
fromDate = datetime.date(2024,10,15)
fromDateStr = fromDate.strftime("%Y-%m-%d")

weeklyreportLabel = 'wr'
