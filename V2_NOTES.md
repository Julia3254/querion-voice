# Voice Avatar V2 – TV + telefon

## Główne założenia

System nie wyświetla transkrypcji ani napisów odpowiedzi. Tekst odpowiedzi i transkrypcja mogą istnieć technicznie w backendzie, bo są potrzebne do STT, GPT i TTS, ale frontend ich nie pokazuje użytkownikowi.

Komunikacja użytkownika odbywa się przez:
- głos,
- przycisk push-to-talk,
- animację avatara,
- krótkie komunikaty techniczne na telefonie, np. miejsce w kolejce do TV.

## Moduły

- `/phone` – samodzielna rozmowa na telefonie z avatarem dziewczyny.
- `/tv` – ekran TV z avatarem chłopca, kodem QR do podpięcia telefonu jako mikrofonu i linkiem do samodzielnej rozmowy na telefonie.
- `/phone?tvSessionId=...` – telefon działa jako mikrofon dla konkretnej sesji TV.
- `/phone` – użytkownik rozmawia samodzielnie na telefonie bez QR.

## Stany animacji

Każdy wariant avatara ma 4 stany:

- `waiting` – czeka,
- `listening` – słucha,
- `thinking` – myśli,
- `speaking` – odpowiada.

Ścieżki plików animacji:

```text
frontend/public/avatar/phone/waiting.mp4
frontend/public/avatar/phone/listening.mp4
frontend/public/avatar/phone/thinking.mp4
frontend/public/avatar/phone/speaking.mp4

frontend/public/avatar/tv/waiting.mp4
frontend/public/avatar/tv/listening.mp4
frontend/public/avatar/tv/thinking.mp4
frontend/public/avatar/tv/speaking.mp4
```

W tej wersji skopiowano stare animacje jako placeholdery. Animacje od grafików trzeba podmienić w tych folderach.

## Backend

Dodane elementy:

- `app/api/sessions.py` – tworzenie sesji telefonu i TV, dołączanie telefonu do TV, status kolejki, WebSocket eventów.
- `app/services/session_manager.py` – in-memory sesje i kolejka TV.
- `app/services/event_manager.py` – WebSocket eventy do synchronizacji animacji TV.
- poprawiony `app/api/voice.py` – obsługa `session_id`, `target=phone/tv`, `client_id` i kolejki.
- poprawiony `app/services/chat_service.py` – GPT generuje odpowiedź na podstawie kontekstu z bazy wiedzy.
- poprawiony `app/services/rag_service.py` – proste wyszukiwanie sekcji w plikach markdown bazy wiedzy.
- poprawiony `app/services/exclusion_service.py` – obsługuje prawidłowy folder `knowledge_base/exclusions` i stary literówkowy `exclusuins`.

## Uruchamianie lokalne

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# uzupełnij OPENAI_API_KEY w backend/.env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Na telefonie w tej samej sieci otwórz adres komputera, np.:

```text
http://192.168.1.50:3000/phone
```

Dla TV:

```text
http://192.168.1.50:3000/tv
```

Jeżeli frontend i backend są na innym hoście/porcie, ustaw:

```bash
NEXT_PUBLIC_API_BASE_URL=http://192.168.1.50:8000
NEXT_PUBLIC_WS_BASE_URL=ws://192.168.1.50:8000
NEXT_PUBLIC_PUBLIC_APP_URL=http://192.168.1.50:3000
```

## UX TV

Na ekranie TV użytkownik widzi:

- animację chłopca,
- kod QR do zeskanowania telefonem,
- krótki komunikat, że telefon zostanie użyty jako mikrofon dla TV,
- na samym dole link do samodzielnej rozmowy na telefonie.

QR prowadzi do adresu w formacie:

```text
/phone?tvSessionId=<id_sesji_tv>
```

Dolny link prowadzi do:

```text
/phone
```

Dzięki temu QR służy tylko do połączenia telefonu z konkretnym telewizorem, a zwykła rozmowa na telefonie działa bez QR.

## Ważne ograniczenia MVP

- Sesje i kolejka są trzymane w pamięci procesu. Do produkcji trzeba przenieść to do Redis.
- Ekran TV pokazuje kod QR do użycia telefonu jako mikrofonu TV oraz link `/phone` na dole ekranu dla osób, które chcą rozmawiać bezpośrednio na telefonie.
- Brak napisów dotyczy transkrypcji i treści odpowiedzi. Telefon pokazuje tylko techniczne statusy, np. miejsce w kolejce.
- W WebSocketach jest podstawowa synchronizacja stanów. Do produkcji warto dodać reconnect i wygaszanie starych sesji.
