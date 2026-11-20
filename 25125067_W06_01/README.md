# 25125067 - Lab06: StudySpot

StudySpot finds cafes and libraries using the **OpenStreetMap API**, without an API key.

## Run the website

Python 3.10 or later and an Internet connection are required. Open a terminal in this directory:

```powershell
cd 02_Source_Code
python server.py
```

Open **http://127.0.0.1:8086** and keep the terminal running. If the port is busy, use `python server.py --port 8087`. Press Ctrl+C to stop.

## Submission contents

- [Report (Markdown)](01_Documentation/Report.md) and [report (PDF)](01_Documentation/Report.pdf): features, API integration, validation, limitations and AI use.
- [AI usage declaration](01_Documentation/AI_Usage_Declaration.md), also provided as PDF.
- `02_Source_Code/`: complete application source, Leaflet with its license, and tests.
- `03_Demo/Demo.mp4`: an annotated Vietnamese-language video assembled from screenshots of real interactions, not a continuous screen recording. The original screenshots, subtitles and a sample GeoJSON are included.
- `04_Testing/`: recorded test results and the saved live API response.
- `00_Assignment/Lab06.pdf`: original assignment.
- Git history is exported separately as a text file after the homework commit.

## Tests and limitations

```powershell
cd 02_Source_Code
python -m unittest discover -s tests -v
node --test tests/geojson.test.cjs
```

Node.js 18+ is needed only for the JavaScript tests. The default mode queries the OSM map API in a 200-500 m radius with a 10-minute cache, for small local use. An optional Overpass mode is available with `python server.py --provider overpass`; it was not successfully verified live in this environment. Do not open `index.html` via file://, as the website needs `/api/places` from the local server.

Codex assisted with the implementation, testing, documentation, English translation and demo. See the AI usage declaration for details.
