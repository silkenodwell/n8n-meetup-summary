#Create the virtual environment On macOS/Linux if it doesn't exist:
if [ ! -d "myenv" ]; then
    python3.12 -m venv myenv
fi

#Activate the virtual environment:
source myenv/bin/activate

# Install packages
pip install -r requirements.txt

python3.12 download_meetup_ics.py

python3.12 meetup_import.py