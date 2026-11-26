# Lab07 | PhraseTrip

Student ID 25125067  
26 November 2026 (UTC+7)

## Purpose

PhraseTrip helps travelers translate short messages for transport, accommodation and meals. A traveler can start with a sample phrase or enter their own, choose a target language and either select a source language or let the service detect it.

## Website features

- Translate among eight selectable languages. Auto detection also reports the source language returned by the service.
- Load travel phrases for train stations, hotel check-in and restaurants, plus a Spanish example.
- Copy a successful translation. Swap the languages to use the translation as the new input, or clear the form to start over.
- Read a status message while waiting, after success or when a request fails. The form disables duplicate submissions while a request is pending.

## API integration

The selected tutorial is “Using py-googletrans for Translation in Python: A Travel Application Tutorial.” PhraseTrip uses its travel examples, source-language detection and Translator workflow. The project pins googletrans 4.0.2 and uses its asynchronous interface.

The JavaScript form sends JSON to POST /api/translate on the local Python server. The request contains text, source and target. The server validates the phrase and language codes, then awaits Translator.translate with translate.googleapis.com as the service URL. When source is auto, the call returns the detected language along with the translation. The server returns text, source, target and provider as JSON. The browser displays text as text content.

The server accepts phrases up to 1,000 characters, uses a 12-second time limit for translation and allows two upstream calls at once. It returns HTTP 400 for invalid input, 429 when both slots are occupied, 504 on the server deadline and 502 for other upstream failures. The app sends phrases only on submission and keeps no translation history.

googletrans is a third-party wrapper for an unofficial Google Translate interface. This project uses the tutorial approach without an API key. Service behavior can change or be rate-limited, and Internet access is required. Firebase and the official Google Cloud Translation API are outside this project's scope.

## Verified examples

On 26 November 2026, the local website and its HTTP endpoint both returned these translations through googletrans.

- English to Vietnamese. “Where is the nearest train station?” returned “Ga xe lửa gần nhất ở đâu?”.
- Spanish to English. “¿Dónde puedo comprar un billete?” returned “Where can I buy a ticket?”.

The browser displayed the detected language and confirmed the copy action. Swapping after the first translation set the source to Vietnamese, the target to English and the input to the Vietnamese result. The HTTP checks returned 400 for blank text, an oversized phrase, an unsupported target and malformed JSON. The recorded responses are in 04_Testing/api_checks.json.

## Submission files

- 02_Source_Code contains the Python server, frontend and dependency list.
- 03_Demo contains Demo.mp4 and the browser screenshots used for it. The video is an annotated walkthrough assembled from those screenshots.
- 01_Documentation contains the English report and AI usage declaration in Markdown and PDF.
- gitlog.txt records the repository history after the week 7 commit. It is supplied separately from the files committed to GitHub.

See README.md for the launch commands.

## References

- Lab07 assignment and the instructor's supplied py-googletrans travel tutorial.
- [googletrans 4.0.2 documentation and examples](https://pypi.org/project/googletrans/4.0.2/)
