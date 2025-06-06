

# change user and passwd if you use it

all: 
	if [ ! -e mysetting.py ]; then cp mysetting_example.py mysetting.py; echo "edit mysetting.py"; exit 4;  fi
	echo "!! you should change your id passwd in mysetting.py."
	python3 CJQLAdvancedPersonal.py --dirname=wrjson/data --fileprefix="wr-vlm.lge.com" --alltickets
	python3 CJQLAdvancedPersonal.jira.lge.com.py --dirname=wrjson/data --fileprefix="wr-jira.lge.com" --alltickets
	make t
	make h
t:
	python3 CAnalysisVlm.py --inputdir=wrjson/data --inputfileprefix="wr" --outputfileprefix=updated --finaldir=wrjson

h:
	python3 CWeeklyReport.py --inputdir=wrjson/data --inputfileprefix=updated --outputfileprefix=html
