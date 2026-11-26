# PhraseTrip | Lab07

PhraseTrip translates travel phrases through googletrans, the unofficial Google Translate wrapper described in the supplied tutorial.

## Run on Windows

Open PowerShell in the submission folder. Use Python 3.10 or later with pip and an Internet connection.

```powershell
cd 02_Source_Code
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Open http://127.0.0.1:8077 in your browser. Keep the server running while using the website and press Ctrl+C to stop it. If necessary, append --port 8078 and open that port instead.

Select Train station and Translate phrase for the first demo. The default target is Vietnamese. After a result, try Copy or Swap languages. Then select Spanish example and choose English as the target to check auto detection again.

## Submission contents

- 00_Assignment/Lab07.pdf is the original assignment.
- 01_Documentation includes the English report and AI declaration, each in Markdown and PDF.
- 02_Source_Code includes the website and Python server.
- 03_Demo/Demo.mp4 walks through actual translations using annotated browser screenshots.
- 04_Testing/api_checks.json lists the recorded HTTP responses.

Submit gitlog.txt alongside this folder. The log is exported after the week 7 commit.
