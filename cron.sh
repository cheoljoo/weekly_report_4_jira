# change your id , passwd in myidpasswd.py file
cd /home/cheoljoo.lee/code/crontab/weekly_report_4_jira; source /home/cheoljoo.lee/code/problemSolving/2022/a/bin/activate ; make > /home/cheoljoo.lee/code/crontab/weekly_report_4_jira/cron.log 2>&1
grep "Traceback (most recent call last)" /home/cheoljoo.lee/code/crontab/weekly_report_4_jira/cron.log
if [ $? -eq 0 ]
then
    python3 /home/cheoljoo.lee/code/crontab/weekly_report_4_jira/sendmail.py --sender="cheoljoo.lee@lge.com"  --logfile="/home/cheoljoo.lee/code/crontab/weekly_report_4_jira/cron.log"
else
    echo "no error : weekly_report_4_jira"
fi

