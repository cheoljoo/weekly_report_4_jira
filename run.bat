@echo off
python -m venv venv
call venv\Scripts\activate

echo Installing dependencies...
# pip install --upgrade pip
pip install -r requirements.txt

echo Running Python scripts...
python CJQLAdvancedPersonal.py --dirname=wrjson/data --fileprefix="wr" --alltickets
python CAnalysisVlm.py --inputdir=wrjson/data --inputfileprefix="wr" --outputfileprefix=updated --finaldir=wrjson
python CWeeklyReport.py --inputdir=wrjson/data --inputfileprefix=updated --outputfileprefix=html

echo Done!